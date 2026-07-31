"""Mutation-load gate — measure the bad-genetic-material rate with the REAL gate.

Operator-selected regime (2026-07-23). One passing champion proves EXISTENCE, not
selective pressure. This module takes a generation's surviving champion artifact,
samples K deterministic single-edit mutants from a transparent, seeded operator
family, and runs every mutant through the SAME gate the live pipeline uses:

  * real Docker ``py_compile`` (``--network none``, dropped caps, read-only) —
    syntactic viability;
  * the identical deterministic review scan
    (:func:`team_artifact_pipeline.review_artifact_errors`) — private-marker leak +
    role-interface preservation.

A mutant is ACCEPTED only if both gates pass; otherwise it is REJECTED with a
reason. Most random single edits to source are non-viable, so the accept rate is
low by nature of the gate, not by construction: every variant records its exact
``mutation_op`` so the ledger is auditable line by line. This directly measures the
README's "most specimens are bad genetic material" and hands selection a real pool
(the parent champion plus any surviving mutants) instead of a definitional pick.

The bad-rate denominator is the K sampled mutants ONLY. The champion is a guaranteed
survivor (it already passed the live gate) and is reported separately, never counted
as "good genetic material" that would flatter the rate.
"""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path
from typing import Any

from .team_artifact_pipeline import review_artifact_errors

SCHEMA = "battle.adaptive_specimen_population.v1"

# Transparent, seeded operator family. Each is a single local edit. A few are
# neutral (silent mutations that keep the source viable); most are deleterious.
# The REAL gate — not this list — decides which survive; the mix is only the
# sampling distribution, and every draw is recorded by name in the ledger.
# Real code mutation is almost always lethal. There are NO guaranteed-survivor
# ops here (the earlier `identity_comment`/`blank_pad` padding manufactured
# survival that is supposed to be rare). The rare survivor emerges only when a
# destructive edit happens to land somewhere the gate still accepts.
_MUTATION_OPS = (
    "delete_line",        # drops a statement (often an interface/def line)
    "dedent_line",        # strips indentation -> IndentationError
    "drop_colon",         # removes a block ':' -> SyntaxError
    "truncate_tail",      # cuts the file -> open block / missing interface
    "unbalance_paren",    # appends stray '(' -> SyntaxError
    "swap_adjacent",      # reorders two lines -> usually breaks indentation
    "corrupt_keyword",    # mangles a Python keyword -> SyntaxError
)


def _apply_mutation(source: str, op: str, rng: random.Random) -> str:
    lines = source.splitlines()
    if not lines:
        return source
    non_blank = [i for i, ln in enumerate(lines) if ln.strip()]
    indented = [i for i, ln in enumerate(lines) if ln[:1] in (" ", "\t") and ln.strip()]
    colon_lines = [i for i, ln in enumerate(lines) if ln.rstrip().endswith(":")]
    _KEYWORDS = ("def", "return", "import", "class", "for", "while", "with", "if", "try", "except")

    if op == "corrupt_keyword":
        kw_lines = [i for i in non_blank if any(f"{k} " in lines[i] or lines[i].strip().startswith(k) for k in _KEYWORDS)]
        if kw_lines:
            idx = rng.choice(kw_lines)
            for k in _KEYWORDS:
                if k in lines[idx]:
                    lines[idx] = lines[idx].replace(k, k[:-1] + "x", 1)  # def -> dex, return -> returx
                    break
        else:
            del lines[rng.choice(non_blank)]
    elif op == "delete_line":
        idx = rng.choice(non_blank)
        del lines[idx]
    elif op == "dedent_line":
        if indented:
            idx = rng.choice(indented)
            lines[idx] = lines[idx].lstrip()
        else:  # no indentation to strip: fall back to a deletion
            del lines[rng.choice(non_blank)]
    elif op == "drop_colon":
        if colon_lines:
            idx = rng.choice(colon_lines)
            stripped = lines[idx].rstrip()
            lines[idx] = stripped[:-1]
        else:
            lines[rng.choice(non_blank)] += " ("
    elif op == "truncate_tail":
        cut = rng.randrange(1, len(lines)) if len(lines) > 1 else 1
        lines = lines[:cut]
    elif op == "unbalance_paren":
        idx = rng.choice(non_blank)
        lines[idx] = lines[idx] + " ("
    elif op == "swap_adjacent":
        if len(lines) >= 2:
            idx = rng.randrange(len(lines) - 1)
            lines[idx], lines[idx + 1] = lines[idx + 1], lines[idx]
    return "\n".join(lines) + "\n"


