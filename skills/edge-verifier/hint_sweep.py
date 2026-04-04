#!/usr/bin/env python3
"""Hint Sweep — Validate SKILL.md hints against memory lessons.

Extracts operational hints from SKILL.md files, checks each against the
memory knowledge graph for contradictions, confirmations, or updates.
Creates edges in lesson_edges with source="hint-sweep".

Reuses edge-verifier infrastructure: score_candidates(), parallel_acompletions.
"""
import typer
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

# Reuse edge-verifier infrastructure
from verify_edges import score_candidates, parallel_acompletions

SKILLS_DIR = Path(__file__).resolve().parent.parent
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

try:
    from task_monitor_client import EdgeVerifierTaskClient
    TASK_MONITOR_AVAILABLE = True
except ImportError:
    TASK_MONITOR_AVAILABLE = False

# Default skill directories to sweep
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SKILLS_DIR.parent.parent
DEFAULT_SKILL_DIRS = [
    _PROJECT_ROOT.parent / "memory" / ".agents" / "skills",
    _SKILLS_DIR,
]

# Minimum hint length to consider (skip trivial lines)
MIN_HINT_LENGTH = 30

# Score threshold for sending a hint-candidate pair to LLM
RELEVANCE_THRESHOLD = float(os.getenv("HINT_SWEEP_THRESHOLD", "0.4"))

# Maximum LLM calls per sweep run
MAX_LLM_CALLS = int(os.getenv("HINT_SWEEP_MAX_LLM", "200"))

# Strong marker patterns indicating operational hints
STRONG_MARKERS = re.compile(
    r"\b(MUST|NEVER|NON-NEGOTIABLE|CRITICAL|WARNING|IMPORTANT|REQUIRED|MANDATORY|DO NOT)\b",
    re.IGNORECASE,
)

# Threshold patterns (numbers with units)
THRESHOLD_PATTERN = re.compile(
    r"\b\d+\.?\d*\s*(%|seconds?|minutes?|hours?|ms|MB|GB|tokens?)\b"
    r"|\b[<>]=?\s*\d+\.?\d*\b"
    r"|\b0\.\d+\b",
)


@dataclass
class HintRecord:
    """A single extracted hint from a SKILL.md file."""
    skill_name: str
    section: str
    text: str
    hint_type: str  # "bullet", "table_row", "threshold", "strong_marker"
    hint_id: str = ""  # Set after creation

    def __post_init__(self):
        if not self.hint_id:
            h = hashlib.sha256(f"{self.skill_name}:{self.section}:{self.text}".encode()).hexdigest()[:12]
            self.hint_id = f"hints/{self.skill_name}_{h}"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and return (metadata, body)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5:]
    data = {}
    for line in raw.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            data[key.strip()] = val.strip()
    return data, body


