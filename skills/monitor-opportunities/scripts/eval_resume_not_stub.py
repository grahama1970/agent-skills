#!/usr/bin/env python3
"""Regression guard: the tailored resume must be a COMPOSED resume, not a stub.

Incident (2026-08-22): the nightly tailoring path in ``tailoring.py`` wrote
``resume.txt`` / ``resume.docx`` containing only a 6-line claim-highlights
delta ("Target role:" + "Selected claims:" + claim sentences). It never read
or composed the active ATS base resume, so the artifact uploaded to an employer
would have been a claim list, not a resume. The correct behavior (already in
``resume_artifact.build_variant_markdown``) is base resume + claim-bound
targeted highlights.

This guard drives the REAL ``_tailor_posting`` renderer on a fixture posting and
FAILS with the stable code ``RESUME_STUB_REGRESSION`` when the produced resume
lacks the canonical base-resume sections or falls under a realistic length. It
must fail against the pre-fix behavior (non-vacuity) and pass once the renderer
composes the base.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.tailoring import _tailor_posting  # noqa: E402
from monitor_opportunities.util import read_json  # noqa: E402

# A composed resume must carry the base resume's own sections. These markers are
# present in the active ATS base resume and absent from the claim-only stub.
BASE_SECTION_MARKERS = ("SUMMARY", "CORE SKILLS", "PROFESSIONAL EXPERIENCE")
MIN_REQUIRED_MARKERS = 2
MIN_RESUME_BYTES = 1500  # the stub is ~370 bytes; the composed base is ~4.4 KB
UNAPPROVED_METRIC_MARKERS = (
    "80% reduction in compliance verification costs",
    "3-5x more critical issues found",
    "3\u20135x more critical issues found",
)


def _fixture_posting(claim_keys: list[str]) -> dict[str, object]:
    return {
        "posting_key": "eval:resume-not-stub",
        "opportunity_id": "eval:resume-not-stub",
        "title": "AI Engineer - Public Sector",
        "organization": "Eval Fixture Co.",
        "selected_claim_keys": claim_keys[:3],
        "ats_provider": "ashby",
        "ats_host": "jobs.ashbyhq.com",
        "employer_url": "https://jobs.ashbyhq.com/eval/resume-not-stub",
        "form_fields": [],
        "accepted_file_formats": ["pdf", "docx", "txt"],
        "jd_language_patterns": ["agent", "AI", "document", "retrieval"],
        "observed": ["Eval fixture posting for the resume-stub regression guard."],
    }


def main() -> int:
    claims_path = SKILL_DIR / "tests" / "fixtures" / "claims" / "approved-claims.json"
    snapshot = read_json(claims_path)
    claim_keys = [c["claim_key"] for c in snapshot.get("claims", [])]
    if len(claim_keys) < 1:
        print("EVAL_SETUP_FAILED: no approved claims in fixture", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        _tailor_posting(_fixture_posting(claim_keys), claims_path, out_dir)
        resume_txt = (out_dir / "resume.txt").read_text(encoding="utf-8")

    size = len(resume_txt.encode("utf-8"))
    present = [m for m in BASE_SECTION_MARKERS if m in resume_txt.upper()]

    if size < MIN_RESUME_BYTES or len(present) < MIN_REQUIRED_MARKERS:
        print(
            "RESUME_STUB_REGRESSION: tailored resume is a claim-only stub, not a "
            "composed resume. "
            f"bytes={size} (min {MIN_RESUME_BYTES}); "
            f"base_sections_present={present} (need >= {MIN_REQUIRED_MARKERS} of "
            f"{list(BASE_SECTION_MARKERS)}). "
            "The nightly tailoring path must compose the ATS base resume + "
            "claim-bound highlights (see resume_artifact.build_variant_markdown), "
            "not emit only the claim-highlights delta.",
            file=sys.stderr,
        )
        return 1

    unapproved_metrics = [marker for marker in UNAPPROVED_METRIC_MARKERS if marker in resume_txt]
    if unapproved_metrics:
        print(
            "RESUME_UNAPPROVED_METRIC_REGRESSION: active base resume injected "
            f"unsupported metric text into tailored output: {unapproved_metrics}. "
            "Remove or approve the metric in the claim ledger before rendering.",
            file=sys.stderr,
        )
        return 1

    print(
        f"RESUME_COMPOSED_OK: bytes={size}, base_sections_present={present}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
