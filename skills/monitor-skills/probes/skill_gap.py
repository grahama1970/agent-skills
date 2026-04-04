"""Skill gap detection via Shadow-LEGO cascade.

Detects skills that *should exist but don't* by mining transcripts and
episodic archives for unserved user requests, then running a 3-tier
cascade (heuristic → classifier → teacher) to validate gap proposals.

Delegates to existing modules — NO reimplementation:
    chain_miner.mine_sessions      — transcript mining
    gap_detector.detect_gaps       — heuristic gap detection
    transition_matrix              — missing skill detection
    gap_synthesizer._tier_scillm   — LLM teacher
    energy_model + bond_predictor  — elegance scoring
    common.cascade.CascadeRunner   — cascade orchestration

Usage:
    python -m probes.skill_gap gap-scan --dry-run --json
    python -m probes.skill_gap gap-status
"""
from __future__ import annotations
import os

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Path setup — add skill-lab/scripts and common to sys.path
# ---------------------------------------------------------------------------
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SKILL_LAB_SCRIPTS = SKILLS_DIR / "skill-lab" / "scripts"
STATE_DIR = Path.home() / ".pi" / "monitor-skills"

# State files
GAP_LABELS_FILE = STATE_DIR / "gap_labels.jsonl"
GAP_PROPOSALS_FILE = STATE_DIR / "gap_proposals.jsonl"
GAP_SHADOW_FILE = STATE_DIR / "gap_shadow.jsonl"
GAP_SEEN_HASHES_FILE = STATE_DIR / "gap_seen_hashes.json"
GAP_STATE_FILE = STATE_DIR / "task_state_gap.json"


def _ensure_imports():
    """Lazily add skill-lab/scripts and common to sys.path.

    NOTE: skill-lab/scripts modules (chain_miner, gap_detector, etc.) do not
    have CLI wrappers yet.  Once skill-lab exposes these via run.sh subcommands,
    this sys.path shim should be replaced with subprocess calls.  Tracked in
    best-practices-skills/SKILL.md under 'ArangoDB Access Policy' (same
    principle: delegate to the owning skill's CLI).
    """
    for p in [str(SKILL_LAB_SCRIPTS), str(SKILLS_DIR)]:
        if p not in sys.path:
            sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Phase 1: Mine unserved requests from transcripts
# ---------------------------------------------------------------------------

def mine_unserved_requests(
    skills_root: Path | None = None,
    max_sessions: int = 200,
) -> list[dict]:
    """Extract sessions where no skill was invoked or user expressed frustration.

    Delegates to chain_miner.mine_sessions(min_skills=0).
    """
    _ensure_imports()
    try:
        from chain_miner import mine_sessions  # type: ignore[import-untyped]
    except ImportError as e:
        logger.warning(f"chain_miner not available: {e}")
        return []

    root = skills_root or SKILLS_DIR
    try:
        sessions = mine_sessions(root, min_skills=0, max_sessions=max_sessions)
    except Exception as e:
        logger.warning(f"mine_sessions failed: {e}")
        return []

    # Filter to sessions with 0 skills or frustration markers
    frustration_markers = {"failed", "error", "can't", "doesn't work", "broken", "wrong"}
    unserved = []
    for session in sessions:
        skill_count = len(session.get("skills", []))
        request = session.get("user_request", "") or session.get("request", "")
        request_lower = request.lower()

        if skill_count == 0 or any(m in request_lower for m in frustration_markers):
            unserved.append({
                "request": request,
                "skills": session.get("skills", []),
                "skill_count": skill_count,
                "source": "transcript",
                "session_id": session.get("session_id", ""),
            })

    logger.info(f"Mined {len(unserved)} unserved requests from {len(sessions)} sessions")
    return unserved


# ---------------------------------------------------------------------------
# Phase 2: Query episodic archives for abandoned sessions
# ---------------------------------------------------------------------------

def query_episodic_gaps(max_results: int = 50) -> list[dict]:
    """Find abandoned/failed sessions via memory daemon Unix socket."""
    import httpx

    queries = [
        "sessions where user request was not fulfilled",
        "abandoned tasks with unresolved errors",
        "conversations where no skill was invoked",
    ]

    results = []
    for query in queries:
        try:
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                resp = client.post("/recall", json={"q": query, "k": 20})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", data.get("results", []))
                    for item in items[:max_results]:
                        content = item.get("content", "") or item.get("text", "")
                        if content:
                            results.append({
                                "request": content[:500],
                                "source": "episodic",
                                "query": query,
                                "score": item.get("score", 0),
                            })
        except Exception as e:
            logger.debug(f"Episodic query failed: {e}")

    logger.info(f"Found {len(results)} episodic gap candidates")
    return results


