"""Stress test runner — orchestrates intent → answer → grade.

Two answer paths:
  1. SPARTA compliance (Brandon) — QRA retrieval via /memory recall
  2. Code/pipeline (Nico→Embry) — /recommend-skill-chain → invoke skills → synthesize

Routes each question through the appropriate pipeline and collects
graded results for reporting.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from . import grader

SKILLS_ROOT = Path(__file__).resolve().parents[2]
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
RECOMMEND_RUN = str(SKILLS_ROOT / "recommend-skill-chain" / "run.sh")
ASSISTANT_RUN = str(SKILLS_ROOT / "assistant" / "run.sh")
ORCHESTRATE_RUN = str(SKILLS_ROOT / "orchestrate" / "run.sh")


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
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
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

def _get_intent_mapper():
    """Lazy-load the IntentMapper from graph_memory."""
    try:
        from graph_memory.intent import IntentMapper
        mapper = IntentMapper(persona_id="brandon_bailey")
        return mapper
    except Exception as e:
        logger.warning(f"IntentMapper unavailable: {e}")
        return None


def _get_nlg_synthesizer():
    """Lazy-load NLG synthesis for Brandon responses."""
    try:
        from persona.bridge.disambiguation.nlg import synthesize_brandon_response
        return synthesize_brandon_response
    except ImportError:
        logger.debug("NLG synthesis not available — using raw QRA answers")
        return None


def _skill_cmd(run_sh: str, args: list, timeout: int = 30) -> dict | None:
    """Invoke a sibling skill via subprocess, parse JSON output.

    Strips VIRTUAL_ENV and PYTHONPATH so sibling skills use their own
    uv environment instead of inheriting the caller's venv.
    """
    try:
        env = {k: v for k, v in os.environ.items()
               if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        # Strip .venv/bin from PATH so sibling skills don't inherit caller's venv
        env["PATH"] = ":".join(
            p for p in env.get("PATH", "").split(":") if ".venv" not in p
        )
        # Run in the skill's own directory so `python3 -m src.cli` finds
        # the skill's src/, not the caller's src/ via CWD.
        skill_dir = str(Path(run_sh).resolve().parent)
        result = subprocess.run(
            [run_sh] + [str(a) for a in args],
            capture_output=True, text=True, timeout=timeout,
            env=env, cwd=skill_dir,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return None
        idx = stdout.find("{")
        if idx < 0:
            idx = stdout.find("[")
        if idx < 0:
            return None
        raw = stdout[idx:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Output may have trailing text or multiple JSON objects —
            # use the decoder to grab the first valid object.
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(raw)
            return obj
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.debug(f"skill invocation failed: {e}")
        return None


def _is_code_question(question: dict) -> bool:
    """Detect if this is a code/pipeline question (Nico's domain), not SPARTA."""
    category = question.get("category", "")
    if category in ("code", "pipeline"):
        return True
    persona = question.get("persona", "")
    if persona == "Nico Bailon":
        return True
    return False


def _classify_code_question(question: dict) -> dict:
    """Intent classification for code/pipeline questions.

    Code questions route through /recommend-skill-chain, not QRA retrieval.
    """
    q_text = question.get("question", "")
    target_file = question.get("target_file", "")

    # Flawed: referencing nonexistent files/steps
    if target_file and "nonexistent" in target_file.lower():
        return {
            "action": "NO_MATCH", "scope": "code",
            "persona_guidance": (
                f"'{target_file}' does not exist in the codebase. "
                f"Check the pipeline step naming convention (s00-s14)."
            ),
        }

    # Flawed: referencing removed features
    removed_features = {"duckdb", "pipeline.duckdb", "s07b"}
    q_lower = q_text.lower()
    for removed in removed_features:
        if removed in q_lower and "current" in q_lower:
            return {
                "action": "NO_MATCH", "scope": "code",
                "persona_guidance": (
                    f"DuckDB was removed from the pipeline. "
                    f"S07 now uses json_assembler producing assembled_content.json."
                ),
            }

    # Ambiguous: too vague to answer
    if len(q_text.split()) < 7 and not target_file:
        return {
            "action": "CLARIFY", "scope": "code",
            "suggested_questions": [
                "Which pipeline step or module are you asking about?",
                "Are you asking about code structure, convergence metrics, or behavior?",
            ],
            "persona_guidance": (
                "Could you be more specific? Which file, step, or module "
                "are you asking about?"
            ),
        }

    return {"action": "QUERY", "scope": "code"}


def _ask_embry_via_skill_chain(question: dict) -> Optional[dict]:
    """Answer code/pipeline questions the way the project agent does it.

    Mirrors the standard human↔agent interaction pattern:
    1. /recommend-skill-chain — what skills answer this question?
    2. /assistant validate — Shadow-LEGO cascade scores the chain
    3. Invoke recommended skills sequentially
    4. /assistant synthesize — produce a coherent answer from skill outputs

    No QRAs. No evidence cases. This is the project agent (as Embry)
    answering Nico's code questions using whatever skills are available.
    """
    q_text = question.get("question", "")
    target_file = question.get("target_file", "")
    target_module = question.get("target_module", "")

    # Step 1: /recommend-skill-chain — ask what skills to use
    task_desc = f"{q_text[:200]}"
    if target_file:
        task_desc = f"about {target_file}: {task_desc}"

    chain_result = _skill_cmd(RECOMMEND_RUN, [
        "recommend", "--task", task_desc, "--limit", "3", "--json",
    ], timeout=30)

    recommended_chain = []
    chain_confidence = 0.0
    chain_reason = ""
    if chain_result and isinstance(chain_result, dict):
        recs = chain_result.get("recommendations", [])
        if recs:
            # Prefer classifier (tier 0.5) over cold_start heuristic.
            # The Markov chain returns "consume-music" at conf=1.0 when
            # untrained — the classifier's skill chain is more useful.
            top = recs[0]
            for rec in recs:
                reason = rec.get("reason", "")
                chain = rec.get("chain", [])
                # Skip broken results (error dicts, cold_start nonsense)
                if any("error" in str(c) for c in chain):
                    continue
                if "cold_start" in reason:
                    continue
                # Accept first non-broken recommendation
                top = rec
                break
            recommended_chain = top.get("chain", [])
            chain_confidence = top.get("confidence", 0.0)
            chain_reason = top.get("reason", "")
            logger.info(
                "recommend-skill-chain: {} (conf={:.2f}, tier={}, reason={})",
                recommended_chain, chain_confidence,
                top.get("tier", "?"), chain_reason[:60],
            )

    # Step 2: Invoke each skill in the recommended chain
    answer_parts = []
    source_skills = []

    for skill_name in recommended_chain:
        clean = skill_name.lstrip("/")
        skill_run = SKILLS_ROOT / clean / "run.sh"
        if not skill_run.exists():
            logger.debug(f"skill {clean} not found at {skill_run}")
            continue

        # Build skill-appropriate args
        args = _build_skill_args_for_question(clean, q_text, target_file)
        resp = _skill_cmd(str(skill_run), args, timeout=30)

        if resp:
            # Extract answer from whatever the skill returns
            text = _extract_skill_answer(resp)
            if text:
                answer_parts.append(text)
                source_skills.append(clean)

    # Step 3: For pipeline/analytics questions, try domain-specific skills
    # before the generic memory fallback
    if not answer_parts:
        category = question.get("category", "")
        q_lower = q_text.lower()
        is_analytics = category == "pipeline" or any(
            kw in q_lower for kw in (
                "convergence", "trend", "degrading", "pass", "fail",
                "verdict", "dimension", "remediation", "score",
            )
        )
        if is_analytics:
            # Try /extractor-quality-check status for live pipeline data
            eqc_run = SKILLS_ROOT / "extractor-quality-check" / "run.sh"
            if eqc_run.exists():
                resp = _skill_cmd(str(eqc_run), ["status", "--json"], timeout=30)
                if resp:
                    text = _extract_skill_answer(resp)
                    if text:
                        answer_parts.append(text)
                        source_skills.append("extractor-quality-check")

            # Try /review-pdf for dimension-specific data
            rpdf_run = SKILLS_ROOT / "review-pdf" / "run.sh"
            if rpdf_run.exists() and not answer_parts:
                resp = _skill_cmd(str(rpdf_run), ["summary", "--json"], timeout=30)
                if resp:
                    text = _extract_skill_answer(resp)
                    if text:
                        answer_parts.append(text)
                        source_skills.append("review-pdf")

    # Step 4: Fall back to /memory recall (the agent always has memory)
    if not answer_parts:
        for scope in ("nico-bailon", "extractor", "datalake_pdf", "embry-lawson"):
            try:
                mem_result = _memory_cmd([
                    "recall", "--q", q_text[:200],
                    "--scope", scope, "--k", "5",
                ])
                items = mem_result.get("items", mem_result.get("results", []))
                for item in items[:3]:
                    sol = item.get("solution", item.get("text", ""))
                    if sol and len(sol) > 20:
                        answer_parts.append(sol[:300])
                        source_skills.append(f"memory/{scope}")
                if answer_parts:
                    break
            except Exception:
                continue

    if not answer_parts:
        return {
            "answered": False,
            "answer_text": f"No information found for: {q_text[:80]}",
            "source_skills": [],
            "skill_count": 0,
            "recommended_chain": recommended_chain,
            "source_qra_keys": [],
            "qra_count": 0,
            "sparta_techniques": [],
            "sparta_countermeasures": [],
        }

    # Step 5: Synthesize — combine skill outputs into a coherent answer
    prefix = f"Regarding {target_file}: " if target_file else ""
    answer_text = prefix + "\n\n".join(answer_parts)

    return {
        "answered": True,
        "answer_text": answer_text,
        "source_skills": source_skills,
        "skill_count": len(source_skills),
        "recommended_chain": recommended_chain,
        "chain_confidence": chain_confidence,
        # Compatibility fields (no QRAs for code questions)
        "source_qra_keys": [],
        "qra_count": 0,
        "sparta_techniques": [],
        "sparta_countermeasures": [],
    }


def _build_skill_args_for_question(
    skill_name: str, question: str, target_file: str,
) -> list[str]:
    """Build CLI args appropriate for each skill type.

    Each skill has its own CLI interface — we map the question
    into the right flags/subcommands.
    """
    q = question[:200]

    # Skills with known CLI patterns
    if skill_name == "treesitter":
        # treesitter needs a file path — try to find the target
        # Note: --json does NOT exist (output is always JSON).
        # Without --content, returns {name, kind, signature, docstring} per function.
        # With --content, returns full source code per function (can be large).
        if target_file:
            _workspace = SKILLS_ROOT.parents[2]
            for root in (
                _workspace / "extractor" / "src",
                SKILLS_ROOT,
            ):
                for match in root.glob(f"**/{target_file}"):
                    # No --content: get function signatures + docstrings (lightweight)
                    return ["symbols", str(match)]
        return ["scan", str(SKILLS_ROOT.parents[2] / "extractor" / "src")]

    if skill_name == "memory":
        return ["recall", "--q", q, "--scope", "nico-bailon", "--k", "5"]

    if skill_name in ("analytics", "extractor-quality-check"):
        return ["status", "--json"]

    if skill_name == "review-pdf":
        return ["check", "--query", q, "--json"]

    if skill_name == "assess":
        return ["run", ".", "--output", "/dev/stdout"]

    if skill_name == "dogpile":
        return ["search", q]

    # Generic: most skills accept a positional or --query arg
    return ["--query", q]


def _extract_skill_answer(resp: dict | list) -> str:
    """Extract the useful answer text from a skill's JSON response."""
    if isinstance(resp, list):
        # Treesitter array: [{kind, name, signature, docstring}, ...]
        # Or generic array of items
        items = resp[:15]
        parts = []
        for item in items:
            if isinstance(item, dict):
                # Treesitter symbol format
                if item.get("kind") and item.get("name"):
                    sig = item.get("signature", "")
                    doc = item.get("docstring", "")
                    line = f"{item['kind']} {item['name']}"
                    if sig:
                        line += f": {sig[:80]}"
                    if doc:
                        line += f" — {doc[:80]}"
                    parts.append(line)
                else:
                    name = item.get("name", item.get("_key", ""))
                    kind = item.get("kind", item.get("type", ""))
                    text = item.get("text", item.get("solution", item.get("content", "")))
                    if name:
                        parts.append(f"{kind} {name}" if kind else name)
                    elif text:
                        parts.append(str(text)[:100])
            else:
                parts.append(str(item)[:100])
        return "\n".join(parts) if parts else ""

    if isinstance(resp, dict):
        # Treesitter single-symbol output: {kind, name, signature, docstring, content}
        if resp.get("kind") and resp.get("name"):
            parts = []
            if resp.get("docstring"):
                parts.append(resp["docstring"][:300])
            if resp.get("signature"):
                parts.append(f"Signature: {resp['signature']}")
            # Prefer docstring over dumping entire content
            if parts:
                return "\n".join(parts)
            # Last resort: truncated content
            if resp.get("content"):
                return resp["content"][:500]

        # Try common response fields
        for key in ("answer", "result", "output", "summary", "text", "solution"):
            val = resp.get(key)
            if val:
                if isinstance(val, str):
                    return val[:500]
                if isinstance(val, dict):
                    return json.dumps(val, default=str)[:500]
                if isinstance(val, list):
                    return json.dumps(val[:5], default=str)[:500]

        # Try symbols list (treesitter output)
        symbols = resp.get("symbols", [])
        if symbols:
            names = []
            for s in symbols[:15]:
                n = s.get("name", "") if isinstance(s, dict) else str(s)
                k = s.get("kind", "") if isinstance(s, dict) else ""
                if n:
                    names.append(f"{k} {n}" if k else n)
            return f"Symbols found: {', '.join(names)}"

        # Try items list (memory output)
        items = resp.get("items", resp.get("results", []))
        if items:
            parts = []
            for item in items[:3]:
                sol = item.get("solution", item.get("text", ""))
                if sol:
                    parts.append(str(sol)[:200])
            return "\n".join(parts) if parts else ""

    return ""


def _ask_brandon_via_qra(question: dict) -> Optional[dict]:
    """Look up QRAs via /memory recall subprocess (BM25 + vector + graph)."""
    try:
        ctrl_id = question.get("target_control", "")
        q_text = question.get("question", "")
        search_query = f"{ctrl_id} {q_text}" if ctrl_id else q_text

        if not search_query.strip():
            return None

        result = _memory_cmd([
            "recall", "--q", search_query,
            "--scope", "brandon_bailey",
            "--k", "10",
        ])

        qras = result.get("items", result.get("results", []))

        if not qras:
            return {
                "answered": False,
                "answer_text": f"No QRAs found for {ctrl_id or 'query'}",
                "source_qra_keys": [],
                "qra_count": 0,
                "sparta_techniques": [],
                "sparta_countermeasures": [],
                "search_scores": [],
            }

        answer_parts = []
        source_keys = []
        all_techniques = []
        all_cms = []
        search_scores = []

        for qra in qras[:5]:
            if qra.get("answer") or qra.get("solution"):
                answer_parts.append((qra.get("answer") or qra.get("solution", ""))[:300])
                source_keys.append(qra.get("_key", ""))
            search_scores.append({
                "key": qra.get("_key", ""),
                "score": qra.get("score", qra.get("_score", 0)),
                "bm25": qra.get("bm25_score", 0),
                "dense": qra.get("similarity_score", 0),
            })
            if ctrl_id and qra.get("control_id") == ctrl_id:
                for t in (qra.get("sparta_techniques") or []):
                    tid = t.get("id", "") if isinstance(t, dict) else str(t)
                    if tid and tid not in all_techniques:
                        all_techniques.append(tid)
                for cm in (qra.get("sparta_countermeasures") or []):
                    cmid = cm.get("id", "") if isinstance(cm, dict) else str(cm)
                    if cmid and cmid not in all_cms:
                        all_cms.append(cmid)

        # Compose answer: prefix with control ID for name_match grading,
        # join with newlines (not pipes) for response_naturalness.
        prefix = f"Regarding {ctrl_id}: " if ctrl_id else ""
        answer_text = prefix + "\n\n".join(answer_parts)

        return {
            "answered": True,
            "answer_text": answer_text,
            "source_qra_keys": source_keys,
            "qra_count": len(qras),
            "sparta_techniques": all_techniques,
            "sparta_countermeasures": all_cms,
            "search_scores": search_scores,
        }
    except Exception as e:
        logger.warning(f"QRA lookup failed: {e}")
        return None


from .control_validation import (
import httpx
    CONTROL_PATTERN as _CONTROL_PATTERN,
    validate_control_id as _validate_control_id,
    find_closest_control as _find_closest_control,
    classify_without_mapper as _classify_without_mapper,
    get_valid_prefixes,
)


def run_single(
    question: dict,
    mapper=None,
    nlg_fn=None,
) -> dict:
    """Run a single question through the full pipeline and grade it.

    Routes to the correct answer path:
      - SPARTA compliance (Brandon persona) → QRA retrieval
      - Code/pipeline (Nico persona) → /recommend-skill-chain → invoke → synthesize

    Returns dict with question, intent_result, answer, nlg_response, and grade.
    """
    start = time.monotonic()
    is_code = _is_code_question(question)

    # Step 1: Intent classification (different classifiers per domain)
    if is_code:
        intent_result = _classify_code_question(question)
    elif mapper:
        intent_result = mapper.infer(question["question"])
    else:
        intent_result = _classify_without_mapper(question)

    # Step 1b: Validate control ID for SPARTA questions only
    if not is_code:
        ctrl = question.get("target_control") or ""
        if ctrl and intent_result.get("action") == "QUERY":
            invalid = _validate_control_id(ctrl)
            if invalid:
                intent_result = invalid

    action = intent_result.get("action", "QUERY")

    # Step 2: Route to the correct answer path
    answer = None
    nlg_response = None

    if action == "QUERY":
        if is_code:
            # Nico's code questions: /recommend-skill-chain → invoke → synthesize
            answer = _ask_embry_via_skill_chain(question)
        else:
            # Brandon's SPARTA questions: QRA retrieval via /memory
            answer = _ask_brandon_via_qra(question)

            # Post-retrieval reclassification for SPARTA
            ctrl = question.get("target_control") or ""
            if ctrl and answer and not answer.get("answered"):
                action = "NO_MATCH"
                intent_result["action"] = "NO_MATCH"
                closest = _find_closest_control(ctrl)
                intent_result["persona_guidance"] = (
                    f"I couldn't find any information about '{ctrl}'. "
                    f"Did you mean {closest}? "
                    f"Valid control families: {', '.join(sorted(get_valid_prefixes()))}."
                ) if closest else f"'{ctrl}' doesn't match any known SPARTA control."

            # NLG synthesis for SPARTA answers
            if answer and answer.get("answered") and nlg_fn:
                try:
                    nlg_response = nlg_fn(
                        question=question["question"],
                        qras=answer,
                        persona_id="brandon_bailey",
                    )
                except Exception as e:
                    logger.debug(f"NLG synthesis failed: {e}")

    elif action == "CLARIFY":
        pass  # Disambiguation handled by intent_result persona_guidance

    elif action == "NO_MATCH":
        pass  # Error detection handled by intent_result

    # Step 3: Grade via full cascade (Tier 0 → 0.5 → 1.5 → 2)
    # grade_via_cascade falls back to heuristic-only if /assistant unavailable
    grade_result = grader.grade_via_cascade(
        question=question,
        intent_result=intent_result,
        answer=answer,
        nlg_response=nlg_response,
    )

    elapsed = time.monotonic() - start

    # Extract citation data for downstream consumers
    qra_count = 0
    source_keys = []
    answer_text = ""
    source_skills = []
    if answer and isinstance(answer, dict):
        qra_count = answer.get("qra_count", 0)
        source_keys = answer.get("source_qra_keys", [])
        answer_text = answer.get("answer_text", "")
        source_skills = answer.get("source_skills", [])

    grade_result["qra_citations_total"] = qra_count

    # Build minimal turns structure for review-conversation/conversation-lab
    turns = []
    if answer_text or qra_count or source_skills:
        turns.append({
            "turn_number": 1,
            "role": "user",
            "content": question["question"],
        })
        metadata = {
            "qra_count": qra_count,
            "source_keys": source_keys,
            "techniques": answer.get("sparta_techniques", []) if answer else [],
            "countermeasures": answer.get("sparta_countermeasures", []) if answer else [],
        }
        if source_skills:
            metadata["source_skills"] = source_skills
            metadata["recommended_chain"] = answer.get("recommended_chain", [])
        turns.append({
            "turn_number": 2,
            "role": "assistant",
            "content": answer_text[:500] if answer_text else "(no answer)",
            "action": action,
            "metadata": metadata,
        })

    return {
        "question_id": question.get("id", "?"),
        "question_text": question["question"][:100],
        "difficulty": question.get("difficulty", "unknown"),
        "persona": question.get("persona", "unknown"),
        "category": question.get("category", "sparta"),
        "expected_action": question.get("expected_action", "QUERY"),
        "actual_action": action,
        "target_control": question.get("target_control"),
        "target_file": question.get("target_file"),
        "grade": grade_result.get("grade", "?"),
        "composite": grade_result.get("composite", 0),
        "scores": grade_result.get("scores", {}),
        "tier": grade_result.get("tier", 0),
        "source": grade_result.get("source", "heuristic"),
        "confidence": grade_result.get("confidence"),
        "latency_ms": grade_result.get("latency_ms"),
        "cascade_failed": grade_result.get("cascade_failed"),
        "turns": turns,
        "source_keys": source_keys,
        "source_skills": source_skills,
        "qra_count": qra_count,
        "elapsed_s": round(elapsed, 3),
        "had_nlg": nlg_response is not None,
        "had_answer": answer is not None and answer.get("answered", False),
    }


def run_batch(
    questions: list[dict],
    verbose: bool = False,
) -> list[dict]:
    """Run a batch of questions through the pipeline.

    Initializes the mapper and NLG once, then runs all questions.
    """
    mapper = _get_intent_mapper()
    nlg_fn = _get_nlg_synthesizer()

    if not mapper:
        logger.warning("IntentMapper not available — using fallback routing")
    if not nlg_fn:
        logger.info("NLG synthesis not available — grading raw QRA answers")

    results = []
    for i, question in enumerate(questions):
        result = run_single(question, mapper=mapper, nlg_fn=nlg_fn)
        results.append(result)

        if verbose or result["grade"] in ("C", "F"):
            logger.info(
                f"[{i+1}/{len(questions)}] {result['grade']} "
                f"({result['composite']:.0%}) "
                f"tier={result['tier']} {result['source']:>10} "
                f"{result['difficulty']:>9} "
                f"{result['expected_action']:>8}→{result['actual_action']:>8} "
                f"{result['question_text'][:60]}"
            )
        elif (i + 1) % 50 == 0:
            logger.info(f"Progress: {i+1}/{len(questions)}")

    return results


def save_results(results: list[dict], output_path: Path):
    """Save results to JSONL for later analysis."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")
    logger.info(f"Results saved to {output_path} ({len(results)} entries)")