def _compile_all(population_dir: Path, docker_image: str) -> dict[str, dict[str, Any]]:
    """Batch-compile every ``*.py`` in ``population_dir`` in ONE Docker run."""
    driver = (
        "import glob,json,py_compile\n"
        "for f in sorted(glob.glob('/work/*.py')):\n"
        "    name=f.rsplit('/',1)[-1]\n"
        "    try:\n"
        "        py_compile.compile(f, doraise=True)\n"
        "        print(json.dumps({'file':name,'ok':True}))\n"
        "    except Exception as e:\n"
        "        print(json.dumps({'file':name,'ok':False,'err':type(e).__name__+': '+str(e)[:160]}))\n"
    )
    command = [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "256m", "--cpus", "1", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
        "-e", "PYTHONPYCACHEPREFIX=/tmp/pycache", "--user", "65534:65534",
        "-v", f"{population_dir}:/work:ro", "-w", "/work", docker_image,
        "python", "-c", driver,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    results: dict[str, dict[str, Any]] = {}
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        results[str(row.get("file"))] = row
    if not results:
        raise RuntimeError(
            f"specimen compile driver produced no rows (exit {completed.returncode}): "
            f"{completed.stderr[-200:]}"
        )
    return results


def run_specimen_population(
    *,
    champion_source: Path,
    team: str,
    generation: int,
    seed: int,
    out_dir: Path,
    variants: int = 8,
    max_edits: int = 5,
    docker_image: str = "python:3.12-slim",
) -> dict[str, Any]:
    """Sample K mutants of the champion and gate them; return an auditable ledger."""
    if team not in {"red", "blue"}:
        raise ValueError("team must be red or blue")
    champion_source = champion_source.resolve()
    out_dir = out_dir.resolve()
    population_dir = out_dir / "population"
    population_dir.mkdir(parents=True, exist_ok=True)
    champion_text = champion_source.read_text(encoding="utf-8", errors="replace")

    # The champion is a guaranteed survivor (already passed the live gate). It is
    # written into the population so the batch compile re-proves it, but it is not
    # part of the bad-rate denominator.
    (population_dir / "champion.py").write_text(champion_text, encoding="utf-8")

    planned: list[dict[str, Any]] = []
    for k in range(variants):
        rng = random.Random(seed * 100_003 + generation * 1_009 + k)
        # A specimen sits at a real mutational distance from its parent, not one
        # keystroke away. Draw a seeded number of compounding edits so the sample
        # spans near-clones through heavily-drifted candidates; the count is
        # recorded per variant so the bad-rate is auditable, not tuned.
        edit_count = rng.randint(1, max_edits)
        ops: list[str] = []
        mutant = champion_text
        for _ in range(edit_count):
            op = rng.choice(_MUTATION_OPS)
            ops.append(op)
            mutant = _apply_mutation(mutant, op, rng)
        name = f"variant_{k:02d}.py"
        (population_dir / name).write_text(mutant, encoding="utf-8")
        planned.append({
            "file": name,
            "index": k,
            "edit_count": edit_count,
            "mutation_ops": ops,
            "text": mutant,
        })

    compiled = _compile_all(population_dir, docker_image)

    ledger: list[dict[str, Any]] = []
    accepted = 0
    for spec in planned:
        comp = compiled.get(spec["file"], {"ok": False, "err": "no compile row"})
        compile_ok = bool(comp.get("ok"))
        review_errors = review_artifact_errors(team, spec["text"]) if compile_ok else []
        is_accepted = compile_ok and not review_errors
        if is_accepted:
            accepted += 1
        reason = None
        if not compile_ok:
            reason = f"compile: {comp.get('err', 'BLOCKED')}"
        elif review_errors:
            reason = f"review: {review_errors[0]}"
        ledger.append({
            "file": spec["file"],
            "index": spec["index"],
            "edit_count": spec["edit_count"],
            "mutation_ops": spec["mutation_ops"],
            "compile_ok": compile_ok,
            "review_errors": review_errors,
            "accepted": is_accepted,
            "reject_reason": reason,
        })

    champion_compile = compiled.get("champion.py", {"ok": False})
    rejected = variants - accepted
    return {
        "schema": SCHEMA,
        "team": team,
        "generation": generation,
        "seed": seed,
        "docker_image": docker_image,
        "mocked": False,
        "live": "docker_py_compile+deterministic_review",
        "champion_source_sha_bytes": len(champion_text.encode("utf-8")),
        "champion_recompiled_ok": bool(champion_compile.get("ok")),
        "variants_sampled": variants,
        "variants_accepted": accepted,
        "variants_rejected": rejected,
        "bad_rate_local": round(rejected / variants, 4) if variants else 0.0,
        "max_edits_per_variant": max_edits,
        "mutation_ops_available": list(_MUTATION_OPS),
        "survivor_pool_size": accepted + 1,  # surviving mutants + the parent champion
        "ledger": ledger,
        "proves": [
            "Of K deterministic single-edit mutants sampled from the champion, the fraction "
            "rejected by the REAL Docker compile + review gate is the measured "
            "bad-genetic-material rate; every mutation_op and reject_reason is recorded.",
        ],
    }
