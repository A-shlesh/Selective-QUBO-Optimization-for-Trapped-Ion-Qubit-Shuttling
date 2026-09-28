"""
solution_decoder.py
===================
Phases 8 and 9 of the Selective-QUBO methodology:
  8. Decode QUBO binary solution → physical shuttling operations.
  9. Validate + compare cost → accept QUBO route or fall back to heuristic.

ASSIGNED TO: Person 3
======================

YOUR TASK
---------
Implement SolutionDecoder.decode_and_validate(solution, placement, pg) so that it:

  1. Reads the binary sample from QUBOSolution and reconstructs the
     ion trajectories:
         trajectory[ion][t] = position  (for t = 0..T)

  2. Validates ALL five constraints:
       (a) Movement legality   – each step is a legal G_p edge
       (b) Occupancy           – no two ions at same position at same t
       (c) Capacity            – occupancy(v, t) ≤ cap(v)
       (d) Collision avoidance – no crossing moves (ions don't swap
                                  in one step without an explicit swap gate)
       (e) Gate feasibility    – target ion reaches window.target at t=T

  3. Extracts the decoded path for the MOVING ION
     (the one that starts at window.source and must reach window.target).

  4. Computes QUBO routing cost C_QUBO = number of hops in decoded path.

  5. Computes heuristic cost C_heur from the original blocked path length.

  6. Accepts the QUBO solution ONLY if:
         solution.is_feasible  AND  C_QUBO < C_heur
     Otherwise, returns None to signal "fall back to heuristic".

METHODOLOGY REFERENCE (§8–9)
-----------------------------
"An invalid QUBO solution is immediately rejected."
"The QUBO solution is applied only if it is both feasible and
sufficiently beneficial: C_QUBO < C_heuristic."

REFERENCE PAPERS
----------------
[SHAW]  Bach et al. arXiv 2501.12470, §3 – legality checks for
        QCCD shuttling (trap capacity, junction constraints).

HOW TO RUN YOUR CODE
--------------------
  python src/solution_decoder.py          # smoke test
  pytest tests/test_solution_decoder.py   # unit tests

INTERFACES YOU CONSUME
----------------------
  QUBOSolution  from qubo_solver.py
  WindowInfo    from congestion_handler.py
  Placement     from position_graph.py
  PositionGraph from position_graph.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from congestion_handler import WindowInfo
from qubo_solver import QUBOSolution

if TYPE_CHECKING:
    from position_graph import Placement, PositionGraph

logger = logging.getLogger("shaw_router.solution_decoder")


# ---------------------------------------------------------------------------
# Output data structure  (DO NOT CHANGE – congestion_handler.py will consume this)
# ---------------------------------------------------------------------------

@dataclass
class DecodedSolution:
    """
    Result of decoding and validating a QUBO solution.

    Attributes
    ----------
    accepted : bool
        True iff the QUBO solution passed all validation checks AND
        C_QUBO < C_heuristic.  Only accepted solutions are handed to
        ShawRoutingPass.
    decoded_path : list or None
        The physical shuttling path for the moving ion
        [pos_at_t0, pos_at_t1, ..., pos_at_tT], or None if rejected.
    C_QUBO : int
        Hop count of the QUBO-decoded path (0 if rejected).
    C_heuristic : int
        Hop count of the original heuristic path (for comparison).
    improvement : float
        (C_heuristic - C_QUBO) / C_heuristic  (0.0 if rejected or equal).
    violation : str or None
        If rejected, which constraint was violated (for diagnostics).
    trajectories : dict  { ion_id: list[position_at_t] }
        Full decoded position sequence for all active ions.
    """
    accepted: bool
    decoded_path: Optional[List[Any]]
    C_QUBO: int
    C_heuristic: int
    improvement: float
    violation: Optional[str]
    trajectories: Dict[Any, List[Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation result helper
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Outcome of one validation check."""
    passed: bool
    constraint: str       # e.g. "movement_legality"
    detail: str = ""      # human-readable failure description


# ---------------------------------------------------------------------------
# Main class  (Person 3 implements the methods marked TODO)
# ---------------------------------------------------------------------------

