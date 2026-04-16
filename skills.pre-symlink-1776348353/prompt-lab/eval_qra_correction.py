"""Evaluate QRA correction prompt against ground truth cases via scillm."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

SKILL_DIR = Path(__file__).parent
SCILLM_BASE = "http://localhost:4001"
SCILLM_KEY = "sk-dev-proxy-123"


def load_prompt(name: str) -> tuple[str, str]:
    """Load prompt template, return (system, user_template)."""
    text = (SKILL_DIR / "prompts" / f"{name}.txt").read_text()
    parts = text.split("[USER]")
    system = parts[0].replace("[SYSTEM]", "").strip()
    user_template = parts[1].strip() if len(parts) > 1 else ""
    return system, user_template


def load_ground_truth(name: str) -> list[dict]:
    """Load ground truth cases."""
    data = json.loads(
        (SKILL_DIR / "ground_truth" / f"{name}.json").read_text(),
    )
    return data["cases"]


def call_scillm(system: str, user: str) -> str:
    """Call scillm and return content."""
    resp = httpx.post(
        f"{SCILLM_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        json={
            "model": "text",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 256,
            "temperature": 0.2,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def evaluate(prompt_name: str, gt_name: str) -> None:
    """Run evaluation."""
    system, user_template = load_prompt(prompt_name)
    cases = load_ground_truth(gt_name)

    print(f"Evaluating {prompt_name} against {len(cases)} cases\n")

    correct = 0
    total = len(cases)
    results = []

    for case in cases:
        inp = case["input"]
        expected = case["expected"]["corrected_question"]

        # Format user prompt
        user = user_template.format(
            original_question=inp["original_question"],
            control_id=inp["control_id"],
            gate_failures=json.dumps(inp["gate_failures"], indent=2),
        )

        t0 = time.monotonic()
        try:
            content = call_scillm(system, user)
            parsed = json.loads(content)
            got = parsed.get("corrected_question", "PARSE_ERROR")
        except Exception as e:
            got = f"ERROR: {e}"
        elapsed = round((time.monotonic() - t0) * 1000)

        # Score: exact match for UNFIXABLE, fuzzy for corrections
        if expected == "UNFIXABLE":
            match = got.upper().strip() == "UNFIXABLE"
        else:
            # For corrections, check if the key entity was fixed
            match = _fuzzy_match(expected, got)

        if match:
            correct += 1

        status = "PASS" if match else "FAIL"
        print(f"  [{status}] {case['id']}: {elapsed}ms")
        if not match:
            print(f"    Expected: {expected}")
            print(f"    Got:      {got}")

        results.append({
            "id": case["id"],
            "expected": expected,
            "got": got,
            "match": match,
            "elapsed_ms": elapsed,
            "notes": case.get("notes", ""),
        })

    rate = correct / total if total else 0
    print(f"\nResults: {correct}/{total} ({rate:.0%})")
    print(f"Gate: {'PASS' if rate >= 0.80 else 'FAIL'} (threshold: 80%)")

    # Save results
    out = SKILL_DIR / "results" / f"{prompt_name}_eval_{int(time.time())}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "prompt": prompt_name,
        "ground_truth": gt_name,
        "correct": correct,
        "total": total,
        "rate": rate,
        "passed": rate >= 0.80,
        "results": results,
    }, indent=2))
    print(f"Results saved: {out}")


def _fuzzy_match(expected: str, got: str) -> bool:
    """Check if correction matches expected output."""
    if not got or got.startswith("ERROR"):
        return False
    # Normalize
    e = expected.lower().strip().rstrip("?")
    g = got.lower().strip().rstrip("?")
    # Exact match
    if e == g:
        return True
    # Key entity match — check if the corrected control ID is present
    # Extract the control ID from expected
    import re
    ids = re.findall(r'[A-Z]{2,}-[A-Z]*-?\d+|CWE-\d+|AC-\d+', expected)
    if ids:
        return all(cid.lower() in g for cid in ids)
    return False


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "evidence_qra_correction_v1"
    gt = sys.argv[2] if len(sys.argv) > 2 else "evidence_qra_correction"
    evaluate(prompt, gt)
