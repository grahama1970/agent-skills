"""Discrepancy Analysis: cross-reference Requirement vs Table chunks per SPARTA control.

For each control with both Requirement AND Table chunks (via chunk_control_edges),
compare the requirement claim against the table data using scillm.
Flag contradictions: requirement says "encrypted" but table shows "None".

Usage:
    uv run python tools/discrepancy_analysis.py [--limit 50] [--dry-run]

Results stored in evidence_cases collection with tag "discrepancy".
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer()

# ── Config ───────────────────────────────────────────────────────────────────

MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)
SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
SCILLM_MODEL = os.getenv("SCILLM_MODEL", "text")

OUTPUT_DIR = Path("/mnt/storage12tb/skills/create-evidence-case/discrepancy")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)


def _memory_post(client: httpx.Client, path: str, body: dict) -> dict:
    resp = client.post(path, json=body)
    if resp.status_code != 200:
        logger.warning("Memory {} failed: {}", path, resp.status_code)
        return {}
    return resp.json()


# ── Step 1: Find controls with both Requirement and Table chunks ─────────────


def find_controls_with_both_types(client: httpx.Client, limit: int = 50) -> list[dict]:
    """Find SPARTA controls, then recall Requirement and Table chunks for each.

    NOTE: chunk_control_edges only link Text/Equation chunks (324K).
    Requirement (1.5K) and Table (123K) chunks exist but have no edges.
    So we use /recall semantic search against datalake_chunks instead.
    """
    # Get SPARTA controls
    ctrls = _memory_post(client, "/list", {
        "collection": "sparta_controls",
        "limit": 200,
        "filters": {"source_framework": "SPARTA", "control_type": "technique"},
    }).get("documents", [])

    logger.info("Loaded {} SPARTA technique controls", len(ctrls))

    controls_with_both = []
    for ctrl in ctrls[:limit * 3]:  # Check 3x limit to find enough matches
        ctrl_id = ctrl.get("control_id", "")
        ctrl_name = ctrl.get("name", "")

        # Recall Requirement chunks mentioning this control
        req_res = _memory_post(client, "/recall", {
            "q": f"{ctrl_id} {ctrl_name} requirement shall",
            "collections": ["datalake_chunks"],
            "k": 5,
        })
        req_items = [
            it for it in (req_res.get("items") or [])
            if (it.get("asset_type") or "") == "Requirement"
        ]

        if not req_items:
            continue

        # Recall Table chunks mentioning this control
        tbl_res = _memory_post(client, "/recall", {
            "q": f"{ctrl_id} {ctrl_name} table specification",
            "collections": ["datalake_chunks"],
            "k": 5,
        })
        tbl_items = [
            it for it in (tbl_res.get("items") or [])
            if (it.get("asset_type") or "") == "Table"
        ]

        if not tbl_items:
            continue

        controls_with_both.append({
            "control_id": ctrl_id,
            "control_key": f"sparta_controls/ctrl__{ctrl_id}",
            "requirement_chunks": req_items[:3],
            "table_chunks": tbl_items[:3],
            "types": ["Requirement", "Table"],
        })

        if len(controls_with_both) >= limit:
            break

    logger.info(
        "Found {} controls with both Requirement and Table chunks",
        len(controls_with_both),
    )
    return controls_with_both


# ── Step 2: Compare via scillm ───────────────────────────────────────────────


def compare_requirement_vs_table(
    control_id: str,
    req_text: str,
    table_text: str,
) -> dict | None:
    """Call scillm to check if requirement matches table data."""
    prompt = f"""You are a cybersecurity compliance analyst for aerospace systems.

Compare this REQUIREMENT against this TABLE DATA for SPARTA control {control_id}.

REQUIREMENT:
{req_text[:1000]}

TABLE DATA:
{table_text[:1000]}

Does the requirement claim match the table data? Look for contradictions:
- Requirement says "encrypted" but table shows "None" or "Disabled"
- Requirement says "authenticated" but table shows no auth column
- Requirement specifies a standard but table shows a different one
- Requirement mandates a threshold but table shows values outside it

