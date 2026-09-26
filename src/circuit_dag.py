"""
Builds a dependency DAG from a BQSKit Circuit by walking each qudit's
operation sequence in program order. Two gates are dependent if they
share a qudit and one appears after the other on that qudit's
timeline. This is the standard construction used by SWAP-based
routers (SABRE-style) to compute "front layers" -- gates whose
dependencies are all satisfied and are therefore ready to execute.
 
This module is generic: it only depends on bqskit.ir, not on the
Position Graph / SHAW-specific routing logic in shaw_routing_pass.py.
That's deliberate -- it's reusable on its own and independently
testable (see tests/test_circuit_dag.py).
"""
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
 
from bqskit.ir.circuit import Circuit
from bqskit.ir.operation import Operation
 
 
@dataclass
class DAGNode:
    """Wraps a single BQSKit Operation with its DAG edges."""
    op_id: int
    operation: Operation
    qudits: Tuple[int, ...]
    predecessors: List[int] = field(default_factory=list)
    successors: List[int] = field(default_factory=list)
    unresolved_preds: int = 0
 
 
class CircuitDAG:
    """Dependency DAG over a circuit's operations, plus front-layer
    bookkeeping (which gates are ready to execute right now)."""
 
    def __init__(self, circuit: Circuit) -> None:
        self.nodes: Dict[int, DAGNode] = {}
        self._build(circuit)
 
    def _build(self, circuit: Circuit) -> None:
        # Track the last operation seen on each qudit so we can wire
        # up predecessor/successor edges as we scan the circuit.
        last_op_on_qudit: Dict[int, int] = {}
 
        for op_id, op in enumerate(circuit.operations()):
            qudits: Tuple[int, ...] = tuple(op.location)
            node = DAGNode(op_id=op_id, operation=op, qudits=qudits)
            self.nodes[op_id] = node
 
            for q in qudits:
                pred_id = last_op_on_qudit.get(q)
                if pred_id is not None and pred_id != op_id:
                    self.nodes[pred_id].successors.append(op_id)
                    node.predecessors.append(pred_id)
                last_op_on_qudit[q] = op_id
 
        for node in self.nodes.values():
            node.unresolved_preds = len(node.predecessors)
 
    def initial_front_layer(self) -> List[int]:
        """Gates with no unresolved predecessors are ready immediately."""
        return [n.op_id for n in self.nodes.values() if n.unresolved_preds == 0]
 
    def mark_executed(self, op_id: int) -> List[int]:
        """
        Mark a gate as executed and return any successor gates that
        just became ready (i.e. all of their predecessors are done).
        """
        newly_ready = []
        for succ_id in self.nodes[op_id].successors:
            succ = self.nodes[succ_id]
            succ.unresolved_preds -= 1
            if succ.unresolved_preds == 0:
                newly_ready.append(succ_id)
        return newly_ready
 
    def program_order(self) -> List[int]:
        """op_ids in the order the circuit originally listed them --
        used as the source list for lookahead-window construction."""
        return list(self.nodes.keys())
 
