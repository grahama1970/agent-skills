#!/usr/bin/env python3
"""Trajectory Distiller — differential distillation of execution traces.

Inspired by SkillRL (arxiv:2602.08234): successful and failed trajectories
receive fundamentally different treatment:

  Success traces → reusable composition patterns
    "extractor before memory when ingesting PDFs"

  Failure traces → counterfactual lessons
    "dogpile + battle fails because battle needs structured input"

These patterns are stored to /memory and used to gradually replace the
hand-tuned AFFINITIES dict in composer.py with learned affinities.

Usage:
    python trajectory_distiller.py distill              # Full distillation
    python trajectory_distiller.py distill --top-k 10   # Custom K
    python trajectory_distiller.py distill --dry-run     # Preview only
    python trajectory_distiller.py affinities            # Show learned affinities
    python trajectory_distiller.py affinities --json     # JSON format
"""
from __future__ import annotations

import httpx
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
SKILLS_DIR = SCRIPTS_DIR.parent.parent

_PROMPT_DIR = SKILLS_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()

sys.path.insert(0, str(SCRIPTS_DIR))
from bond_predictor import append_jsonl
from scan_soup import _memory_learn, _memory_recall

TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
DISTILL_LOG = STATE_DIR / "distill_log.jsonl"
LEARNED_AFFINITIES_FILE = STATE_DIR / "learned_affinities.json"

# scillm HTTP proxy for LLM distillation
SCILLM_URL = "http://localhost:4001"


# ---------------------------------------------------------------------------
# Trace Aggregation
# ---------------------------------------------------------------------------

def load_traces() -> list[dict]:
    """Load all execution traces from JSONL."""
    if not TRACES_FILE.exists():
        return []
    traces = []
    for line in TRACES_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return traces


def aggregate_pairs(traces: list[dict]) -> dict[str, dict]:
    """Aggregate traces into per-pair statistics.

    Returns:
        {
          "extractor+memory": {
            "pair": "extractor+memory",
            "skill_a": "extractor",
            "skill_b": "memory",
            "total": 12,
            "successes": 10,
            "failures": 2,
            "success_rate": 0.833,
            "mean_latency_ms": 150.0,
            "errors": ["timeout on large PDF", ...],
            "chains": [["extractor", "memory"], ...],
          }
        }
    """
    pairs: dict[str, dict] = {}

    for trace in traces:
        # Only forward traces — reverse are derivatives
        if trace.get("direction") == "reverse":
            continue

        pair_key = trace.get("pair", "")
        if not pair_key or "+" not in pair_key:
            continue

        parts = pair_key.split("+", 1)
        if len(parts) != 2:
            continue

        if pair_key not in pairs:
            pairs[pair_key] = {
                "pair": pair_key,
                "skill_a": parts[0],
                "skill_b": parts[1],
                "total": 0,
                "successes": 0,
                "failures": 0,
                "latencies": [],
                "errors": [],
                "chains": [],
            }

        p = pairs[pair_key]
        p["total"] += 1
        if trace.get("success"):
            p["successes"] += 1
        else:
            p["failures"] += 1
            err = trace.get("error", "")
            if err and err not in p["errors"]:
                p["errors"].append(err[:200])

        lat = trace.get("latency_ms", 0)
        if lat > 0:
            p["latencies"].append(lat)

        chain = trace.get("chain", [])
        chain_key = "→".join(chain)
        if chain_key not in [("→".join(c)) for c in p["chains"]]:
            p["chains"].append(chain)

    # Compute aggregates
    for p in pairs.values():
        p["success_rate"] = p["successes"] / max(p["total"], 1)
        p["mean_latency_ms"] = (
            sum(p["latencies"]) / len(p["latencies"])
            if p["latencies"] else 0.0
        )
        del p["latencies"]  # Don't need raw list anymore

    return pairs


