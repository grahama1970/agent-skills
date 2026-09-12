import json
import time
import pytest


@pytest.fixture(autouse=True)
def _hermetic_state(tmp_path_factory, monkeypatch):
    """Hermetic per-test state root; never read live production state.

    The dispatch path consults transport-outage and capability-preflight receipts
    and the global runtime-state doc under the state root. Isolate every test to
    an empty state root and seed: an active global runtime state, and a fresh
    ready capability receipt so dispatch-logic tests are not gated by fleet
    activation or the cron capability preflight they do not exercise. A seeded
    receipt (not a skip env) keeps the capability gate itself testable.
    """
    root = tmp_path_factory.mktemp("pwstate")
    monkeypatch.setenv("PROJECT_WATCHDOG_STATE_ROOT", str(root))
    (root / "state.json").write_text(json.dumps({
        "schema": "agent_skills.project_watchdog.state.v1",
        "global": {"state": "active"},
        "projects": {pid: {"state": "active"} for pid in
                     ("p", "tau", "agent-skills", "graph-memory-operator",
                      "pdf_oxide", "sparta", "chatgpt-lab", "memory", "scillm",
                      "nowhere", "orphan", "x")},
    }))
    (root / "capability-preflight.json").write_text(json.dumps({
        "schema": "agent_skills.project_watchdog.capability_receipt.v1",
        "checked_at": time.time(), "dispatch_ready": True, "failed": [], "dependencies": {},
    }))
