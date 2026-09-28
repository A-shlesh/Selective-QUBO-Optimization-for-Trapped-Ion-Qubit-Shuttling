"""
test_solution_decoder.py

Unit tests for SolutionDecoder (Person 3's module).
Tests decoding of QUBOSolution samples, trajectory extraction,
constraint validation checks, and cost-comparison decision logic.

Run with: pytest tests/test_solution_decoder.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from congestion_handler import WindowInfo
from position_graph import Placement, build_linear_qccd
from qubo_formulator import QUBOProblem
from qubo_solver import QUBOSolution
from solution_decoder import DecodedSolution, SolutionDecoder, ValidationResult


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

def _make_dummy_solution(is_feasible: bool = True, energy: float = 1.0):
    dummy_window = WindowInfo(
        window_nodes=frozenset(["t0:0", "seg0", "t1:0"]),
        active_ions={0: "t0:0", 1: "t1:0"},
        obstacle_ions={},
        source="t0:0",
        target="t1:0",
        blocked_path=["seg0"],
        center_nodes=["seg0"],
        radius=1,
        size_capped=False,
    )
    problem = QUBOProblem(
        bqm=None,
        var_map={},
        inv_var_map={},
        num_variables=6,
        num_aux_variables=0,
        time_horizon=2,
        penalty_lambda=10.0,
        window=dummy_window,
    )
    return QUBOSolution(
        sample={},
        energy=energy,
        is_feasible=is_feasible,
        solver_used="exact",
        solve_time_s=0.01,
        num_reads=1,
        problem=problem,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_decoder_initialization():
    decoder = SolutionDecoder(strict_capacity=True)
    assert decoder.strict_capacity is True


def test_reject_when_infeasible():
    solution = _make_dummy_solution(is_feasible=False, energy=100.0)
    pg = build_linear_qccd(num_traps=2, trap_capacity=2)
    pl = Placement(pg)
    pl.place(0, pg.slots_of("t0")[0])

    decoder = SolutionDecoder()
    decoded = decoder.decode_and_validate(solution, pl, pg)
    assert isinstance(decoded, DecodedSolution)
    assert decoded.accepted is False
    assert decoded.violation == "infeasible_energy"


@pytest.mark.xfail(reason="Not yet implemented by Person 3", strict=False)
def test_decode_trajectories_reconstructs_path():
    decoder = SolutionDecoder()
    solution = _make_dummy_solution(is_feasible=True, energy=2.0)
    trajectories = decoder._decode_trajectories(solution)
    assert isinstance(trajectories, dict)


@pytest.mark.xfail(reason="Not yet implemented by Person 3", strict=False)
def test_validation_movement_legality():
    decoder = SolutionDecoder()
    pg = build_linear_qccd(num_traps=3, trap_capacity=2)
    window = _make_dummy_solution().problem.window
    trajectories = {0: ["t0:0", "seg0", "t1:0"]}
    res = decoder._check_movement_legality(trajectories, window, pg)
    assert isinstance(res, ValidationResult)


@pytest.mark.xfail(reason="Not yet implemented by Person 3", strict=False)
def test_cost_comparison_rejection_if_worse():
    """Verify methodology §9: QUBO solution rejected if C_QUBO >= C_heuristic."""
    decoder = SolutionDecoder()
    pg = build_linear_qccd(num_traps=3, trap_capacity=2)
    pl = Placement(pg)
    solution = _make_dummy_solution(is_feasible=True, energy=50.0)
    decoded = decoder.decode_and_validate(solution, pl, pg)
    if decoded.accepted:
        assert decoded.C_QUBO < decoded.C_heuristic


if __name__ == "__main__":
    print("test_solution_decoder.py: placeholder tests loaded.")
    print("Implement SolutionDecoder (Person 3), then run: pytest tests/test_solution_decoder.py")
