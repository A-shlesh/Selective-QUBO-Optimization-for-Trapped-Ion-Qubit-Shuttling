"""
qubo_formulator.py
==================
Phase 6 of the Selective-QUBO methodology:
  Build the QUBO Q-matrix from the local congestion window W.

ASSIGNED TO: Person 1
======================

YOUR TASK
---------
Implement QUBOFormulator.build(window, pg) so that it:

  1. Enumerates binary decision variables
         x_{i, v, t}  ∈  {0, 1}
     meaning "ion i is at position v at time step t".

  2. Encodes four groups of penalty terms into a dimod
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
  dimod>=3.5   (BinaryQuadraticModel, QUBO utilities)
  networkx     (graph traversal, already used throughout)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

# dimod is installed via requirements.txt
import dimod

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
# Main class  (Person 1 implements the methods marked TODO)
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
        # TODO (Person 1): implement the full formulation.
        #
        # Suggested sub-steps:
        #   1. _compute_time_horizon(window, pg) → T
        #   2. _make_variables(window, T) → var_map, inv_var_map
        #   3. _init_bqm(var_map) → bqm
        #   4. _add_one_hot_penalty(bqm, var_map, T, lambda_)
        #   5. _add_capacity_penalty(bqm, var_map, window, pg, T, lambda_)
        #   6. _add_movement_penalty(bqm, var_map, window, pg, T, lambda_)
        #   7. _add_goal_penalty(bqm, var_map, window, T, lambda_)
        #   8. _add_cost_objective(bqm, var_map, window, T)
        #   9. _rosenberg_quadratize(bqm) → num_aux
        #  10. Assemble and return QUBOProblem(...)
        raise NotImplementedError(
            "QUBOFormulator.build() is not yet implemented. "
            "See the TODO comments in src/qubo_formulator.py."
        )

    # -----------------------------------------------------------------------
    # Sub-steps (implement each one separately – easier to unit-test)
    # -----------------------------------------------------------------------

    def _compute_time_horizon(self, window: WindowInfo, pg: Any) -> int:
        """
        TODO: Compute the number of time steps T.

        A reasonable default:
            T = shortest_path_length(source, target) + len(blocked_path)
        This gives just enough slack to clear the blockers one by one.
        """
        # TODO (Person 1)
        raise NotImplementedError

    def _make_variables(
        self,
        window: WindowInfo,
        T: int,
    ) -> Tuple[Dict, Dict]:
        """
        TODO: Create one binary variable per (ion, position, timestep).

        Only create variables for ions in window.active_ions and
        positions in window.window_nodes.

        Return (var_map, inv_var_map) where:
          var_map     : (ion, pos, t) → label string e.g. "x_0_t0:0_2"
          inv_var_map : label → (ion, pos, t)
        """
        # TODO (Person 1)
        raise NotImplementedError

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
        TODO: Add one-hot constraint:
            for each ion i and timestep t:
                (sum_v x_{i,v,t} - 1)^2  -->  expand and add to bqm

        Expanding: sum_v x_{i,v,t}^2  +  2 * sum_{v<w} x_{i,v,t}*x_{i,w,t}
                   - 2 * sum_v x_{i,v,t}  +  constant
        In QUBO form: linear terms → bqm.add_variable; quadratic → bqm.add_interaction
        """
        # TODO (Person 1)
        raise NotImplementedError

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
        TODO: Add capacity constraint:
            for each position v and timestep t:
                sum_i x_{i,v,t}  <=  cap(v)

        For cap(v) = 1:
            x_{i,v,t} * x_{j,v,t}  for all pairs i≠j  (simple quadratic)
        For cap(v) = 2:
            x_{i,v,t} * x_{j,v,t} * x_{k,v,t}  (cubic – needs Rosenberg)
        """
        # TODO (Person 1)
        raise NotImplementedError

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
        TODO: Add movement legality constraint:
            for each ion i and adjacent timesteps (t, t+1):
                ion i can only be at position w at t+1 if:
                    w == v  (stayed)  OR  (v, w) is a legal G_p edge

        Penalty for illegal move:
            x_{i,v,t} * x_{i,w,t+1} * lambda_  for all illegal (v→w) pairs
        (This is already quadratic – no quadratization needed.)
        """
        # TODO (Person 1)
        raise NotImplementedError

    def _add_goal_penalty(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        T: int,
        lambda_: float,
    ) -> None:
        """
        TODO: Add goal constraint:
            The moving ion must be at window.target at timestep T.

            Penalty: lambda_ * (1 - x_{moving_ion, target, T})
            → Subtract lambda_ * x_{moving_ion, target, T} from BQM linear.

        The 'moving ion' is the one whose source is window.source.
        Identify it from window.active_ions.
        """
        # TODO (Person 1)
        raise NotImplementedError

    def _add_cost_objective(
        self,
        bqm: dimod.BinaryQuadraticModel,
        var_map: Dict,
        window: WindowInfo,
        T: int,
    ) -> None:
        """
        TODO: Add movement cost objective:
            H_cost = sum_{i,v,t} hop_cost * x_{i,v,t}
                     where the variable represents a move (v ≠ prev position)

        Simpler version: penalise every position that is NOT the ion's
        current (t=0) location, weighted by self.hop_cost.
        """
        # TODO (Person 1)
        raise NotImplementedError

    def _rosenberg_quadratize(
        self,
        bqm: dimod.BinaryQuadraticModel,
    ) -> int:
        """
        TODO: Replace any remaining higher-order terms with auxiliary
        binary variables using Rosenberg's substitution:

            x * y  →  introduce  z  with penalties:
                3z + xy - 2xz - 2yz

        dimod's `make_quadratic` utility can help:
            from dimod import make_quadratic
            poly = dimod.BinaryPolynomial(...)
            bqm, aux = make_quadratic(poly, strength, vartype)

        Return the number of auxiliary variables introduced.
        """
        # TODO (Person 1)
        return 0  # placeholder


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("qubo_formulator.py: skeleton loaded.")
    print("QUBOFormulator.build() is not yet implemented.")
    print("Implement the TODO methods and run: pytest tests/test_qubo_formulator.py")
