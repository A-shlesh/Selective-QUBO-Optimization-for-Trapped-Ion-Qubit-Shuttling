"""
experiment_tracker.py
======================
Tracks system performance across code iterations (e.g. execution time,
shuttle movements, variable counts) and generates comparative summaries.

Usage:
------
1. Record a new experiment snapshot:
   python src/experiment_tracker.py --record "Initial QUBO Formulator"

2. View all recorded historical runs:
   python src/experiment_tracker.py --history

3. Compare two specific runs:
   python src/experiment_tracker.py --compare run_001 run_002
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments" / "results"
HISTORY_FILE = EXPERIMENTS_DIR / "experiment_history.json"
PLOTS_DIR = ROOT / "experiments" / "plots"

logger = logging.getLogger("shaw_router.experiment_tracker")


@dataclass
class ExperimentRun:
    run_id: str
    timestamp: str
    label: str
    git_commit: str
    total_shuttle_ops: int
    total_compile_time_s: float
    total_qubo_triggers: int
    avg_qubo_vars: float
    circuits_tested: int
    custom_metrics: Dict[str, float] = field(default_factory=dict)


class ExperimentTracker:
    def __init__(self, history_file: Path = HISTORY_FILE) -> None:
        self.history_file = history_file
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_git_commit(self) -> str:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            return res.stdout.strip() if res.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    def load_history(self) -> List[ExperimentRun]:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ExperimentRun(**item) for item in data]
        except Exception as exc:
            logger.warning("Failed to load history: %s", exc)
            return []

    def save_history(self, history: List[ExperimentRun]) -> None:
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump([asdict(run) for run in history], f, indent=2)

    def record_run(
        self,
        label: str,
        total_shuttle_ops: int,
        total_compile_time_s: float,
        total_qubo_triggers: int = 0,
        avg_qubo_vars: float = 0.0,
        circuits_tested: int = 1,
        custom_metrics: Optional[Dict[str, float]] = None,
    ) -> ExperimentRun:
        history = self.load_history()
        run_num = len(history) + 1
        run_id = f"run_{run_num:03d}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        git_hash = self._get_git_commit()

        run = ExperimentRun(
            run_id=run_id,
            timestamp=now_str,
            label=label,
            git_commit=git_hash,
            total_shuttle_ops=total_shuttle_ops,
            total_compile_time_s=round(total_compile_time_s, 4),
            total_qubo_triggers=total_qubo_triggers,
            avg_qubo_vars=round(avg_qubo_vars, 2),
            circuits_tested=circuits_tested,
            custom_metrics=custom_metrics or {},
        )

        history.append(run)
        self.save_history(history)
        print(f"\n[+] Recorded Experiment Snapshot: {run_id} ({label})")
        return run

    def print_history(self) -> None:
        history = self.load_history()
        if not history:
            print("No experiment runs recorded yet.")
            return

        print("\n================ SYSTEM EXPERIMENT TRACKER HISTORY ================")
        header = f"{'Run ID':<8} | {'Timestamp':<19} | {'Label':<25} | {'Shuttle Ops':<11} | {'Time (s)':<8} | {'Git'}"
        print(header)
        print("-" * len(header))

        for idx, run in enumerate(history):
            ops_diff = ""
            time_diff = ""
            if idx > 0:
                prev = history[idx - 1]
                if prev.total_shuttle_ops > 0:
                    d_ops = ((run.total_shuttle_ops - prev.total_shuttle_ops) / prev.total_shuttle_ops) * 100
                    ops_diff = f" ({d_ops:+.1f}%)"
                if prev.total_compile_time_s > 0:
                    d_time = ((run.total_compile_time_s - prev.total_compile_time_s) / prev.total_compile_time_s) * 100
                    time_diff = f" ({d_time:+.1f}%)"

            ops_str = f"{run.total_shuttle_ops}{ops_diff}"
            time_str = f"{run.total_compile_time_s:.3f}{time_diff}"

            print(
                f"{run.run_id:<8} | {run.timestamp:<19} | {run.label[:25]:<25} | "
                f"{ops_str:<11} | {time_str:<8} | {run.git_commit}"
            )
        print("===================================================================\n")

    def compare_runs(self, run_id_a: str, run_id_b: str) -> None:
        history = {r.run_id: r for r in self.load_history()}
        if run_id_a not in history or run_id_b not in history:
            print(f"Error: Run IDs '{run_id_a}' or '{run_id_b}' not found in history.")
            return

        ra = history[run_id_a]
        rb = history[run_id_b]

        print(f"\n================ COMPARISON: {ra.run_id} vs {rb.run_id} ================")
        print(f"  {ra.run_id} ({ra.label}) -> {rb.run_id} ({rb.label})")
        print("-" * 65)

        # Shuttle ops
        d_ops = rb.total_shuttle_ops - ra.total_shuttle_ops
        p_ops = (d_ops / ra.total_shuttle_ops * 100) if ra.total_shuttle_ops else 0
        ops_status = "IMPROVED (Fewer moves)" if d_ops < 0 else ("REPRESSED" if d_ops > 0 else "NO CHANGE")
        print(f"  Shuttle Movements : {ra.total_shuttle_ops} -> {rb.total_shuttle_ops} ({d_ops:+d}, {p_ops:+.1f}%) [{ops_status}]")

        # Compile time
        d_time = rb.total_compile_time_s - ra.total_compile_time_s
        p_time = (d_time / ra.total_compile_time_s * 100) if ra.total_compile_time_s else 0
        time_status = "FASTER" if d_time < 0 else ("SLOWER" if d_time > 0 else "NO CHANGE")
        print(f"  Execution Time    : {ra.total_compile_time_s:.4f}s -> {rb.total_compile_time_s:.4f}s ({d_time:+.4f}s, {p_time:+.1f}%) [{time_status}]")

        print("===================================================================\n")

    def plot_history(self) -> None:
        history = self.load_history()
        if len(history) < 2:
            print("Need at least 2 recorded runs to plot trend history.")
            return

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        PLOTS_DIR.mkdir(parents=True, exist_ok=True)
        labels = [f"{r.run_id}\n({r.label[:10]})" for r in history]
        ops = [r.total_shuttle_ops for r in history]
        times = [r.total_compile_time_s for r in history]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

        ax1.plot(labels, ops, marker="o", color="blue", linewidth=2)
        ax1.set_ylabel("Total Shuttle Ops (Movements)")
        ax1.set_title("System Progression: Shuttle Movements Over Iterations")
        ax1.grid(True, linestyle="--", alpha=0.5)

        ax2.plot(labels, times, marker="s", color="green", linewidth=2)
        ax2.set_ylabel("Compile Time (Seconds)")
        ax2.set_xlabel("Experiment Iterations")
        ax2.grid(True, linestyle="--", alpha=0.5)

        fig.tight_layout()
        plot_path = PLOTS_DIR / "system_iteration_trend.png"
        fig.savefig(plot_path, dpi=160)
        plt.close(fig)
        print(f"[+] Saved system progression plot to: {plot_path}")


def main():
    parser = argparse.ArgumentParser(description="Track system performance across code iterations.")
    parser.add_argument("--record", type=str, help="Record current benchmark run with a descriptive label")
    parser.add_argument("--history", action="store_true", help="Print all recorded experiment history")
    parser.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), help="Compare two run IDs (e.g. run_001 run_002)")
    parser.add_argument("--plot", action="store_true", help="Generate trend plot of experiment history")
    parser.add_argument("--shuttles", type=int, default=0, help="Total shuttle ops for manual record")
    parser.add_argument("--time", type=float, default=0.0, help="Total time in seconds for manual record")

    args = parser.parse_args()
    tracker = ExperimentTracker()

    if args.record:
        # If shuttles and time provided manually, record them; otherwise run benchmark_runner
        if args.shuttles > 0 or args.time > 0:
            tracker.record_run(
                label=args.record,
                total_shuttle_ops=args.shuttles,
                total_compile_time_s=args.time,
            )
        else:
            # Auto-run benchmark runner to collect current system stats
            from benchmark_runner import BenchmarkRunner
            runner = BenchmarkRunner(qubo_enabled=True)
            results = runner.run_all()
            total_ops = sum(r.hybrid.total_shuttle_ops for r in results if r.hybrid.success)
            total_time = sum(r.hybrid.compile_time_s for r in results)
            triggers = sum(r.hybrid.qubo_triggers for r in results)
            tracker.record_run(
                label=args.record,
                total_shuttle_ops=total_ops,
                total_compile_time_s=total_time,
                total_qubo_triggers=triggers,
                circuits_tested=len(results),
            )
        if len(tracker.load_history()) >= 2:
            tracker.plot_history()

    elif args.compare:
        tracker.compare_runs(args.compare[0], args.compare[1])

    elif args.plot:
        tracker.plot_history()

    else:
        tracker.print_history()


if __name__ == "__main__":
    main()
