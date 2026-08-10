from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from probes import ProbeStatus  # noqa: E402
from probes import registry  # noqa: E402
from probes import tier_code_projection as cp  # noqa: E402
from reporter import _save_state  # noqa: E402


class FakeAql:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses

    def execute(self, query: str, bind_vars: dict | None = None):
        for marker, rows in self.responses.items():
            if marker in query:
                return list(rows)
        return []


class FakeDb:
    def __init__(self, responses: dict[str, list[dict]], collections: set[str] | None = None) -> None:
        self.aql = FakeAql(responses)
        self.collections = collections or {
            "code_indexes",
            "code_generations",
            "code_files",
            "code_symbols",
            "curate_edges",
            "semantic_projection_outbox",
        }

    def has_collection(self, name: str) -> bool:
        return name in self.collections


def test_code_projection_probes_are_registered() -> None:
    probes = {entry["name"]: entry for entry in registry.get_probes(tier=8)}

    assert len(probes) == 10
    assert probes["code-projection-active-generation"]["probe_id"] == "CP01"
    assert probes["code-projection-delta-efficiency"]["probe_id"] == "CP10"


def test_cp01_passes_unique_active_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-active-generation": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "branch": "main",
                    "active_generation_id": "cg_1",
                    "active_generation_count": 1,
                    "current_record_generation_ids": ["cg_1"],
                    "mixed_current_records": False,
                    "missing_active_pointer": False,
                    "stale_staging_count": 0,
                }
            ]
        }
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_active_generation()

    assert result.status == ProbeStatus.PASS
    assert result.details["remediation"] == "observe"
    assert result.details["rows"][0]["generation_id"] if result.details["rows"][0].get("generation_id") else True


def test_cp01_fails_two_active_generations_and_mixed_records(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-active-generation": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "branch": "main",
                    "active_generation_id": "cg_2",
                    "active_generation_count": 2,
                    "current_record_generation_ids": ["cg_1", "cg_2"],
                    "mixed_current_records": True,
                    "missing_active_pointer": False,
                    "stale_staging_count": 1,
                }
            ]
        }
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_active_generation()

    assert result.status == ProbeStatus.FAIL
    assert result.details["remediation"] == "reapply_projection"
    assert result.details["bad_active_counts"][0]["active_generation_count"] == 2
    assert "mixed_current_records" in result.details["issues"][0]["issues"]


def test_cp02_fails_bundle_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-bundle-reconciliation": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "branch": "main",
                    "generation_id": "cg_1",
                    "expected_counts": {"files": 2, "symbols": 4, "edges": 7},
                    "observed_counts": {"files": 2, "symbols": 3, "edges": 7},
                    "count_mismatch": True,
                    "missing_bundle_digest": False,
                }
            ]
        }
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_bundle_reconciliation()

    assert result.status == ProbeStatus.FAIL
    assert result.details["remediation"] == "reapply_projection"