def rank_pairs(
    pairs: dict[str, dict],
    top_k: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Rank pairs into top successes and top failures.

    Success ranking: highest success_rate (min 3 traces)
    Failure ranking: lowest success_rate (min 2 traces)
    """
    eligible = [p for p in pairs.values() if p["total"] >= 2]

    # Top successes: high success rate, enough data
    successes = sorted(
        [p for p in eligible if p["success_rate"] >= 0.6],
        key=lambda p: (p["success_rate"], p["total"]),
        reverse=True,
    )

    # Top failures: low success rate, have errors
    failures = sorted(
        [p for p in eligible if p["success_rate"] < 0.6],
        key=lambda p: (p["success_rate"], -p["total"]),
    )

    return successes[:top_k], failures[:top_k]


# ---------------------------------------------------------------------------
# LLM Distillation via scillm
# ---------------------------------------------------------------------------

SUCCESS_PROMPT = _load_prompt("skill_lab_distill_success_v1")

FAILURE_PROMPT = _load_prompt("skill_lab_distill_failure_v1")


def _call_scillm(prompt: str, timeout: int = 30) -> dict | None:
    """Call scillm HTTP proxy for LLM completion, return parsed JSON."""
    try:
        payload = {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        }
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            timeout=float(timeout),
        )
        resp.raise_for_status()
        stdout = resp.json()["choices"][0]["message"]["content"].strip()

        json_start = stdout.find("{")
        json_end = stdout.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(stdout[json_start:json_end])
    except (httpx.HTTPStatusError, httpx.TimeoutException, json.JSONDecodeError, OSError):
        pass
    return None


def distill_success(pair: dict) -> dict | None:
    """Distill a successful pair into a composition pattern."""
    chains_str = "; ".join(
        " → ".join(c) for c in pair["chains"][:3]
    )

    prompt = SUCCESS_PROMPT.format(
        skill_a=pair["skill_a"],
        skill_b=pair["skill_b"],
        total=pair["total"],
        success_rate=pair["success_rate"],
        mean_latency_ms=pair["mean_latency_ms"],
        chains=chains_str,
    )

    result = _call_scillm(prompt)
    if result:
        result["type"] = "composition_pattern"
        result["pair"] = pair["pair"]
        result["skill_a"] = pair["skill_a"]
        result["skill_b"] = pair["skill_b"]
        result["evidence"] = {
            "total": pair["total"],
            "success_rate": pair["success_rate"],
        }
    return result


def distill_failure(pair: dict) -> dict | None:
    """Distill a failed pair into a counterfactual lesson."""
    chains_str = "; ".join(
        " → ".join(c) for c in pair["chains"][:3]
    )
    errors_str = "; ".join(pair["errors"][:3]) if pair["errors"] else "unknown"

    prompt = FAILURE_PROMPT.format(
        skill_a=pair["skill_a"],
        skill_b=pair["skill_b"],
        total=pair["total"],
        success_rate=pair["success_rate"],
        errors=errors_str,
        chains=chains_str,
    )

    result = _call_scillm(prompt)
    if result:
        result["type"] = "failure_lesson"
        result["pair"] = pair["pair"]
        result["skill_a"] = pair["skill_a"]
        result["skill_b"] = pair["skill_b"]
        result["evidence"] = {
            "total": pair["total"],
            "success_rate": pair["success_rate"],
            "errors": pair["errors"][:3],
        }
    return result


# ---------------------------------------------------------------------------
# Heuristic Distillation (no LLM needed)
# ---------------------------------------------------------------------------

def distill_heuristic(pair: dict) -> dict:
    """Generate a pattern/lesson from stats alone — no LLM call.

    Used when scillm is unavailable or for pairs with very clear signals.
    """
    a, b = pair["skill_a"], pair["skill_b"]
    rate = pair["success_rate"]
    total = pair["total"]

    if rate >= 0.8:
        return {
            "type": "composition_pattern",
            "pair": pair["pair"],
            "skill_a": a,
            "skill_b": b,
            "pattern": f"{a} chains reliably with {b} ({rate:.0%} success over {total} executions)",
            "when_to_use": f"When {a} output feeds into {b}",
            "ordering": f"{a} before {b}",
            "affinity_weight": min(rate, 0.95),
            "evidence": {"total": total, "success_rate": rate},
        }
    elif rate >= 0.6:
        return {
            "type": "composition_pattern",
            "pair": pair["pair"],
            "skill_a": a,
            "skill_b": b,
            "pattern": f"{a} + {b} works but has {1 - rate:.0%} failure rate",
            "when_to_use": f"When {a} output feeds {b}, with error handling",
            "ordering": f"{a} before {b}",
            "affinity_weight": rate * 0.9,
            "evidence": {"total": total, "success_rate": rate},
        }
    else:
        errors = "; ".join(pair["errors"][:2]) if pair["errors"] else "unknown failures"
        return {
            "type": "failure_lesson",
            "pair": pair["pair"],
            "skill_a": a,
            "skill_b": b,
            "lesson": f"{a} + {b} fails {1 - rate:.0%} of the time: {errors}",
            "root_cause": errors or "incompatible output/input formats",
            "alternative": "none",
            "affinity_weight": max(rate * 0.7, 0.05),
            "evidence": {"total": total, "success_rate": rate},
        }


# ---------------------------------------------------------------------------
# Memory Storage
# ---------------------------------------------------------------------------

def store_pattern(distilled: dict) -> bool:
    """Store a distilled pattern/lesson to /memory."""
    dtype = distilled.get("type", "unknown")
    pair = distilled.get("pair", "?+?")
    a = distilled.get("skill_a", "?")
    b = distilled.get("skill_b", "?")

    if dtype == "composition_pattern":
        problem = f"composition pattern: {a} → {b}"
        solution = json.dumps({
            "pattern": distilled.get("pattern", ""),
            "when_to_use": distilled.get("when_to_use", ""),
            "ordering": distilled.get("ordering", ""),
            "affinity_weight": distilled.get("affinity_weight", 0.5),
            "evidence": distilled.get("evidence", {}),
        })
        tags = [
            "composition-pattern",
            f"skill:{a}",
            f"skill:{b}",
            "distilled",
        ]
    else:
        problem = f"composition failure: {a} + {b}"
        solution = json.dumps({
            "lesson": distilled.get("lesson", ""),
            "root_cause": distilled.get("root_cause", ""),
            "alternative": distilled.get("alternative", ""),
            "affinity_weight": distilled.get("affinity_weight", 0.1),
            "evidence": distilled.get("evidence", {}),
        })
        tags = [
            "composition-failure",
            f"skill:{a}",
            f"skill:{b}",
            "distilled",
        ]

    return _memory_learn(problem, solution, tags, scope="skill_registry")


# ---------------------------------------------------------------------------
# Learned Affinities
# ---------------------------------------------------------------------------

def compute_learned_affinities(pairs: dict[str, dict]) -> dict:
    """Compute learned affinities from trace statistics.

    Returns dict compatible with composer.py AFFINITIES format:
      {"extractor": [("memory", 0.83), ("review-pdf", 0.9)], ...}
    """
    # Group by skill_a
    by_skill: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for p in pairs.values():
        if p["total"] < 2:
            continue
        a, b = p["skill_a"], p["skill_b"]
        weight = p["success_rate"]

        # Discount low-evidence pairs
        if p["total"] < 5:
            weight *= 0.8
        if p["total"] < 3:
            weight *= 0.7

        by_skill[a].append((b, round(weight, 3)))

    # Sort each skill's partners by weight descending, keep top 5
    learned = {}
    for skill, partners in by_skill.items():
        partners.sort(key=lambda x: -x[1])
        learned[skill] = partners[:5]

    return learned


def save_learned_affinities(learned: dict) -> None:
    """Save learned affinities to state file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Convert tuples to lists for JSON
    serializable = {
        k: [[p, w] for p, w in v]
        for k, v in learned.items()
    }
    serializable["_meta"] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "trajectory_distiller",
    }
    LEARNED_AFFINITIES_FILE.write_text(json.dumps(serializable, indent=2))


