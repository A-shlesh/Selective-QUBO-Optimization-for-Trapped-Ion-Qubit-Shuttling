import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bqskit.ir.circuit import Circuit
from bqskit.ir.gates import CNOTGate, HGate

from circuit_dag import CircuitDAG


def test_single_qudit_gate_has_no_dependencies():
    c = Circuit(1)
    c.append_gate(HGate(), (0,))
    dag = CircuitDAG(c)
    assert dag.initial_front_layer() == [0]


def test_two_qudit_gate_dependency_chain():
    # CNOT(0,1) must happen before CNOT(1,2), since qudit 1 is shared.
    c = Circuit(3)
    c.append_gate(CNOTGate(), (0, 1))
    c.append_gate(CNOTGate(), (1, 2))

    dag = CircuitDAG(c)
    front = dag.initial_front_layer()

    assert front == [0]  # only the first gate is ready
    newly_ready = dag.mark_executed(0)
    assert newly_ready == [1]  # second gate becomes ready after the first


def test_independent_gates_are_both_in_front_layer():
    c = Circuit(4)
    c.append_gate(CNOTGate(), (0, 1))
    c.append_gate(CNOTGate(), (2, 3))

    dag = CircuitDAG(c)
    front = set(dag.initial_front_layer())
    assert front == {0, 1}


if __name__ == "__main__":
    test_single_qudit_gate_has_no_dependencies()
    test_two_qudit_gate_dependency_chain()
    test_independent_gates_are_both_in_front_layer()
    print("circuit_dag: all tests passed")