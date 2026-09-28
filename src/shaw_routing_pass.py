"""
shaw_routing_pass.py

Core SHAW (SWAP-based BidiREctional heuristic search) routing loop,
implemented as a BQSKit compiler pass for a Trapped-Ion QCCD target.

This file is intentionally thin: the DAG bookkeeping lives in
circuit_dag.py, the physical hardware model lives in position_graph.py
(real module), and congestion resolution lives in
congestion_handler.py (currently a stub). This file just
wires them together into the actual routing loop.

High-level algorithm:
  1. Build a PositionGraph + Placement (or accept ones already built
     from a real machine model) and seed each logical qudit into a
     home trap.
  2. Build the circuit DAG and seed the Front Layer with gates that
     have no unresolved dependencies. Keep a shallow Lookahead Window
     of not-yet-ready gates to bias trap-selection scoring.
  3. For each two-qudit gate in the Front Layer:
       - If both ions already share a trap -> execute directly.
       - Otherwise, find a free slot in the other ion's trap for one
         of the two ions to move into, score the candidates using
         path length + a lookahead-based parallelism bonus, and pick
         the best one.
       - Send the chosen path through the (mock) Congestion Handler.
       - Walk the path hop by hop, updating Placement. A hop that
         lands on a slot already occupied by a *different* logical
         qudit is a genuine ion swap (emit a SwapGate on those two
         logical qudits); a hop onto a free slot or transport segment
         is pure shuttling (state update only, no circuit gate).
  4. Retire executed gates from the DAG, pulling any newly-ready
     successors into the Front Layer, and repeat until done.

Glossary (so this reads cleanly for anyone new to the vocabulary):
  - "trap"     : a physical location that can hold one or more ions.
  - "slot"     : one specific spot inside a trap (a trap with
                 capacity=2 has 2 slots, e.g. "t0:0" and "t0:1").
  - "segment"  : a transport/junction position an ion passes through
                 *between* traps -- it can't sit there long-term, it's
                 just a hop on the way somewhere else.
  - "position" : the umbrella term for "a slot OR a segment" -- i.e.
                 any node in PositionGraph.
  - "Placement": the live answer to "which logical qudit is at which
                 position right now". This is the only thing that
                 changes as routing proceeds; the PositionGraph
                 (the traps/segments/edges themselves) is fixed.
  - "logical qudit": a qubit as your original circuit refers to it
                 (an integer index like 0, 1, 2...), independent of
                 whatever physical position it's currently sitting at.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from bqskit.compiler.basepass import BasePass
from bqskit.compiler.passdata import PassData
from bqskit.ir.circuit import Circuit
from bqskit.ir.gates import IdentityGate, SwapGate

from circuit_dag import CircuitDAG
from congestion_handler import CongestionHandler
from position_graph import Placement, PositionGraph, build_linear_qccd

logger = logging.getLogger("shaw_router")
logging.basicConfig(level=logging.INFO)


class ShawRoutingPass(BasePass):
    """The core SHAW routing loop. See module docstring for the algorithm."""

    LOOKAHEAD_SIZE = 5  # how many upcoming gates to consider for scoring
    DEFAULT_TRAP_CAPACITY = 2  # room for a home ion + one visiting ion

    def __init__(
        self,
        position_graph: Optional[PositionGraph] = None,
        placement: Optional[Placement] = None,
        congestion_handler: Optional[CongestionHandler] = None,
    ) -> None:
        """
        position_graph / placement: pass in a real machine model +
        initial layout if you have one (e.g. from an earlier pass).
        If omitted, `run()` builds a default linear QCCD chain sized
        to the circuit and places logical qudit i at trap i, slot 0.

        congestion_handler: defaults to stub.
        """
        super().__init__()
        self._position_graph = position_graph
        self._placement = placement
        # TODO: Replace with module
        self.congestion_handler = congestion_handler or CongestionHandler()

    async def run(self, circuit: Circuit, data: PassData) -> None:
        """BQSKit entry point. Mutates `circuit` in place."""

        # --------------------------------------------------------
        # 1. STATE INITIALIZATION
        # --------------------------------------------------------
        pg, placement = self._get_or_build_machine_model(circuit)

        # --------------------------------------------------------
        # 2. CIRCUIT DAG PARSING
        # --------------------------------------------------------
        dag = CircuitDAG(circuit)
        program_order = dag.program_order()
        order_index = {op_id: i for i, op_id in enumerate(program_order)}
        front_layer: Deque[int] = deque(dag.initial_front_layer())

        routed_circuit = Circuit(circuit.num_qudits, circuit.radixes)
        remaining = set(dag.nodes.keys())

        # Safety valve for a genuine deadlock: if a gate keeps getting
        # deferred (no free slot to co-locate its qudits) with zero
        # other progress happening in between, the front layer will
        # otherwise spin on it forever -- there's no congestion
        # resolver yet to break the tie, so nothing will ever change.
        # Track how many loop iterations have passed since `remaining`
        # last shrank; if that exceeds the total gate count, nothing
        # left in the front layer can possibly make progress either,
        # so stop and say so clearly instead of hanging silently.
        iterations_since_progress = 0
        stall_limit = len(dag.nodes) + 1

        # --------------------------------------------------------
        # 3 & 4. FRONT-LAYER EVALUATION LOOP + EXECUTION/STATE UPDATE
        # --------------------------------------------------------
        # "front_layer" holds op_ids that are ready to run right now
        # (every gate before them, on every qudit they touch, has
        # already been placed into `routed_circuit`). We pop one,
        # try to execute it, and if it unlocks any successor gates
        # (via dag.mark_executed), those get pushed back in.
        while front_layer:
            op_id = front_layer.popleft()
            node = dag.nodes[op_id]
            op = node.operation

            if len(node.qudits) < 2:
                # Single-qudit gate: no routing needed.
                routed_circuit.append(op)
                remaining.discard(op_id)
                front_layer.extend(dag.mark_executed(op_id))
                iterations_since_progress = 0
                continue

            # This loop handles 2-qudit gates directly. (An N-qudit
            # gate would decompose into repeated pairwise routing
            # steps using the same scoring logic.)
            logical_a, logical_b = node.qudits[0], node.qudits[1]
            pos_a = placement.position_of(logical_a)
            pos_b = placement.position_of(logical_b)
            trap_a = self._trap_of(pg, pos_a)
            trap_b = self._trap_of(pg, pos_b)

            if trap_a == trap_b:
                # Ions already share a trap -> execute directly.
                routed_circuit.append(op)
                remaining.discard(op_id)
                front_layer.extend(dag.mark_executed(op_id))
                iterations_since_progress = 0
                continue

            # --- Ions are NOT co-located: need to route one to the other ---
            lookahead_ops = self._get_lookahead_window(
                remaining, order_index, program_order, exclude=op_id
            )

            mover_logical, target_slot, _score = self._choose_move(
                pg=pg,
                placement=placement,
                logical_a=logical_a,
                logical_b=logical_b,
                trap_a=trap_a,
                trap_b=trap_b,
                lookahead_ops=lookahead_ops,
                dag=dag,
            )

            if mover_logical is None:
                # Both candidate traps are full (no free slot for a
                # visiting ion). A real implementation would hand
                # this to congestion resolver to evict/
                # reroute; for now, log and defer this gate for later
                # retry once other traffic clears -- UNLESS nothing
                # else in the whole circuit has made progress in a
                # while either, in which case "later" will never come
                # (e.g. two OTHER qudits are permanently parked in
                # both candidate traps and never leave): that's a
                # genuine deadlock, not a temporary traffic jam, so we
                # stop and say so instead of retrying forever.
                iterations_since_progress += 1
                if iterations_since_progress > stall_limit:
                    raise RuntimeError(
                        f"Routing deadlock: qudits {logical_a}/{logical_b} "
                        f"cannot be co-located (traps {trap_a!r}/{trap_b!r} "
                        f"both stayed full) after {iterations_since_progress} "
                        "attempts with no other progress. This needs real "
                        "congestion resolution (eviction/rerouting), which "
                        "doesn't exist yet -- see CongestionHandler."
                    )
                logger.warning(
                    "No free slot to co-locate qudits %s/%s right now; "
                    "deferring gate %s", logical_a, logical_b, op_id,
                )
                front_layer.append(op_id)  # retry later
                continue

            mover_start_pos = placement.position_of(mover_logical)
            raw_path = pg.shortest_path(mover_start_pos, target_slot)

            clear_path = self.congestion_handler.resolve_path_congestion(
                raw_path, placement, pg
            )

            # --- EXECUTION & STATE UPDATE ---
            self._walk_path(routed_circuit, pg, placement, clear_path, mover_logical)

            # The walk can leave a *gate* qudit parked on transport:
            # a swap-through inside a full trap parks whoever was
            # already there wherever the mover came from, which may
            # be a segment. Appending the gate on top of that layout
            # would bake in a broken circuit, so retry the gate later
            # from the (still fully consistent) new positions instead
            # -- persistent failure becomes the deadlock RuntimeError
            # via the same counter/guard, never a silent wrong answer.
            # (Non-gate ions stranded mid-walk are tolerated: later
            # steps route them back when needed. Real eviction that
            # avoids stranding anyone is congestion resolution's job.)
            final_trap_a = self._trap_of(pg, placement.position_of(logical_a))
            final_trap_b = self._trap_of(pg, placement.position_of(logical_b))
            if (
                final_trap_a is None
                or final_trap_b is None
                or final_trap_a != final_trap_b
            ):
                iterations_since_progress += 1
                if iterations_since_progress > stall_limit:
                    raise RuntimeError(
                        f"Routing deadlock: qudits {logical_a}/{logical_b} "
                        f"ended in different traps ({final_trap_a!r} vs "
                        f"{final_trap_b!r}) after routing for gate {op_id} "
                        f"{iterations_since_progress} times with no other "
                        "progress. This needs real congestion resolution "
                        "(eviction/rerouting), which doesn't exist yet -- "
                        "see CongestionHandler."
                    )
                logger.warning(
                    "Gate %s left qudits %s/%s in different traps (%r vs %r); "
                    "deferring for retry", op_id, logical_a, logical_b,
                    final_trap_a, final_trap_b,
                )
                front_layer.append(op_id)  # retry later
                continue

            assert final_trap_a == final_trap_b, (
                f"Routing invariant violated: qudits {logical_a}/{logical_b} "
                f"still in different traps ({final_trap_a} vs {final_trap_b}) "
                f"after routing for gate {op_id}."
            )

            # Now both ions share a trap -> append the actual gate.
            routed_circuit.append(op)

            remaining.discard(op_id)
            front_layer.extend(dag.mark_executed(op_id))
            iterations_since_progress = 0

        circuit.become(routed_circuit)

    # ------------------------------------------------------------
    # Machine model setup
    # ------------------------------------------------------------
    def _get_or_build_machine_model(
        self, circuit: Circuit
    ) -> Tuple[PositionGraph, Placement]:
        if self._position_graph is not None and self._placement is not None:
            return self._position_graph, self._placement

        # Default: one home trap per logical qudit, in a line, each
        # with room for a home ion plus one visiting ion.
        pg = build_linear_qccd(
            num_traps=circuit.num_qudits,
            trap_capacity=self.DEFAULT_TRAP_CAPACITY,
        )
        placement = Placement(pg)
        for q in range(circuit.num_qudits):
            home_slot = pg.slots_of(f"t{q}")[0]
            placement.place(q, home_slot)
        return pg, placement

    @staticmethod
    def _trap_of(pg: PositionGraph, position: str) -> Optional[str]:
        """trap_id of a trap-slot position, or None for a segment."""
        return pg.graph.nodes[position].get("trap_id")

    # ------------------------------------------------------------
    # Lookahead window
    # ------------------------------------------------------------
    def _get_lookahead_window(
        self,
        remaining: set,
        order_index: Dict[int, int],
        program_order: List[int],
        exclude: int,
    ) -> List[int]:
        start = order_index[exclude] + 1
        window = []
        for op_id in program_order[start:]:
            if op_id in remaining:
                window.append(op_id)
            if len(window) >= self.LOOKAHEAD_SIZE:
                break
        return window

    # ------------------------------------------------------------
    # Candidate scoring
    # ------------------------------------------------------------
    def _choose_move(
        self,
        pg: PositionGraph,
        placement: Placement,
        logical_a: int,
        logical_b: int,
        trap_a: str,
        trap_b: str,
        lookahead_ops: List[int],
        dag: CircuitDAG,
    ) -> Tuple[Optional[int], Optional[str], float]:
        """
        Basic scoring function: lower score is better.
            score = path_length - parallelism_bonus
        Candidates are "move A into trap_b" and "move B into trap_a".
        Returns (mover_logical, target_slot, score), or
        (None, None, inf) if neither candidate trap has a free slot.
        """
        candidates: Sequence[Tuple[int, str, str]] = (
            (logical_a, placement.position_of(logical_a), trap_b),
            (logical_b, placement.position_of(logical_b), trap_a),
        )

        best_score = float("inf")
        best_mover: Optional[int] = None
        best_slot: Optional[str] = None

        for mover_logical, mover_pos, target_trap in candidates:
            if target_trap is None:
                continue  # qudit parked on transport has no trap to target
            target_slot = self._free_slot_in_trap(pg, placement, target_trap)
            if target_slot is None:
                continue  # trap is full; not a usable candidate right now

            path_len = len(pg.shortest_path(mover_pos, target_slot)) - 1

            bonus = self._parallelism_bonus(
                pg=pg,
                placement=placement,
                moved_logical=mover_logical,
                candidate_slot=target_slot,
                lookahead_ops=lookahead_ops,
                dag=dag,
            )

            score = path_len - bonus
            if score < best_score:
                best_score = score
                best_mover = mover_logical
                best_slot = target_slot

        return best_mover, best_slot, best_score

    @staticmethod
    def _free_slot_in_trap(
        pg: PositionGraph, placement: Placement, trap_id: str
    ) -> Optional[str]:
        for slot in pg.slots_of(trap_id):
            if not placement.is_occupied(slot):
                return slot
        return None

    def _parallelism_bonus(
        self,
        pg: PositionGraph,
        placement: Placement,
        moved_logical: int,
        candidate_slot: str,
        lookahead_ops: List[int],
        dag: CircuitDAG,
    ) -> float:
        """
        Small heuristic bonus: if moving `moved_logical` to
        `candidate_slot` would also shorten the distance for a gate
        sitting in the lookahead window, nudge the score in favor of
        this move. Simplified stand-in for SHAW's bidirectional
        search heuristic.
        """
        bonus = 0.0
        for op_id in lookahead_ops:
            node = dag.nodes[op_id]
            if len(node.qudits) < 2 or moved_logical not in node.qudits:
                continue

            other_logical = [q for q in node.qudits if q != moved_logical][0]
            try:
                other_pos = placement.position_of(other_logical)
            except KeyError:
                continue

            current_pos = placement.position_of(moved_logical)
            current_dist = len(pg.shortest_path(current_pos, other_pos)) - 1
            new_dist = len(pg.shortest_path(candidate_slot, other_pos)) - 1

            if new_dist < current_dist:
                bonus += (current_dist - new_dist) * 0.1  # small weight

        return bonus

    # ------------------------------------------------------------
    # Path execution
    # ------------------------------------------------------------
    def _walk_path(
        self,
        routed_circuit: Circuit,
        pg: PositionGraph,
        placement: Placement,
        path: List[str],
        mover_logical: int,
    ) -> None:
        """
        Walk `mover_logical` hop by hop along `path`, updating
        Placement as we go.

        Per hop, with occupant O on the next position (if any):
          - free -> pure shuttling: move, mark with a 1-qudit
            IdentityGate placeholder (no logical effect, but the
            physical move really happened -- see note below).
          - occupied and O's trap has a free slot -> shuffle O aside
            into it first (also just an IdentityGate marker: a
            physical move with no logical effect), then move in.
            Preferring the shuffle over a swap keeps O inside its
            trap instead of stranding it wherever the mover came
            from (which may be a transport segment).
          - occupied with nowhere to shuffle O into -> fall back to
            a direct exchange, emitting a SwapGate on the two
            logical qudits (the historical behavior). NOTE: if the
            mover came from a different trap/segment, this parks O
            there -- possibly on transport. run()'s post-walk check
            retries the gate later when that leaves a *gate* qudit
            stranded; parking only non-gate ions is tolerated (later
            steps route them back when needed). Teaching the walk to
            never strand anyone is real eviction planning and belongs
            to congestion resolution, not this loop.

        Why bother marking pure shuttles at all: a SwapGate changing
        the circuit's *logical* meaning is one thing, but real
        hardware still has to physically move the ion through every
        segment/slot on `path`, and that has a real time/error cost.
        If we emit nothing for those hops, anyone reading the routed
        circuit (a test, a scheduler, a cost estimator,
        eventual congestion resolver) has no way to see that movement
        happened at all. The IdentityGate marker is itself still a
        placeholder -- real hardware-control layer
        will translate each one into an actual shuttle/junction-
        crossing instruction -- but at least the *event* is now
        visible in the circuit instead of silently vanishing.
        """
        for next_pos in path[1:]:
            occupant = placement.occupant_of(next_pos)

            if occupant is None or occupant == mover_logical:
                placement.move(mover_logical, next_pos)
                # TODO: Replace with module
                # Real version: emit the actual shuttle/junction-
                # crossing hardware instruction here instead of a
                # placeholder IdentityGate.
                routed_circuit.append_gate(IdentityGate(1), (mover_logical,))
                logger.debug(
                    "Shuttled logical qudit %s -> %s", mover_logical, next_pos
                )
                continue

            next_trap = self._trap_of(pg, next_pos)
            if next_trap is not None:
                free_slot = self._free_slot_in_trap(pg, placement, next_trap)
                if free_slot is not None:
                    placement.move(occupant, free_slot)
                    routed_circuit.append_gate(IdentityGate(1), (occupant,))
                    logger.debug(
                        "Shuffled logical qudit %s aside -> %s",
                        occupant, free_slot,
                    )
                    placement.move(mover_logical, next_pos)
                    routed_circuit.append_gate(IdentityGate(1), (mover_logical,))
                    logger.debug(
                        "Shuttled logical qudit %s -> %s", mover_logical, next_pos
                    )
                    continue

            self._swap_ions(placement, mover_logical, occupant)
            routed_circuit.append_gate(SwapGate(), (mover_logical, occupant))
            logger.debug(
                "Swapped logical qudits %s <-> %s at %s",
                mover_logical, occupant, next_pos,
            )

    @staticmethod
    def _swap_ions(placement: Placement, qudit_a: int, qudit_b: int) -> None:
        """
        Exchange the positions of two already-placed logical qudits.

        NOTE: Placement (position_graph.py) currently only exposes
        `place` (target must be free) and `move` (also requires the
        target to be free), so there's no public API for "these two
        occupied slots trade occupants". This is a real gap worth
        raising with -- e.g. a `Placement.swap(qudit_a, qudit_b)`
        method. Until then, this reaches into Placement's private
        `_occupant` dict to clear both slots before re-placing each
        qudit into the other's old spot. That private-attribute
        access is a deliberate, flagged workaround -- not something
        to build further logic on top of.
        """
        pos_a = placement.position_of(qudit_a)
        pos_b = placement.position_of(qudit_b)

        # TODO: Replace with Placement.swap(qudit_a, qudit_b) once
        # module exposes one -- this manual two-step dance
        # reaching into private state is a workaround, not the
        # intended long-term API.
        placement._occupant.pop(pos_a, None)  # type: ignore[attr-defined]
        placement._occupant.pop(pos_b, None)  # type: ignore[attr-defined]
        placement.place(qudit_a, pos_b)
        placement.place(qudit_b, pos_a)


# ======================================================================
# Quick smoke test / usage example
# ======================================================================
if __name__ == "__main__":
    import asyncio
    from bqskit.ir.gates import CNOTGate, HGate

    test_circuit = Circuit(4)
    test_circuit.append_gate(HGate(), (0,))
    test_circuit.append_gate(CNOTGate(), (0, 3))
    test_circuit.append_gate(CNOTGate(), (1, 2))
    test_circuit.append_gate(CNOTGate(), (0, 1))

    # Explicit machine model, built the same way run() would default to.
    pg = build_linear_qccd(num_traps=test_circuit.num_qudits, trap_capacity=2)
    placement = Placement(pg)
    for q in range(test_circuit.num_qudits):
        placement.place(q, pg.slots_of(f"t{q}")[0])

    shaw_pass = ShawRoutingPass(position_graph=pg, placement=placement)

    async def _main() -> None:
        data = PassData(test_circuit)
        print("Before routing, each logical qudit's home trap:")
        for q in range(test_circuit.num_qudits):
            print(f"  qudit {q} -> {placement.position_of(q)}")

        await shaw_pass.run(test_circuit, data)

        print(f"\nRouted circuit has {test_circuit.num_operations} operations:")
        for op in test_circuit.operations():
            print(f"  {op.gate.name} on {tuple(op.location)}")

        print("\nAfter routing, each logical qudit's final trap:")
        for q in range(test_circuit.num_qudits):
            print(f"  qudit {q} -> {placement.position_of(q)}")

    asyncio.run(_main())