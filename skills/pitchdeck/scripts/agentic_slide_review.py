"""Agentic per-slide review: SEE the slide next to its nearest real page.

The deterministic gates are regression floors; this is the judgment loop the
operator specified — for each generated slide, a vision seat (via /ask ->
Tau -> scillm claude-fable-low, receipted) is SHOWN a side-by-side composite
(generated | nearest real Graham page), given both structural JSONs and the
design laws, and returns VERDICT + concrete numbered fixes.

Inputs: a render dir + house-similarity log (nearest/diff_target per slide).
Outputs: reports/agentic-slide-review-<stamp>.md with per-slide verdicts.
Failure modes: a seat that fails is recorded NEEDS_ATTENTION, never skipped
silently.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).parent.parent
PAGES = Path("/mnt/storage12tb/skills/pitchdeck/outputs/house-slides")


def composite(generated: Path, real: Path, out: Path) -> None:
    from PIL import Image, ImageDraw

    a, b = Image.open(generated).convert("RGB"), Image.open(real).convert("RGB")
    h = 500
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    canvas = Image.new("RGB", (a.width + b.width + 30, h + 40), "white")
    canvas.paste(a, (0, 40)); canvas.paste(b, (a.width + 30, 40))
    d = ImageDraw.Draw(canvas)
    d.text((10, 10), "LEFT: generated slide", fill="black")
    d.text((a.width + 40, 10), "RIGHT: nearest REAL Graham page", fill="black")
    canvas.save(out)


def ask_seat(prompt: str, attachment: Path, target: str) -> str:
    proc = subprocess.run(
        [str(SKILL.parent / "ask" / "run.sh"), "tau-dag", prompt,
         "--repo", "local/agent-skills", "--target", target,
         "--immutable-goal", "per-slide visual judgment against the nearest real page",
         "--handler", "claude-fable-low", "--attach-file", str(attachment),
         "--execute", "--json"],
        capture_output=True, text=True, timeout=1800, cwd=SKILL)
    match = re.search(r'"run_dir":\s*"([^"]+)"', proc.stdout or "")
    if match:
        response = Path(match.group(1)) / "node-artifacts" / "handler-claude-fable-low" / "response.md"
        if response.is_file():
            return response.read_text(encoding="utf-8")
    return f"NEEDS_ATTENTION: seat failed\n{(proc.stdout or proc.stderr)[-300:]}"


def main() -> None:
    render_dir = Path(sys.argv[sys.argv.index("--render-dir") + 1])
    sim_log = json.loads(Path(sys.argv[sys.argv.index("--similarity-log") + 1]).read_text())
    document = json.loads(Path(sys.argv[sys.argv.index("--document") + 1]).read_text())
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 99
    laws = (SKILL.parent / "best-practices-slide-design" / "references" / "DESIGN_SLIDES.md").read_text()[:3000]
    doc_slides = [s for s in document["slides"] if not s.get("hidden")]
    stamp = subprocess.run(["date", "-u", "+%Y%m%dT%H%M%S"], capture_output=True, text=True).stdout.strip()
    out_lines = [f"# Agentic slide review — {stamp}\n"]
    work = Path(f"/tmp/pd-agentic-review-{stamp}"); work.mkdir(parents=True, exist_ok=True)

    for row in sorted(sim_log["slides"], key=lambda r: r["slide"])[:limit]:
        index = int(re.search(r"s(\d+)", row["slide"]).group(1)) - 1
        slide_doc = doc_slides[index]
        real_deck, real_page = row["nearest"].rsplit("#", 1)
        candidates = [PAGES / f"{real_deck}-{int(real_page):02d}.png",
                      PAGES / f"{real_deck}-{real_page}.png"]
        real_png = next(c for c in candidates if c.is_file())
        record = {}
        if row.get("diff_target") and Path(row["diff_target"]).is_file():
            record = json.loads(Path(row["diff_target"]).read_text())
        comp = work / f"compare-{row['slide']}"
        composite(render_dir / row["slide"], real_png, comp.with_suffix(".png"))
        prompt = (
            "You are judging whether a generated slide reads as a Graham house page. The attached image "
            "shows the GENERATED slide (left) beside the NEAREST REAL page (right). Judge composition, "
            "type, density, art register — NOT content overlap.\n\n"
            f"GENERATED slide structure (canonical JSON): {json.dumps({k: slide_doc.get(k) for k in ('id','section','notes')})} "
            f"elements: {json.dumps([{k: e.get(k) for k in ('id','role','kind','bbox')} for e in slide_doc.get('elements', [])])[:1200]}\n\n"
            f"NEAREST REAL page record: {json.dumps(record)[:800]}\n\n"
            f"DESIGN LAWS (excerpt):\n{laws[:1500]}\n\n"
            "Return exactly: VERDICT: HOUSE|NOT_HOUSE|BORDERLINE, then THE ONE BIGGEST GAP (one sentence), "
            "then FIXES: up to 3 numbered, mechanical (bbox/size/element-level) changes."
        )
        print(f"reviewing {row['slide']} vs {row['nearest']} ...", flush=True)
        answer = ask_seat(prompt, comp.with_suffix(".png"), f"slide-review-{stamp}-{row['slide']}")
        out_lines.append(f"\n## {row['slide']} (vs {row['nearest']}, embed {row['score']})\n\n{answer.strip()}\n")

    out = SKILL / "reports" / f"agentic-slide-review-{stamp}.md"
    out.write_text("\n".join(out_lines))
    print(json.dumps({"report": str(out), "slides_reviewed": min(limit, len(sim_log['slides']))}))


if __name__ == "__main__":
    main()
