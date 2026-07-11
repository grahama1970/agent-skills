#!/usr/bin/env python3
"""Check script for $loop panel repair — calls scillm GPT-5.5 vision to review.
Used as: --check 'python scripts/panel_review_check.py --panel 03 --run-root .'
Exit 0 = PASS, Exit 1 = NEEDS_CHANGES. Outputs structured JSON to stderr for $loop.
"""
import sys, os, json, base64, urllib.request, argparse

SCILLM_URL = "http://127.0.0.1:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"
CALLER = "persona-dream"

ENTITY_PROMPTS = {
    "01": "Panel 01 (wide establishing). Check: 1) Embry Lawson visible (young woman, dark ponytail, gray fieldwear, human scale, NOT Space Marine)? 2) Horus at 11.5ft Primarch scale (bald, pale, black-gold armor)? 3) Tyranids with chitin/scything talons? 4) Tzeentch sky-eye (blue-violet)? 5) Tea steam rising? 6) Umbrella fabric in wind?",
    "02": "Panel 02 (medium shot on Horus). Check: 1) Horus at 11.5ft Primarch scale, black-gold armor? 2) Tea steam curling around gauntlet with heat shimmer? 3) Umbrella fabric responding to wind above frame?",
    "03": "Panel 03 (medium shot on Embry). Check: 1) Embry opening SPARTA Explorer? 2) Screen glow reflecting on face? 3) Tea steam crossing sightline? 4) Thumb rubbing laptop edge?",
    "04": "Panel 04 (background wide). Check: 1) Tyranids at distance with scything talons, chitin? 2) Stone railing with grit/wet detail? 3) Sky-eye watching with pupil twitch?",
    "05": "Panel 05 (insert detail). Check: 1) Tea steam rising/bending downwind? 2) Evidence card corners lifting? 3) Sky-eye glint on tea? 4) Umbrella shadow shifting on notes?",
    "06": "Panel 06 (MCU on Horus, over Embry's shoulder). Check: 1) Horus holding evidence card (paper flexing)? 2) Steam threading past cheek? 3) Brow tightening, jaw creasing, dry smile? 4) Foreground over-shoulder subject is Embry Lawson (young human woman in gray fieldwear), NOT a random Space Marine or armored male? 5) Tea table/umbrella/SPARTA work context remains visible enough for continuity?",
    "07": "Panel 07 (reverse MCU on Embry). Check: 1) Embry tapping source_refs with fingerprint? 2) Thumb pausing on laptop edge? 3) Shoulders dropping? 4) Tea steam curling?",
    "08": "Panel 08 (screen insert). Check: 1) SPARTA screen with monitor_sparta.py readable? 2) Reflections in glass are identifiable as Horus and Embry, NOT unknown/random characters? 3) Cold light + warm screen glow mix? 4) Tea table/umbrella context remains visible?",
    "09": "Panel 09 (wide motion). Check: 1) Tyranids behind umbrella with chitin/talons? 2) Sky-eye blinking/tracking? 3) Umbrella canopy straining in gust? 4) Tea steam rising? 5) Horus and Embry both visibly present at the table? 6) SPARTA laptop visibly present on the table?",
    "10": "Panel 10 (closing two-shot). Check: 1) Umbrella canopy pulling camera-left with rib flex? 2) Steam thinning/dissipating? 3) Sky-eye dimming with final blink? 4) Horus/Embry leaning over notes?",
}

def review_panel(panel_num, img_path):
    if not os.path.exists(img_path):
        return "MISSING", []
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()
    body = json.dumps({
        "model": "gpt-5.5",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": ENTITY_PROMPTS.get(panel_num, "Review this panel image. Check if required entities are visible per the interaction contract.") + "\nReturn ONLY one line: PASS if every listed check is satisfied, otherwise NEEDS_CHANGES: <specific failing checks with details>."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]
        }]
    }).encode()
    req = urllib.request.Request(SCILLM_URL, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {SCILLM_KEY}", "X-Caller-Skill": CALLER})
    resp = urllib.request.urlopen(req, timeout=60)
    result = json.loads(resp.read())
    verdict = result['choices'][0]['message']['content'].strip()
    failures = []
    if verdict.startswith("NEEDS_CHANGES:"):
        failures = [f.strip() for f in verdict.replace("NEEDS_CHANGES:", "").split(";") if f.strip()]
    return verdict, failures

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", required=True, help="Panel number (01-10)")
    parser.add_argument("--run-root", required=True, help="Pipeline run root")
    parser.add_argument(
        "--image",
        default=None,
        help="Optional panel image path to review instead of the active pipeline_review_8892 asset",
    )
    args = parser.parse_args()
    img_path = args.image or os.path.join(
        args.run_root,
        "pipeline_review_8892",
        "assets",
        "panels",
        f"panel_{args.panel}_storyboard.png",
    )
    verdict, failures = review_panel(args.panel, img_path)
    result = {"panel": args.panel, "verdict": verdict[:300], "failures": failures}
    print(json.dumps(result), file=sys.stderr)
    if verdict.startswith("PASS"):
        print(f"Panel {args.panel}: PASS")
        sys.exit(0)
    else:
        print(f"Panel {args.panel}: {verdict[:200]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