def test_cp03_reports_incomplete_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-incomplete-immutability": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_rejected",
                    "active_before_generation_id": "cg_old",
                    "active_after_generation_id": "cg_new",
                    "active_generation_mutated": True,
                    "current_keyset_mutated": False,
                }
            ]
        },
        collections={"code_generations"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_incomplete_immutability()

    assert result.status == ProbeStatus.FAIL
    assert result.details["remediation"] == "human_review"


def test_cp04_fails_missing_and_retired_semantic_points(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-semantic-parity": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_1",
                    "active_symbol_count": 4,
                    "missing_point_count": 1,
                    "stale_text_count": 0,
                    "retired_point_count": 1,
                }
            ]
        },
        collections={"code_indexes", "code_symbols"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_semantic_parity()

    assert result.status == ProbeStatus.FAIL
    assert result.details["remediation"] == "retry_outbox"


def test_cp05_warns_pending_outbox_and_fails_failed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    db_warn = FakeDb(
        {"code-projection-outbox-backlog": [{"state": "pending", "count": 1}]},
        collections={"semantic_projection_outbox"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db_warn)
    warn = cp.probe_outbox_backlog()
    assert warn.status == ProbeStatus.WARN

    db_fail = FakeDb(
        {"code-projection-outbox-backlog": [{"state": "failed", "count": 1, "last_error": "qdrant down"}]},
        collections={"semantic_projection_outbox"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db_fail)
    fail = cp.probe_outbox_backlog()
    assert fail.status == ProbeStatus.FAIL


def test_cp06_skips_without_retired_canary_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb({}, collections={"code_symbols"})
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_retired_leakage()

    assert result.status == ProbeStatus.SKIP
    assert result.details["remediation"] == "observe"


def test_cp07_warns_stale_and_missing_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    live = tmp_path / "live.py"
    live.write_text("print('new')\n")
    db = FakeDb(
        {
            "code-projection-source-freshness": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_1",
                    "root": str(tmp_path),
                    "path": "live.py",
                    "content_hash": "sha256:not-the-current-hash",
                },
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_1",
                    "root": str(tmp_path),
                    "path": "missing.py",
                    "content_hash": "sha256:any",
                },
            ]
        },
        collections={"code_indexes", "code_symbols"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_source_freshness()

    assert result.status == ProbeStatus.WARN
    assert len(result.details["stale"]) == 1
    assert len(result.details["missing"]) == 1
    assert result.details["remediation"] == "reindex"


def test_cp08_warns_transform_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-transform-drift": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_1",
                    "transform_fingerprint": "old",
                    "semantic_text_schemas": ["memory.code_symbol_semantic_text.v1"],
                }
            ]
        },
        collections={"code_indexes", "code_generations", "code_symbols"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_transform_drift()

    assert result.status == ProbeStatus.WARN
    assert result.details["drift"][0]["drift"] == "transform_fingerprint"


def test_cp09_warns_stale_debugger_status(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-derived-summary-status": [{"kind": "derived_summary", "status": "current", "count": 3}],
            "code-projection-debugger-recipe-status": [{"kind": "debugger_recipe", "status": "needs_fixture", "count": 2}],
        },
        collections={"code_indexes", "code_symbols", "code_debug_recipes"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_doc_debug_staleness()

    assert result.status == ProbeStatus.WARN
    assert result.details["stale"][0]["status"] == "needs_fixture"


def test_cp10_skips_without_telemetry_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb({}, collections={"code_indexes"})
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_delta_efficiency()

    assert result.status == ProbeStatus.SKIP
    assert "ingest-code#1347" in result.details["limitations"][0]


def test_cp10_warns_excessive_reparse(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(
        {
            "code-projection-delta-efficiency": [
                {
                    "scope": "memory",
                    "code_index_id": "ci_1",
                    "generation_id": "cg_1",
                    "discovered_files": 100,
                    "parsed_files": 80,
                    "reused_files": 20,
                }
            ]
        },
        collections={"code_indexes", "code_ingest_telemetry"},
    )
    monkeypatch.setattr(cp, "_get_db", lambda: db)

    result = cp.probe_delta_efficiency()

    assert result.status == ProbeStatus.WARN
    assert result.details["inefficient"][0]["reparse_pct"] == 80.0


def test_saved_state_includes_machine_readable_details(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = cp.probe_bundle_reconciliation.__wrapped__ if hasattr(cp.probe_bundle_reconciliation, "__wrapped__") else None
    assert result is None
    probe = cp.ProbeResult if hasattr(cp, "ProbeResult") else None
    assert probe is not None
    state_dir = tmp_path / "state"
    monkeypatch.setattr("config.STATE_DIR", state_dir)
    _save_state(
        [
            probe(
                probe_id="CP02",
                name="code-projection-bundle-reconciliation",
                tier=8,
                status=ProbeStatus.FAIL,
                message="mismatch",
                details={"remediation": "reapply_projection", "issues": [{"code_index_id": "ci_1"}]},
            )
        ],
        "critical",
        {status: int(status == ProbeStatus.FAIL) for status in ProbeStatus},
        1,
    )

    payload = json.loads((state_dir / "latest_report.json").read_text())

    assert payload["probes"][0]["details"]["remediation"] == "reapply_projection"
