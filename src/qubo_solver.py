"""
qubo_solver.py
==============
Phase 7 of the Selective-QUBO methodology:
  Solve the QUBOProblem using ExactSolver (small) or SimulatedAnnealing (large).

ASSIGNED TO: Person 2
======================

YOUR TASK
---------
Implement QUBOSolver.solve(problem) so that it:

  1. Checks problem.num_variables:
       ≤ EXACT_THRESHOLD  →  use dimod.ExactSolver (guaranteed optimal)
       >  EXACT_THRESHOLD  →  use neal.SimulatedAnnealingSampler

  2. Runs the chosen sampler and returns the best (lowest-energy) sample
     as a QUBOSolution.

  3. Checks feasibility: the solution satisfies all constraints iff
     its energy equals the objective-only energy (no penalty fired).
     A simpler check: energy < lambda (no constraint term contributed).

  4. Exposes separate solve_exact() and solve_sa() methods so the
     decoder can call them directly in tests.

  5. (Optional but useful) Implements penalty calibration:
     run bisection over lambda values on a tiny synthetic problem to
     find the tightest lambda that still satisfies all constraints.

REFERENCE
---------
[QUBO]  Glover et al. 2019, §4 – solver selection and parameter tuning.
neal documentation: https://docs.ocean.dwavesys.com/projects/neal/

HOW TO RUN YOUR CODE
--------------------
  python src/qubo_solver.py           # smoke test
  pytest tests/test_qubo_solver.py    # unit tests

DEPENDENCIES
------------
  dimod>=3.5      (ExactSolver, BinaryQuadraticModel)
  dwave-neal>=0.6 (SimulatedAnnealingSampler)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import dimod
import neal

from qubo_formulator import QUBOProblem

logger = logging.getLogger("shaw_router.qubo_solver")

# Threshold: instances with more variables than this get SimulatedAnnealing
EXACT_THRESHOLD: int = 20


# ---------------------------------------------------------------------------
# Output data structure  (DO NOT CHANGE – solution_decoder.py depends on this)
# ---------------------------------------------------------------------------

@dataclass
class QUBOSolution:
    """
    Result returned by the solver.

    Attributes
    ----------
    sample : dict  { variable_label : 0 or 1 }
        The best binary assignment found.
    energy : float
        Objective + penalty energy of this sample.
    is_feasible : bool
        True if no constraint penalty term fired in this sample.
        (Checked by: energy < problem.penalty_lambda * num_constraints)
    solver_used : str
        "exact" or "simulated_annealing"
    solve_time_s : float
        Wall-clock seconds taken by the solver.
    num_reads : int
        Number of samples taken (1 for ExactSolver, configurable for SA).
    problem : QUBOProblem
        The source problem (kept for the decoder).
    metadata : dict
        Anything extra you want to record (e.g. all samples, energies).
    """
    sample: Dict[str, int]
    energy: float
    is_feasible: bool
    solver_used: str
    solve_time_s: float
    num_reads: int
    problem: QUBOProblem
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main class  (Person 2 implements the methods marked TODO)
# ---------------------------------------------------------------------------

class QUBOSolver:
    """
    Selects and runs the appropriate solver for a QUBOProblem.

    Parameters
    ----------
    exact_threshold : int
        Max variables before switching from ExactSolver to SA (default 20).
    sa_num_reads : int
        Number of SA reads (independent restarts). Default 200.
    sa_num_sweeps : int
        Sweeps per SA read. Default 1000.
    """

    def __init__(
        self,
        exact_threshold: int = EXACT_THRESHOLD,
        sa_num_reads: int = 200,
        sa_num_sweeps: int = 1000,
    ) -> None:
        self.exact_threshold = exact_threshold
        self.sa_num_reads = sa_num_reads
        self.sa_num_sweeps = sa_num_sweeps

    def solve(self, problem: QUBOProblem) -> QUBOSolution:
        """
        Auto-select solver based on problem size and return best solution.

        Parameters
        ----------
        problem : QUBOProblem   (from qubo_formulator.py)

        Returns
        -------
        QUBOSolution
        """
        total_vars = problem.num_variables + problem.num_aux_variables
        if total_vars <= self.exact_threshold:
            return self.solve_exact(problem)
        else:
            return self.solve_sa(problem)

    def solve_exact(self, problem: QUBOProblem) -> QUBOSolution:
        """
        TODO: Solve with dimod.ExactSolver (guaranteed optimal, exponential cost).

        Steps:
          1. sampler = dimod.ExactSolver()
          2. sampleset = sampler.sample(problem.bqm)
          3. best = sampleset.first  (lowest energy)
          4. is_feasible = _check_feasibility(best.energy, problem)
          5. return QUBOSolution(...)

        Only call this when num_variables <= exact_threshold.
        Log a warning and fall back to SA if called on a large problem.
        """
        # TODO (Person 2)
        raise NotImplementedError

    def solve_sa(self, problem: QUBOProblem) -> QUBOSolution:
        """
        TODO: Solve with neal.SimulatedAnnealingSampler.

        Steps:
          1. sampler = neal.SimulatedAnnealingSampler()
          2. sampleset = sampler.sample(
                 problem.bqm,
                 num_reads=self.sa_num_reads,
                 num_sweeps=self.sa_num_sweeps,
             )
          3. best = sampleset.first
          4. is_feasible = _check_feasibility(best.energy, problem)
          5. return QUBOSolution(...)

        Tips:
          - Log the best energy and whether it's feasible.
          - Store the full sampleset in metadata for analysis.
          - Consider sorting all samples and logging the feasibility rate.
        """
        # TODO (Person 2)
        raise NotImplementedError

    def _check_feasibility(
        self,
        energy: float,
        problem: QUBOProblem,
    ) -> bool:
        """
        TODO: Decide whether a solution with this energy is feasible.

        A solution is feasible iff none of the constraint penalty terms
        contributed to the energy (i.e. all constraints are satisfied).

        Simple heuristic: energy < problem.penalty_lambda
        (because each violated constraint adds at least lambda to energy).

        More precise: decode the sample and directly check each constraint.
        The decoder (solution_decoder.py) does the precise check; this
        method provides a quick pre-filter.
        """
        # TODO (Person 2)
        raise NotImplementedError

    def calibrate_penalty(
        self,
        problem: QUBOProblem,
        target_feasibility: float = 0.95,
        max_iterations: int = 10,
    ) -> float:
        """
        TODO (Optional): Find the smallest lambda that achieves
        `target_feasibility` fraction of feasible SA samples, using
        bisection search over lambda.

        Algorithm:
          lo, hi = 1.0, problem.penalty_lambda * 10
          for _ in range(max_iterations):
              mid = (lo + hi) / 2
              rebuild BQM with penalty=mid (rebuild problem)
              rate = fraction of feasible SA samples
              if rate >= target_feasibility: hi = mid
              else: lo = mid
          return hi

        This is an offline calibration step run once on small benchmark
        instances to set good default thresholds.
        """
        # TODO (Person 2)
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("qubo_solver.py: skeleton loaded.")
    print("QUBOSolver.solve() is not yet implemented.")
    print("Implement the TODO methods and run: pytest tests/test_qubo_solver.py")
