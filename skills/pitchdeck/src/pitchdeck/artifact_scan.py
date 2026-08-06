"""Post-emit artifact scan (roundtable blind spot: 'nobody scanned the emitted bytes').

The validator checks the MODEL; the emitted artifact is the threat surface. A
PPTX is an OPC zip whose parts (slides, notes, docProps, custom XML, media)
can carry text the model never showed; the self-contained HTML is trivially
decompilable. scan_artifact opens the actual output bytes and fails closed if
any private-claim text, private source path, or forbidden unqualified phrase
appears in any part of a public artifact. Also verifies (whole-string level)
that every visible slide title survives into the PPTX — the cheap version of
the RenderPlan text check. Raises ArtifactLeak on any finding.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import zipfile
from pathlib import Path

from loguru import logger

from .models import ClaimLedger, DeckManifest, SourceManifest, Visibility
from .validation import _qualified_occurrence


class ArtifactLeak(ValueError):
    """A public artifact contains text that must not leave the private boundary."""


def _pptx_text(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith((".xml", ".rels", ".txt")):
                try:
                    chunks.append(zf.read(name).decode("utf-8", errors="ignore"))
                except Exception:
                    continue
    return "\n".join(chunks)


def _strip_xml(xml_text: str) -> str:
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", xml_text))


def scan_artifact(
    artifact: Path,
    deck: DeckManifest,
    ledger: ClaimLedger,
    sources: SourceManifest,
    *,
    forbidden_phrases: list[str] | None = None,
) -> dict[str, int]:
    """Scan the emitted bytes of a public artifact; raise ArtifactLeak on findings."""
    if deck.deck.visibility != Visibility.PUBLIC:
        return {"skipped_private_deck": 1}

    suffix = artifact.suffix.lower()
    if suffix == ".pptx":
        raw = _pptx_text(artifact)
        visible = _strip_xml(raw)
    else:
        raw = artifact.read_text(encoding="utf-8", errors="ignore")
        visible = _strip_xml(raw)

    findings: list[str] = []

    # 1) Private claim text must never appear in any part of a public artifact.
    for claim in ledger.claims:
        if claim.visibility == Visibility.PRIVATE and claim.text.strip():
            if claim.text.strip().lower() in raw.lower():
                findings.append(f"private claim text present: '{claim.id}'")

    # 2) Private source paths/titles must not leak into artifact metadata.
    for source in sources.sources:
        if source.visibility == Visibility.PRIVATE:
            for needle in (source.path, source.title):
                if needle and len(needle) > 8 and needle.lower() in raw.lower():
                    findings.append(f"private source reference present: '{source.id}' ({needle[:40]})")

    # 3) Forbidden unqualified phrases in the rendered text (defense in depth).
    phrases = forbidden_phrases if forbidden_phrases is not None else sources.policy.forbidden_unqualified_claims
    for phrase in phrases:
        if phrase.lower() in visible.lower() and not _qualified_occurrence(visible, phrase):
            findings.append(f"forbidden unqualified phrase in artifact text: '{phrase}'")

    # 4) Whole-string RenderPlan verification: every visible string must survive
    # into the artifact (title, message, body, freeform text, visual items).
    visible_lower = re.sub(r"\s+", " ", visible.lower())
    strings_verified = 0
    for slide in deck.slides:
        if slide.hidden:
            continue
        expected: list[tuple[str, str]] = [("title", slide.title), ("message", slide.message)]
        expected += [(f"body:{i}", line) for i, line in enumerate(slide.body)]
        if slide.layout.value == "freeform":
            expected = [("title", "")]  # freeform renders elements instead of title/message/body
            expected += [(f"element:{e.id}", e.text or "") for e in slide.elements if e.type == "text"]
        expected += [(f"visual.items:{i}", item) for i, item in enumerate(slide.visual.items)]
        for path, text in expected:
            needle = re.sub(r"\s+", " ", text.strip().lower())
            if not needle:
                continue
            strings_verified += 1
            if needle not in visible_lower:
                findings.append(
                    f"visible string missing from artifact: {slide.id}/{path} ('{text[:40]}')"
                )

    # 5) Embedded evidence JSON (HTML only): parse the DECODED payloads and
    # assert the positive allowlist — review P0: byte-search misses unicode
    # escapes, and "renders only public records" must be "embeds only the
    # minimal approved records".
    if suffix != ".pptx":
        approved_public = {
            c.id for c in ledger.claims
            if c.status.value == "approved" and c.visibility == Visibility.PUBLIC
        }
        allowed_keys = {"id", "text", "status", "qualifier"}
        for match in re.finditer(r'data-claims="([^"]*)"', raw):
            try:
                records = json.loads(html_mod.unescape(match.group(1)))
            except (ValueError, TypeError):
                findings.append("embedded data-claims payload is not parseable JSON")
                continue
            for record in records:
                extra = set(record) - allowed_keys
                if extra:
                    findings.append(f"embedded evidence record has non-allowlisted keys: {sorted(extra)}")
                if record.get("status") != "approved":
                    findings.append(f"embedded evidence record '{record.get('id')}' is not approved")
                if record.get("id") not in approved_public:
                    findings.append(
                        f"embedded evidence record '{record.get('id')}' is not a public approved ledger claim"
                    )

    if findings:
        detail = "; ".join(findings[:6])
        raise ArtifactLeak(f"post-emit artifact scan failed for {artifact.name}: {detail}")

    counts = {
        "private_claims_checked": sum(1 for c in ledger.claims if c.visibility == Visibility.PRIVATE),
        "private_sources_checked": sum(1 for s in sources.sources if s.visibility == Visibility.PRIVATE),
        "strings_verified": strings_verified,
    }
    logger.info("artifact scan PASS: {} ({})", artifact.name, counts)
    return counts
