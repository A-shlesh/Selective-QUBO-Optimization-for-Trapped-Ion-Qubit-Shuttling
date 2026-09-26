"""
position_graph.py
=================
Implements the Position Graph abstraction for QCCD (Quantum Charge-Coupled
Device) trapped-ion architectures, as defined in the methodology:

    G_p = (V, E, ψ)

where
  V  – physical ion positions (nodes),
  E  – legal transitions between positions (edges),
  ψ  – movement or interaction operation associated with each edge.

The module provides:
  * NodeType   – enumeration of vertex roles (trap, junction, channel, …)
  * EdgeOperation – enumeration of ψ values (shuttle, merge, split, interact)
  * PositionNode  – typed vertex with capacity and occupancy tracking
  * PositionGraph – core graph class built on top of networkx.DiGraph

It also ships three ready-made architecture factories:
  * LinearChainArchitecture – a single linear ion trap with channel nodes
  * GridArchitecture        – a 2-D grid of traps joined by junction/channel
                              nodes (suitable for the QCCD 2-D model)
  * JunctionArchitecture    – H-shaped / cross-shaped single-junction layout
                              (baseline for small benchmarks)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple

import networkx as nx


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class NodeType(enum.Enum):
    """Roles that a physical position can play in a QCCD architecture."""

    TRAP = "trap"         # Storage or interaction trap (can hold multiple ions)
    JUNCTION = "junction" # Routing junction (allows path bifurcation)
    CHANNEL = "channel"   # Linear transport channel between traps/junctions


class EdgeOperation(enum.Enum):
    """
    ψ : E → {shuttle, merge, split, interact}

    Legal movement / interaction associated with each directed edge.
    """

    SHUTTLE = "shuttle"   # Transport a single ion along a channel segment
    MERGE = "merge"       # Move ions together into the same trap zone
    SPLIT = "split"       # Separate ions from a trap zone
    INTERACT = "interact" # Two-qubit gate interaction within the same trap


# ---------------------------------------------------------------------------
# PositionNode dataclass
# ---------------------------------------------------------------------------

@dataclass
class PositionNode:
    """
    A vertex v ∈ V of the Position Graph G_p.

    Attributes
    ----------
    node_id : int | str
        Unique identifier for this position.
    node_type : NodeType
        Role of the position (trap / junction / channel).
    capacity : int
        Maximum number of ions this position can hold simultaneously.
        *  TRAP      → typically 2 (for a two-qubit gate zone)
        *  JUNCTION  → 1 (ion passes through; not stored)
        *  CHANNEL   → 1 (single-file transport)
    coords : tuple[float, float], optional
        Physical 2-D coordinates (x, y) for visualisation.
    metadata : dict
        Arbitrary extra attributes (e.g. gate zone label, laser access, …).
    """

    node_id: Any
    node_type: NodeType
    capacity: int = 1
    coords: Optional[Tuple[float, float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Runtime occupancy (mutable state; NOT part of the graph topology)
    # ------------------------------------------------------------------
    _occupants: Set[Any] = field(default_factory=set, init=False, repr=False)

    # --- occupancy helpers --------------------------------------------

    def is_occupied(self) -> bool:
        """Return True if at least one ion occupies this position."""
        return len(self._occupants) > 0

    @property
    def occupancy(self) -> int:
        """Number of ions currently at this position."""
        return len(self._occupants)

    def has_capacity(self) -> bool:
        """Return True if another ion can be placed here."""
        return len(self._occupants) < self.capacity

    def place_ion(self, ion_id: Any) -> None:
        """
        Place *ion_id* at this position.

        Raises
        ------
        ValueError
            If the position is already at full capacity.
        """
        if len(self._occupants) >= self.capacity:
            raise ValueError(
                f"Position {self.node_id!r} is at full capacity "
                f"({self.capacity}); cannot place ion {ion_id!r}."
            )
        self._occupants.add(ion_id)

    def remove_ion(self, ion_id: Any) -> None:
        """
        Remove *ion_id* from this position.

        Raises
        ------
        KeyError
            If the ion is not present at this position.
        """
        if ion_id not in self._occupants:
            raise KeyError(
                f"Ion {ion_id!r} is not at position {self.node_id!r}."
            )
        self._occupants.discard(ion_id)

    def get_occupants(self) -> FrozenSet[Any]:
        """Return the (immutable) set of ion IDs currently at this node."""
        return frozenset(self._occupants)

    def clear_occupants(self) -> None:
        """Remove all ions from this position (used for state reset)."""
        self._occupants.clear()

    def __repr__(self) -> str:
        return (
            f"PositionNode(id={self.node_id!r}, type={self.node_type.value}, "
            f"cap={self.capacity}, occ={self.occupancy})"
        )


# ---------------------------------------------------------------------------
# PositionGraph
# ---------------------------------------------------------------------------

class PositionGraph:
    """
    The Position Graph  G_p = (V, E, ψ)  for a QCCD architecture.

    Backed by a *directed* NetworkX graph so that asymmetric movement
    costs or one-way transport sections can be modelled if needed.
    By default, ``add_edge`` inserts *both* directions (bidirectional
    transport), but the user may call ``add_directed_edge`` for one-way
    edges.

    Parameters
    ----------
    name : str
        Human-readable label for the architecture (e.g. "LinearChain-10").

    Key methods
    -----------
    add_node(node)          – register a PositionNode
    add_edge(...)           – add a *bidirectional* transport edge
    add_directed_edge(...)  – add a *unidirectional* edge
    shortest_path(src, dst) – Dijkstra shortest path (hop count)
    shortest_path_length(src, dst)
    blocked_positions(path) – B(P) = {v ∈ P | occ(v) = 1}
    subgraph_window(nodes)  – extract a local congestion window W
    place_ion(ion, node)    – update occupancy
    move_ion(ion, src, dst) – validate legality and update occupancy
    reset_occupancy()       – clear all ion placements
    to_dict() / from_dict() – (de)serialise the graph topology
    draw()                  – visualise with matplotlib
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, name: str = "PositionGraph") -> None:
        self.name = name
        # Internal directed graph.  Node attribute "data" holds PositionNode.
        self._graph: nx.DiGraph = nx.DiGraph()
        # Fast lookup: node_id → PositionNode
        self._nodes: Dict[Any, PositionNode] = {}

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_node(self, node: PositionNode) -> None:
        """
        Register *node* in the graph.

        Raises
        ------
        ValueError
            If a node with the same ``node_id`` already exists.
        """
        if node.node_id in self._nodes:
            raise ValueError(
                f"Node {node.node_id!r} already exists in the graph."
            )
        self._nodes[node.node_id] = node
        self._graph.add_node(node.node_id, data=node)

    def get_node(self, node_id: Any) -> PositionNode:
        """Return the PositionNode for *node_id*."""
        try:
            return self._nodes[node_id]
        except KeyError:
            raise KeyError(f"Node {node_id!r} not found in PositionGraph.")

    def nodes(self) -> List[PositionNode]:
        """Return all PositionNodes in insertion order."""
        return list(self._nodes.values())

    def node_ids(self) -> List[Any]:
        """Return all node IDs."""
        return list(self._nodes.keys())

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: Any) -> bool:
        return node_id in self._nodes

    def __iter__(self) -> Iterator[PositionNode]:
        return iter(self._nodes.values())

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def add_edge(
        self,
        src_id: Any,
        dst_id: Any,
        operation: EdgeOperation = EdgeOperation.SHUTTLE,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a **bidirectional** edge (src ↔ dst) with the given ψ operation.

        Parameters
        ----------
        src_id, dst_id : node identifiers
        operation : EdgeOperation
            The ψ label for this edge.
        weight : float
            Cost of traversal (used by shortest-path algorithms).
        metadata : dict, optional
            Additional edge attributes.
        """
        self._validate_node_ids(src_id, dst_id)
        attrs = {
            "operation": operation,
            "weight": weight,
            **(metadata or {}),
        }
        self._graph.add_edge(src_id, dst_id, **attrs)
        self._graph.add_edge(dst_id, src_id, **attrs)

    def add_directed_edge(
        self,
        src_id: Any,
        dst_id: Any,
        operation: EdgeOperation = EdgeOperation.SHUTTLE,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a **unidirectional** edge (src → dst)."""
        self._validate_node_ids(src_id, dst_id)
        attrs = {
            "operation": operation,
            "weight": weight,
            **(metadata or {}),
        }
        self._graph.add_edge(src_id, dst_id, **attrs)

    def edges(self) -> List[Tuple[Any, Any, Dict]]:
        """Return list of (src_id, dst_id, attr_dict) tuples."""
        return list(self._graph.edges(data=True))

    def neighbors(self, node_id: Any) -> List[Any]:
        """Return direct successor node IDs for *node_id*."""
        return list(self._graph.successors(node_id))

    # ------------------------------------------------------------------
    # Shortest-path queries
    # ------------------------------------------------------------------

    def shortest_path(
        self,
        src_id: Any,
        dst_id: Any,
        weight: Optional[str] = None,
    ) -> List[Any]:
        """
        Return the shortest path P = {v₁, v₂, …, vₙ} from *src_id* to
        *dst_id* as a list of node IDs.

        Parameters
        ----------
        weight : str or None
            Edge attribute to use as cost.  Pass ``"weight"`` for weighted
            shortest path; ``None`` for hop-count (BFS).

        Raises
        ------
        nx.NetworkXNoPath
            If no path exists between the two nodes.
        """
        self._validate_node_ids(src_id, dst_id)
        return nx.shortest_path(
            self._graph, source=src_id, target=dst_id, weight=weight
        )

    def shortest_path_length(
        self,
        src_id: Any,
        dst_id: Any,
        weight: Optional[str] = None,
    ) -> float:
        """Return the length (hop count or weighted cost) of the shortest path."""
        self._validate_node_ids(src_id, dst_id)
        return nx.shortest_path_length(
            self._graph, source=src_id, target=dst_id, weight=weight
        )

    def all_shortest_paths(
        self,
        src_id: Any,
        dst_id: Any,
    ) -> Iterator[List[Any]]:
        """Yield all hop-count-shortest paths from *src_id* to *dst_id*."""
        self._validate_node_ids(src_id, dst_id)
        return nx.all_shortest_paths(self._graph, source=src_id, target=dst_id)

    # ------------------------------------------------------------------
    # Blockage detection  B(P) = {v ∈ P | occ(v) = 1}
    # ------------------------------------------------------------------

    def blocked_positions(
        self,
        path: List[Any],
        *,
        exclude_endpoints: bool = True,
    ) -> List[Any]:
        """
        Identify occupied intermediate positions along *path*.

        Implements the methodology formula:
            B(P) = {v ∈ P | occ(v) = 1}

        Parameters
        ----------
        path : list of node IDs
            The shuttling path P = {v₁, v₂, …, vₙ}.
        exclude_endpoints : bool
            When True (default), the source (v₁) and destination (vₙ) are
            not checked — only intermediate positions are considered blocked.

        Returns
        -------
        list of node IDs that are currently occupied (blocking ions).
        """
        if exclude_endpoints and len(path) > 2:
            check = path[1:-1]
        else:
            check = path

        return [v for v in check if self._nodes[v].is_occupied()]

    def is_path_clear(
        self,
        path: List[Any],
        *,
        exclude_endpoints: bool = True,
    ) -> bool:
        """
        Return True iff |B(P)| = 0 (no blockages on the path).

        Corresponds to the methodology condition:
            |B(P)| = 0  →  movement proceeds normally.
        """
        return len(self.blocked_positions(path, exclude_endpoints=exclude_endpoints)) == 0

    # ------------------------------------------------------------------
    # Occupancy management
    # ------------------------------------------------------------------

    def place_ion(self, ion_id: Any, node_id: Any) -> None:
        """Place *ion_id* at position *node_id*."""
        self.get_node(node_id).place_ion(ion_id)

    def remove_ion(self, ion_id: Any, node_id: Any) -> None:
        """Remove *ion_id* from position *node_id*."""
        self.get_node(node_id).remove_ion(ion_id)

    def move_ion(self, ion_id: Any, src_id: Any, dst_id: Any) -> None:
        """
        Move *ion_id* along the edge (src_id → dst_id).

        Validates:
          1. The edge exists in G_p  (legal transition).
          2. The destination has capacity.

        Raises
        ------
        ValueError  if the edge does not exist or the destination is full.
        """
        if not self._graph.has_edge(src_id, dst_id):
            raise ValueError(
                f"No legal edge from {src_id!r} to {dst_id!r} in G_p."
            )
        dst_node = self.get_node(dst_id)
        if not dst_node.has_capacity():
            raise ValueError(
                f"Destination {dst_id!r} is at full capacity "
                f"({dst_node.capacity}); cannot move ion {ion_id!r}."
            )
        self.remove_ion(ion_id, src_id)
        self.place_ion(ion_id, dst_id)

    def ion_location(self, ion_id: Any) -> Optional[Any]:
        """
        Return the node_id where *ion_id* currently resides, or None.

        Linear scan — use a mapping layer above if performance matters.
        """
        for nid, node in self._nodes.items():
            if ion_id in node.get_occupants():
                return nid
        return None

    def reset_occupancy(self) -> None:
        """Clear all ion placements (reset to empty architecture)."""
        for node in self._nodes.values():
            node.clear_occupants()

    # ------------------------------------------------------------------
    # Local congestion window  W ⊆ V
    # ------------------------------------------------------------------

    def subgraph_window(
        self,
        center_nodes: List[Any],
        radius: int = 1,
    ) -> "PositionGraph":
        """
        Extract a bounded local window W around *center_nodes*.

        The window includes every node reachable from any center node
        within *radius* hops (using BFS in the undirected projection).

        This implements the methodology step:
            W extracted around the problematic region, |W| ≤ W_max

        Parameters
        ----------
        center_nodes : list of node IDs
        radius : int
            Number of hops to expand around the center.

        Returns
        -------
        PositionGraph
            A new PositionGraph restricted to the window nodes, with
            the same occupancy state as the parent.
        """
        undirected = self._graph.to_undirected()
        window_ids: Set[Any] = set()
        for cn in center_nodes:
            reachable = nx.single_source_shortest_path_length(
                undirected, cn, cutoff=radius
            )
            window_ids.update(reachable.keys())

        sub = PositionGraph(name=f"{self.name}[window]")
        for nid in window_ids:
            src_node = self._nodes[nid]
            new_node = PositionNode(
                node_id=src_node.node_id,
                node_type=src_node.node_type,
                capacity=src_node.capacity,
                coords=src_node.coords,
                metadata=dict(src_node.metadata),
            )
            # Mirror occupancy
            for ion in src_node.get_occupants():
                new_node._occupants.add(ion)
            sub.add_node(new_node)

        for u, v, attrs in self._graph.edges(data=True):
            if u in window_ids and v in window_ids:
                sub._graph.add_edge(u, v, **attrs)

        return sub

    # ------------------------------------------------------------------
    # Contention metric  κ (used by congestion severity stage)
    # ------------------------------------------------------------------

    def contention(self, region_ids: Optional[List[Any]] = None) -> float:
        """
        Compute the local contention metric κ:

            κ = (occupied positions in local region)
                / (total positions in local region)

        Parameters
        ----------
        region_ids : list of node IDs, optional
            The local region.  If None, the entire graph is used.

        Returns
        -------
        float in [0, 1].
        """
        ids = region_ids if region_ids is not None else self.node_ids()
        if not ids:
            return 0.0
        occupied = sum(1 for nid in ids if self._nodes[nid].is_occupied())
        return occupied / len(ids)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the graph topology (no runtime state) to a dict."""
        nodes_data = []
        for node in self._nodes.values():
            nodes_data.append(
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type.value,
                    "capacity": node.capacity,
                    "coords": node.coords,
                    "metadata": node.metadata,
                }
            )

        edges_data = []
        seen = set()
        for u, v, attrs in self._graph.edges(data=True):
            key = (min(str(u), str(v)), max(str(u), str(v)))
            if key not in seen:
                seen.add(key)
                edges_data.append(
                    {
                        "src": u,
                        "dst": v,
                        "operation": attrs["operation"].value,
                        "weight": attrs.get("weight", 1.0),
                    }
                )

        return {"name": self.name, "nodes": nodes_data, "edges": edges_data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionGraph":
        """Reconstruct a PositionGraph from a serialised dict."""
        pg = cls(name=data.get("name", "PositionGraph"))
        for nd in data["nodes"]:
            pg.add_node(
                PositionNode(
                    node_id=nd["node_id"],
                    node_type=NodeType(nd["node_type"]),
                    capacity=nd["capacity"],
                    coords=tuple(nd["coords"]) if nd["coords"] else None,
                    metadata=nd.get("metadata", {}),
                )
            )
        for ed in data["edges"]:
            pg.add_edge(
                ed["src"],
                ed["dst"],
                operation=EdgeOperation(ed["operation"]),
                weight=ed.get("weight", 1.0),
            )
        return pg

    # ------------------------------------------------------------------
    # Visualisation
    # ------------------------------------------------------------------

    def draw(
        self,
        *,
        show_occupancy: bool = True,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
        ax=None,
    ) -> None:
        """
        Draw the Position Graph with matplotlib.

        Node colour encodes type:
          TRAP     → steel blue
          JUNCTION → orange
          CHANNEL  → light grey

        Occupied nodes are outlined in red.

        Parameters
        ----------
        show_occupancy : bool
            Highlight nodes with ion(s) if True.
        figsize : tuple
            Figure size in inches (used only when *ax* is None).
        title : str, optional
            Plot title.  Defaults to ``self.name``.
        ax : matplotlib Axes, optional
            If provided, draw into this Axes object.
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
        except ImportError:
            raise ImportError(
                "matplotlib is required for PositionGraph.draw(). "
                "Install it with: pip install matplotlib"
            )

        _color_map = {
            NodeType.TRAP: "#4682B4",      # SteelBlue
            NodeType.JUNCTION: "#FFA500",  # Orange
            NodeType.CHANNEL: "#D3D3D3",   # LightGrey
        }

        # Use stored coordinates if available, else spring layout
        if all(self._nodes[nid].coords is not None for nid in self._nodes):
            pos = {nid: self._nodes[nid].coords for nid in self._nodes}
        else:
            pos = nx.spring_layout(self._graph, seed=42)

        node_colors = [_color_map[self._nodes[nid].node_type] for nid in self._graph.nodes()]
        node_edge_colors = [
            "red" if (show_occupancy and self._nodes[nid].is_occupied()) else "black"
            for nid in self._graph.nodes()
        ]
        node_edge_widths = [
            3.0 if (show_occupancy and self._nodes[nid].is_occupied()) else 1.0
            for nid in self._graph.nodes()
        ]

        labels = {nid: str(nid) for nid in self._graph.nodes()}

        standalone = ax is None
        if standalone:
            fig, ax = plt.subplots(figsize=figsize)

        nx.draw_networkx(
            self._graph,
            pos=pos,
            ax=ax,
            labels=labels,
            node_color=node_colors,
            edgecolors=node_edge_colors,
            linewidths=node_edge_widths,
            node_size=600,
            font_size=9,
            font_color="white",
            arrows=False,
            edge_color="#555555",
        )

        # Legend
        patches = [
            mpatches.Patch(color=c, label=nt.value.capitalize())
            for nt, c in _color_map.items()
        ]
        if show_occupancy:
            patches.append(
                mpatches.Patch(edgecolor="red", facecolor="white",
                               linewidth=2, label="Occupied")
            )
        ax.legend(handles=patches, loc="upper left", fontsize=8)
        ax.set_title(title or self.name)
        ax.axis("off")

        if standalone:
            plt.tight_layout()
            plt.show()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_node_ids(self, *ids: Any) -> None:
        for nid in ids:
            if nid not in self._nodes:
                raise KeyError(f"Node {nid!r} not found in PositionGraph.")

    def __repr__(self) -> str:
        return (
            f"PositionGraph(name={self.name!r}, "
            f"|V|={len(self._nodes)}, "
            f"|E|={self._graph.number_of_edges()})"
        )


# ---------------------------------------------------------------------------
# Architecture factories
# ---------------------------------------------------------------------------

class LinearChainArchitecture:
    """
    Factory for a single linear chain of *n_traps* traps connected by
    channel nodes.

    Layout:
        T0 ── C ── T1 ── C ── T2 ── … ── T(n-1)

    where T = TRAP, C = CHANNEL.

    Parameters
    ----------
    n_traps : int
        Number of traps (≥ 2).
    trap_capacity : int
        Number of ions each trap can hold (default 2).
    channel_capacity : int
        Number of ions each channel node can hold (default 1).
    """

    @staticmethod
    def build(
        n_traps: int = 5,
        trap_capacity: int = 2,
        channel_capacity: int = 1,
    ) -> PositionGraph:
        if n_traps < 2:
            raise ValueError("LinearChainArchitecture requires at least 2 traps.")

        pg = PositionGraph(name=f"LinearChain-{n_traps}")
        node_ids: List[Any] = []

        # Create nodes: T0, C0_1, T1, C1_2, T2, …
        for i in range(n_traps):
            trap_id = f"T{i}"
            pg.add_node(
                PositionNode(
                    node_id=trap_id,
                    node_type=NodeType.TRAP,
                    capacity=trap_capacity,
                    coords=(i * 2.0, 0.0),
                )
            )
            node_ids.append(trap_id)

            if i < n_traps - 1:
                ch_id = f"C{i}_{i+1}"
                pg.add_node(
                    PositionNode(
                        node_id=ch_id,
                        node_type=NodeType.CHANNEL,
                        capacity=channel_capacity,
                        coords=(i * 2.0 + 1.0, 0.0),
                    )
                )
                node_ids.append(ch_id)

        # Wire edges
        for k in range(len(node_ids) - 1):
            pg.add_edge(node_ids[k], node_ids[k + 1])

        return pg


class GridArchitecture:
    """
    Factory for a 2-D grid of traps connected by channel / junction nodes.

    Each "cell" consists of a TRAP node; cells in the same row are
    connected via CHANNEL nodes, and cells in adjacent rows are connected
    via JUNCTION nodes (at the channel midpoints).

    Parameters
    ----------
    rows, cols : int
        Grid dimensions.
    trap_capacity : int
        Capacity of each trap (default 2).
    """

    @staticmethod
    def build(
        rows: int = 3,
        cols: int = 3,
        trap_capacity: int = 2,
    ) -> PositionGraph:
        if rows < 1 or cols < 1:
            raise ValueError("Grid must have at least 1 row and 1 column.")

        pg = PositionGraph(name=f"Grid-{rows}x{cols}")

        # Add trap nodes
        for r in range(rows):
            for c in range(cols):
                pg.add_node(
                    PositionNode(
                        node_id=(r, c),
                        node_type=NodeType.TRAP,
                        capacity=trap_capacity,
                        coords=(float(c * 2), float(r * 2)),
                    )
                )

        # Horizontal channel nodes and edges
        for r in range(rows):
            for c in range(cols - 1):
                ch_id = ("H", r, c)
                pg.add_node(
                    PositionNode(
                        node_id=ch_id,
                        node_type=NodeType.CHANNEL,
                        capacity=1,
                        coords=(c * 2.0 + 1.0, r * 2.0),
                    )
                )
                pg.add_edge((r, c), ch_id)
                pg.add_edge(ch_id, (r, c + 1))

        # Vertical junction nodes and edges
        for r in range(rows - 1):
            for c in range(cols):
                jn_id = ("V", r, c)
                pg.add_node(
                    PositionNode(
                        node_id=jn_id,
                        node_type=NodeType.JUNCTION,
                        capacity=1,
                        coords=(c * 2.0, r * 2.0 + 1.0),
                    )
                )
                pg.add_edge((r, c), jn_id)
                pg.add_edge(jn_id, (r + 1, c))

        return pg


class JunctionArchitecture:
    """
    Factory for a simple cross / H-shaped QCCD architecture with a
    single central junction — a standard small benchmark topology.

    Layout (7 nodes):

              T_top
                |
        T_left──J──T_right
                |
             T_bottom

    with additional channel nodes on each arm.

    Parameters
    ----------
    arm_length : int
        Number of channel nodes between the junction and each trap (≥ 1).
    trap_capacity : int
        Capacity of each end trap.
    """

    @staticmethod
    def build(
        arm_length: int = 1,
        trap_capacity: int = 2,
    ) -> PositionGraph:
        if arm_length < 1:
            raise ValueError("arm_length must be ≥ 1.")

        pg = PositionGraph(name=f"Junction-arm{arm_length}")

        # Central junction
        pg.add_node(
            PositionNode(
                node_id="J",
                node_type=NodeType.JUNCTION,
                capacity=1,
                coords=(0.0, 0.0),
            )
        )

        directions = {
            "left":   (-1.0,  0.0),
            "right":  ( 1.0,  0.0),
            "top":    ( 0.0,  1.0),
            "bottom": ( 0.0, -1.0),
        }

        for arm, (dx, dy) in directions.items():
            prev_id: Any = "J"
            for k in range(1, arm_length + 1):
                node_id = f"C_{arm}_{k}"
                is_trap = (k == arm_length)
                pg.add_node(
                    PositionNode(
                        node_id=node_id,
                        node_type=NodeType.TRAP if is_trap else NodeType.CHANNEL,
                        capacity=trap_capacity if is_trap else 1,
                        coords=(dx * k, dy * k),
                        metadata={"arm": arm},
                    )
                )
                pg.add_edge(prev_id, node_id)
                prev_id = node_id

        return pg
