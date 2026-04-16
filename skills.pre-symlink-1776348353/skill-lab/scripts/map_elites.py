#!/usr/bin/env python3
"""MAP-Elites archive — Quality-Diversity search for skill compositions.

Instead of optimizing for a single best composition, MAP-Elites maintains
a 2D archive grid indexed by (energy_cost, quality). Each cell holds the
best composition for that behavioral region, giving a diverse repertoire
of solutions.

Reference: Mouret & Clune, "Illuminating search spaces by mapping elites"
           https://arxiv.org/abs/1504.04909

Usage:
    from map_elites import MAPElitesArchive
    archive = MAPElitesArchive.load_or_create()
    archive.try_insert(chain, energy, quality, elegance, metadata)
    archive.save()
    repertoire = archive.get_repertoire()
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

ARCHIVE_FILE = STATE_DIR / "map_elites_archive.json"

# Grid dimensions
ENERGY_BINS = 10   # 0-15 ATP range, 1.5 ATP per bin
QUALITY_BINS = 10  # 0.0-1.0 range, 0.1 per bin
MAX_ENERGY = 15.0
MAX_QUALITY = 1.0


@dataclass
class ArchiveCell:
    """A single cell in the MAP-Elites archive."""
    chain: list[str]
    energy: float
    quality: float
    elegance_score: float
    elegance_grade: str
    metadata: dict = field(default_factory=dict)
    inserted_at: float = 0.0

    def fitness(self) -> float:
        """Primary fitness for cell replacement decisions."""
        return self.elegance_score


@dataclass
class MAPElitesArchive:
    """2D archive grid indexed by (energy_cost, quality).

    Each cell stores the best composition found for that region.
    The archive "illuminates" the search space by maintaining diverse
    high-quality solutions across the energy-quality landscape.
    """
    grid: dict[str, ArchiveCell] = field(default_factory=dict)
    total_insertions: int = 0
    total_attempts: int = 0
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def _bin_key(energy: float, quality: float) -> str:
        """Convert continuous (energy, quality) to discrete grid cell key."""
        e_bin = min(ENERGY_BINS - 1, max(0, int(energy / MAX_ENERGY * ENERGY_BINS)))
        q_bin = min(QUALITY_BINS - 1, max(0, int(quality / MAX_QUALITY * QUALITY_BINS)))
        return f"{e_bin}:{q_bin}"

    def try_insert(
        self,
        chain: list[str],
        energy: float,
        quality: float,
        elegance_score: float,
        elegance_grade: str,
        metadata: dict | None = None,
    ) -> bool:
        """Try to insert a composition into the archive.

        Returns True if inserted (cell was empty or new fitness is higher).
        """
        self.total_attempts += 1
        key = self._bin_key(energy, quality)

        cell = ArchiveCell(
            chain=chain,
            energy=energy,
            quality=quality,
            elegance_score=elegance_score,
            elegance_grade=elegance_grade,
            metadata=metadata or {},
            inserted_at=time.time(),
        )

        existing = self.grid.get(key)
        if existing is None or cell.fitness() > existing.fitness():
            self.grid[key] = cell
            self.total_insertions += 1
            return True
        return False

    def get_repertoire(self) -> list[ArchiveCell]:
        """Return all compositions in the archive, sorted by fitness."""
        return sorted(self.grid.values(), key=lambda c: c.fitness(), reverse=True)

    def get_pareto_front(self) -> list[ArchiveCell]:
        """Return non-dominated compositions (Pareto front).

        A composition is non-dominated if no other composition is
        better on BOTH quality AND energy efficiency (lower energy).
        """
        cells = list(self.grid.values())
        pareto: list[ArchiveCell] = []
        for c in cells:
            dominated = False
            for other in cells:
                if other is c:
                    continue
                # other dominates c if better on both objectives
                if other.quality >= c.quality and other.energy <= c.energy:
                    if other.quality > c.quality or other.energy < c.energy:
                        dominated = True
                        break
            if not dominated:
                pareto.append(c)
        return sorted(pareto, key=lambda c: c.quality, reverse=True)

    def coverage(self) -> float:
        """Fraction of grid cells that are occupied."""
        total_cells = ENERGY_BINS * QUALITY_BINS
        return len(self.grid) / total_cells

    def stats(self) -> dict[str, Any]:
        """Summary statistics for the archive."""
        cells = list(self.grid.values())
        if not cells:
            return {
                "occupied_cells": 0,
                "total_cells": ENERGY_BINS * QUALITY_BINS,
                "coverage": 0.0,
                "total_attempts": self.total_attempts,
                "total_insertions": self.total_insertions,
            }
        fitnesses = [c.fitness() for c in cells]
        return {
            "occupied_cells": len(cells),
            "total_cells": ENERGY_BINS * QUALITY_BINS,
            "coverage": round(self.coverage(), 4),
            "total_attempts": self.total_attempts,
            "total_insertions": self.total_insertions,
            "best_fitness": round(max(fitnesses), 4),
            "avg_fitness": round(sum(fitnesses) / len(fitnesses), 4),
            "pareto_front_size": len(self.get_pareto_front()),
        }

    def save(self, path: Path | None = None) -> None:
        """Persist archive to JSON."""
        path = path or ARCHIVE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_insertions": self.total_insertions,
            "total_attempts": self.total_attempts,
            "created_at": self.created_at,
            "grid": {k: asdict(v) for k, v in self.grid.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load_or_create(cls, path: Path | None = None) -> MAPElitesArchive:
        """Load existing archive or create a new one."""
        path = path or ARCHIVE_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            archive = cls(
                total_insertions=data.get("total_insertions", 0),
                total_attempts=data.get("total_attempts", 0),
                created_at=data.get("created_at", time.time()),
            )
            for key, cell_data in data.get("grid", {}).items():
                archive.grid[key] = ArchiveCell(**cell_data)
            return archive
        except (json.JSONDecodeError, OSError, TypeError):
            return cls()
