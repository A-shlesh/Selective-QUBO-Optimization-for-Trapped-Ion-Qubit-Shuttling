"""
conftest.py
===========
Pytest configuration & automatic experiment tracking plugin.

Whenever `pytest` is executed, this hook automatically:
  1. Measures test suite execution time & success metrics.
  2. Records an Experiment Snapshot into `experiments/results/experiment_history.json`.
  3. Updates trend graphs in `experiments/plots/system_iteration_trend.png`.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

session_start_time = 0.0


def pytest_sessionstart(session):
    global session_start_time
    session_start_time = time.perf_counter()


def pytest_sessionfinish(session, exitstatus):
    global session_start_time
    elapsed = time.perf_counter() - session_start_time

    # Collect test stats
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return

    passed = len(reporter.stats.get("passed", []))
    failed = len(reporter.stats.get("failed", []))
    xpassed = len(reporter.stats.get("xpass", []))
    total_tests = passed + failed + xpassed

    if total_tests == 0:
        return

    try:
        from experiment_tracker import ExperimentTracker
        tracker = ExperimentTracker()

        label = f"pytest run ({passed}/{total_tests} passed)"
        tracker.record_run(
            label=label,
            total_shuttle_ops=0,  # Will be populated when running full benchmark suite
            total_compile_time_s=elapsed,
            circuits_tested=total_tests,
            custom_metrics={
                "tests_passed": float(passed),
                "tests_failed": float(failed),
                "pass_rate_pct": round((passed / total_tests) * 100, 1) if total_tests else 0.0,
            }
        )
        if len(tracker.load_history()) >= 2:
            tracker.plot_history()

    except Exception as exc:
        print(f"\n[ExperimentTracker] Auto-logging note: {exc}")
