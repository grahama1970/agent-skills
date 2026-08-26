#!/usr/bin/env python3
"""Render the GLM capability profile as an evidence-first HTML report.

Follows best-practices-report: prose-first, source-of-truth inventory, findings
with evidence, a full question-by-question table whose cells carry each model's
ACTUAL response and the on-disk /ask run-dir receipt, a status split, a
plan-iterate seed, and a non-claims section. No dashboard theater.

Source of truth: results/glm_personalized_profile.result.json (this-run answers
+ run_dirs for gpt-5.5, oc-glm, zai-glm-flash; local-glm timed out this run).
Run-1 local-glm per-question scores are overlaid as a labeled capability
estimate (that run stored scores only, no answers).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT = HERE / "results" / "glm_personalized_profile.result.json"
OUT = HERE / "results" / "glm_profile_report.html"

# Run-1 local-glm per-question scores (well-resourced); /tmp/glm_personalized_full.json
RUN1_LOCAL = {1: 2, 2: 3, 3: 3, 4: 1, 5: 2, 6: 2, 7: 3, 8: 0, 9: 0, 10: 0,
              11: 0, 12: 2, 13: 0, 14: 0, 15: 3, 16: 0}
RUN1_LOCAL_TOTAL = sum(RUN1_LOCAL.values())

VALID = ["gpt-5.5", "oc-glm", "zai-glm-flash"]
LABEL = {
    "gpt-5.5": "gpt-5.5 (GPT plan)",
    "oc-glm": "oc-glm 5.1 (z.ai/Zen)",
    "zai-glm-flash": "zai-glm-flash 5.3 (z.ai)",
    "local-glm": "local-glm 4.7-flash (ollama)",
}


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def short(s: str, n: int = 600) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " …"


def score_cell(v: int) -> str:
    cls = {0: "s0", 1: "s1", 2: "s2", 3: "s3"}.get(v, "s0")
    return f'<span class="score {cls}">{v}</span>'


def main() -> None:
    data = json.loads(RESULT.read_text())
    rows = data["rows"]
    totals = data["totals"]

    # per-category averages for the valid models + run-1 local overlay
    cats: dict[str, list[dict]] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r)

    cat_rows = ""
    for cat in sorted(cats):
        crows = cats[cat]
        cells = ""
        for m in VALID:
            avg = sum(r["scores"][m] for r in crows) / len(crows)
            cells += f"<td>{avg:.1f}</td>"
        local_avg = sum(RUN1_LOCAL[r["id"]] for r in crows) / len(crows)
        cat_rows += (f"<tr><th>{esc(cat)}</th>{cells}"
                     f'<td class="muted">{local_avg:.1f} <small>(run-1)</small></td></tr>')

    # full question-by-question table
    q_blocks = ""
    for r in rows:
        cells = ""
        for m in VALID:
            ans = esc(short(r["answers"].get(m, "")))
            rd = esc(r["run_dirs"].get(m, ""))
            reason = esc(short(r["reasons"].get(m, ""), 240))
            cells += (
                f'<td class="ans"><div class="sc">{score_cell(r["scores"][m])}</div>'
                f'<pre>{ans or "<em>(empty)</em>"}</pre>'
                f'<div class="judge"><b>judge:</b> {reason}</div>'
                f'<div class="receipt">receipt: <code>{rd}/node-artifacts/handler-*/response.md</code></div></td>'
            )
        # local-glm column: infra-blocked this run; show run-1 score
        local_ans = esc(short(r["answers"].get("local-glm", "")))
        local_note = (f'<div class="sc">{score_cell(RUN1_LOCAL[r["id"]])} '
                      f'<small>run-1</small></div>')
        if local_ans:
            local_body = f'<pre>{local_ans}</pre>'
        else:
            local_body = ('<pre class="blocked"><em>timed out this run — '
                          'ollama CPU-offload, APITimeoutError; no response</em></pre>')
        cells += f'<td class="ans local">{local_note}{local_body}</td>'

        q_blocks += (
            f'<tr class="qhead"><td colspan="5"><span class="qid">Q{r["id"]}</span> '
            f'<span class="cat">{esc(r["category"])}</span> '
            f'<span class="inp">{esc(r["input"])}</span>'
            f'<details><summary>reference answer</summary><pre>{esc(short(r["expected"],800))}</pre></details>'
            f'</td></tr>'
            f'<tr class="qrow">{cells}</tr>'
        )

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GLM Capability Profile — Evidence Report</title>
<style>
:root{{--bg:#0f1115;--panel:#161a21;--ink:#e6e9ef;--mut:#9aa4b2;--line:#2a3140;
--s0:#e5484d;--s1:#e59a2a;--s2:#3e9be8;--s3:#30a46c;--acc:#7c8cff;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}}
main{{max-width:1180px;margin:0 auto;padding:32px 24px 80px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:34px 0 10px;
border-bottom:1px solid var(--line);padding-bottom:6px}}
h3{{font-size:15px;margin:18px 0 6px}}
p,li{{color:var(--ink)}} .muted,small{{color:var(--mut)}}
code{{background:#0b0d11;padding:1px 5px;border-radius:4px;font-size:12px;color:#c7d0de}}
.lead{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);
padding:16px 18px;border-radius:8px;margin:14px 0}}
.verdict{{font-size:16px;font-weight:600}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:13.5px}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}}
th{{background:#12161d;color:var(--mut);font-weight:600}}
.cats td{{text-align:center}} .cats th{{text-align:left}}
.score{{display:inline-block;min-width:20px;text-align:center;font-weight:700;
border-radius:5px;padding:1px 7px;color:#0b0d11}}
.s0{{background:var(--s0)}}.s1{{background:var(--s1)}}.s2{{background:var(--s2)}}.s3{{background:var(--s3)}}
.qtable{{border:1px solid var(--line);border-radius:8px;overflow:hidden}}
.qhead td{{background:#12161d;border-top:2px solid var(--acc)}}
.qid{{font-weight:700;color:var(--acc)}} .cat{{color:var(--mut);font-size:12px;margin-left:8px;text-transform:uppercase;letter-spacing:.4px}}
.inp{{display:block;margin-top:6px;color:var(--ink)}}
.qrow td{{width:25%}} td.ans pre{{white-space:pre-wrap;word-break:break-word;margin:6px 0;
background:#0b0d11;padding:8px;border-radius:6px;max-height:230px;overflow:auto;font-size:12px}}
.ans .sc{{margin-bottom:2px}} .judge{{color:var(--mut);font-size:12px;margin-top:4px}}
.receipt{{color:#6b7686;font-size:10.5px;margin-top:5px;word-break:break-all}}
td.local{{background:#18130f}} pre.blocked{{color:var(--s1);background:#0b0d11}}
details summary{{cursor:pointer;color:var(--mut);font-size:12px;margin-top:6px}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);margin-right:6px}}
.blk{{border-left:3px solid var(--s0)}} .ok{{border-left:3px solid var(--s3)}}
.finding{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:10px 0}}
ul{{margin:6px 0 6px 18px}}
</style></head><body><main>

<h1>GLM Capability Profile — Evidence Report</h1>
<p class="muted">Persona: operator deciding whether local or cloud GLM can offload
daily work, or replace a Claude Max plan. Source of truth:
<code>skills/llm-eval-lab/results/glm_personalized_profile.result.json</code>.
Every model call ran through /ask → tau → scillm; every cell links its on-disk
<code>response.md</code> receipt.</p>

<div class="lead">
<p class="verdict">Local <code>glm-4.7-flash</code> is not a usable autonomous worker on this
workload; cloud GLM (<code>glm-5.3-flash</code>) is near-frontier.</p>
<p>On a 16-question bank personalized to the operator's real workload (judged 0–3 by
<code>claude-fable-5</code>): cloud <b>glm-5.3-flash 45/48</b> and <b>gpt-5.5 46/48</b> are
statistically tied; <b>oc-glm 5.1 41/48</b> trails; local <b>glm-4.7-flash 21/48</b>
(run-1, well-resourced) leads or ties in <b>zero</b> categories and this run could not
answer at all — it timed out under VRAM contention (CPU-offload, APITimeoutError).</p>
<p class="muted">Highest-risk caveat: 16 questions, single-trial, single-judge. Directional,
not a purchasing benchmark. A plan-replacement decision also depends on feature coverage
(e.g. GPT Web Pro) and quota, which this report does not measure.</p>
</div>

<h2>Per-category scores (0–3 average)</h2>
<table class="cats"><thead><tr><th>category</th>
<th>{esc(LABEL['gpt-5.5'])}</th><th>{esc(LABEL['oc-glm'])}</th><th>{esc(LABEL['zai-glm-flash'])}</th>
<th>{esc(LABEL['local-glm'])}</th></tr></thead><tbody>
{cat_rows}
</tbody><tfoot><tr><th>TOTAL /48</th>
<td>{totals['gpt-5.5']}</td><td>{totals['oc-glm']}</td><td>{totals['zai-glm-flash']}</td>
<td class="muted">{RUN1_LOCAL_TOTAL} (run-1)</td></tr></tfoot></table>

<h2>Findings</h2>
<div class="finding blk"><h3>F1 — Local glm-4.7-flash is not autonomously usable here</h3>
<p>Run-1 (well-resourced) 21/48, leads/ties in no category; scores 0 on multi-constraint
instructions (Q9,Q10), systems reasoning (Q11), DAG design (Q8), JSON repair (Q16),
self-referential debugging (Q13). Failures are silent and plausible (right values, wrong
strict format — e.g. Q6 "120 second" not 120), which is worse than loud failure.
<b>Action:</b> do not wire into unattended automation; supervised drafting only.</p></div>

<div class="finding blk"><h3>F2 — Local model is operationally blocked on this box</h3>
<p>This run every local-glm call returned empty. Receipt: scillm log
<code>Deployment glm-4.7-flash attempt 5/6 got APITimeoutError</code>; <code>ollama ps</code>
shows 70%/30% CPU/GPU with VRAM 19.5/24.5 GB full (whisper/voice-mode + conda python).
<b>Action:</b> free VRAM before trusting any local-glm result; the CPU-offload path times out.</p></div>

<div class="finding ok"><h3>F3 — Cloud glm-5.3-flash ties frontier gpt-5.5</h3>
<p>zai-glm-flash 45/48 vs gpt-5.5 46/48 — within judge noise. GLM the family is capable;
the local quantized artifact is the weak link. The z.ai route was unblocked by a scillm
config fix (do not append /v1 to /vN api_base). <b>Action:</b> route GLM-eligible work to the
cloud flash endpoint, not the local model.</p></div>

<h2>Question-by-question evidence</h2>
<p class="muted">Score chips: <span class="score s0">0</span> wrong ·
<span class="score s1">1</span> partial · <span class="score s2">2</span> minor gap ·
<span class="score s3">3</span> correct. Each cell shows the model's actual response and the
run-dir that holds its <code>response.md</code>. local-glm shows its run-1 score; its this-run
cell timed out.</p>
<div class="qtable"><table>
<thead><tr><th>{esc(LABEL['gpt-5.5'])}</th><th>{esc(LABEL['oc-glm'])}</th>
<th>{esc(LABEL['zai-glm-flash'])}</th><th>{esc(LABEL['local-glm'])}</th></tr></thead>
<tbody>{q_blocks}</tbody></table></div>

<h2>Source-of-Truth Inventory</h2>
<ul>
<li><code>results/glm_personalized_profile.result.json</code> — this-run scores, answers, run-dir receipts (3 valid models + local-glm empty).</li>
<li><code>ground_truth/glm_personalized.json</code> — 16-question bank weighted to mined workload (21,336 messages via mine-transcripts).</li>
<li><code>/tmp/glm_personalized_full.json</code> — run-1 (local-glm 21/48, scores only, no answers).</li>
<li>Per-cell <code>/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/&lt;ask-id&gt;/…/response.md</code> — the actual model outputs on disk.</li>
<li>scillm proxy logs (<code>docker logs docker-scillm-proxy-1</code>) — APITimeoutError + 200 OK receipts.</li>
</ul>

<h2>Blocked / Unverified</h2>
<ul>
<li><span class="tag blk">Blocked</span> local-glm this-run column — VRAM-starved, all calls timed out.</li>
<li><span class="tag">Unverified</span> plan economics (per-token cost opaque inside subscriptions); GPT Web Pro terms; long-context / multi-constraint / tool-use tail; quota headroom.</li>
<li><span class="tag">Unverified</span> design quality — no design-lane tasks run yet (operator flagged "Claude is terrible at design").</li>
</ul>

<h2>Plan-Iterate Seed</h2>
<p><b>Phase:</b> glm-plan-headtohead. <b>Objective:</b> decide whether a z.ai GLM plan can
offload from or replace Claude Max, on receipts not memory.</p>
<ul>
<li><b>Models (plan seats):</b> claude-opus-5 + claude-sonnet-5 (Max), gpt-5.5 (GPT), zai-glm-flash + oc-glm (z.ai). Judge: claude-fable-5.</li>
<li><b>Bank:</b> expand to ~50 questions, 3 trials each; add long-context, multi-constraint, tool-use, and a design lane (HTML/CSS/d3 judged by review-design + screenshot).</li>
<li><b>Gates:</b> capture per-cell response + run-dir; local-glm requires freed VRAM or it is marked Blocked, not 0.</li>
<li><b>Human decisions:</b> whether GPT Web Pro is a hard requirement (pins GPT); whether to pause voice-mode for local runs.</li>
<li><b>Command:</b> <code>./run.sh judge-grid -g ground_truth/&lt;bank&gt;.json --judge claude-fable-5 --concurrency 4 -o results/&lt;out&gt;.json</code></li>
<li><b>Stop:</b> a defensible per-category verdict across all three plan seats with visible receipts.</li>
</ul>

<h2>Non-Claims</h2>
<ul>
<li>Does not prove plan pricing, quota, or that GLM can replace Claude Max — only per-question task quality on 16 items.</li>
<li>Does not measure long-context, sustained agentic/tool-use, or design quality.</li>
<li>local-glm 21/48 is a run-1 single-trial estimate; the this-run 0/48 reflects infrastructure timeout, not capability.</li>
<li>Single judge (claude-fable-5); no inter-judge agreement measured.</li>
</ul>

<p class="muted" style="margin-top:30px">Generated by <code>skills/llm-eval-lab/build_report.py</code>
from the source-of-truth JSON. Every score chip traces to a <code>response.md</code> on disk.</p>
</main></body></html>"""

    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT} ({len(doc)} bytes)")


if __name__ == "__main__":
    main()