# ---------------------------------------------------------------------------
# Phase 3: Deduplication
# ---------------------------------------------------------------------------

def _hash_request(request: str) -> str:
    """SHA-256 hash of normalized request."""
    normalized = " ".join(request.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _load_seen_hashes() -> set[str]:
    """Load previously seen request hashes."""
    if GAP_SEEN_HASHES_FILE.exists():
        try:
            return set(json.loads(GAP_SEEN_HASHES_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_seen_hashes(hashes: set[str]) -> None:
    """Persist seen hashes."""
    GAP_SEEN_HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    GAP_SEEN_HASHES_FILE.write_text(json.dumps(sorted(hashes)))


def deduplicate(requests: list[dict], seen: set[str] | None = None) -> list[dict]:
    """Remove already-processed requests and internal duplicates."""
    if seen is None:
        seen = _load_seen_hashes()

    unique = []
    encountered: set[str] = set()
    for req in requests:
        h = _hash_request(req.get("request", ""))
        if h not in seen and h not in encountered:
            encountered.add(h)
            req["input_hash"] = h
            unique.append(req)

    logger.info(f"Deduplicated {len(requests)} → {len(unique)} requests")
    return unique


# ---------------------------------------------------------------------------
# Phase 4: Cascade tiers
# ---------------------------------------------------------------------------

def tier0_gap_heuristic(input_data: Any, **kwargs) -> Any:
    """Tier 0: heuristic gap detection via gap_detector + transition_matrix."""
    _ensure_imports()
    from common.cascade import TierResult  # type: ignore[import-untyped]

    request = input_data.get("request", "") if isinstance(input_data, dict) else str(input_data)
    if not request:
        return None

    gaps_found = []
    confidence = 0.0

    # Delegate to gap_detector.detect_gaps
    try:
        from gap_detector import detect_gaps  # type: ignore[import-untyped]
        from scan_soup import scan_soup  # type: ignore[import-untyped]
        graph = scan_soup(SKILLS_DIR)
        gap_result = detect_gaps(request, graph)
        if gap_result.get("create"):
            gaps_found.extend(gap_result["create"])
            coverage = gap_result.get("coverage", 0)
            confidence = max(confidence, 1.0 - coverage)
    except Exception as e:
        logger.debug(f"gap_detector failed: {e}")

    # Delegate to transition_matrix.detect_missing_skills
    try:
        from transition_matrix import detect_missing_skills  # type: ignore[import-untyped]
        tm_result = detect_missing_skills(request)
        if tm_result.get("missing_positions"):
            for pos in tm_result["missing_positions"]:
                gaps_found.append(pos.get("expected_skill", f"position-{pos.get('position', '?')}"))
            confidence = max(confidence, tm_result.get("confidence", 0.0))
    except Exception as e:
        logger.debug(f"transition_matrix failed: {e}")

    if not gaps_found:
        return None

    return TierResult(
        result={"gaps": gaps_found, "request": request},
        confidence=confidence,
        source="heuristic",
    )


def tier05_gap_classifier(input_data: Any, **kwargs) -> Any:
    """Tier 0.5: sklearn RF classifier on gap features."""
    _ensure_imports()
    from common.cascade import TierResult  # type: ignore[import-untyped]

    classifier_path = SKILLS_DIR / "skill-lab" / "state" / "gap_classifier.pkl"
    if not classifier_path.exists():
        return None  # No trained model yet — skip tier

    request = input_data.get("request", "") if isinstance(input_data, dict) else str(input_data)
    if not request:
        return None

    try:
        import pickle
        with open(classifier_path, "rb") as f:
            model = pickle.load(f)  # noqa: S301

        # Build feature vector from request metadata
        features = _build_gap_features(input_data)
        proba = model.predict_proba([features])[0]
        classes = list(model.classes_)

        gap_idx = classes.index("gap") if "gap" in classes else 1
        gap_prob = float(proba[gap_idx])

        return TierResult(
            result={"prediction": "gap" if gap_prob >= 0.5 else "no_gap", "probability": gap_prob},
            confidence=gap_prob,
            prediction="gap" if gap_prob >= 0.5 else "no_gap",
            probabilities=dict(zip(classes, [float(p) for p in proba])),
            source="classifier",
        )
    except Exception as e:
        logger.debug(f"Gap classifier failed: {e}")
        return None


def _build_gap_features(input_data: dict) -> list[float]:
    """Extract numeric features for the gap classifier."""
    request = input_data.get("request", "")
    return [
        len(request),
        len(request.split()),
        input_data.get("skill_count", 0),
        1.0 if input_data.get("source") == "episodic" else 0.0,
        input_data.get("score", 0.0),
    ]


def tier2_gap_teacher(input_data: Any, **kwargs) -> Any:
    """Tier 2: LLM teacher via gap_synthesizer._tier_scillm."""
    _ensure_imports()
    from common.cascade import TierResult  # type: ignore[import-untyped]

    request = input_data.get("request", "") if isinstance(input_data, dict) else str(input_data)
    if not request:
        return None

    try:
        from gap_synthesizer import _tier_scillm  # type: ignore[import-untyped]
        result = _tier_scillm(
            task=request,
            chain=[],
            gap_position=None,
            from_skill=None,
            to_skill=None,
        )

        if result is None:
            return TierResult(
                result={"verdict": "no_gap", "request": request},
                confidence=0.8,
                source="scillm",
            )

        return TierResult(
            result={
                "verdict": "gap",
                "proposal": result,
                "request": request,
            },
            confidence=result.get("confidence", 0.7),
            source="scillm",
        )
    except Exception as e:
        logger.debug(f"gap_synthesizer teacher failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Phase 4b: Build the cascade
# ---------------------------------------------------------------------------

def build_gap_cascade() -> Any:
    """Wire the 3-tier cascade via CascadeRunner."""
    _ensure_imports()
    from common.cascade import CascadeRunner, TierDef  # type: ignore[import-untyped]

    return CascadeRunner(
        tiers=[
            TierDef(
                tier=0, name="gap-heuristic",
                fn=tier0_gap_heuristic, threshold=0.4,
            ),
            TierDef(
                tier=0.5, name="gap-classifier",
                fn=tier05_gap_classifier, threshold=0.6,
                shadow_mode=True,
            ),
            TierDef(
                tier=2, name="gap-teacher",
                fn=tier2_gap_teacher, threshold=0.0,
                is_teacher=True,
            ),
        ],
        shadow_file=GAP_SHADOW_FILE,
        metrics_file=STATE_DIR / "gap_metrics.jsonl",
    )


# ---------------------------------------------------------------------------
# Phase 5: Rank proposals via energy + bond prediction
# ---------------------------------------------------------------------------

def rank_proposals(proposals: list[dict], graph: dict | None = None) -> list[dict]:
    """Score gap proposals by elegance (energy + bond prediction)."""
    _ensure_imports()

    try:
        from energy_model import compute_chain_energy, compute_elegance  # type: ignore[import-untyped]
        from bond_predictor import predict_chain_success  # type: ignore[import-untyped]
    except ImportError as e:
        logger.warning(f"Energy/bond modules not available: {e}")
        # Return proposals unranked
        for i, p in enumerate(proposals):
            p["rank"] = i + 1
            p["elegance_score"] = 0.0
        return proposals

    ranked = []
    for proposal in proposals:
        result = proposal.get("result", {})
        prop_detail = result.get("proposal", {})
        skill_name = prop_detail.get("name", "unknown-gap")
        composes = prop_detail.get("composes", [])
        chain = composes + [skill_name] if composes else [skill_name]

        try:
            chain_energy = compute_chain_energy(chain, graph=graph)
            bond_result = predict_chain_success(chain, graph=graph)
            success_prob = bond_result.get("success_probability", 0.5)
            elegance = compute_elegance(chain_energy, success_prob)

            proposal["elegance_score"] = elegance.get("elegance_score", 0.0)
            proposal["elegance_grade"] = elegance.get("grade", "?")
            proposal["success_probability"] = success_prob
        except Exception as e:
            logger.debug(f"Ranking failed for {skill_name}: {e}")
            proposal["elegance_score"] = 0.0
            proposal["elegance_grade"] = "?"
            proposal["success_probability"] = 0.0

        ranked.append(proposal)

    # Sort descending by elegance
    ranked.sort(key=lambda p: p.get("elegance_score", 0), reverse=True)
    for i, p in enumerate(ranked):
        p["rank"] = i + 1

    return ranked


# ---------------------------------------------------------------------------
# Phase 6: Persist results and notify
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, entry: dict) -> None:
    """Append a JSON line to a local state file.

    Used for shadow/label files consumed by the cascade — these MUST stay
    local (not in /memory) because CascadeRunner reads them directly.
    Proposal persistence goes through /memory learn via _sync_to_memory().
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _notify_inbox(proposals: list[dict]) -> None:
    """Send gap proposals to agent-inbox."""
    inbox_run = SKILLS_DIR / "agent-inbox" / "run.sh"
    if not inbox_run.exists() or not proposals:
        return

    lines = ["## Skill Gap Proposals\n"]
    lines.append("| Rank | Skill | Elegance | Source |")
    lines.append("|------|-------|----------|--------|")
    for p in proposals[:10]:
        result = p.get("result", {})
        prop = result.get("proposal", {})
        name = prop.get("name", "unknown")
        score = p.get("elegance_score", 0)
        source = p.get("source", "?")
        rank = p.get("rank", "?")
        lines.append(f"| {rank} | {name} | {score:.2f} | {source} |")

    body = "\n".join(lines)
    try:
        subprocess.run(
            [str(inbox_run), "send", "--from", "monitor-skills", "--subject",
             f"Gap scan: {len(proposals)} proposals", "--body", body],
            capture_output=True, text=True, timeout=15, check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _sync_to_memory(proposals: list[dict]) -> None:
    """Persist gap proposals to /memory for cross-session recall.

    Stores both a scan summary and individual proposals so future agents
    can recall specific gaps via ``memory recall --scope skill_gaps``.
    """
    if not proposals:
        return

    import httpx

    # Store scan summary
    summary = json.dumps({
        "type": "skill_gap_scan",
        "timestamp": int(time.time()),
        "proposal_count": len(proposals),
        "top_proposals": [
            {
                "name": p.get("result", {}).get("proposal", {}).get("name", "?"),
                "elegance": p.get("elegance_score", 0),
            }
            for p in proposals[:5]
        ],
    })

    try:
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
            client.post("/learn", json={
                "problem": f"Skill gap scan: {len(proposals)} proposals",
                "solution": summary,
                "scope": "skill_gaps",
                "tags": ["gap_scan"],
            })
    except Exception:
        pass

    # Store individual top proposals for granular recall
    for p in proposals[:10]:
        name = p.get("result", {}).get("proposal", {}).get("name", "unknown")
        try:
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
                client.post("/learn", json={
                    "problem": f"Skill gap proposal: {name}",
                    "solution": json.dumps(p, ensure_ascii=False),
                    "scope": "skill_gaps",
                    "tags": ["gap_proposal"],
                })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main entry: run_gap_scan
# ---------------------------------------------------------------------------

def run_gap_scan(dry_run: bool = False) -> dict[str, Any]:
    """Run the full gap detection pipeline.

    Returns dict with mined_requests, proposals, shadow stats.
    """
    start = time.time()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Mine transcripts
    transcript_requests = mine_unserved_requests()

    # Phase 2: Query episodic archives
    episodic_requests = query_episodic_gaps()

    # Phase 3: Deduplicate
    all_requests = transcript_requests + episodic_requests
    seen = _load_seen_hashes()
    unique_requests = deduplicate(all_requests, seen)

    # Phase 4: Run cascade on each request
    cascade = build_gap_cascade()
    proposals = []
    for req in unique_requests:
        result = cascade.run(
            input_data=req,
            task="skill-gap",
            scope="gap-detection",
            input_hash=req.get("input_hash", ""),
        )

        if result.source != "fallback":
            verdict = result.result.get("verdict", "")
            if verdict == "gap" or result.result.get("gaps"):
                proposal = {
                    "request": req.get("request", ""),
                    "source": req.get("source", ""),
                    "result": result.result,
                    "confidence": result.confidence,
                    "tier": result.tier,
                    "tier_source": result.source,
                    "timestamp": int(time.time()),
                }
                proposals.append(proposal)

                # Log teacher labels for future classifier training
                if result.source == "scillm":
                    _append_jsonl(GAP_LABELS_FILE, {
                        "request": req.get("request", ""),
                        "label": "gap",
                        "teacher_result": result.result,
                        "confidence": result.confidence,
                        "timestamp": int(time.time()),
                    })

    # Phase 5: Rank proposals
    graph = None
    try:
        _ensure_imports()
        from scan_soup import scan_soup  # type: ignore[import-untyped]
        graph = scan_soup(SKILLS_DIR)
    except Exception:
        pass

    ranked = rank_proposals(proposals, graph)

    # Phase 6: Persist and notify
    if not dry_run:
        # Update seen hashes
        new_hashes = {req.get("input_hash", "") for req in unique_requests if req.get("input_hash")}
        seen.update(new_hashes)
        _save_seen_hashes(seen)

        # Log proposals locally (for gap-status queries)
        for p in ranked:
            _append_jsonl(GAP_PROPOSALS_FILE, p)

        # Persist to /memory for cross-session recall + notify inbox
        _sync_to_memory(ranked)
        _notify_inbox(ranked)

    # Shadow stats
    shadow_stats = {}
    try:
        shadow_stats = cascade.shadow_report(task="skill-gap", hours=24)
    except Exception:
        pass

    # Update task state
    elapsed = round(time.time() - start, 2)
    state = {
        "last_run": int(time.time()),
        "status": "success",
        "dry_run": dry_run,
        "mined_requests": len(all_requests),
        "unique_requests": len(unique_requests),
        "proposals": len(ranked),
        "shadow": shadow_stats,
        "elapsed_seconds": elapsed,
    }
    GAP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    GAP_STATE_FILE.write_text(json.dumps(state, indent=2))

    return {
        "mined_requests": len(all_requests),
        "unique_requests": len(unique_requests),
        "proposals": [
            {
                "rank": p.get("rank"),
                "name": p.get("result", {}).get("proposal", {}).get("name", "?"),
                "elegance_score": p.get("elegance_score", 0),
                "confidence": p.get("confidence", 0),
                "source": p.get("tier_source", "?"),
            }
            for p in ranked
        ],
        "shadow": shadow_stats,
        "elapsed_seconds": elapsed,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Gap status report
# ---------------------------------------------------------------------------

def gap_scan_status() -> dict[str, Any]:
    """Health report for gap scan state files."""
    status: dict[str, Any] = {"state_dir": str(STATE_DIR)}

    # Task state
    if GAP_STATE_FILE.exists():
        try:
            status["last_run"] = json.loads(GAP_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            status["last_run"] = "corrupt"
    else:
        status["last_run"] = None

    # Count state files
    for name, path in [
        ("gap_labels", GAP_LABELS_FILE),
        ("gap_proposals", GAP_PROPOSALS_FILE),
        ("gap_shadow", GAP_SHADOW_FILE),
    ]:
        if path.exists():
            lines = sum(1 for line in path.read_text().splitlines() if line.strip())
            status[name] = {"path": str(path), "count": lines}
        else:
            status[name] = {"path": str(path), "count": 0}

    # Seen hashes
    if GAP_SEEN_HASHES_FILE.exists():
        try:
            hashes = json.loads(GAP_SEEN_HASHES_FILE.read_text())
            status["seen_hashes"] = {"path": str(GAP_SEEN_HASHES_FILE), "count": len(hashes)}
        except (json.JSONDecodeError, OSError):
            status["seen_hashes"] = {"path": str(GAP_SEEN_HASHES_FILE), "count": "corrupt"}
    else:
        status["seen_hashes"] = {"path": str(GAP_SEEN_HASHES_FILE), "count": 0}

    # Classifier availability
    classifier_path = SKILLS_DIR / "skill-lab" / "state" / "gap_classifier.pkl"
    status["gap_classifier"] = {
        "path": str(classifier_path),
        "exists": classifier_path.exists(),
    }

    return status


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

import typer

app = typer.Typer(help="Skill gap detection probe")


@app.command("gap-scan")
def gap_scan_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without persisting"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    result = run_gap_scan(dry_run=dry_run)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Mined requests: {result['mined_requests']}")
        print(f"Unique requests: {result['unique_requests']}")
        print(f"Proposals: {len(result['proposals'])}")
        if result["proposals"]:
            print("\nTop proposals:")
            for p in result["proposals"][:5]:
                print(f"  #{p['rank']} {p['name']} (elegance={p['elegance_score']:.2f})")
        shadow = result.get("shadow", {})
        if shadow.get("total"):
            print(f"\nShadow: {shadow['agreement_rate']:.1%} agreement ({shadow['total']} samples)")
        print(f"\nElapsed: {result['elapsed_seconds']}s")


@app.command("gap-status")
def gap_status_cmd():
    status = gap_scan_status()
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    app()
