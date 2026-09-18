#!/usr/bin/env python3
"""Capture a ChatGPT reasoning summary from a live surf tab and grade it with jev.

The reasoning is visible in the browser ("Worked for Ns" header, click to expand).
No native-host feature, no DOM-text regex baked into surf: one surf js read + jev.

Usage:
  capture_reasoning.py --tab-id 837439662 --question "Prove ..." \
      [--out reasoning.txt] [--grade]

Reasoning text is read by expanding any collapsed reasoning block and taking the
fullest block whose visible text starts with the reasoning header. If ChatGPT
renames the header again, change HEADER_PREFIXES here in one place -- it is data,
not logic scattered across the host.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

SURF = Path(__file__).resolve().parents[1] / "surf" / "run.sh"
JEV = Path(__file__).resolve().parents[1] / "jev" / "run.sh"
# Observed reasoning header wordings, newest first. Data, changed in one place.
HEADER_PREFIXES = ["worked for", "thought for", "reasoned", "thinking"]

# One expression: expand collapsed reasoning, then return the fullest block whose
# visible text begins with a known reasoning header. Prefixes injected as data.
JS = """
(()=>{
  const prefixes = %s;
  const isHeader = (t) => prefixes.some(p => t.toLowerCase().startsWith(p));
  document.querySelectorAll('div,span,button').forEach(e=>{
    const t=(e.innerText||'').trim();
    if(t.length<30 && isHeader(t)){ try{e.click()}catch(_){}}
  });
  let best='';
  document.querySelectorAll('div').forEach(e=>{
    const t=(e.innerText||'').trim();
    if(isHeader(t) && t.length>best.length && t.length<20000) best=t;
  });
  return best;
})()
"""


def capture(tab_id: str) -> str:
    code = JS % json.dumps(HEADER_PREFIXES)
    out = subprocess.run(
        [str(SURF), "js", "--tab-id", tab_id, "--no-activate", "--code", code],
        capture_output=True, text=True, timeout=90,
    )
    raw = out.stdout.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = json.loads(raw)  # unwrap the JSON string surf returns
    return raw.replace("\\n", "\n").strip()


def grade(question: str, reasoning: str) -> dict:
    state = {"turns": [
        f"0|user|question|{question}",
        f"1|assistant|reasoning|{reasoning[:4000]}",
    ]}
    Path("/tmp/jev_reasoning_state.json").write_text(json.dumps(state))
    out = subprocess.run(
        [str(JEV), "ask", "--preset", "reasoning_trace",
         "--state", "@/tmp/jev_reasoning_state.json", "--allow-egress"],
        capture_output=True, text=True, timeout=120,
    )
    return json.loads(out.stdout)


def _selftest() -> None:
    # The one piece of real logic: which visible headers count as reasoning.
    hit = lambda t: any(t.lower().startswith(p) for p in HEADER_PREFIXES)
    assert hit("Worked for 39s"), "current ChatGPT header must match"
    assert hit("Thought for 12s"), "legacy header must still match"
    assert not hit("Prove there are infinitely many primes"), "answer text must not match"
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab-id")
    ap.add_argument("--question", default="")
    ap.add_argument("--out")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return 0

    reasoning = capture(args.tab_id)
    # A real reasoning block starts with a known header ("Worked for Ns") and
    # has substance. A bogus/empty tab returns junk or nothing -- reject it so
    # captured:true means an actual reasoning block, not any stray text.
    low = reasoning.lower()
    is_block = any(low.startswith(p) for p in HEADER_PREFIXES) and len(reasoning) > 100
    if not is_block:
        print(json.dumps({"captured": False, "chars": len(reasoning),
                          "reason": "no reasoning block on tab"}))
        return 1
    if args.out:
        Path(args.out).write_text(reasoning + "\n")
    result = {"captured": True, "chars": len(reasoning), "out": args.out}
    if args.grade:
        result["jev"] = grade(args.question, reasoning)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
