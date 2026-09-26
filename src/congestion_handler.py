"""
# TODO: Replace with Chaitanya's module (congestion resolution)

Placeholder for resolving path blockages using search-depth
backtracking or local QUBO optimization over contested path segments.

Signature is written against Pavan's real position_graph.py:
  - a "path" is a list of position-id strings (as returned by
    PositionGraph.shortest_path)
  - occupancy is read via a Placement instance (Placement.occupant_of /
    Placement.is_occupied), not a plain dict

This mock does no actual resolution: it logs "Path clear" and returns
the path unmodified. Chaitanya's real version will inspect `placement`
for positions along `path` that are already occupied by a different
qudit and either re-route around them or resolve the contested
junction via a local QUBO solve.
"""

from __future__ import annotations

import logging
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from position_graph import Placement

logger = logging.getLogger("shaw_router.congestion")


# TODO: Replace with Chaitanya's module
class CongestionHandler:
    def resolve_path_congestion(
        self,
        path: List[str],
        placement: "Placement",
    ) -> List[str]:
        """
        Dummy congestion resolution: pass the path through unchanged.

        Real version: walk `path`, use `placement.occupant_of(pos)` to
        find contested positions, and return a re-routed path (or
        trigger a local QUBO solve) when a collision is found.
        """
        logger.info("Path clear")
        return path