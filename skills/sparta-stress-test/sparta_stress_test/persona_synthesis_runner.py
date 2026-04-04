"""Bulk persona->Brandon synthesis conversation runner.

Runs Margaret Chen and Jennifer Cheung personas against EmbrySPARTAIntern
to generate cross-control synthesis questions that trigger new QRA creation
via _capture_synthesis_as_qra().

Delegates to common.persona_synthesis for the generic batch runner,
providing SPARTA-specific QuestionSources and SynthesisConfig.

Usage:
    python persona_synthesis_runner.py --count 100 --persona both
    python persona_synthesis_runner.py --dry-run --count 5 --persona margaret
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

# Ensure skills are importable
_skills_dir = str(Path(__file__).resolve().parents[2])
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

# Memory accessed via subprocess only — no sys.path hacks

# Ensure question_miner is importable
_stress_test_path = str(Path(__file__).resolve().parent)
if _stress_test_path not in sys.path:
    sys.path.insert(0, _stress_test_path)

from common.paths import SUBGRAPH_FEEDBACK_FILE
from common.persona_synthesis import (
    QuestionSource,
    SynthesisConfig,
    generate_questions,
    run_batch_synthesis as _run_batch,
)

MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory")))
MEMORY_VENV_PYTHON = str(MEMORY_ROOT / ".venv" / "bin" / "python")
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
    from dotenv import load_dotenv
    load_dotenv(MEMORY_ROOT / ".env")
except ImportError:
    pass

app = typer.Typer(add_completion=False, help="SPARTA persona synthesis runner")


# ---------------------------------------------------------------------------
# SPARTA-specific helpers (domain counting, feedback checking)
# ---------------------------------------------------------------------------

def _count_sparta_qras() -> int:
    """Count current QRAs via /memory count subprocess."""
    try:
        result = _memory_cmd(["count", "--scope", "brandon_bailey"])
        return result.get("count", -1)
    except Exception as e:
        logger.debug(f"QRA count failed: {e}")
    return -1


def _check_feedback_file() -> int:
    """Count entries in subgraph_feedback.jsonl."""
    if not SUBGRAPH_FEEDBACK_FILE.exists():
        return 0
    return sum(1 for line in SUBGRAPH_FEEDBACK_FILE.read_text().splitlines() if line.strip())


# ---------------------------------------------------------------------------
# SPARTA-specific QuestionSource generators
# ---------------------------------------------------------------------------

def _generate_direct_cross_control(persona_name: str, n: int) -> List[Dict[str, Any]]:
    """Generate cross-control synthesis questions directly from QRA corpus.

    No LLM calls needed. Mines pairs from /memory sample and builds natural
    questions that combine them, ensuring multi-QRA retrieval paths.
    """
    try:
        result = _memory_cmd([
            "sample", "--scope", "brandon_bailey", "--k", str(n * 3),
        ])
        docs = result.get("items", result.get("results", []))
    except Exception as e:
        logger.error(f"Direct question generation failed: {e}")
        return []

    if not docs:
        return []

    random.shuffle(docs)
    pairs = []
    for i in range(0, len(docs) - 1, 2):
        a, b = docs[i], docs[i + 1]
        a_ctrl = a.get("control_id", a.get("_key", ""))
        b_ctrl = b.get("control_id", b.get("_key", ""))
        if a_ctrl != b_ctrl:
            pairs.append((a, b))
        if len(pairs) >= n:
            break

    templates = [
        "How does {ctrl_a} relate to {ctrl_b} in terms of space system defense?",
        "What is the relationship between {ctrl_a} and {ctrl_b} for protecting spacecraft?",
        "If an attacker exploits weaknesses covered by {ctrl_a}, how does {ctrl_b} provide defense-in-depth?",
        "Compare the defensive approaches of {ctrl_a} and {ctrl_b} for satellite security.",
        "How should {ctrl_a} and {ctrl_b} be implemented together to address {topic_a}?",
        "What gaps exist between {ctrl_a} and {ctrl_b} regarding {topic_b}?",
        "Explain how {ctrl_a} addresses {topic_a} and how {ctrl_b} complements it.",
        "What attack vectors span both {ctrl_a} and {ctrl_b}?",
        "How do countermeasures in {ctrl_a} interact with those in {ctrl_b}?",
        "What are the cross-domain implications of {ctrl_a} and {ctrl_b} for ground station security?",
    ]

    questions = []
    for i, (a, b) in enumerate(pairs):
        template = random.choice(templates)
        raw_a = a.get("question", "cybersecurity")
        raw_b = b.get("question", "threat mitigation")
        topic_a = raw_a.split("?")[0].split(".")[0][:80].strip()
        topic_b = raw_b.split("?")[0].split(".")[0][:80].strip()

        a_ctrl = a.get("control_id", a.get("_key", "unknown"))
        b_ctrl = b.get("control_id", b.get("_key", "unknown"))
        q_text = template.format(
            ctrl_a=a_ctrl, ctrl_b=b_ctrl,
            topic_a=topic_a, topic_b=topic_b,
        )
        qid = hashlib.sha256(q_text.encode()).hexdigest()[:12]
        questions.append({
            "id": f"synth-{qid}",
            "question": q_text,
            "persona": persona_name or "Margaret Chen",
            "expected_action": "QUERY",
            "difficulty": "complex",
            "source": "direct_cross_control",
            "target_control": a_ctrl,
            "bridge_tags": list(set((a.get("tags") or []) + (b.get("tags") or []))),
        })

    logger.info(f"Generated {len(questions)} direct cross-control questions")
    return questions


def _generate_via_scillm(persona_name: str, n: int) -> List[Dict[str, Any]]:
    """Generate questions via scillm (Source B). Requires API quota."""
    from question_miner import mine_sparta_qras, _get_db

    db = _get_db()
    questions = mine_sparta_qras(db, limit=n * 2)
    if persona_name:
        questions = [q for q in questions if q.get("persona") == persona_name]
    return questions[:n]


# ---------------------------------------------------------------------------
# Build SPARTA SynthesisConfig
# ---------------------------------------------------------------------------

def build_sparta_config(
    persona: str = "both",
    use_llm: bool = False,
) -> SynthesisConfig:
    """Build SynthesisConfig with SPARTA-specific sources.

    Args:
        persona: "margaret", "jennifer", or "both"
        use_llm: Use scillm for question generation (Source B)

    Returns:
        SynthesisConfig ready for run_batch_synthesis()
    """
    from brandon_simulacrum import EmbrySPARTAIntern
import httpx

    embry = EmbrySPARTAIntern(client_scope="sparta")

    sources = [
        QuestionSource("direct_cross_control", 0.70, _generate_direct_cross_control),
    ]
    if use_llm:
        sources.append(QuestionSource("scillm_source_b", 0.30, _generate_via_scillm))

    return SynthesisConfig(
        respond_fn=embry.respond,
        scope="brandon_bailey",
        question_sources=sources,
        count_fn=_count_sparta_qras,
        feedback_check_fn=_check_feedback_file,
        batch_log_interval=50,
    )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def generate_synthesis_questions(
    n: int,
    persona: str = "both",
    use_llm: bool = False,
) -> List[Dict[str, Any]]:
    """Generate cross-control synthesis questions.

    Backward-compatible wrapper around common.persona_synthesis.generate_questions.
    """
    personas_cycle = []
    if persona in ("margaret", "both"):
        personas_cycle.append("Margaret Chen")
    if persona in ("jennifer", "both"):
        personas_cycle.append("Jennifer Cheung")

    all_questions: List[Dict[str, Any]] = []
    for p in personas_cycle:
        if use_llm:
            qs = _generate_via_scillm(p, n)
        else:
            qs = _generate_direct_cross_control(p, n)
        all_questions.extend(qs)

    return all_questions


def run_batch_synthesis(
    questions: List[Dict[str, Any]],
    batch_size: int = 50,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run batch synthesis — delegates to common.persona_synthesis."""
    config = build_sparta_config()
    config.batch_log_interval = batch_size
    return _run_batch(questions, config, output_path=output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@app.command()
def run(
    persona: str = typer.Option("both", help="margaret, jennifer, or both"),
    count: int = typer.Option(100, help="Questions per persona"),
    batch_size: int = typer.Option(50, help="Progress log interval"),
    dry_run: bool = typer.Option(False, help="Mine questions only"),
    use_llm: bool = typer.Option(False, help="Use scillm for question generation"),
    output: Optional[str] = typer.Option(None, help="Output JSONL path"),
):
    """Run bulk persona->Brandon synthesis conversations."""
    logger.info(f"Generating {count} questions per persona ({persona})")
    questions = generate_synthesis_questions(count, persona, use_llm=use_llm)
    logger.info(f"Mined {len(questions)} questions")

    if dry_run:
        for i, q in enumerate(questions):
            print(f"{i+1}. [{q.get('persona', '?')}] {q.get('question', '')}")
        print(f"\n{len(questions)} questions mined (dry run, no conversations run)")
        return

    output_path = Path(output) if output else None
    summary = run_batch_synthesis(questions, batch_size=batch_size, output_path=output_path)
    print("\n=== Synthesis Run Summary ===")
    print(json.dumps(summary, indent=2))


def main():
    app()


if __name__ == "__main__":
    main()
