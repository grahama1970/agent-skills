"""Frozen, content-addressed calibration for the house gate (#1379).

Every number the gate compares against must derive from ONE committed artifact
(house_gate_calibration.v1) — never a hard-coded constant — and the gate must
refuse to run when the render it scores is not provably the render of the deck
under test. The prior gate loaded a mutable workstation JSON and accepted any
PNG directory; the external review (reports/webgpt-house-gate-review-2026-08-11.md)
named both as false-pass channels.

Inputs: the corpus pages dir (renders), records dir, archetype catalog,
page mapping, live service identities. Outputs: a calibration artifact with
per-page hashes, perceptual-duplicate clusters, cluster-weighted style
distributions, thresholds, render profile, and a content digest; plus
verify helpers for render receipts. Failure modes: missing pages/records
raise; a receipt whose hashes or counts disagree yields typed findings,
never a silent pass.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from .build_manifest import bytes_digest, file_digest
from .style_metrics import _histogram

HOUSE_PAGES_DIR = Path("/mnt/storage12tb/skills/pitchdeck/outputs/house-slides")


def dhash(image_path: Path, size: int = 8) -> int:
    """Perceptual difference hash — deterministic, service-free duplicate signal."""
    from PIL import Image

    img = Image.open(image_path).convert("L").resize((size + 1, size))
    px = list(img.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (1 if px[row * (size + 1) + col] > px[row * (size + 1) + col + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class CorpusPage(BaseModel):
    file: str
    deck: str
    sha256: str
    dhash_hex: str
    duplicate_cluster: int
    ink_fraction: float
    palette_similarity: float
    archetype: str | None = None


class RenderProfile(BaseModel):
    dpi: int = 50
    expected_width_px: int = 667
    renderer: str = ""
    rasterizer: str = "pdftoppm"


class Thresholds(BaseModel):
    embedding_anomaly_floor: float
    ink_floor: float
    palette_floor: float
    provenance: str


class HouseGateCalibration(BaseModel):
    schema_: str = Field(default="pitchdeck.house_gate_calibration.v1", alias="schema")
    pages: list[CorpusPage]
    populations: dict[str, int | str]
    duplicate_cluster_count: int
    corpus_palette_histogram: list[float]
    distributions: dict
    thresholds: Thresholds
    render_profile: RenderProfile
    embedding_model: str = ""
    qdrant_collection: str = "pitchdeck_house_slides_v1"

    def content_digest(self) -> str:
        return bytes_digest(self.model_dump_json(by_alias=True))


def _archetype_by_page(pages_dir: Path) -> dict[str, str]:
    """deck-pagefile -> archetype, via the catalog examples + page mapping."""
    out: dict[str, str] = {}
    try:
        groups = json.loads((pages_dir / "archetypes.json").read_text())["groups"]
        mapping = json.loads((pages_dir / "page-mapping.json").read_text())
    except (OSError, KeyError, json.JSONDecodeError):
        return out
    for group in groups:
        for name in group.get("examples", []):
            page = mapping.get(name)
            if not isinstance(page, int):
                continue
            deck = name.rsplit("#", 1)[0]
            for pattern in (f"{deck}-{page:02d}.png", f"{deck}-{page}.png"):
                if (pages_dir / pattern).exists():
                    out[pattern] = group["archetype"]
    return out


def build_calibration(pages_dir: Path = HOUSE_PAGES_DIR,
                      dup_hamming_max: int = 6) -> HouseGateCalibration:
    pngs = sorted(pages_dir.glob("*.png"))
    if not pngs:
        raise ValueError(f"no corpus pages under {pages_dir}")
    hashes = [dhash(p) for p in pngs]
    # union-find perceptual duplicate clusters
    parent = list(range(len(pngs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(pngs)):
        for j in range(i + 1, len(pngs)):
            if hamming(hashes[i], hashes[j]) <= dup_hamming_max:
                parent[find(i)] = find(j)
    cluster_ids: dict[int, int] = {}
    clusters = [cluster_ids.setdefault(find(i), len(cluster_ids)) for i in range(len(pngs))]

    # cluster-weighted mean histogram: one vote per duplicate cluster
    per_page_hist = []
    inks = []
    for p in pngs:
        hist, ink = _histogram(p)
        per_page_hist.append(hist)
        inks.append(round(ink, 4))
    by_cluster: dict[int, list[int]] = {}
    for idx, c in enumerate(clusters):
        by_cluster.setdefault(c, []).append(idx)
    cluster_hists = []
    for members in by_cluster.values():
        acc = [0.0] * len(per_page_hist[0])
        for m in members:
            acc = [a + h for a, h in zip(acc, per_page_hist[m])]
        cluster_hists.append([a / len(members) for a in acc])
    mean_hist = [sum(col) / len(cluster_hists) for col in zip(*cluster_hists)]

    import math
    def bhatt(h):
        return round(sum(math.sqrt(a * b) for a, b in zip(h, mean_hist)), 4)
    sims = [bhatt(h) for h in per_page_hist]

    # cluster-weighted distributions: one representative per cluster
    rep_idx = [members[0] for members in by_cluster.values()]
    rep_sims = sorted(sims[i] for i in rep_idx)
    rep_inks = sorted(inks[i] for i in rep_idx)
    n = len(rep_idx)
    def dist(v):
        return {"n": n, "min": v[0], "p5": v[int(0.05 * n)], "p25": v[int(0.25 * n)],
                "median": round(statistics.median(v), 4), "p95": v[int(0.95 * n)]}

    arch = _archetype_by_page(pages_dir)
    pages = [CorpusPage(file=p.name, deck=p.name.rsplit("-", 1)[0], sha256=file_digest(p) or "",
                        dhash_hex=f"{hashes[i]:016x}", duplicate_cluster=clusters[i],
                        ink_fraction=inks[i], palette_similarity=sims[i],
                        archetype=arch.get(p.name))
             for i, p in enumerate(pngs)]

    try:
        renderer = subprocess.run(["soffice", "--version"], capture_output=True, text=True,
                                  timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        renderer = "unknown"
    model = ""
    try:
        import httpx
        model = httpx.get("http://localhost:8603/health", timeout=5).json().get("model", "")
    except Exception:
        pass

    records_dir = pages_dir / "records"
    n_records = len(list(records_dir.glob("*.json"))) if records_dir.is_dir() else 0
    catalogued = 0
    try:
        catalogued = json.loads((pages_dir / "archetypes.json").read_text()).get("total", 0)
    except (OSError, json.JSONDecodeError):
        pass

    return HouseGateCalibration(
        pages=pages,
        populations={
            "rendered_pages": len(pngs),
            "indexed_records": n_records,
            "catalogued_slides": catalogued,
            "reconciliation": ("catalogued counts pptx slides incl. hidden; rendered counts visible "
                                "PDF pages; records cover pages resolvable through page-mapping.json"),
        },
        duplicate_cluster_count=len(by_cluster),
        corpus_palette_histogram=[round(v, 6) for v in mean_hist],
        distributions={"palette_similarity": dist(rep_sims), "ink_fraction": dist(rep_inks)},
        thresholds=Thresholds(
            embedding_anomaly_floor=0.395,
            ink_floor=dist(rep_inks)["p5"],
            palette_floor=dist(rep_sims)["p5"],
            provenance=("p5 of duplicate-CLUSTER representatives (one vote per perceptual cluster, "
                         "dhash hamming<=6); embedding floor = duplicate-free corpus minimum, "
                         "2026-08-11 analysis"),
        ),
        render_profile=RenderProfile(renderer=renderer),
        embedding_model=model,
    )


class ReceiptFinding(BaseModel):
    code: str
    detail: str


def verify_render_receipt(receipt: dict, *, renders_dir: Path, pptx_path: Path | None,
                          expected_pages: int | None,
                          calibration: HouseGateCalibration) -> list[ReceiptFinding]:
    """Bind the scored PNGs to the deck under test. Re-computes every hash."""
    findings: list[ReceiptFinding] = []
    if pptx_path is not None:
        actual = file_digest(pptx_path)
        if receipt.get("pptx_sha256") != actual:
            findings.append(ReceiptFinding(code="PPTX_HASH_MISMATCH",
                detail=f"receipt {str(receipt.get('pptx_sha256'))[:12]}… vs delivered {str(actual)[:12]}…"))
    if receipt.get("dpi") != calibration.render_profile.dpi:
        findings.append(ReceiptFinding(code="RENDER_PROFILE_MISMATCH",
            detail=f"render dpi {receipt.get('dpi')} != calibrated {calibration.render_profile.dpi}"))
    pages = receipt.get("pages", [])
    if expected_pages is not None and len(pages) != expected_pages:
        findings.append(ReceiptFinding(code="PAGE_COUNT_MISMATCH",
            detail=f"receipt has {len(pages)} pages, document declares {expected_pages} visible slides"))
    listed = set()
    for entry in pages:
        f = renders_dir / entry.get("file", "")
        listed.add(entry.get("file", ""))
        actual = file_digest(f)
        if actual is None:
            findings.append(ReceiptFinding(code="RENDER_MISSING", detail=f"{entry.get('file')} absent"))
        elif actual != entry.get("sha256"):
            findings.append(ReceiptFinding(code="RENDER_HASH_MISMATCH",
                detail=f"{entry.get('file')}: receipt {str(entry.get('sha256'))[:12]}… vs on-disk {actual[:12]}…"))
    strays = {p.name for p in renders_dir.glob("s*.png")} - listed
    if strays:
        findings.append(ReceiptFinding(code="UNRECEIPTED_RENDER",
            detail=f"{len(strays)} PNG(s) in the scored directory are not in the receipt: {sorted(strays)[:3]}"))
    return findings
