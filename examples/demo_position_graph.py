"""
examples/demo_position_graph.py
================================
Demonstration of the Position Graph (G_p = (V, E, ψ)) abstraction.

Run from the project root:
    python examples/demo_position_graph.py

Demonstrates:
  1. Building a LinearChain, Grid, and Junction architecture.
  2. Placing ions and checking occupancy.
  3. Computing shortest-path P and blockage set B(P).
  4. Computing the contention metric κ.
  5. Extracting a local congestion window W.
  6. Serialising/deserialising the graph.
  7. Drawing the graph (requires matplotlib).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure Unicode output (→, ×, κ, …) works on Windows consoles that
# default to cp1252. Safe no-op on UTF-8 systems / when redirected.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    try:
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
del _stream_name, _stream

from qccd import (
    NodeType, EdgeOperation, PositionNode, PositionGraph,
    LinearChainArchitecture, GridArchitecture, JunctionArchitecture,
)


# ── Separator helper ──────────────────────────────────────────────────────────
SEP = "-" * 60

def section(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


# =============================================================================
# 1. Build architectures
# =============================================================================
section("1. Architecture Factories")

linear = LinearChainArchitecture.build(n_traps=6)
print(f"LinearChain : {linear}")

grid = GridArchitecture.build(rows=3, cols=3)
print(f"Grid 3×3    : {grid}")

cross = JunctionArchitecture.build(arm_length=2)
print(f"Junction    : {cross}")


# =============================================================================
# 2. Place ions and inspect occupancy
# =============================================================================
section("2. Ion Placement & Occupancy")

pg = LinearChainArchitecture.build(n_traps=5)

ions = {"q0": "T0", "q1": "T2", "q_blocker": "C1_2"}
for ion, pos in ions.items():
    pg.place_ion(ion, pos)
    print(f"  Placed {ion!r:12s} at {pos!r}")

print()
for node in pg:
    if node.is_occupied():
        print(f"  {node}")


# =============================================================================
# 3. Shortest path and blockage detection B(P)
# =============================================================================
section("3. Shortest Path  P  &  Blockage Set  B(P)")

path = pg.shortest_path("T0", "T4")
print(f"  P(T0 → T4)  = {path}")

blocked = pg.blocked_positions(path)
print(f"  B(P)        = {blocked}")

clear = pg.is_path_clear(path)
print(f"  Path clear? = {clear}")

if blocked:
    print("  → Path is BLOCKED; heuristic / QUBO resolution required.")
else:
    print("  → Path is CLEAR; movement proceeds normally.")


# =============================================================================
# 4. Contention metric κ
# =============================================================================
section("4. Contention  κ")

kappa_global = pg.contention()
print(f"  κ (global)          = {kappa_global:.3f}")

local_region = ["T1", "C1_2", "T2"]
kappa_local = pg.contention(local_region)
print(f"  κ ({local_region})  = {kappa_local:.3f}")


# =============================================================================
# 5. Local congestion window W
# =============================================================================
section("5. Congestion Window  W")

window = pg.subgraph_window(center_nodes=["C1_2"], radius=2)
print(f"  Window around 'C1_2' (radius=2): {window}")
print(f"  Window nodes: {window.node_ids()}")
print(f"  κ inside W: {window.contention():.3f}")


# =============================================================================
# 6. Ion movement and validation
# =============================================================================
section("6. Ion Movement (legal check)")

print("  Before: q_blocker at", pg.ion_location("q_blocker"))
try:
    pg.move_ion("q_blocker", "C1_2", "T2")
    print("  After:  q_blocker at", pg.ion_location("q_blocker"))
except ValueError as e:
    print(f"  Movement blocked: {e}")

# Now the path should be clear
blocked_after = pg.blocked_positions(path)
print(f"  B(P) after move: {blocked_after}")
print(f"  Path clear?      {pg.is_path_clear(path)}")


# =============================================================================
# 7. Serialisation round-trip
# =============================================================================
section("7. Serialisation (to_dict / from_dict)")

data = pg.to_dict()
restored = PositionGraph.from_dict(data)
print(f"  Original : {pg}")
print(f"  Restored : {restored}")
assert pg.shortest_path("T0", "T4") == restored.shortest_path("T0", "T4")
print("  Shortest-path round-trip: ✓")


# =============================================================================
# 8. Grid shortest path and window
# =============================================================================
section("8. Grid Architecture — path across the grid")

g = GridArchitecture.build(rows=4, cols=4)
g.place_ion("src_ion",   (0, 0))
g.place_ion("dst_ion",   (3, 3))
g.place_ion("blocker_a", ("V", 0, 1))
g.place_ion("blocker_b", ("H", 1, 1))

path_g = g.shortest_path((0, 0), (3, 3))
print(f"  P((0,0) → (3,3)) = {path_g}")
blocked_g = g.blocked_positions(path_g)
print(f"  B(P) = {blocked_g}")
kappa_g = g.contention()
print(f"  κ (global, {len(g)} nodes) = {kappa_g:.3f}")


# =============================================================================
# 9. Draw (optional — requires matplotlib)
# =============================================================================
section("9. Visualisation (requires matplotlib)")

try:
    import matplotlib
    matplotlib.use("Agg")           # non-interactive for headless environments
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    pg_draw = LinearChainArchitecture.build(n_traps=5)
    pg_draw.place_ion("q0", "T0")
    pg_draw.place_ion("blocker", "C1_2")
    pg_draw.draw(ax=axes[0], title="LinearChain (occupancy)")

    grid_draw = GridArchitecture.build(rows=3, cols=3)
    grid_draw.place_ion("q0", (1, 1))
    grid_draw.draw(ax=axes[1], title="Grid 3×3 (occupancy)")

    cross_draw = JunctionArchitecture.build(arm_length=1)
    cross_draw.place_ion("q0", "C_left_1")
    cross_draw.draw(ax=axes[2], title="Junction (occupancy)")

    out_path = os.path.join(os.path.dirname(__file__), "position_graph_demo.png")
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"  Saved figure → {out_path}")
    plt.close(fig)
except ImportError:
    print("  matplotlib not available; skipping visualisation.")

print(f"\n{SEP}\n  Demo complete.\n{SEP}\n")
