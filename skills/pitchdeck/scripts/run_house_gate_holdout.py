"""#1385: blinded holdout for the phrase 'looks like Graham'.

PROTOCOL (pre-registered, before any scoring):
- Thresholds: the committed digest-bound artifacts (calibration.v1,
  deck-calibration.v1). Nothing is retuned after results are seen.
- Labels: ground truth by construction — the five real Graham decks are HOUSE;
  every mutant/foreign deck is OFF-HOUSE. The generated Sparta deck is scored
  but reported separately (it is the development target, not holdout evidence).
- Deck verdict (declared a priori from the floors' own semantics): a p5
  per-slide floor fails ~5% of real pages BY DEFINITION, so a deck passes the
  pixel/embedding channels when <=5% of its slides fall below the floors
  (fractional slides round up to 1 allowed on small decks... no: allowance =
  ceil(0.05*n)). Structure channel: 0 findings required where a canonical
  document exists (generated decks + document-bearing mutants); real decks
  carry no document, so structure is N/A there and the report says so.
  Deck-gate (LODO structural distance): median and p90 within bars.
- Composite HOUSE verdict = pixel/embedding deck-pass AND conformance <=5%
  slides flagged AND deck-gate pass AND (structure pass when applicable).
- Bar (from the review): >=18/20 house pages... adapted to available material:
  ALL 5 real decks must pass; at most 1 of the off-house decks may pass.

Inputs: real corpus decks, mutant decks, the generated deck. Outputs: a
confusion matrix JSON + per-deck channel table. Failure modes: a deck that
cannot render is reported UNSCORABLE (counts as neither pass nor fail —
named, not dropped).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).parent.parent


def run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=SKILL)
    return proc.returncode, proc.stdout


def render(pptx: Path, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["soffice", f"-env:UserInstallation=file://{out_dir}/.lo", "--headless",
                    "--convert-to", "pdf", str(pptx), "--outdir", str(out_dir)],
                   capture_output=True, timeout=600)
    pdf = out_dir / (pptx.stem + ".pdf")
    if not pdf.exists():
        return None
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    pages = int(next(line.split()[1] for line in info.splitlines() if line.startswith("Pages:")))
    for page in range(1, pages + 1):
        subprocess.run(["pdftoppm", "-png", "-r", "50", "-f", str(page), "-l", str(page),
                        str(pdf), str(out_dir / f"s{page:03d}")], capture_output=True, timeout=120)
    return out_dir


def score_deck(name: str, pptx: Path, document: Path | None, work: Path) -> dict:
    renders = render(pptx, work / name)
    if renders is None:
        return {"deck": name, "verdict": "UNSCORABLE", "reason": "render failed"}
    n = len(list(renders.glob("s*.png")))
    allowance = math.ceil(0.05 * n)

    code, out = run(["./run.sh", "house-similarity", "--slides-dir", str(renders),
                     "--glob", "s*.png", "--calibration", "fixtures/house-gate/calibration.v1.json"])
    sim = json.loads(out) if out.strip().startswith("{") else {"failed": n, "slides": []}
    pixel_ok = sim.get("failed", n) <= allowance

    code, out = run(["./run.sh", "house-conformance", "--pptx", str(pptx)])
    conf = json.loads(out) if out.strip().startswith("{") else {"findings": [{}] * n}
    conf_slides = {f.get("slide") for f in conf.get("findings", [])}
    conf_ok = len(conf_slides) <= allowance

    code, out = run(["./run.sh", "house-deck-gate", "--pptx", str(pptx)])
    dg = json.loads(out) if out.strip().startswith("{") else {"status": "FAIL"}
    deck_gate_ok = dg.get("status") == "DECK_STRUCTURAL_MATCH"

    structure_ok, structure = None, None
    if document is not None:
        code, out = run(["./run.sh", "house-structure", "--pptx", str(pptx),
                         "--document", str(document)])
        structure = json.loads(out) if out.strip().startswith("{") else {"findings": [{}]}
        structure_ok = not structure.get("findings")

    checks = [pixel_ok, conf_ok, deck_gate_ok] + ([structure_ok] if structure_ok is not None else [])
    return {"deck": name, "slides": n, "allowance": allowance,
            "pixel_embed_failed_slides": sim.get("failed"), "pixel_ok": pixel_ok,
            "conformance_flagged_slides": len(conf_slides), "conformance_ok": conf_ok,
            "deck_gate": {"median": dg.get("median"), "bar": dg.get("median_bar"),
                           "p90": dg.get("p90"), "p90_bar": dg.get("p90_bar")},
            "deck_gate_ok": deck_gate_ok,
            "structure_findings": (len(structure.get("findings", [])) if structure else None),
            "structure_ok": structure_ok,
            "verdict": "HOUSE" if all(checks) else "OFF-HOUSE"}


def main() -> None:
    corpus = Path("/mnt/storage12tb/skills/pitchdeck/sources/style-corpus")
    mutants = Path(sys.argv[sys.argv.index("--mutants") + 1])
    generated = Path(sys.argv[sys.argv.index("--generated") + 1])
    document = Path(sys.argv[sys.argv.index("--document") + 1])
    out_path = Path(sys.argv[sys.argv.index("--output") + 1])
    work = Path(tempfile.mkdtemp(prefix="pd-holdout-score-"))

    results = {"house": [], "off_house": [], "development_target": None}
    for deck in sorted(corpus.glob("*.pptx")):
        results["house"].append(score_deck(f"real:{deck.stem}", deck, None, work))
    for deck in sorted(mutants.glob("*.pptx")):
        results["off_house"].append(score_deck(f"mutant:{deck.stem}", deck, document, work))
    results["development_target"] = score_deck("generated:sparta-explorer", generated, document, work)

    house_pass = sum(1 for r in results["house"] if r["verdict"] == "HOUSE")
    off_pass = sum(1 for r in results["off_house"] if r["verdict"] == "HOUSE")
    results["confusion"] = {
        "house_decks": len(results["house"]), "house_pass": house_pass,
        "off_house_decks": len(results["off_house"]), "off_house_false_pass": off_pass,
        "bar": "all real decks pass; at most 1 off-house deck passes",
        "bar_met": house_pass == len(results["house"]) and off_pass <= 1,
    }
    out_path.write_text(json.dumps(results, indent=1))
    print(json.dumps(results["confusion"], indent=1))


if __name__ == "__main__":
    main()
