"""
test_benchmark_runner.py

Unit tests for BenchmarkRunner (Person 4's module).
Validates baseline and hybrid routing runners, metric gathering,
comparison logic, and CSV/plotting utilities.

Run with: pytest tests/test_benchmark_runner.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_runner import BenchmarkRunner, ComparisonResult, RunMetrics
from bqskit.ir.circuit import Circuit
from bqskit.ir.gates import CNOTGate, HGate


def _make_test_circuit():
    c = Circuit(4)
    c.append_gate(HGate(), (0,))
    c.append_gate(CNOTGate(), (0, 3))
    c.append_gate(CNOTGate(), (1, 2))
    return c


def test_runner_initialization():
    runner = BenchmarkRunner(qubo_enabled=True, kappa_threshold=0.6, rho_threshold=0.4)
    assert runner.qubo_enabled is True
    assert runner.kappa_threshold == 0.6
    assert runner.rho_threshold == 0.4


@pytest.mark.xfail(reason="Not yet implemented by Person 4", strict=False)
def test_run_baseline_metrics():
    runner = BenchmarkRunner()
    circuit = _make_test_circuit()
    metrics = runner.run_baseline("test_4q", circuit)
    assert isinstance(metrics, RunMetrics)
    assert metrics.mode == "baseline"
    assert metrics.success is True
    assert metrics.total_shuttle_ops >= 0


@pytest.mark.xfail(reason="Not yet implemented by Person 4", strict=False)
def test_compare_baseline_vs_hybrid():
    runner = BenchmarkRunner()
    b_metrics = RunMetrics(
        circuit_name="test", mode="baseline", num_qudits=4, num_gates_original=3,
        total_shuttle_ops=10, swap_count=1, compile_time_s=0.05,
        congestion_events=2, qubo_triggers=0, qubo_accepted=0, qubo_acceptance_rate=0.0,
        kappa_mean=0.5, rho_mean=0.2, depth_mean=1.0, routing_cost_improvement=0.0,
        success=True,
    )
    h_metrics = RunMetrics(
        circuit_name="test", mode="hybrid_qubo", num_qudits=4, num_gates_original=3,
        total_shuttle_ops=8, swap_count=1, compile_time_s=0.08,
        congestion_events=2, qubo_triggers=1, qubo_accepted=1, qubo_acceptance_rate=1.0,
        kappa_mean=0.5, rho_mean=0.2, depth_mean=1.0, routing_cost_improvement=0.2,
        success=True,
    )
    comp = runner.compare(b_metrics, h_metrics)
    assert isinstance(comp, ComparisonResult)
    assert comp.verdict == "qubo_wins"
    assert comp.shuttle_improvement == 0.2


if __name__ == "__main__":
    print("test_benchmark_runner.py: placeholder tests loaded.")
    print("Implement BenchmarkRunner (Person 4), then run: pytest tests/test_benchmark_runner.py")