def extract_hints_from_skill(skill_dir: Path) -> List[HintRecord]:
    """Extract operational hints from a single SKILL.md file."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []

    text = skill_md.read_text(errors="replace")
    meta, body = parse_frontmatter(text)
    skill_name = meta.get("name", skill_dir.name)

    hints: List[HintRecord] = []
    current_section = "top"

    for line in body.splitlines():
        stripped = line.strip()

        # Track sections
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue
        if stripped.startswith("### "):
            current_section = stripped[4:].strip()
            continue

        # Skip empty lines, code fence markers, frontmatter refs
        if not stripped or stripped.startswith("```") or stripped.startswith("---"):
            continue

        # Skip lines that are just headers or too short
        if len(stripped) < MIN_HINT_LENGTH:
            continue

        # Extract bullet points
        if stripped.startswith(("- ", "* ", "1. ", "2. ", "3. ")):
            content = re.sub(r"^[-*\d.]+\s+", "", stripped)
            if len(content) >= MIN_HINT_LENGTH:
                hints.append(HintRecord(
                    skill_name=skill_name,
                    section=current_section,
                    text=content,
                    hint_type="bullet",
                ))
            continue

        # Extract table rows (skip header separator rows)
        if "|" in stripped and not re.match(r"^\|[-:\s|]+\|$", stripped):
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            content = " | ".join(cells)
            if len(content) >= MIN_HINT_LENGTH and not all(c == "-" for c in content.replace("|", "").replace(" ", "")):
                hints.append(HintRecord(
                    skill_name=skill_name,
                    section=current_section,
                    text=content,
                    hint_type="table_row",
                ))
            continue

        # Extract lines with strong markers
        if STRONG_MARKERS.search(stripped):
            hints.append(HintRecord(
                skill_name=skill_name,
                section=current_section,
                text=stripped,
                hint_type="strong_marker",
            ))
            continue

        # Extract lines with threshold values
        if THRESHOLD_PATTERN.search(stripped):
            hints.append(HintRecord(
                skill_name=skill_name,
                section=current_section,
                text=stripped,
                hint_type="threshold",
            ))
            continue

    # Deduplicate by content hash
    seen = set()
    unique = []
    for h in hints:
        if h.hint_id not in seen:
            seen.add(h.hint_id)
            unique.append(h)

    return unique


def extract_hints(skill_dirs: List[Path]) -> List[HintRecord]:
    """Extract hints from all SKILL.md files in the given directories."""
    all_hints: List[HintRecord] = []
    for skill_dir_root in skill_dirs:
        if not skill_dir_root.exists():
            print(f"[hint-sweep] Skipping non-existent dir: {skill_dir_root}", file=sys.stderr)
            continue
        for child in sorted(skill_dir_root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                hints = extract_hints_from_skill(child)
                if hints:
                    all_hints.extend(hints)
    return all_hints


async def validate_hints(
    hints: List[HintRecord],
    k: int = 15,
    verify_top: int = 3,
    max_llm: int = MAX_LLM_CALLS,
    json_stream: bool = False,
    task_monitor: bool = False,
) -> Dict[str, Any]:
    """Validate hints against memory lessons using KNN + LLM."""

    monitor = None
    if task_monitor and TASK_MONITOR_AVAILABLE:
        monitor = EdgeVerifierTaskClient("hint-sweep", len(hints))
        print(f"[hint-sweep] Task-monitor registered ({len(hints)} hints)", file=sys.stderr)

    stats = {"total": len(hints), "checked": 0, "contradicts": 0, "confirms": 0, "updates": 0, "irrelevant": 0, "skipped": 0, "errors": 0}
    llm_calls = 0
    skill_stats: Dict[str, Dict[str, int]] = {}

    for idx, hint in enumerate(hints):
        if llm_calls >= max_llm:
            stats["skipped"] += len(hints) - idx
            print(f"[hint-sweep] Max LLM calls reached ({max_llm}), skipping remaining", file=sys.stderr)
            break

        # Initialize per-skill stats
        if hint.skill_name not in skill_stats:
            skill_stats[hint.skill_name] = {"hints": 0, "checked": 0, "contradicts": 0, "confirms": 0, "updates": 0}
        skill_stats[hint.skill_name]["hints"] += 1

        # Score candidates
        try:
            candidates = score_candidates(hint.text, scope="", k=k)
        except Exception as e:
            print(f"[hint-sweep] Error scoring hint {hint.hint_id}: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue

        if not candidates or candidates[0].get("score", 0) < RELEVANCE_THRESHOLD:
            stats["skipped"] += 1
            continue

        # Take top candidates for LLM verification
        chosen = candidates[:verify_top]

        system_prompt = (
            "You are a Knowledge Auditor. Compare a SKILL hint (embedded documentation) "
            "against a memory lesson (learned from experience).\n\n"
            "Determine if the lesson CONTRADICTS, CONFIRMS, or UPDATES the hint.\n"
            "- contradicts: The lesson says the hint is wrong or outdated\n"
            "- confirms: The lesson validates the hint is still correct\n"
            "- updates: The lesson adds nuance/refinement to the hint\n"
            "- irrelevant: No meaningful relationship\n\n"
            'Return JSON: {"stance": "contradicts|confirms|updates|irrelevant", "weight": float 0-1, "rationale": "string"}'
        )

        reqs = []
        for cand in chosen:
            payload = {
                "task": "verify_skill_hint",
                "skill_hint": {
                    "id": hint.hint_id,
                    "skill": hint.skill_name,
                    "section": hint.section,
                    "text": hint.text[:600],
                    "type": hint.hint_type,
                },
                "memory_lesson": {
                    "id": cand.get("_key"),
                    "title": cand.get("title"),
                    "problem": (cand.get("problem") or "")[:400],
                    "solution": (cand.get("solution") or "")[:400],
                },
            }
            reqs.append({
                "model": os.getenv("CHUTES_TEXT_MODEL", "sonar-medium"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            })

        try:
            responses = await parallel_acompletions(
                reqs,
                api_base=os.getenv("SCILLM_API_BASE", "http://localhost:4001"),
                api_key=os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123"),
                custom_llm_provider="openai",
                timeout=45,
            )
            llm_calls += len(reqs)
        except Exception as e:
            print(f"[hint-sweep] LLM error for {hint.hint_id}: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue

        stats["checked"] += 1
        skill_stats[hint.skill_name]["checked"] += 1

        # Process responses and create edges
        for resp_idx, result in enumerate(responses):
            if result.get("error"):
                continue
            try:
                data = json.loads(result.get("content") or "{}")
                stance = (data.get("stance") or "irrelevant").lower()
                weight = float(data.get("weight", 0.0))
                rationale = data.get("rationale", "")
            except Exception:
                continue

            if stance not in ("contradicts", "confirms", "updates"):
                stats["irrelevant"] += 1
                continue

            stats[stance] += 1
            if hint.skill_name in skill_stats:
                skill_stats[hint.skill_name][stance] = skill_stats[hint.skill_name].get(stance, 0) + 1

            target_id = chosen[resp_idx].get("_id")
            if not target_id:
                continue

            # Map stance to edge type
            edge_type = stance  # contradicts, confirms, updates are all valid edge types

            ts = int(time.time())
            edge_doc = {
                "_from": hint.hint_id,
                "_to": target_id,
                "type": edge_type,
                "source": "hint-sweep",
                "hint_text": hint.text[:500],
                "skill_name": hint.skill_name,
                "hint_section": hint.section,
                "hint_type": hint.hint_type,
                "llm_rationale": rationale,
                "weight_llm": weight,
                "stance": stance,
                "updated_at": ts,
                "created_at": ts,
            }

            try:
                _memory_cmd([
                    "learn",
                    "--problem", f"hint-edge:{stance}:{hint.hint_id}->{target_id}",
                    "--solution", json.dumps(edge_doc),
                    "--scope", "operational",
                    "--tag", f"hint-sweep,{stance},{hint.skill_name}",
                ])
            except Exception as e:
                print(f"[hint-sweep] Edge write error: {e}", file=sys.stderr)
                stats["errors"] += 1
                continue

            if stance == "contradicts":
                print(
                    f"[CONTRADICTION] {hint.skill_name}/{hint.section}: "
                    f"{hint.text[:80]}... vs {chosen[resp_idx].get('title', '?')} "
                    f"— {rationale[:100]}",
                    file=sys.stderr,
                )

        if monitor:
            monitor.update(
                hint.hint_id,
                edges_created=1,
                candidates_scored=len(candidates),
            )

        if json_stream:
            print(json.dumps({
                "hint_id": hint.hint_id,
                "skill": hint.skill_name,
                "section": hint.section,
                "checked": True,
                "candidates": len(candidates),
            }), flush=True)

    if monitor:
        monitor.finish()

    return {"stats": stats, "per_skill": skill_stats}


app = typer.Typer(help="Hint Sweep — Validate SKILL.md hints against memory lessons")


@app.command()
def main(
    skill_dirs: str = typer.Option(None, help=""),
    skill: str = typer.Option(None, help=""),
    dry_run: bool = typer.Option(False, help="Extract hints only, no LLM validation"),
    k: int = typer.Option(15, help="KNN candidate pool size per hint"),
    verify_top: int = typer.Option(3, help="Top candidates to LLM-verify per hint"),
    max_llm: int = typer.Option(MAX_LLM_CALLS, help="Max total LLM calls"),
    task_monitor: bool = typer.Option(False, help=""),
    json_stream: bool = typer.Option(False, help="Output NDJSON per hint"),
):
    # Resolve skill directories
    if skill_dirs:
        dirs = [Path(p) for p in skill_dirs.split(":")]
    else:
        dirs = [d for d in DEFAULT_SKILL_DIRS if d.exists()]

    if not dirs:
        print("[hint-sweep] No skill directories found", file=sys.stderr)
        sys.exit(1)

    print(f"[hint-sweep] Scanning {len(dirs)} skill directories", file=sys.stderr)

    # Extract hints
    all_hints = extract_hints(dirs)

    # Filter to single skill if requested
    if skill:
        all_hints = [h for h in all_hints if h.skill_name == skill]

    print(f"[hint-sweep] Extracted {len(all_hints)} hints from {len(set(h.skill_name for h in all_hints))} skills", file=sys.stderr)

    if dry_run:
        # Print extracted hints and exit
        for h in all_hints:
            print(json.dumps(asdict(h)), flush=True)
        print(f"\n[hint-sweep] Dry run complete: {len(all_hints)} hints extracted", file=sys.stderr)
        # Summary per skill
        from collections import Counter
        by_skill = Counter(h.skill_name for h in all_hints)
        for skill, count in by_skill.most_common():
            print(f"  {skill}: {count} hints", file=sys.stderr)
        return

    if not all_hints:
        print("[hint-sweep] No hints to validate", file=sys.stderr)
        return

    # Run validation
    result = asyncio.run(validate_hints(
        hints=all_hints,
        k=k,
        verify_top=verify_top,
        max_llm=max_llm,
        json_stream=json_stream,
        task_monitor=task_monitor,
    ))

    # Print summary
    stats = result["stats"]
    print(f"\n[hint-sweep] === SWEEP COMPLETE ===", file=sys.stderr)
    print(f"  Total hints:    {stats['total']}", file=sys.stderr)
    print(f"  Checked (LLM):  {stats['checked']}", file=sys.stderr)
    print(f"  Contradicts:    {stats['contradicts']}", file=sys.stderr)
    print(f"  Confirms:       {stats['confirms']}", file=sys.stderr)
    print(f"  Updates:        {stats['updates']}", file=sys.stderr)
    print(f"  Irrelevant:     {stats['irrelevant']}", file=sys.stderr)
    print(f"  Skipped:        {stats['skipped']}", file=sys.stderr)
    print(f"  Errors:         {stats['errors']}", file=sys.stderr)

    # Per-skill summary as NDJSON
    for skill, ss in result["per_skill"].items():
        print(json.dumps({"skill": skill, **ss}), flush=True)

    if stats["contradicts"] > 0:
        print(f"\n[hint-sweep] ⚠ {stats['contradicts']} CONTRADICTIONS found — review edges with source='hint-sweep' type='contradicts'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    app()
