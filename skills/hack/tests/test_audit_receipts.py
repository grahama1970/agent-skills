from __future__ import annotations

from hack.audit_receipts import build_audit_receipt, memory_document, parse_bandit, summarize_findings


def test_parse_bandit_cwe78_shell_true() -> None:
    text = """
>> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified, security issue.
   Severity: High   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   Location: /scan/insecure.py:4:11
3       def run(user_input):
4           return subprocess.run("echo " + user_input, shell=True)

--------------------------------------------------
"""
    findings = parse_bandit(text)
    assert findings == [{
        "tool": "bandit",
        "rule_id": "B602",
        "rule_name": "subprocess_popen_with_shell_equals_true",
        "message": "subprocess call with shell=True identified, security issue.",
        "severity": "HIGH",
        "confidence": "HIGH",
        "cwe": "CWE-78",
        "location": "/scan/insecure.py:4:11",
    }]


def test_audit_receipt_and_memory_document_are_distilled() -> None:
    findings = [{"tool": "bandit", "rule_id": "B602", "severity": "HIGH", "cwe": "CWE-78"}]
    receipt = build_audit_receipt(
        target="/tmp/target",
        tool="bandit",
        severity="low",
        profile="hobbyist",
        mount_path="/tmp",
        scan_target="/scan/target.py",
        tool_results=[{"tool": "bandit", "returncode": 1, "network": "none"}],
        findings=findings,
        memory_recall={"found": False},
    )
    assert receipt["schema"] == "hack.audit_receipt.v1"
    assert receipt["summary"] == {"finding_count": 1, "severity_counts": {"HIGH": 1}, "high_count": 1, "cwes": ["CWE-78"]}
    assert receipt["isolation"]["network"] == "none"
    assert receipt["isolation"]["target_mount"] == "read_only"

    doc = memory_document(receipt, "/tmp/receipt.json")
    assert doc["schema"] == "hack.audit_memory_summary.v1"
    assert doc["finding_count"] == 1
    assert doc["cwes"] == ["CWE-78"]
    assert "findings" not in doc


def test_summarize_findings_counts_error_as_high() -> None:
    summary = summarize_findings([
        {"severity": "ERROR", "cwe": "CWE-89"},
        {"severity": "LOW", "cwe": "CWE-89"},
    ])
    assert summary["finding_count"] == 2
    assert summary["high_count"] == 1
    assert summary["cwes"] == ["CWE-89"]
