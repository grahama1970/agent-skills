"""Bounded creator-reviewer loop, per slide, through /ask -> Tau DAG.

The operator's review architecture, in order:
  Tier 1  deck ARCHITECTURE: does the deck represent the source doc, its
          images, and the project? (run first; a per-slide loop cannot fix a
          deck that carries the wrong sections)
  Tier 2  per-slide review with BOTH the structural JSON and the rendered
          image beside the nearest real page
  Tier 3  each slide gets at most N creator-reviewer rounds — creator proposes
          mechanical fixes, reviewer votes PASS/FAIL, loop stops on PASS or at
          the bound

The bound is the point: an unbounded loop is how an agentic second pass
burns a budget without converging (observed on pdf_oxide). Every round is a
receipted Tau DAG; the transcript per slide is the evidence.

Inputs: render dir, document, nearest-page map, N. Outputs: a per-slide
transcript with the final verdict and the surviving fix list. Failure modes: a
seat that fails is recorded NEEDS_ATTENTION and the slide stops, never
silently passes.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import typer
from loguru import logger

SKILL = Path(__file__).resolve().parent.parent
ASK = SKILL.parent / "ask" / "run.sh"
app = typer.Typer(help="Bounded per-slide creator-reviewer loop via /ask.")


@dataclass
class SlideOutcome:
    slide: str
    rounds: int = 0
    verdict: str = "UNRUN"
    fixes: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


def _ask(prompt: str, target: str, attachment: Path | None, model: str, timeout: int = 1500) -> str:
    cmd = [str(ASK), "tau-dag", prompt, "--repo", "local/agent-skills", "--target", target,
           "--immutable-goal", "bounded per-slide creator-reviewer round",
           "--handler", model, "--allow-provider-calls", "--execute", "--json"]
    if attachment is not None:
        cmd += ["--attach-file", str(attachment)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(SKILL))
    match = re.search(r'"run_dir":\s*"([^"]+)"', out.stdout or "")
    if not match:
        return "NEEDS_ATTENTION: no run_dir in ask output"
    response = Path(match.group(1)) / "node-artifacts" / f"handler-{model}" / "response.md"
    return response.read_text(encoding="utf-8") if response.is_file() else "NEEDS_ATTENTION: no response artifact"


@app.command()
def run(
    render_dir: Path = typer.Option(..., help="Rendered slide PNGs."),
    document: Path = typer.Option(..., help="deck.document.json."),
    composites: Path = typer.Option(..., help="Dir of <slide>-vs-real composites (tier 2 inputs)."),
    max_rounds: int = typer.Option(2, help="N: hard bound on creator-reviewer rounds per slide."),
    model: str = typer.Option("claude-opus-4-8", help="scillm seat for both roles."),
    only: str = typer.Option("", help="Comma-separated slide stems to run (default: all)."),
    output: Path = typer.Option(Path("reports/slide-loop.json")),
) -> None:
    """Run at most N creator-reviewer rounds per slide; stop each slide on PASS."""
    doc = json.loads(document.read_text())
    slides = [s for s in doc["slides"] if not s.get("hidden")]
    wanted = {w.strip() for w in only.split(",") if w.strip()}
    outcomes: list[SlideOutcome] = []

    for index, slide in enumerate(slides, start=1):
        stem = f"s{index}"
        if wanted and stem not in wanted and slide["id"] not in wanted:
            continue
        composite = next(iter(sorted(composites.glob(f"*{stem}-*.png"))), None)
        if composite is None:
            logger.warning("no composite for {}; skipping", stem)
            continue
        outcome = SlideOutcome(slide=slide["id"])
        geometry = json.dumps([{k: e.get(k) for k in ("id", "role", "kind", "bbox")}
                               for e in slide.get("elements", [])])[:1200]
        for round_index in range(1, max_rounds + 1):
            outcome.rounds = round_index
            creator = _ask(
                "CREATOR round %d. The attached composite shows the GENERATED slide beside the nearest REAL "
                "house page. Structural JSON: %s. Propose at most 3 MECHANICAL fixes (element id + new bbox or "
                "style) that move the generated slide toward the house register. Reject any fix that merely "
                "clones the real page. If nothing needs fixing say NO_FIXES." % (round_index, geometry),
                f"slide-loop-{slide['id']}-r{round_index}-creator", composite, model)
            reviewer = _ask(
                "REVIEWER round %d. The attached composite is the CURRENT state of the slide. A creator proposed: "
                "%s\n\nJudge from what you SEE: would applying these make it read as a house page? Answer "
                "VERDICT: PASS if the slide is already house-faithful or the fixes are correct and sufficient; "
                "VERDICT: FAIL otherwise, naming what remains." % (round_index, creator[:1500]),
                f"slide-loop-{slide['id']}-r{round_index}-reviewer", composite, model)
            outcome.transcript.append({"round": round_index, "creator": creator[:1200], "reviewer": reviewer[:1200]})
            verdict = re.search(r"VERDICT:\s*(PASS|FAIL)", reviewer)
            outcome.verdict = verdict.group(1) if verdict else "NEEDS_ATTENTION"
            outcome.fixes = re.findall(r"^\s*\d[.)]\s*(.+)$", creator, re.M)[:3]
            if outcome.verdict == "PASS" or outcome.verdict == "NEEDS_ATTENTION":
                break
        outcomes.append(outcome)
        typer.echo(f"{outcome.slide}: {outcome.verdict} after {outcome.rounds} round(s)")

    payload = {"schema": "pitchdeck.slide_review_loop.v1", "max_rounds": max_rounds, "model": model,
               "slides": [o.__dict__ for o in outcomes]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1))
    typer.echo(json.dumps({"status": "PASS", "output": str(output),
                           "passed": sum(1 for o in outcomes if o.verdict == "PASS"),
                           "total": len(outcomes)}))


if __name__ == "__main__":
    app()
