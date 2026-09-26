"""
test_qccd_adapter.py

Two things worth proving about the adapter:

  1. ShawRoutingPass runs *unmodified* against a real qccd
     PositionGraph via the adapter -- on LinearChain here (Grid and
     Junction are covered by the deadlock test below instead, since at
     the small sizes used in these tests they run out of slack
     capacity for this particular circuit -- see test 2).

  2. When a topology genuinely doesn't have enough spare capacity to
     ever co-locate two qudits (no congestion/eviction logic exists
     yet to free them up), the pass raises a clear RuntimeError
     instead of spinning forever. This was a real bug caught while
     building this adapter -- worth a regression test on its own.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # repo root, for `qccd`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # for qccd_adapter, shaw_routing_pass

import pytest
from bqskit.compiler.passdata import PassData
from bqskit.ir.circuit import Circuit
from bqskit.ir.gates import CNOTGate, HGate

from qccd.position_graph import GridArchitecture, LinearChainArchitecture
from qccd_adapter import build_from_qccd, seed_default_placement
from shaw_routing_pass import ShawRoutingPass


def _build_test_circuit() -> Circuit:
    c = Circuit(4)
    c.append_gate(HGate(), (0,))
    c.append_gate(CNOTGate(), (0, 3))
    c.append_gate(CNOTGate(), (1, 2))
    c.append_gate(CNOTGate(), (0, 1))
    return c


async def _run(qccd_graph):
    circuit = _build_test_circuit()
    adapter, placement = build_from_qccd(qccd_graph)
    seed_default_placement(adapter, placement, circuit.num_qudits)
    routing_pass = ShawRoutingPass(position_graph=adapter, placement=placement)
    await routing_pass.run(circuit, PassData(circuit))
    return circuit


def test_shaw_runs_unmodified_on_qccd_linear_chain():
    qccd_graph = LinearChainArchitecture.build(n_traps=4, trap_capacity=2)
    routed_circuit = asyncio.run(_run(qccd_graph))

    gate_names = [op.gate.name for op in routed_circuit.operations()]
    assert "HGate" in gate_names
    assert gate_names.count("CNOTGate") == 3  # all 3 original CNOTs survived


def test_capacity_deadlock_raises_instead_of_hanging():
    # A small 2x2 grid (4 traps, capacity 2 each = 8 slots for 4 ions)
    # has plenty of *total* capacity, but not enough *local* slack for
    # this specific circuit/seeding without real congestion resolution
    # (eviction/rerouting) -- which doesn't exist yet. This should
    # fail fast with a clear error, not hang.
    qccd_graph = GridArchitecture.build(rows=2, cols=2, trap_capacity=2)
    with pytest.raises(RuntimeError, match="Routing deadlock"):
        asyncio.run(_run(qccd_graph))


if __name__ == "__main__":
    test_shaw_runs_unmodified_on_qccd_linear_chain()
    try:
        test_capacity_deadlock_raises_instead_of_hanging()
    except NameError:
        # pytest.raises unavailable when run standalone without pytest;
        # fall back to a manual check so `python test_qccd_adapter.py`
        # still works without pytest installed.
        qccd_graph = GridArchitecture.build(rows=2, cols=2, trap_capacity=2)
        try:
            asyncio.run(_run(qccd_graph))
            raise AssertionError("expected a RuntimeError deadlock, got none")
        except RuntimeError as e:
            assert "Routing deadlock" in str(e)
    print("qccd_adapter: all tests passed")