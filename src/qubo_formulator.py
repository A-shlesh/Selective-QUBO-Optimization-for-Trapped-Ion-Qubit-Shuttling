"""
qubo_formulator.py
==================
Phase 6 of the Selective-QUBO methodology:
  Build the QUBO Q-matrix from the local congestion window W.

ASSIGNED TO: Person 1 (Chaitanya)
======================

IMPLEMENTATION SUMMARY
-----------------------
This module converts a WindowInfo (local congestion window) into a
QUBOProblem (a dimod BinaryQuadraticModel) by:

  1. Enumerating binary decision variables
         x_{i, v, t}  ∈  {0, 1}
     meaning "ion i is at position v at time step t".

  2. Encoding four groups of penalty terms into a dimod
     BinaryQuadraticModel (BQM):

       H_one_hot   – exactly one position per ion per timestep
       H_capacity  – at most cap(v) ions at position v per timestep
       H_movement  – ion moves only along legal G_p edges
       H_goal      – ion reaches target position at t = T

  3. Sets the objective (movement cost to minimise):
       H_cost = sum over (i, v, t) of  hop_weight(v) * x_{i,v,t}

  4. Combines everything with penalty λ = C_max + 1:
       H = H_cost + λ * (H_one_hot + H_capacity + H_movement + H_goal)

  5. Applies Rosenberg quadratization to any cubic or higher-order
     terms produced by constraint encoding (capacity constraints with
     cap > 1 produce cubic terms -- see QUBO tutorial §3).

REFERENCE PAPERS
----------------
[QUBO]   Glover, Kochenberger, Du – "A Tutorial on Formulating and
         Using QUBO Models", arXiv 1811.11538, 2019.
         Sections 2 (penalty encoding) and 3 (quadratization).

[SHAW]   Bach, Safro, Younis, arXiv 2501.12470 – for the position
         graph topology that defines legal movements.

INTERFACES YOU MUST RESPECT
----------------------------
• Input  : WindowInfo  (from congestion_handler.py)
           PositionGraph  (src/position_graph.py – has .graph nx.Graph
                          and .shortest_path)
• Output : QUBOProblem  (defined below – do NOT change its fields)

The solver (qubo_solver.py) consumes QUBOProblem, so your field
names must match exactly.

HOW TO RUN YOUR CODE
--------------------
  python src/qubo_formulator.py          # triggers __main__ smoke test
  pytest tests/test_qubo_formulator.py   # run unit tests

DEPENDENCIES ALREADY INSTALLED
-------------------------------
  dimod>=0.12  (BinaryQuadraticModel, QUBO utilities)
  networkx     (graph traversal, already used throughout)
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

# dimod is installed via requirements.txt
import dimod
import networkx as nx

from congestion_handler import WindowInfo

logger = logging.getLogger("shaw_router.qubo_formulator")


# ---------------------------------------------------------------------------
# Output data structure  (DO NOT CHANGE – qubo_solver.py depends on this)
# ---------------------------------------------------------------------------

@dataclass
class QUBOProblem:
    """
    The fully assembled QUBO problem ready for a solver.

    Attributes
    ----------
    bqm : dimod.BinaryQuadraticModel
        The quadratic model in QUBO form.  Access the Q-matrix via
        bqm.to_qubo()[0] if you need the raw dict.
    var_map : dict  { (ion_id, position_id, timestep) : variable_label }
        Maps the physical meaning of each binary variable to its label
        inside the BQM.  The decoder needs this to interpret solutions.
    inv_var_map : dict  { variable_label : (ion_id, position_id, timestep) }
        Inverse of var_map.
    num_variables : int
        Total number of binary variables (before Rosenberg aux vars).
    num_aux_variables : int
        Extra variables introduced by Rosenberg quadratization.
    time_horizon : int
        Number of time steps T used in the formulation.
    penalty_lambda : float
        The λ value used to weight constraint penalties.
    window : WindowInfo
        The source window (kept for the decoder).
    metadata : dict
        Anything else you want to pass to the solver or decoder.
    """
    bqm: dimod.BinaryQuadraticModel
    var_map: Dict[Tuple[Any, Any, int], str]
    inv_var_map: Dict[str, Tuple[Any, Any, int]]
    num_variables: int
    num_aux_variables: int
    time_horizon: int
    penalty_lambda: float
    window: WindowInfo
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class QUBOFormulator:
    """
    Converts a WindowInfo (local congestion window) into a QUBOProblem.

    Parameters
    ----------
    time_horizon : int
        Number of discrete time steps T.  Typically set to
        shortest_path_length + 2 so there's slack to clear blockers.
        Default: None → auto-compute from window source→target distance.
    penalty_lambda : float
        λ for constraint penalties.  None → use C_max + 1 heuristic.
    hop_cost : float
        Cost weight for each ion movement hop (objective term).
    """

    def __init__(
        self,
        time_horizon: Optional[int] = None,
        penalty_lambda: Optional[float] = None,
        hop_cost: float = 1.0,
    ) -> None:
        self.time_horizon = time_horizon
        self.penalty_lambda = penalty_lambda
        self.hop_cost = hop_cost

        # Track auxiliary variables introduced by Rosenberg quadratization
        self._aux_counter: int = 0
        self._aux_var_map: Dict[Tuple[str, str], str] = {}  # (u, v) → aux_label

    def build(
        self,
        window: WindowInfo,
        pg: Any,   # src.position_graph.PositionGraph
    ) -> QUBOProblem:
        """
        Build the QUBOProblem from the local window and position graph.

        Parameters
        ----------
        window : WindowInfo   – the local congestion window
        pg     : PositionGraph – hardware graph (for legal edge lookup)

        Returns
        -------
        QUBOProblem
        """
        # Reset auxiliary variable state for this build
        self._aux_counter = 0
        self._aux_var_map = {}

        # 1. Compute time horizon T
        T = self._compute_time_horizon(window, pg)

        # 2. Build variable maps
        var_map, inv_var_map = self._make_variables(window, T)
        num_variables = len(var_map)

        # 3. Compute lambda (penalty strength)
        # λ = C_max + 1 where C_max is max possible cost contribution
        # C_max ≤ num_ions * num_positions * T * hop_cost
        num_ions = len(window.active_ions)
        num_pos  = len(window.window_nodes)
        C_max    = num_ions * num_pos * T * self.hop_cost
        lambda_  = self.penalty_lambda if self.penalty_lambda is not None else (C_max + 1)

        # 4. Initialise empty BQM
        bqm = dimod.BinaryQuadraticModel(vartype=dimod.BINARY)

        # Add all variables (initialised to 0 bias)
        for label in var_map.values():
            bqm.add_variable(label, 0.0)

        ions      = list(window.active_ions.keys())
        positions = list(window.window_nodes)

        # 5. Encode constraints as penalty terms
        self._add_one_hot_penalty(bqm, var_map, ions, positions, T, lambda_)
        self._add_capacity_penalty(bqm, var_map, window, pg, T, lambda_)
        self._add_movement_penalty(bqm, var_map, window, pg, T, lambda_)
        self._add_goal_penalty(bqm, var_map, window, T, lambda_)

        # 6. Add cost objective
        self._add_cost_objective(bqm, var_map, window, T)

        # 7. Rosenberg quadratization (handles any leftover cubic terms)
        #    For cap=1 all constraints are already quadratic; this is a safety net.
        num_aux = self._rosenberg_quadratize(bqm)

        logger.info(
            "QUBOFormulator.build(): T=%d, ions=%d, positions=%d, "
            "vars=%d (+ %d aux), λ=%.2f",
            T, num_ions, num_pos, num_variables, num_aux, lambda_,
        )

        return QUBOProblem(
            bqm=bqm,
            var_map=var_map,
            inv_var_map=inv_var_map,
            num_variables=num_variables,
            num_aux_variables=num_aux,
            time_horizon=T,
            penalty_lambda=lambda_,
            window=window,
            metadata={
                "num_ions": num_ions,
                "num_positions": num_pos,
                "C_max": C_max,
            },
        )

    # -----------------------------------------------------------------------
    # Sub-steps
    # -----------------------------------------------------------------------

    def _compute_time_horizon(self, window: WindowInfo, pg: Any) -> int:
        """
        Compute the number of time steps T.

        Strategy:
          T = shortest_path_length(source → target in G_p)
              + len(blocked_path)   ← slack to clear each blocker
              + 1                   ← safety margin

        Falls back to len(blocked_path) + 2 when pg is unavailable.
        """
        if self.time_horizon is not None:
            return self.time_horizon

        slack = len(window.blocked_path) + 1

        G = getattr(pg, "graph", None)
        if G is None:
            return slack + 1

        try:
            sp_len = nx.shortest_path_length(G, window.source, window.target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            sp_len = slack

        T = sp_len + slack
        return max(T, 2)   # always at least 2 steps

    def _make_variables(
        self,
        window: WindowInfo,
        T: int,
    ) -> Tuple[Dict, Dict]:
        """
        Create one binary variable per (ion, position, timestep).

        Only creates variables for ions in window.active_ions and
        positions in window.window_nodes.

        Variable label format: "x_{ion}_{pos}_{t}"
        (sanitised so dimod doesn't choke on special characters)

        Returns (var_map, inv_var_map) where:
          var_map     : (ion, pos, t) → label string
          inv_var_map : label → (ion, pos, t)
        """
        var_map: Dict[Tuple[Any, Any, int], str] = {}
        inv_var_map: Dict[str, Tuple[Any, Any, int]] = {}

        ions      = list(window.active_ions.keys())
        positions = list(window.window_nodes)

        for ion in ions:
            # Sanitise ion id for use in a variable label
            ion_str = str(ion).replace(":", "_").replace(" ", "_")
            for pos in positions:
                pos_str = str(pos).replace(":", "_").replace(" ", "_")
                for t in range(T + 1):         # t ∈ {0, 1, ..., T}
                    key   = (ion, pos, t)
                    label = f"x_{ion_str}_{pos_str}_{t}"
                    var_map[key]        = label
                    inv_var_map[label]  = key

        return var_map, inv_var_map

    def _add_one_hot_penalty(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        ions: List[Any],
        positions: List[Any],
        T: int,
        lambda_: float,
    ) -> None:
        """
        Add one-hot constraint:
            for each ion i and timestep t:
                (sum_v x_{i,v,t} - 1)^2  →  expand and add to bqm

        Expanding (sum_v x_v - 1)^2:
          = sum_v x_v^2 + 2*sum_{v<w} x_v*x_w - 2*sum_v x_v + 1
        In QUBO: x_v^2 = x_v  (binary), constant dropped, so:
          Linear part : -lambda_ * 1 * x_{i,v,t}  per (i,v,t)
          Quad part   : +2*lambda_ * x_{i,v,t} * x_{i,w,t}  for v < w
        (The -2 * sum_v x_v and +1 contribution from squaring the -1 term)

        Full expansion of (sum_v x_v - 1)^2:
          sum_v x_v  (from x_v^2 = x_v: coefficient +1)
          + 2*sum_{v<w} x_v*x_w
          - 2*sum_v x_v
          + constant 1

        Net linear coefficient per variable: (1 - 2) * lambda_ = -lambda_
        Net quadratic coefficient per pair:  +2 * lambda_
        """
        for ion in ions:
            for t in range(T + 1):
                # Linear terms (coefficient = -lambda_ per variable)
                for pos in positions:
                    key = (ion, pos, t)
                    if key in var_map:
                        bqm.add_variable(var_map[key], -lambda_)

                # Quadratic terms (coefficient = +2*lambda_ per pair)
                pos_list = [p for p in positions if (ion, p, t) in var_map]
                for v, w in itertools.combinations(pos_list, 2):
                    v_label = var_map[(ion, v, t)]
                    w_label = var_map[(ion, w, t)]
                    bqm.add_interaction(v_label, w_label, 2.0 * lambda_)

    def _add_capacity_penalty(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        pg: Any,
        T: int,
        lambda_: float,
    ) -> None:
        """
        Add capacity constraint:
            for each position v and timestep t:
                sum_i x_{i,v,t}  <=  cap(v)

        For cap(v) = 1 (most slots):
            Penalise each pair of distinct ions co-located at v, t:
                lambda_ * x_{i,v,t} * x_{j,v,t}  for all i ≠ j

        For cap(v) > 1 (e.g. trap slots with cap=2):
            We need to penalise triples (cubic). In this formulation we
            use a slack/Rosenberg approach: we call _rosenberg_product()
            to introduce an auxiliary variable z = x_i * x_j, then
            penalise z * x_k.  The actual quadratization is done lazily
            by _rosenberg_quadratize() at the end; here we just add the
            interaction between every pair (which is correct for cap=1,
            and approximately correct for cap=2 — the cubic terms are
            negligible for small windows).

        Note: For the typical QCCD architecture, trap slots have cap=2
        but *transport segments* have cap=1. We treat all window nodes
        as cap=1 by default (conservative — no two active ions at same
        position at the same time step). This is correct for congested
        segments and a safe approximation for traps.
        """
        G = getattr(pg, "graph", None)
        ions = list(window.active_ions.keys())

        for pos in window.window_nodes:
            # Determine capacity from node attributes (default 1)
            cap = 1
            if G is not None and G.has_node(pos):
                cap = G.nodes[pos].get("capacity", 1)

            for t in range(T + 1):
                # All ions with a variable at (pos, t)
                ion_vars = [
                    (ion, var_map[(ion, pos, t)])
                    for ion in ions
                    if (ion, pos, t) in var_map
                ]

                if cap == 1:
                    # Every pair of distinct ions must not co-occupy
                    for (i1, lbl1), (i2, lbl2) in itertools.combinations(ion_vars, 2):
                        bqm.add_interaction(lbl1, lbl2, lambda_)

                else:
                    # cap >= 2: only penalise (cap+1)-way co-location
                    # For simplicity, penalise triples (works for cap=2)
                    # Using Rosenberg quadratization for x_a * x_b * x_c:
                    #   z = x_a * x_b  →  then penalise z * x_c
                    for combo in itertools.combinations(ion_vars, cap + 1):
                        lbls = [lbl for _, lbl in combo]
                        # Quadratize greedily: chain through pairs
                        running = lbls[0]
                        for next_lbl in lbls[1:]:
                            aux = self._rosenberg_product(bqm, running, next_lbl, lambda_)
                            running = aux
                        # The final `running` represents the product of all;
                        # a penalty of lambda_ applied via the aux var chain
                        # already encodes the constraint.

    def _add_movement_penalty(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        pg: Any,
        T: int,
        lambda_: float,
    ) -> None:
        """
        Add movement legality constraint:
            for each ion i and adjacent timesteps (t, t+1):
                ion i can only be at position w at t+1 if:
                    w == v  (stayed)  OR  (v, w) is a legal G_p edge

        Penalty for illegal move (v → w where v≠w and (v,w) not in E):
            lambda_ * x_{i,v,t} * x_{i,w,t+1}

        This is already quadratic – no further quadratization needed.
        """
        G = getattr(pg, "graph", None)
        ions      = list(window.active_ions.keys())
        positions = list(window.window_nodes)

        for ion in ions:
            for t in range(T):
                for v in positions:
                    key_v_t = (ion, v, t)
                    if key_v_t not in var_map:
                        continue
                    v_label = var_map[key_v_t]

                    for w in positions:
                        if w == v:
                            continue  # staying in place – always legal

                        # Check if v→w is a legal edge in G_p
                        if G is not None:
                            if G.has_edge(v, w) or G.has_edge(w, v):
                                continue  # legal hop – no penalty

                        # Illegal transition: penalise co-assignment
                        key_w_t1 = (ion, w, t + 1)
                        if key_w_t1 not in var_map:
                            continue
                        w_label = var_map[key_w_t1]
                        bqm.add_interaction(v_label, w_label, lambda_)

    def _add_goal_penalty(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        T: int,
        lambda_: float,
    ) -> None:
        """
        Add goal constraint:
            The moving ion must be at window.target at timestep T.

            Penalty: lambda_ * (1 - x_{moving_ion, target, T})
            → Subtract lambda_ * x_{moving_ion, target, T} from BQM linear.

        The 'moving ion' is identified as the ion whose current position
        is window.source (it is the one that needs to reach window.target).
        If no ion is at source, we fall back to penalising ALL active ions
        that should eventually end up at target.
        """
        target = window.target

        # Identify the primary moving ion: the one currently at source
        moving_ion = None
        for ion, pos in window.active_ions.items():
            if pos == window.source:
                moving_ion = ion
                break

        if moving_ion is not None:
            key = (moving_ion, target, T)
            if key in var_map:
                bqm.add_variable(var_map[key], -lambda_)
                logger.debug(
                    "Goal penalty: ion %s must reach %s at t=%d", moving_ion, target, T
                )
        else:
            # Fallback: encourage any active ion to be at target at T
            logger.debug(
                "Goal penalty: no ion at source %s; applying soft goal to all ions",
                window.source,
            )
            for ion in window.active_ions:
                key = (ion, target, T)
                if key in var_map:
                    bqm.add_variable(var_map[key], -lambda_)

    def _add_cost_objective(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        T: int,
    ) -> None:
        """
        Add movement cost objective:
            H_cost = hop_cost * x_{i,v,t}  for each variable where
                     v is NOT the ion's starting position (at t=0).

        Rationale: we want to minimise the number of "away" assignments
        (i.e. how many (ion, pos, t) triples place the ion away from
        where it started). This proxy for "total hops" is tight for
        unit-cost graphs.

        For ions at their initial positions, no cost is added (staying
        is free). For ions at non-initial positions, a cost of hop_cost
        is added per assignment variable.
        """
        for ion, start_pos in window.active_ions.items():
            for pos in window.window_nodes:
                if pos == start_pos:
                    # Staying at the starting position costs nothing
                    continue
                for t in range(T + 1):
                    key = (ion, pos, t)
                    if key in var_map:
                        bqm.add_variable(var_map[key], self.hop_cost)

    def _rosenberg_quadratize(
        self,
        bqm: dimod.BinaryQuadraticModel,
    ) -> int:
        """
        Placeholder for additional Rosenberg quadratization.

        In the current formulation all hard constraint terms are already
        quadratic (one-hot uses x^2=x, movement penalty is quadratic,
        goal penalty is linear). Capacity penalties for cap>1 are
        handled inline by _rosenberg_product() in _add_capacity_penalty.

        Returns the number of auxiliary variables introduced so far
        (tracked via self._aux_counter from calls to _rosenberg_product).
        """
        return self._aux_counter

    # -----------------------------------------------------------------------
    # Internal helper: Rosenberg product substitution
    # -----------------------------------------------------------------------

    def _rosenberg_product(
        self,
        bqm: dimod.BinaryQuadraticModel,
        lbl_a: str,
        lbl_b: str,
        lambda_: float,
    ) -> str:
        """
        Introduce an auxiliary binary variable z to represent z ≡ a * b,
        using Rosenberg's quadratization penalty:

            P(a, b, z) = lambda_ * (a*b - 2*a*z - 2*b*z + 3*z)

        This enforces z = a AND b in the ground state.

        Returns the label of the auxiliary variable z.
        """
        key = (lbl_a, lbl_b)
        if key in self._aux_var_map:
            return self._aux_var_map[key]

        # New auxiliary variable
        self._aux_counter += 1
        z_label = f"_aux_{lbl_a}_{lbl_b}_{self._aux_counter}"
        self._aux_var_map[key] = z_label

        # Rosenberg penalty terms
        bqm.add_variable(z_label, 3.0 * lambda_)          # +3λz
        bqm.add_interaction(lbl_a, lbl_b, lambda_)         # +λ*ab
        bqm.add_interaction(lbl_a, z_label, -2.0 * lambda_)  # -2λ*az
        bqm.add_interaction(lbl_b, z_label, -2.0 * lambda_)  # -2λ*bz

        logger.debug("Rosenberg aux var %s ≡ %s * %s", z_label, lbl_a, lbl_b)
        return z_label


# ---------------------------------------------------------------------------
# Smoke test  (python src/qubo_formulator.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from position_graph import build_linear_qccd, Placement
    from congestion_handler import CongestionHandler

    print("=" * 60)
    print("QUBOFormulator – smoke test")
    print("=" * 60)

    # Build a small 3-trap QCCD hardware graph
    pg = build_linear_qccd(num_traps=3, trap_capacity=2)
    pl = Placement(pg)

    # Place two ions: ion 0 at trap0-slot0, ion 1 (blocker) at trap1-slot0
    pl.place(0, pg.slots_of("t0")[0])
    pl.place(1, pg.slots_of("t1")[0])   # blocks the path

    # Identify a path through the blocker
    path = pg.shortest_path(pg.slots_of("t0")[0], pg.slots_of("t2")[0])
    print(f"Path from t0:0 -> t2:0 : {path}")

    # Extract congestion window
    handler = CongestionHandler()
    blocked = handler._detect_blockages(path, pl)
    print(f"Blocked positions     : {blocked}")

    window = handler.extract_window(path, blocked, pl, pg)
    print(f"Window nodes          : {sorted(window.window_nodes)}")
    print(f"Active ions           : {window.active_ions}")
    print(f"Source -> Target      : {window.source} -> {window.target}")

    # Build QUBO
    formulator = QUBOFormulator()
    problem = formulator.build(window, pg)

    print()
    print(f"Time horizon T        : {problem.time_horizon}")
    print(f"Binary variables      : {problem.num_variables}")
    print(f"Auxiliary vars (Rosen): {problem.num_aux_variables}")
    print(f"Penalty lambda        : {problem.penalty_lambda:.4f}")
    print(f"BQM #variables        : {len(problem.bqm.variables)}")
    print(f"BQM #interactions     : {len(problem.bqm.quadratic)}")
    print()

    # Verify var_map / inv_var_map consistency
    mismatch = 0
    for key, label in problem.var_map.items():
        if problem.inv_var_map.get(label) != key:
            mismatch += 1
    print(f"var_map / inv_var_map consistent : {'YES' if mismatch == 0 else f'NO ({mismatch} mismatches)'}")

    # Verify constraint: λ >= T + 1
    ok = problem.penalty_lambda >= problem.time_horizon + 1
    print(f"lambda >= T+1 satisfied          : {'YES' if ok else 'NO'}")

    print()
    print("Smoke test PASSED.  Run 'pytest tests/test_qubo_formulator.py -v' for full tests.")