Respond in JSON:
{{
  "has_discrepancy": true/false,
  "severity": "high" | "medium" | "low" | "none",
  "summary": "One sentence describing the match or mismatch",
  "requirement_claim": "What the requirement asserts",
  "table_reality": "What the table actually shows",
  "recommendation": "Engineering-level fix if discrepancy exists"
}}"""

    try:
        resp = httpx.post(
            f"{SCILLM_BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": SCILLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            timeout=60.0,
        )
        if resp.status_code != 200:
            logger.warning("scillm failed for {}: {}", control_id, resp.status_code)
            return None

        content = resp.json()["choices"][0]["message"]["content"]
        # Extract JSON from response (may have markdown code fences)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())
    except Exception as exc:
        logger.warning("scillm parse error for {}: {}", control_id, exc)
        return None


# ── Step 3: Store findings ───────────────────────────────────────────────────


def store_findings(client: httpx.Client, findings: list[dict]) -> int:
    """Store discrepancy findings in evidence_cases collection."""
    docs = []
    for f in findings:
        key_src = f["control_id"] + "|discrepancy|" + f.get("summary", "")[:100]
        _key = hashlib.sha256(key_src.encode()).hexdigest()[:16]
        docs.append({
            "_key": _key,
            "control_id": f["control_id"],
            "type": "discrepancy",
            "has_discrepancy": f.get("has_discrepancy", False),
            "severity": f.get("severity", "none"),
            "summary": f.get("summary", ""),
            "requirement_claim": f.get("requirement_claim", ""),
            "table_reality": f.get("table_reality", ""),
            "recommendation": f.get("recommendation", ""),
            "tags": ["discrepancy", f"control:{f['control_id']}", f"severity:{f.get('severity', 'none')}"],
        })

    if not docs:
        return 0

    result = _memory_post(client, "/upsert", {
        "collection": "evidence_cases",
        "documents": docs,
    })
    inserted = result.get("inserted", 0)
    updated = result.get("updated", 0)
    logger.info("Stored {} findings ({} new, {} updated)", len(docs), inserted, updated)
    return inserted + updated


# ── CLI ──────────────────────────────────────────────────────────────────────


@app.command()
def run(
    limit: int = typer.Option(50, help="Max controls to analyze"),
    dry_run: bool = typer.Option(False, help="Analyze but don't store results"),
    delay: float = typer.Option(1.0, help="Seconds between scillm calls"),
) -> None:
    """Run discrepancy analysis across SPARTA controls."""
    client = _memory_client()

    # Step 1: Find controls with both types
    controls = find_controls_with_both_types(client, limit=limit)
    if not controls:
        logger.warning("No controls found with both Requirement and Table chunks")
        raise typer.Exit(0)

    # Step 2: Compare each
    findings: list[dict] = []
    for i, ctrl in enumerate(controls):
        control_id = ctrl["control_id"]
        req_text = "\n".join(
            c.get("text", c.get("content", ""))[:500]
            for c in ctrl["requirement_chunks"]
        )
        table_text = "\n".join(
            c.get("text", c.get("content", ""))[:500]
            for c in ctrl["table_chunks"]
        )

        if not req_text.strip() or not table_text.strip():
            logger.debug("Skipping {} — empty text", control_id)
            continue

        logger.info("[{}/{}] Analyzing {}", i + 1, len(controls), control_id)
        result = compare_requirement_vs_table(control_id, req_text, table_text)

        if result:
            result["control_id"] = control_id
            findings.append(result)

            if result.get("has_discrepancy"):
                logger.warning(
                    "DISCREPANCY in {}: {} (severity: {})",
                    control_id, result.get("summary", "?"), result.get("severity", "?"),
                )

        if i < len(controls) - 1:
            time.sleep(delay)

    # Summary
    discrepancies = [f for f in findings if f.get("has_discrepancy")]
    logger.info(
        "Analysis complete: {} controls, {} findings, {} discrepancies",
        len(controls), len(findings), len(discrepancies),
    )

    # Save JSON report
    report_path = OUTPUT_DIR / "discrepancy_report.json"
    report_path.write_text(json.dumps(findings, indent=2, default=str))
    logger.info("Report saved to {}", report_path)

    # Step 3: Store
    if not dry_run and discrepancies:
        store_findings(client, discrepancies)
    elif dry_run:
        logger.info("Dry run — not storing findings")
        for f in discrepancies:
            print(f"  {f['control_id']}: {f.get('summary', '?')} [{f.get('severity', '?')}]")


if __name__ == "__main__":
    app()
