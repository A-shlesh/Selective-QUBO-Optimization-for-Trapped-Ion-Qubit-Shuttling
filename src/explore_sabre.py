"""
explore_sabre.py

Goal: build a small circuit, run BQSKit's built-in SABRE layout + routing
passes against a restricted coupling graph, and print out what SABRE
actually does (initial layout, inserted SWAPs, before/after gate counts).

This is a *learning* script -- step 1 of the roadmap -- before we touch
the Position Graph / shuttling-specific logic at all.
"""

from bqskit.ir import Circuit
from bqskit.ir.gates import CNOTGate, HGate, SwapGate
from bqskit.compiler import MachineModel, Compiler, Workflow
from bqskit.passes import (
    GeneralizedSabreLayoutPass,
    GeneralizedSabreRoutingPass,
    SetModelPass,
)


def print_gates(circuit: Circuit, label: str) -> None:
    print(f"-- {label} ({circuit.num_operations} ops) --")
    for op in circuit:
        print(f"  {op.gate.name:>10} @ {op.location}")


def build_toy_circuit(num_qudits: int = 5) -> Circuit:
    """A small circuit with gates between *non-adjacent* logical qudits,
    so SABRE is forced to actually do something interesting."""
    circuit = Circuit(num_qudits)
    circuit.append_gate(HGate(), [0])
    # deliberately "far apart" logical interactions
    circuit.append_gate(CNOTGate(), [0, 4])
    circuit.append_gate(CNOTGate(), [1, 3])
    circuit.append_gate(CNOTGate(), [0, 2])
    circuit.append_gate(CNOTGate(), [2, 4])
    circuit.append_gate(CNOTGate(), [1, 4])
    return circuit


def build_linear_coupling_graph(num_qudits: int) -> list[tuple[int, int]]:
    """A simple line topology: 0-1-2-3-4 (like a minimal trapped-ion-ish
    restricted-connectivity chip). Only neighbors can interact directly."""
    return [(i, i + 1) for i in range(num_qudits - 1)]


def main() -> None:
    num_qudits = 5
    circuit = build_toy_circuit(num_qudits)
    coupling_graph = build_linear_coupling_graph(num_qudits)
    model = MachineModel(num_qudits, coupling_graph=coupling_graph)

    print("=== BEFORE ROUTING ===")
    print(f"Qudits: {num_qudits}")
    print(f"Coupling graph (who can talk to whom): {coupling_graph}")
    print(f"Gate count: {circuit.num_operations}")
    print(f"Two-qudit gate count: {circuit.count(CNOTGate())}")
    print_gates(circuit, "gate list")

    workflow = Workflow([
        SetModelPass(model),
        GeneralizedSabreLayoutPass(),
        GeneralizedSabreRoutingPass(),
    ])

    with Compiler() as compiler:
        routed_circuit = compiler.compile(circuit, workflow)

    print("\n=== AFTER SABRE LAYOUT + ROUTING ===")
    print(f"Gate count: {routed_circuit.num_operations}")
    print(f"Two-qudit gate count: {routed_circuit.count(CNOTGate())}")
    print(f"SWAP gate count: {routed_circuit.count(SwapGate())}")
    print_gates(routed_circuit, "gate list")

    swap_overhead = routed_circuit.num_operations - circuit.num_operations
    print(f"\nExtra operations SABRE inserted (routing overhead): {swap_overhead}")
    print(
        "Note: this SWAP count is exactly the kind of number SHAW replaces "
        "with a *shuttling* move count once we swap in the Position Graph."
    )


if __name__ == "__main__":
    main()