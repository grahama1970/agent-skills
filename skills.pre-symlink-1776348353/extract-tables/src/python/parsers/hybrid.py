"""Hybrid parser -- combines lattice and network parsers.

Runs lattice first for bordered regions, then network for remaining areas.
Deduplicates overlapping tables.

All output bboxes use top-left origin: (x0, y0_top, x1, y1_bottom) where y=0 is top.
"""
from __future__ import annotations

from typing import Optional

from ..models import Table
from .lattice import LatticeParser
from .network import NetworkParser


def _bbox_iou(a: tuple, b: tuple) -> float:
    """Compute Intersection over Union of two bboxes (top-left origin).

    Each bbox is (x0, y0_top, x1, y1_bottom).
    """
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])

    if x1 <= x0 or y1 <= y0:
        return 0.0

    inter = (x1 - x0) * (y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


class HybridParser:
    """Extract tables by running lattice first, then network for remaining areas.

    Pipeline:
    1. Run lattice parser (detects bordered tables with visible gridlines)
    2. Run network parser (detects all tables including borderless)
    3. Deduplicate: remove network tables that overlap significantly with lattice tables
    4. Merge results, sorted by reading order

    Parameters
    ----------
    iou_threshold : float
        IoU threshold above which a network table is considered a duplicate
        of a lattice table and is discarded. Default 0.3.
    lattice_kwargs : dict, optional
        Extra kwargs passed to LatticeParser constructor.
    network_kwargs : dict, optional
        Extra kwargs passed to NetworkParser constructor.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        lattice_kwargs: Optional[dict] = None,
        network_kwargs: Optional[dict] = None,
    ):
        self.iou_threshold = iou_threshold
        self._lattice = LatticeParser(**(lattice_kwargs or {}))
        self._network = NetworkParser(**(network_kwargs or {}))

    def extract_tables(
        self,
        pdf_path: str,
        page_num: int,
        password: Optional[str] = None,
        **params,
    ) -> list[Table]:
        """Extract tables using lattice first, then network for remaining areas.

        Parameters
        ----------
        pdf_path : str
            Path to the PDF file.
        page_num : int
            0-indexed page number.
        password : str, optional
            PDF password if encrypted.

        Returns
        -------
        list[Table]
            Deduplicated list of tables sorted by reading order (top-to-bottom,
            left-to-right). Each table's ``strategy`` is either ``'lattice'``
            or ``'hybrid'`` (for network-detected tables kept after dedup).
        """
        iou_threshold = params.pop("iou_threshold", self.iou_threshold)

        # 1. Run lattice parser (bordered tables)
        lattice_tables = self._lattice.extract_tables(
            pdf_path, page_num, password=password, **params
        )

        # 2. Run network parser (all tables including borderless)
        network_tables = self._network.extract_tables(
            pdf_path, page_num, password=password, **params
        )

        # 3. Keep all lattice tables; add non-overlapping network tables
        result: list[Table] = list(lattice_tables)

        for nt in network_tables:
            overlaps = any(
                _bbox_iou(nt.bbox, lt.bbox) > iou_threshold
                for lt in lattice_tables
            )
            if not overlaps:
                # Mark strategy as hybrid for network tables kept via this path
                nt.strategy = "hybrid"
                result.append(nt)

        # 4. Sort by reading order (top-to-bottom, then left-to-right)
        result.sort(key=lambda t: (t.bbox[1], t.bbox[0]))

        return result