class SolutionDecoder:
    """
    Decodes and validates QUBO solutions into physical routing paths.

    Parameters
    ----------
    strict_capacity : bool
        If True, fail on any capacity violation (recommended for correctness).
        If False, log a warning but continue (useful for debugging).
    """

    def __init__(self, strict_capacity: bool = True) -> None:
        self.strict_capacity = strict_capacity

    def decode_and_validate(
        self,
        solution: QUBOSolution,
        placement: "Placement",
        pg: "PositionGraph",
    ) -> DecodedSolution:
        """
        Full decode + validate + cost comparison pipeline.

        Parameters
        ----------
        solution  : QUBOSolution from qubo_solver.py
        placement : current live Placement (before any QUBO move is applied)
        pg        : PositionGraph (for edge legality and capacity checks)

        Returns
        -------
        DecodedSolution
            .accepted = True  →  call apply_to_placement() and use decoded_path
            .accepted = False →  fall back to heuristic
        """
        window = solution.problem.window
        C_heuristic = len(window.blocked_path) + len(window.blocked_path)  # TODO: refine

        # Step 1 – quick pre-filter: solver already flagged infeasible
        if not solution.is_feasible:
            logger.info("QUBO solution pre-rejected: solver flagged infeasible (energy=%.3f)", solution.energy)
            return DecodedSolution(
                accepted=False, decoded_path=None,
                C_QUBO=0, C_heuristic=C_heuristic,
                improvement=0.0, violation="infeasible_energy",
            )

        # Step 2 – decode trajectories
        trajectories = self._decode_trajectories(solution)
        if not trajectories:
            return DecodedSolution(
                accepted=False, decoded_path=None,
                C_QUBO=0, C_heuristic=C_heuristic,
                improvement=0.0, violation="decode_failed",
                trajectories={},
            )

        # Step 3 – run all validation checks
        checks = [
            self._check_movement_legality(trajectories, window, pg),
            self._check_occupancy(trajectories, window),
            self._check_capacity(trajectories, window, pg),
            self._check_collision_avoidance(trajectories, window),
            self._check_gate_feasibility(trajectories, window),
        ]

        for result in checks:
            if not result.passed:
                logger.info(
                    "QUBO solution rejected: %s failed – %s",
                    result.constraint, result.detail,
                )
                return DecodedSolution(
                    accepted=False, decoded_path=None,
                    C_QUBO=0, C_heuristic=C_heuristic,
                    improvement=0.0, violation=result.constraint,
                    trajectories=trajectories,
                )

        # Step 4 – extract moving ion path
        decoded_path = self._extract_moving_ion_path(trajectories, window)
        C_QUBO = len(decoded_path) - 1 if decoded_path else 0

        # Step 5 – cost comparison (methodology §9)
        if C_QUBO >= C_heuristic:
            logger.info(
                "QUBO solution valid but not better: C_QUBO=%d >= C_heur=%d; "
                "falling back to heuristic.",
                C_QUBO, C_heuristic,
            )
            return DecodedSolution(
                accepted=False, decoded_path=None,
                C_QUBO=C_QUBO, C_heuristic=C_heuristic,
                improvement=0.0, violation="not_better_than_heuristic",
                trajectories=trajectories,
            )

        improvement = (C_heuristic - C_QUBO) / max(C_heuristic, 1)
        logger.info(
            "QUBO solution ACCEPTED: C_QUBO=%d < C_heur=%d (%.1f%% improvement)",
            C_QUBO, C_heuristic, improvement * 100,
        )
        return DecodedSolution(
            accepted=True,
            decoded_path=decoded_path,
            C_QUBO=C_QUBO,
            C_heuristic=C_heuristic,
            improvement=improvement,
            violation=None,
            trajectories=trajectories,
        )

    # -----------------------------------------------------------------------
    # Decoding
    # -----------------------------------------------------------------------

    def _decode_trajectories(
        self,
        solution: QUBOSolution,
    ) -> Dict[Any, List[Any]]:
        """
        TODO: Read solution.sample (dict {label: 0|1}) and reconstruct
        the position at each timestep for every active ion.

        Use solution.problem.inv_var_map to convert label → (ion, pos, t).

        Return:
            { ion_id : [pos_at_t0, pos_at_t1, ..., pos_at_T] }

        Edge cases to handle:
          - A variable set to 1 means ion is at that position at that time.
          - If no variable is 1 for (ion, t), the ion didn't move (use t-1 position).
          - If multiple variables are 1 for (ion, t), flag as infeasible.
        """
        # TODO (Person 3)
        raise NotImplementedError

    def _extract_moving_ion_path(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
    ) -> Optional[List[Any]]:
        """
        TODO: From the decoded trajectories, extract the path for the
        ion that starts at window.source.

        Return the sequence [pos_t0, pos_t1, ..., pos_tT] for that ion,
        deduplicated (remove consecutive repeated positions since the
        ion might "stay" at a position for multiple timesteps before moving).
        """
        # TODO (Person 3)
        raise NotImplementedError

    # -----------------------------------------------------------------------
    # Validation checks
    # -----------------------------------------------------------------------

    def _check_movement_legality(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
        pg: "PositionGraph",
    ) -> ValidationResult:
        """
        TODO: For each ion and each consecutive timestep pair (t, t+1),
        verify that either:
          (a) the ion stayed (pos_t == pos_{t+1}), OR
          (b) (pos_t, pos_{t+1}) is an edge in pg.graph.

        Return ValidationResult(passed=False, ...) on first violation.
        """
        # TODO (Person 3)
        raise NotImplementedError

    def _check_occupancy(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
    ) -> ValidationResult:
        """
        TODO: At each timestep t, no two active ions should occupy the
        same position.

        Build position_to_ions[t][pos] = [ion, ...] and check for len > 1.
        """
        # TODO (Person 3)
        raise NotImplementedError

    def _check_capacity(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
        pg: "PositionGraph",
    ) -> ValidationResult:
        """
        TODO: At each timestep t and each position v, verify that the
        number of active ions at v does not exceed pg.graph.nodes[v]['capacity']
        (or 1 if the attribute is missing, for segment nodes).

        Also account for obstacle_ions (outside the window but fixed):
        if an obstacle ion is at position v, it counts toward capacity.
        """
        # TODO (Person 3)
        raise NotImplementedError

    def _check_collision_avoidance(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
    ) -> ValidationResult:
        """
        TODO: Detect crossing moves – if ion A moves from u→v and ion B
        moves from v→u in the same timestep, that is a collision.

        For each (t, t+1): collect all moves, check for any (u→v, v→u) pair.
        """
        # TODO (Person 3)
        raise NotImplementedError

    def _check_gate_feasibility(
        self,
        trajectories: Dict[Any, List[Any]],
        window: WindowInfo,
    ) -> ValidationResult:
        """
        TODO: Verify that the moving ion (starting at window.source)
        reaches window.target by timestep T.

        Return passed=False if the ion ends up somewhere else.
        """
        # TODO (Person 3)
        raise NotImplementedError

    # -----------------------------------------------------------------------
    # Placement update (called ONLY if accepted=True)
    # -----------------------------------------------------------------------

    def apply_to_placement(
        self,
        decoded: DecodedSolution,
        placement: "Placement",
        pg: "PositionGraph",
    ) -> None:
        """
        TODO: Apply the accepted QUBO solution to the live Placement.

        Walk through decoded.trajectories for ALL active ions (not just
        the moving one) and call placement.move(ion, new_pos) for each
        position change.

        Important:
          - Only move ions when their position actually changes.
          - Process moves in timestep order (t=1, t=2, ..., T).
          - Validate each move against pg.graph before calling placement.move().
          - If any move fails (e.g. position still occupied), raise ValueError
            with a clear message – this should never happen if validation passed.

        After this method returns, the Placement reflects the QUBO-optimised
        routing decisions, and ShawRoutingPass continues from the new state.
        """
        # TODO (Person 3)
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("solution_decoder.py: skeleton loaded.")
    print("SolutionDecoder methods are not yet implemented.")
    print("Implement the TODO methods and run: pytest tests/test_solution_decoder.py")