def load_learned_affinities() -> dict:
    """Load learned affinities from state file."""
    if not LEARNED_AFFINITIES_FILE.exists():
        return {}
    try:
        raw = json.loads(LEARNED_AFFINITIES_FILE.read_text())
        # Support both formats: flat {skill: [[partner, weight], ...]}
        # and wrapped {"affinities": {skill: [[partner, weight], ...], ...}, ...}
        data = raw.get("affinities", raw) if isinstance(raw, dict) else raw
        # Remove metadata keys
        data = {k: v for k, v in data.items() if isinstance(v, list)}
        return {
            k: [(p, w) for p, w in v]
            for k, v in data.items()
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def distill(
    top_k: int = 5,
    use_llm: bool = True,
    dry_run: bool = False,
) -> dict:
    """Run the full trajectory distillation pipeline.

    1. Load and aggregate execution traces
    2. Rank into top successes and failures
    3. Distill each via LLM (or heuristic fallback)
    4. Store patterns/lessons to /memory
    5. Update learned affinities

    Returns stats dict.
    """
    start = time.time()
    stats = {
        "traces_loaded": 0,
        "pairs_aggregated": 0,
        "patterns_distilled": 0,
        "lessons_distilled": 0,
        "stored_to_memory": 0,
        "affinities_updated": 0,
        "dry_run": dry_run,
    }

    # Step 1: Load traces
    print("\n== Trajectory Distiller ==\n")
    traces = load_traces()
    stats["traces_loaded"] = len(traces)
    print(f"  Loaded {len(traces)} execution traces")

    if not traces:
        print("  No traces to distill.")
        return stats

    # Step 2: Aggregate
    pairs = aggregate_pairs(traces)
    stats["pairs_aggregated"] = len(pairs)
    print(f"  Aggregated into {len(pairs)} unique pairs")

    # Step 3: Rank
    top_successes, top_failures = rank_pairs(pairs, top_k=top_k)
    print(f"  Top successes: {len(top_successes)} | Top failures: {len(top_failures)}")

    if not top_successes and not top_failures:
        print("  No pairs with enough data to distill.")
        return stats

    # Step 4: Distill
    distilled = []

    has_llm = use_llm
    method = "LLM + heuristic" if has_llm else "heuristic only"
    print(f"\n  Distilling ({method})...\n")

    for p in top_successes:
        print(f"    [+] {p['pair']} ({p['success_rate']:.0%}, n={p['total']})")
        if has_llm and p["total"] >= 5:
            result = distill_success(p)
            if result:
                distilled.append(result)
                stats["patterns_distilled"] += 1
                print(f"        → {result.get('pattern', '')[:80]}")
                continue
        # Heuristic fallback
        result = distill_heuristic(p)
        distilled.append(result)
        stats["patterns_distilled"] += 1
        print(f"        → {result.get('pattern', '')[:80]}")

    for p in top_failures:
        print(f"    [-] {p['pair']} ({p['success_rate']:.0%}, n={p['total']})")
        if has_llm and p["total"] >= 3:
            result = distill_failure(p)
            if result:
                distilled.append(result)
                stats["lessons_distilled"] += 1
                print(f"        → {result.get('lesson', '')[:80]}")
                continue
        # Heuristic fallback
        result = distill_heuristic(p)
        distilled.append(result)
        stats["lessons_distilled"] += 1
        print(f"        → {result.get('lesson', result.get('pattern', ''))[:80]}")

    # Step 5: Store to memory
    if not dry_run and distilled:
        print(f"\n  Storing {len(distilled)} patterns/lessons to /memory...")
        for d in distilled:
            if store_pattern(d):
                stats["stored_to_memory"] += 1
        print(f"  Stored: {stats['stored_to_memory']}")

    # Step 6: Update learned affinities
    learned = compute_learned_affinities(pairs)
    stats["affinities_updated"] = len(learned)

    if not dry_run:
        save_learned_affinities(learned)
        print(f"\n  Updated learned affinities: {len(learned)} skills")
    else:
        print(f"\n  [DRY RUN] Would update affinities for {len(learned)} skills")

    # Step 7: Log distillation run
    if not dry_run:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "patterns": [
                {"pair": d["pair"], "type": d["type"],
                 "weight": d.get("affinity_weight", 0)}
                for d in distilled
            ],
        }
        append_jsonl(DISTILL_LOG, [log_entry])

    elapsed = time.time() - start
    print(f"\n== Distillation Complete ({elapsed:.1f}s) ==\n")
    return stats


