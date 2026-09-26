"""
Right now CongestionHandler is a stub (Chaitanya's real module isn't
merged yet), so this test only checks the *contract* the rest of the
codebase depends on: given a path and a Placement, it returns a path
of the same shape unmodified. Once the real resolver lands, extend
this file with cases that actually create a collision (two qudits
whose paths cross the same segment) and assert it re-routes one of
them instead of returning the path as-is.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from congestion_handler import CongestionHandler
from position_graph import Placement, build_linear_qccd


def test_stub_returns_path_unchanged():
    pg = build_linear_qccd(num_traps=3, trap_capacity=2)
    placement = Placement(pg)
    placement.place(0, pg.slots_of("t0")[0])
    placement.place(1, pg.slots_of("t2")[0])

    path = pg.shortest_path(pg.slots_of("t0")[0], pg.slots_of("t2")[0])

    handler = CongestionHandler()
    result = handler.resolve_path_congestion(path, placement)

    assert result == path  # stub: pass-through, no resolution logic yet


if __name__ == "__main__":
    test_stub_returns_path_unchanged()
    print("congestion_handler: all tests passed")