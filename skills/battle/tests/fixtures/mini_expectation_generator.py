"""Mini generator declaring per-case expectations for the two-axis gate.

One MUST_ACCEPT (valid input that must be processed and judged clean), one
MUST_REJECT (out-of-domain input that must be safely fail-closed), one
MAY_REJECT (either behavior acceptable).
"""
import json
from pathlib import Path


def generate(work_dir, params):
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)

    def bundle(name: str, expectation: str, payload) -> tuple[str, str, str]:
        d = root / name
        (d / "corpus").mkdir(parents=True, exist_ok=True)
        (d / "policy.json").write_text(json.dumps({
            "version": 1, "protected_values": [],
            "sensitive_values": [{"rule_id": "r", "subject_id": "s", "type": "name", "value": "5551234567"}],
        }))
        payload(d / "corpus")
        return name, str(d), expectation

    yield bundle("must-accept-case", "MUST_ACCEPT",
                 lambda c: (c / "d.txt").write_text("v 5551234567\n"))
    def invalid_utf8(c):
        (c / "d.txt").write_bytes(b"\xff\xfe not utf8")
        (c.parent / "invalid_input.json").write_text(json.dumps({
            "schema": "battle.invalid_input_predicate.v1",
            "approved": True,
            "predicate": "fixture contains invalid UTF-8 bytes and must fail closed",
        }))

    yield bundle("must-reject-case", "MUST_REJECT", invalid_utf8)
    yield bundle("may-reject-case", "MAY_REJECT",
                 lambda c: (c / "d.txt").write_text("ok 5551234567\n"))