def show_affinities(as_json: bool = False) -> None:
    """Show current learned affinities vs static AFFINITIES."""
    from composer import AFFINITIES

    learned = load_learned_affinities()

    if as_json:
        print(json.dumps({
            "static": {k: [[p, w] for p, w in v] for k, v in AFFINITIES.items()},
            "learned": {k: [[p, w] for p, w in v] for k, v in learned.items()},
        }, indent=2))
        return

    print("\n== Learned vs Static Affinities ==\n")

    all_skills = sorted(set(list(AFFINITIES.keys()) + list(learned.keys())))

    for skill in all_skills:
        static = dict(AFFINITIES.get(skill, []))
        learn = dict(learned.get(skill, []))
        all_partners = sorted(set(list(static.keys()) + list(learn.keys())))

        if not all_partners:
            continue

        print(f"  {skill}:")
        for partner in all_partners:
            s_val = static.get(partner)
            l_val = learn.get(partner)

            if s_val is not None and l_val is not None:
                delta = l_val - s_val
                arrow = "↑" if delta > 0.05 else ("↓" if delta < -0.05 else "≈")
                print(f"    → {partner:20s}  static={s_val:.2f}  learned={l_val:.3f}  {arrow}")
            elif l_val is not None:
                print(f"    → {partner:20s}  static=----  learned={l_val:.3f}  NEW")
            else:
                print(f"    → {partner:20s}  static={s_val:.2f}  learned=----")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    import sys

    args = sys.argv[1:]
    cmd = args[0] if args else "help"

    if cmd == "distill":
        top_k = 5
        use_llm = True
        dry_run = False
        as_json = False

        i = 1
        while i < len(args):
            if args[i] == "--top-k" and i + 1 < len(args):
                top_k = int(args[i + 1])
                i += 2
            elif args[i] == "--no-llm":
                use_llm = False
                i += 1
            elif args[i] == "--dry-run":
                dry_run = True
                i += 1
            elif args[i] == "--json":
                as_json = True
                i += 1
            else:
                i += 1

        stats = distill(top_k=top_k, use_llm=use_llm, dry_run=dry_run)
        if as_json:
            print(json.dumps(stats, indent=2))

    elif cmd == "affinities":
        as_json = "--json" in args
        show_affinities(as_json=as_json)

    else:
        print("Usage:")
        print("  trajectory_distiller.py distill [--top-k N] [--no-llm] [--dry-run] [--json]")
        print("  trajectory_distiller.py affinities [--json]")
        print()
        print("Distills execution traces into composition patterns and failure lessons.")
        print("Stores to /memory and updates learned_affinities.json.")


if __name__ == "__main__":
    main()
