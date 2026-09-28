"""
benchmark_runner.py
===================
Phase 11 of the Selective-QUBO methodology:
  Run experiments comparing SHAW-only baseline vs. SHAW+QUBO hybrid.
  Measure all metrics listed in the methodology and generate comparison tables/plots.

ASSIGNED TO: Person 4
======================

YOUR TASK
---------
Implement BenchmarkRunner.run_comparison(circuits, modes) so that it:

  1. For each benchmark circuit (from tests/*.qasm):
       a. Run SHAW-only routing → record metrics
       b. Run SHAW+QUBO routing → record metrics
       c. Compare and record improvement

  2. Produces a results DataFrame with all §11 metrics (see METRICS below).

  3. Saves results to  experiments/results/comparison.csv

  4. Generates comparison plots to  experiments/plots/:
       - bar chart: shuttling ops, SWAP count per circuit
       - histogram: κ, ρ, d distributions
       - line chart: compile time vs circuit size
       - scatter: QUBO invocations vs QUBO acceptance rate

  5. Provides a summary table: wins/losses/ties for QUBO vs heuristic.

METRICS TO RECORD (methodology §11)
------------------------------------
  Per routing run:
    total_shuttle_ops    – total IdentityGate markers (hops)
    swap_count           – total SwapGate insertions
    compile_time_s       – wall-clock seconds
    congestion_events    – CongestionHandler.stats['blocked_events']
    qubo_triggers        – CongestionHandler.stats['qubo_triggers']
    qubo_accepted        – number of QUBO solutions accepted by decoder
    qubo_acceptance_rate – qubo_accepted / qubo_triggers
    kappa_mean           – mean κ over all congestion events
    rho_mean             – mean ρ
    depth_mean           – mean d
    routing_cost_improvement – (C_baseline - C_qubo) / C_baseline

HOW TO RUN YOUR CODE
--------------------
  python src/benchmark_runner.py                        # full benchmark
  python src/benchmark_runner.py --circuits 5           # quick test (5 circuits)
  python src/benchmark_runner.py --mode baseline_only   # baseline only
  pytest tests/test_benchmark_runner.py                 # unit tests

DEPENDENCIES
------------
  numpy, matplotlib (already in requirements.txt)
  pandas (add to requirements.txt if you want DataFrame-based output)
  All existing project modules
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bqskit.compiler.passdata import PassData
from bqskit.ir.circuit import Circuit
from bqskit.ir.gates import CNOTGate, HGate, IdentityGate, SwapGate

from congestion_handler import CongestionHandler
from shaw_routing_pass import ShawRoutingPass

logger = logging.getLogger("shaw_router.benchmark")

TESTS_DIR = Path(__file__).resolve().parents[1] / "tests"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "experiments" / "results"
PLOTS_DIR = Path(__file__).resolve().parents[1] / "experiments" / "plots"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RunMetrics:
    """All metrics for one routing run (one circuit, one mode)."""
    circuit_name: str
    mode: str                   # "baseline" or "hybrid_qubo"
    num_qudits: int
    num_gates_original: int
    total_shuttle_ops: int      # IdentityGate count
    swap_count: int             # SwapGate count
    compile_time_s: float
    congestion_events: int
    qubo_triggers: int
    qubo_accepted: int
    qubo_acceptance_rate: float
    kappa_mean: float
    rho_mean: float
    depth_mean: float
    routing_cost_improvement: float
    success: bool               # False if routing raised RuntimeError
    error_msg: str = ""


@dataclass
class ComparisonResult:
    """Side-by-side comparison for one circuit."""
    circuit_name: str
    baseline: RunMetrics
    hybrid: RunMetrics
    shuttle_improvement: float  # (baseline - hybrid) / baseline
    swap_improvement: float
    time_overhead: float        # hybrid compile_time / baseline compile_time - 1
    verdict: str                # "qubo_wins", "tie", "qubo_loses", "baseline_failed"


# ---------------------------------------------------------------------------
# Main class  (Person 4 implements the methods marked TODO)
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """
    Runs the full experimental evaluation from methodology §11.

    Parameters
    ----------
    qubo_enabled : bool
        If True, runs both baseline and hybrid modes.
        If False, runs baseline only (faster for quick checks).
    kappa_threshold : float
        Congestion threshold for QUBO trigger (passed to CongestionHandler).
    rho_threshold : float
        Regret threshold for QUBO trigger.
    """

    def __init__(
        self,
        qubo_enabled: bool = True,
        kappa_threshold: float = 0.5,
        rho_threshold: float = 0.3,
    ) -> None:
        self.qubo_enabled = qubo_enabled
        self.kappa_threshold = kappa_threshold
        self.rho_threshold = rho_threshold

    # -----------------------------------------------------------------------
    # Top-level entry point
    # -----------------------------------------------------------------------

    def run_all(
        self,
        max_circuits: Optional[int] = None,
    ) -> List[ComparisonResult]:
        """
        TODO: Run the full benchmark over all tests/*.qasm files.

        Steps:
          1. Load all .qasm files from TESTS_DIR (use existing load_qasm logic
             from test_qasm_suite.py, or copy the parser here).
          2. For each circuit:
             a. run_baseline(circuit_name, circuit) → RunMetrics
             b. run_hybrid(circuit_name, circuit)   → RunMetrics  (if qubo_enabled)
             c. compare(baseline, hybrid)            → ComparisonResult
          3. Save results to CSV (save_csv).
          4. Plot results (plot_results).
          5. Print summary table (print_summary).
          6. Return list of ComparisonResult.

        Parameters
        ----------
        max_circuits : int or None
            Limit the number of circuits (useful for quick tests).
        """
        # TODO (Person 4)
        raise NotImplementedError

    def run_baseline(
        self,
        circuit_name: str,
        circuit: Circuit,
    ) -> RunMetrics:
        """
        TODO: Route `circuit` using SHAW-only (no QUBO).

        Steps:
          1. Build a fresh ShawRoutingPass with:
               congestion_handler=CongestionHandler(qubo_trigger=never)
             Hint: set kappa_threshold=1.1 so trigger never fires.
          2. Time the routing: t0 = time.perf_counter()
          3. asyncio.run(shaw.run(circuit, PassData(circuit)))
          4. t1 = time.perf_counter()
          5. Count ops: iterate circuit.operations(), count IdentityGate/SwapGate
          6. Pull stats from shaw.congestion_handler.stats
          7. Return RunMetrics(mode="baseline", ...)

        Handle RuntimeError (deadlock) → success=False, error_msg=str(e).
        """
        # TODO (Person 4)
        raise NotImplementedError

    def run_hybrid(
        self,
        circuit_name: str,
        circuit: Circuit,
    ) -> RunMetrics:
        """
        TODO: Route `circuit` using SHAW + selective QUBO.

        Same as run_baseline but use:
            CongestionHandler(
                kappa_threshold=self.kappa_threshold,
                rho_threshold=self.rho_threshold,
            )
        And wire in the QUBOFormulator + QUBOSolver + SolutionDecoder
        once those modules are implemented (Person 1, 2, 3).

        For now (skeleton): just run with the real thresholds so the
        QUBO trigger fires and logs — the greedy fallback handles routing.
        Record qubo_triggers from stats.
        """
        # TODO (Person 4)
        raise NotImplementedError

    def compare(
        self,
        baseline: RunMetrics,
        hybrid: RunMetrics,
    ) -> ComparisonResult:
        """
        TODO: Compare baseline and hybrid metrics; assign verdict.

        Verdict logic:
          - baseline.success=False → "baseline_failed"
          - shuttle_improvement > 0.05 (5%) → "qubo_wins"
          - shuttle_improvement < -0.05 → "qubo_loses"  (should not happen)
          - else → "tie"
        """
        # TODO (Person 4)
        raise NotImplementedError

    # -----------------------------------------------------------------------
    # Output helpers
    # -----------------------------------------------------------------------

    def save_csv(self, results: List[ComparisonResult]) -> Path:
        """
        TODO: Save comparison results to experiments/results/comparison.csv.

        Columns should be all RunMetrics fields for baseline + hybrid,
        plus comparison fields (improvement, verdict).

        Create RESULTS_DIR if it doesn't exist.
        Return the path to the saved file.
        """
        # TODO (Person 4)
        raise NotImplementedError

    def plot_results(self, results: List[ComparisonResult]) -> None:
        """
        TODO: Generate 4 plots and save to experiments/plots/:

          1. shuttling_ops.png  – grouped bar chart (baseline vs hybrid per circuit)
          2. swap_count.png     – same but for SWAP gates
          3. congestion_dist.png – histograms of κ, ρ, d distributions
          4. compile_time.png   – scatter: circuit size vs compile time (both modes)

        Use matplotlib.  Create PLOTS_DIR if it doesn't exist.
        """
        # TODO (Person 4)
        raise NotImplementedError

    def print_summary(self, results: List[ComparisonResult]) -> None:
        """
        TODO: Print a readable summary table to stdout.

        Show:
          - Total circuits tested
          - QUBO wins / ties / losses
          - Mean shuttle improvement %
          - Mean swap improvement %
          - Mean compile time overhead %
          - QUBO trigger rate and acceptance rate

        Example output:
          ========== Benchmark Summary ==========
          Circuits tested : 200
          QUBO wins       :  42 (21%)
          Ties            : 155 (77.5%)
          QUBO losses     :   3 (1.5%)
          Shuttle improv. :  +8.3% (mean over QUBO wins)
          Time overhead   : +12.1% (mean compile time increase)
          ========================================
        """
        # TODO (Person 4)
        raise NotImplementedError

    # -----------------------------------------------------------------------
    # Circuit loading
    # -----------------------------------------------------------------------

    @staticmethod
    def load_all_circuits() -> List[tuple]:
        """
        TODO: Load all tests/*.qasm files.

        Return list of (circuit_name, Circuit) tuples.
        Reuse or copy the load_qasm + build_circuit functions from
        tests/test_qasm_suite.py.
        """
        # TODO (Person 4)
        raise NotImplementedError

    @staticmethod
    def _count_ops(circuit: Circuit) -> tuple:
        """Count (shuttle_hops, swap_count) in a routed circuit."""
        shuttles = sum(1 for op in circuit.operations() if isinstance(op.gate, IdentityGate))
        swaps = sum(1 for op in circuit.operations() if isinstance(op.gate, SwapGate))
        return shuttles, swaps


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description="Benchmark SHAW vs SHAW+QUBO")
    p.add_argument("--circuits", type=int, default=None,
                   help="Limit number of circuits (default: all)")
    p.add_argument("--mode", choices=["both", "baseline_only"], default="both",
                   help="Which modes to run")
    p.add_argument("--kappa", type=float, default=0.5)
    p.add_argument("--rho", type=float, default=0.3)
    return p.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()

    runner = BenchmarkRunner(
        qubo_enabled=(args.mode == "both"),
        kappa_threshold=args.kappa,
        rho_threshold=args.rho,
    )
    print("benchmark_runner.py: skeleton loaded.")
    print("Implement run_all() and helper methods to run experiments.")
    print("Usage: python src/benchmark_runner.py --circuits 10")
