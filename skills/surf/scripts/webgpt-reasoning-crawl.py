#!/usr/bin/env python3
"""Capture ChatGPT reasoning summaries ("Worked for Ns") from the sidebar history.

Surf-native. Looks in the PAST: walks the last N sidebar conversations, one at a
time, navigating a single tab to each, capturing the visible reasoning, then
throttling before the next. Reopened conversations retain their reasoning, so
this harvests history, not just currently-open tabs.

  surf webgpt.reasoning-crawl --tab-id <id> [--limit 20] [--throttle 300] [--store-memory]
  surf webgpt.reasoning-crawl --tab-id <id> --current-only     # just this tab

Reasoning capture keys off the visible header wording, kept here as data so a
ChatGPT rename is a one-line edit, not a code hunt. Observed newest-first.
"""
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
RUN = SKILL_DIR / "run.sh"
HEADER_PREFIXES = ["worked for", "thought for", "reasoned", "thinking"]
MEMORY = "http://127.0.0.1:8601"

SIDEBAR_JS = """
(()=>{
  const links=[...document.querySelectorAll('a[href^="/c/"]')]
    .map(a=>({href:a.getAttribute('href'),title:(a.innerText||'').trim().slice(0,50)}));
  const seen=new Set(); const uniq=[];
  for(const l of links){ if(!seen.has(l.href)){seen.add(l.href); uniq.push(l);} }
  return JSON.stringify(uniq);
})()
"""

CAPTURE_JS = """
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


def surf_js(tab: str, code: str) -> str:
    r = subprocess.run([str(RUN), "js", "--tab-id", tab, "--no-activate", "--code", code],
                       capture_output=True, text=True, timeout=120)
    out = r.stdout.strip()
    return json.loads(out) if out.startswith('"') else out


def capture(tab: str) -> str:
    raw = surf_js(tab, CAPTURE_JS % json.dumps(HEADER_PREFIXES)).replace("\\n", "\n").strip()
    low = raw.lower()
    if any(low.startswith(p) for p in HEADER_PREFIXES) and len(raw) > 100:
        return raw
    return ""


def store_memory(slug: str, text: str) -> bool:
    import httpx
    key = "rt_side_" + hashlib.sha256((slug + text[:200]).encode()).hexdigest()[:16]
    doc = {"_key": key, "schema": "reasoning.trace.v1", "source": "webgpt_sidebar",
           "origin": "model", "convo_slug": slug, "reasoning_chars": len(text),
           "reasoning_text": text, "retrieval_text": text[:1500],
           "captured_at": datetime.datetime.now(datetime.UTC).isoformat(),
           "eligible_for": [], "outcome_label": None,
           "label_provenance": "unlabeled_sidebar_crawl"}
    try:
        r = httpx.post(f"{MEMORY}/upsert",
                       json={"collection": "reasoning_traces", "documents": [doc]}, timeout=60)
        return r.status_code < 300
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab-id", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--throttle", type=int, default=300)
    ap.add_argument("--outdir", default=str(SKILL_DIR / "reports" / "reasoning-crawl"))
    ap.add_argument("--store-memory", action="store_true")
    ap.add_argument("--current-only", action="store_true")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.current_only:
        text = capture(args.tab_id)
        print(json.dumps({"captured": bool(text), "chars": len(text)}))
        if text:
            (outdir / "current.txt").write_text(text + "\n")
        return 0 if text else 1

    convos = json.loads(surf_js(args.tab_id, SIDEBAR_JS))[: args.limit]
    print(f"[{datetime.datetime.now():%H:%M:%S}] crawl {len(convos)} convos throttle={args.throttle}s", flush=True)
    results = []
    for i, c in enumerate(convos):
        href = c["href"].split("?")[0]
        slug = href.rsplit("/", 1)[-1]
        surf_js(args.tab_id, f"location.href={json.dumps(href)}")
        time.sleep(10)
        text = capture(args.tab_id)
        stored = store_memory(slug, text) if (text and args.store_memory) else False
        if text:
            (outdir / f"side_{slug}.txt").write_text(text + "\n")
        results.append({"slug": slug, "title": c["title"], "chars": len(text), "stored": stored})
        print(f"[{datetime.datetime.now():%H:%M:%S}] {i+1}/{len(convos)} {c['title'][:30]!r} "
              f"chars={len(text)} stored={stored}", flush=True)
        if i < len(convos) - 1:
            time.sleep(args.throttle)

    (outdir / "crawl_manifest.json").write_text(json.dumps(
        {"crawled_at": datetime.datetime.now(datetime.UTC).isoformat(),
         "count": len(results), "results": results}, indent=2))
    print(f"[{datetime.datetime.now():%H:%M:%S}] done; {sum(1 for r in results if r['chars']>100)} with reasoning", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
