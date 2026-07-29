"""Tests for dogpile.security_research_packet.v1 generation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

from dogpile.security_research_packet import (
    SCHEMA,
    build_security_research_packet,
    validate_security_research_packet,
)

HACK_DIR = SKILLS_DIR / "hack"
if str(HACK_DIR) not in sys.path:
    sys.path.insert(0, str(HACK_DIR))

from hack_scan_request import validate_scan_request  # noqa: E402


def fixture_inputs() -> dict[str, object]:
    """Return deterministic provider results covering #1113 source classes."""

    stage1 = {
        "brave": {
            "query": "bounded scanning evidence",
            "web": {
                "results": [
                    {
                        "title": "Web source on scan evidence",
                        "url": "https://example.com/security/evidence",
                        "description": "Source-bearing web retrieval fixture.",
                    }
                ]
            },
        },
        "github": {
            "repos": [
                {
                    "fullName": "example/security-tool",
                    "url": "https://github.com/example/security-tool",
                    "description": "Evaluated repository fixture.",
                    "pushedAt": "2026-07-29T00:00:00Z",
                }
            ],
            "issues": [],
        },
        "arxiv": {
            "items": [
                {
                    "id": "2607.11130",
                    "title": "Evidence contracts for security scans",
                    "abs_url": "https://arxiv.org/abs/2607.11130",
                    "abstract": "Fixture paper abstract.",
                }
            ]
        },
        "youtube": [
            {
                "id": "video1113",
                "title": "Security scan evidence talk",
                "url": "https://youtube.com/watch?v=video1113",
                "description": "Fixture video metadata.",
            }
        ],
        "feeds": {"returncode": 0, "stdout": "feed item: source-bearing security update"},
        "readarr": {"skipped": "disabled by default"},
        "wayback": {"skipped": "disabled by default"},
        "perplexity": {"skipped": "retired"},
        "codex_knowledge": "Model-only overview; not retrieval evidence.",
    }
    stage2 = {
        "github": {
            "evaluation_receipt": {
                "artifact_path": "github-search-receipt.json",
                "sha256": "a" * 64,
                "sandbox_result": "metadata_only",
            }
        },
        "arxiv": {"arxiv_details": [], "arxiv_deep": []},
        "youtube": [{"id": "video1113", "full_text": "Transcript fixture."}],
        "brave": [],
        "synthesis": {"ok": True, "text": "Model synthesis is separate from retrieval evidence."},
    }
    return {"stage1": stage1, "stage2": stage2}


class SecurityResearchPacketTests(unittest.TestCase):
    def test_packet_separates_retrieval_evidence_from_model_synthesis(self) -> None:
        data = fixture_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            result = build_security_research_packet(
                requested_query="bounded software security scanning evidence contracts",
                effective_query="bounded software security scanning evidence contracts",
                request_context={"persona": "battle-red"},
                tailored_queries={"brave": "bounded scanning evidence"},
                stage1_results=data["stage1"],
                stage2_results=data["stage2"],
                final_report="# Fixture report\n",
                output_dir=Path(tmp),
                run_id="fixture-run",
                started_at="2026-07-29T00:00:00Z",
                ended_at="2026-07-29T00:00:01Z",
                mocked=False,
                live="fixture_provider_shapes",
            )
            packet = result["packet"]

        self.assertEqual(packet["schema"], SCHEMA)
        self.assertGreaterEqual(packet["source_bearing_provider_count"], 5)
        self.assertGreaterEqual(packet["source_bearing_evidence_count"], 5)
        self.assertFalse(packet["model_synthesis"]["source_bearing"])
        self.assertNotIn("Model-only overview", json.dumps(packet["retrieval_evidence"]))
        self.assertEqual(validate_security_research_packet(packet)["status"], "PASS")

    def test_concurrent_runs_use_distinct_paths_but_stable_packet_hash(self) -> None:
        data = fixture_inputs()
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            kwargs = dict(
                requested_query="bounded software security scanning evidence contracts",
                effective_query="bounded software security scanning evidence contracts",
                request_context={},
                tailored_queries={},
                stage1_results=data["stage1"],
                stage2_results=data["stage2"],
                final_report="# Fixture report\n",
                run_id="stable-fixture-run",
                started_at="2026-07-29T00:00:00Z",
                ended_at="2026-07-29T00:00:01Z",
                mocked=False,
                live="fixture_provider_shapes",
            )
            first = build_security_research_packet(output_dir=Path(left), **kwargs)
            second = build_security_research_packet(output_dir=Path(right), **kwargs)

        self.assertNotEqual(first["packet_path"], second["packet_path"])
        self.assertEqual(first["packet"]["packet_sha256"], second["packet"]["packet_sha256"])

    def test_hack_scan_request_adapter_validates_without_docker(self) -> None:
        data = fixture_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = build_security_research_packet(
                requested_query="bounded software security scanning evidence contracts",
                effective_query="bounded software security scanning evidence contracts",
                request_context={},
                tailored_queries={},
                stage1_results=data["stage1"],
                stage2_results=data["stage2"],
                final_report="# Fixture report\n",
                output_dir=out,
                run_id="adapter-fixture-run",
                started_at="2026-07-29T00:00:00Z",
                ended_at="2026-07-29T00:00:01Z",
                mocked=False,
                live="fixture_provider_shapes",
            )
            receipt = validate_scan_request(
                Path(result["hack_scan_request_path"]),
                expected_target="fixture-target@sha256:fixture",
            )

        self.assertEqual(receipt["status"], "PASS", receipt["errors"])
        self.assertFalse(receipt["docker_invoked"])
        self.assertGreaterEqual(receipt["source_bearing_evidence_count"], 1)

    def test_model_only_packet_has_zero_source_bearing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_security_research_packet(
                requested_query="model only",
                effective_query="model only",
                request_context={},
                tailored_queries={},
                stage1_results={"codex_knowledge": "Only a model overview."},
                stage2_results={"synthesis": {"ok": True, "text": "Model synthesis only."}},
                final_report="# Model only\n",
                output_dir=Path(tmp),
                run_id="model-only-fixture-run",
                started_at="2026-07-29T00:00:00Z",
                ended_at="2026-07-29T00:00:01Z",
                mocked=False,
                live="fixture_provider_shapes",
            )

        self.assertEqual(result["packet"]["source_bearing_evidence_count"], 0)
        self.assertEqual(validate_security_research_packet(result["packet"])["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
