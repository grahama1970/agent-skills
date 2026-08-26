"""Reusable, live evidence-report renderer for the eval lab.

Registered as `report`. Emits a self-contained HTML page whose renderer is
JavaScript, so the SAME page serves two modes:

  --live --src <results.json>  : the page fetches the results file and re-renders
                                 every few seconds (hot reload) while run-matrix
                                 writes cells incrementally -- you watch the grid
                                 fill in, INFRA_BLOCKED badges appear live, and
                                 polling stops when status == "complete".
  (default / snapshot)         : the results JSON is inlined and rendered once,
                                 as a durable artifact to commit/share.

Consumes any run-matrix output (runner.py schema). Not bespoke to one bank or
model set. Evidence-first per best-practices-report: score chip + rationale on
top of each cell, raw response collapsible, on-disk run_dir receipt cited,
INFRA_BLOCKED isolated from accuracy averages. No framework, no build step.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer

from eval_app import app, console

# The client-side renderer. Kept as one JS string so the live and snapshot
# pages share exactly one implementation (DRY). It reads a global RESULTS object
# of the run-matrix schema and paints metrics + a per-question evidence grid.
RENDERER_JS = r"""
const BLOCKED = "INFRA_BLOCKED";
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => (
  {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const short = (s, n=1600) => { s=(s||"").trim(); return s.length<=n ? s : s.slice(0,n)+" …"; };
const chip = (v) => v==null ? '<span class="score blk">–</span>'
  : `<span class="score s${v}">${v}</span>`;

function bestTrial(cell){
  const t=(cell.trials||[]).filter(x=>x.score!=null);
  if(!t.length) return (cell.trials||[])[0]||{};
  return t.reduce((a,b)=> b.score>a.score ? b : a);
}
function metrics(results, models){
  const out={};
  for(const m of models){
    const cells=results.filter(r=>r.model===m);
    const valid=cells.filter(r=>r.status!==BLOCKED && r.pass_at_1!=null);
    const blocked=cells.filter(r=>r.status===BLOCKED);
    const n=valid.length;
    out[m]={n, blocked:blocked.length,
      p1: n? (valid.reduce((s,r)=>s+r.pass_at_1,0)/n).toFixed(2):null,
      p3: n? (valid.reduce((s,r)=>s+r.pass_at_3,0)/n).toFixed(2):null,
      blockedIds: blocked.map(r=>r.id).sort((a,b)=>a-b)};
  }
  return out;
}
function cell(c){
  if(!c) return '<td class="ans muted">—</td>';
  if(c.status===BLOCKED){
    const reason=esc((c.trials&&c.trials[0]&&c.trials[0].reason)||"operational failure");
    return `<td class="ans blocked-cell"><div class="badge-blk">⚠ INFRA_BLOCKED</div>
      <div class="judge">${reason}</div>
      <div class="muted small">excluded from accuracy averages</div></td>`;
  }
  const t=bestTrial(c);
  const raw=esc(short(t.answer))||"<em>(empty)</em>";
  return `<td class="ans">
    <div class="verdict">${chip(t.score)}
      <span class="pk">pass@1 ${c.pass_at_1} · pass@3 ${c.pass_at_3}</span>
      <span class="method">${esc(t.method||c.method||"")}</span></div>
    <div class="judge"><b>rationale:</b> ${esc(short(t.reason,300))}</div>
    <details><summary>show raw model response</summary><pre>${raw}</pre></details>
    <div class="receipt">receipt: <code>${esc(t.run_dir||"")}/node-artifacts/handler-*/response.md</code></div>
  </td>`;
}
function render(D){
  const models=D.models||[], results=D.results||[];
  const M=metrics(results, models);
  const byId={}, cats={};
  for(const r of results){ (byId[r.id]=byId[r.id]||{})[r.model]=r; cats[r.id]=r.category||""; }
  const ids=Object.keys(byId).map(Number).sort((a,b)=>a-b);
  const head=models.map(m=>`<th>${esc(m)}</th>`).join("");

  const prog=D.progress||{done:results.length,total:results.length};
  const live=(D.status==="running");
  document.getElementById("livebar").innerHTML =
    `<span class="dot ${live?'on':'off'}"></span> ${live?'LIVE — running':'complete'} ·
     ${prog.done}/${prog.total} cells`;

  const banner = Object.entries(M).filter(([,v])=>v.blockedIds.length)
    .map(([m,v])=>`${esc(m)} → Q${v.blockedIds.join(",")}`).join("; ");
  document.getElementById("banner").innerHTML = banner
    ? `<div class="lead blk"><b>⚠ Infrastructure notice:</b> items INFRA_BLOCKED
       (timeout / VRAM / guard) and excluded from averages — ${banner}.
       Operational failures, not wrong answers.</div>` : "";

  const row=(label,f)=>`<tr><th>${label}</th>${models.map(m=>`<td>${f(M[m])}</td>`).join("")}</tr>`;
  document.getElementById("summary").innerHTML =
    `<table class="summary"><thead><tr><th>metric</th>${head}</tr></thead><tbody>
     ${row("avg pass@1 (0–3)", v=>v.p1??"—")}
     ${row("avg pass@3 (0–3)", v=>v.p3??"—")}
     ${row("infra-blocked", v=>v.blocked)}
     </tbody></table>`;

  const allCats=[...new Set(Object.values(cats))].sort();
  const catRows=allCats.map(c=>{
    const cid=ids.filter(i=>cats[i]===c);
    const tds=models.map(m=>{
      const vals=cid.filter(i=>byId[i][m]&&byId[i][m].status!==BLOCKED&&byId[i][m].pass_at_1!=null)
        .map(i=>byId[i][m].pass_at_1);
      return vals.length? `<td>${(vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1)}</td>`
        : '<td class="muted">—</td>';
    }).join("");
    return `<tr><th>${esc(c)}</th>${tds}</tr>`;
  }).join("");
  document.getElementById("cats").innerHTML =
    `<table class="summary"><thead><tr><th>category</th>${head}</tr></thead><tbody>${catRows}</tbody></table>`;

  const q=ids.map(i=>`<tr class="qhead"><td colspan="${models.length}">
      <span class="qid">Q${i}</span> <span class="cat">${esc(cats[i])}</span></td></tr>
      <tr class="qrow">${models.map(m=>cell(byId[i][m])).join("")}</tr>`).join("");
  document.getElementById("grid").innerHTML =
    `<div class="qtable"><table><thead><tr>${head}</tr></thead><tbody>${q}</tbody></table></div>`;
  document.title = (D.title||"Eval") + " — Evidence Report";
  document.getElementById("h1").textContent = (D.title||"Eval") + " — Evidence Report";
  return D.status==="complete";
}
"""

CSS = r"""
:root{--bg:#0f1115;--panel:#161a21;--ink:#e6e9ef;--mut:#9aa4b2;--line:#2a3140;
--s0:#e5484d;--s1:#e59a2a;--s2:#3e9be8;--s3:#30a46c;--acc:#7c8cff;--blk:#d97706;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:1220px;margin:0 auto;padding:28px 24px 80px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:30px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
code{background:#0b0d11;padding:1px 5px;border-radius:4px;font-size:12px;color:#c7d0de}
.muted,.small{color:var(--mut)}.small{font-size:12px}
.livebar{display:inline-block;font-size:13px;color:var(--mut);margin:6px 0 2px;padding:3px 10px;border:1px solid var(--line);border-radius:999px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.dot.on{background:var(--s3);box-shadow:0 0 0 0 rgba(48,164,108,.7);animation:pulse 1.4s infinite}
.dot.off{background:var(--mut)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(48,164,108,.6)}70%{box-shadow:0 0 0 7px rgba(48,164,108,0)}100%{box-shadow:0 0 0 0 rgba(48,164,108,0)}}
.lead{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--blk);padding:12px 16px;border-radius:8px;margin:12px 0}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:#12161d;color:var(--mut);font-weight:600}
.summary td,.summary th{text-align:center}.summary th:first-child,.summary td:first-child{text-align:left}
.score{display:inline-block;min-width:20px;text-align:center;font-weight:700;border-radius:5px;padding:1px 7px;color:#0b0d11}
.s0{background:var(--s0)}.s1{background:var(--s1)}.s2{background:var(--s2)}.s3{background:var(--s3)}.blk{background:#3a3a3a;color:#cbd5e1}
.qtable{border:1px solid var(--line);border-radius:8px;overflow:hidden}
.qhead td{background:#12161d;border-top:2px solid var(--acc)}.qid{font-weight:700;color:var(--acc)}
.cat{color:var(--mut);font-size:12px;margin-left:8px;text-transform:uppercase;letter-spacing:.4px}
.verdict{margin-bottom:6px}.pk{font-size:12px;color:var(--mut);margin-left:6px}
.method{font-size:11px;border:1px solid var(--line);border-radius:999px;padding:1px 7px;color:var(--mut);margin-left:6px}
.judge{color:var(--ink);font-size:12.5px;margin:4px 0}
details summary{cursor:pointer;color:var(--mut);font-size:12px}
td.ans pre{white-space:pre-wrap;word-break:break-word;background:#0b0d11;padding:8px;border-radius:6px;max-height:260px;overflow:auto;font-size:12px;margin:6px 0}
.receipt{color:#6b7686;font-size:10.5px;margin-top:5px;word-break:break-all}
.badge-blk{color:var(--blk);font-weight:700}.blocked-cell{background:#18130f}
"""


def _page(bootstrap: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Eval — Evidence Report</title><style>" + CSS + "</style></head><body><main>"
        "<h1 id=\"h1\">Eval — Evidence Report</h1>"
        "<div class=\"livebar\" id=\"livebar\">loading…</div>"
        "<p class=\"muted\">Every call ran through /ask → tau → scillm. Deterministic items "
        "(code/JSON) graded by execution; others by LLM judge. Each cell cites its on-disk "
        "<code>response.md</code>. INFRA_BLOCKED = operational failure, excluded from accuracy.</p>"
        "<div id=\"banner\"></div>"
        "<h2>Per-model metrics (accuracy excludes INFRA_BLOCKED)</h2><div id=\"summary\"></div>"
        "<h2>Per-category pass@1 (0–3, blocked excluded)</h2><div id=\"cats\"></div>"
        "<h2>Question-by-question evidence</h2>"
        "<p class=\"muted\">Cells lead with score and rationale; raw response collapsible; "
        "receipt path holds the model's actual bytes.</p><div id=\"grid\"></div>"
        "<script>" + RENDERER_JS + bootstrap + "</script></main></body></html>"
    )


def live_html(src: str, interval_ms: int) -> str:
    boot = (
        f"\nconst SRC={json.dumps(src)}, POLL={interval_ms};\n"
        "async function tick(){\n"
        "  try{const r=await fetch(SRC+'?t='+Date.now(),{cache:'no-store'});\n"
        "    if(r.ok){const done=render(await r.json()); if(done) return;}}\n"
        "  catch(e){document.getElementById('livebar').innerHTML="
        "'<span class=\"dot off\"></span> waiting for results…';}\n"
        "  setTimeout(tick, POLL);\n}\ntick();\n"
    )
    return _page(boot)


def snapshot_html(data: dict) -> str:
    boot = f"\nconst RESULTS={json.dumps(data)};\nrender(RESULTS);\n"
    return _page(boot)


@app.command(name="report")
def report(
    results: Path = typer.Option(None, "--results", "-i", help="run-matrix JSON (snapshot mode)."),
    output: Path = typer.Option(..., "--output", "-o", help="HTML file to write."),
    live: bool = typer.Option(False, "--live", "-L", help="Emit a hot-reloading page that polls --src."),
    src: str = typer.Option("", "--src", help="Relative URL the live page fetches (e.g. results.json)."),
    interval_ms: int = typer.Option(2500, "--interval-ms", help="Live poll interval."),
) -> None:
    """Render a live-updating or snapshot evidence report from run-matrix output."""
    if live:
        source = src or (results.name if results else "")
        if not source:
            console.print("[red]--live needs --src or --results to name the polled file[/red]")
            raise typer.Exit(2)
        Path(output).write_text(live_html(source, interval_ms), encoding="utf-8")
        console.print(f"[dim]wrote live report {output} (polls {source} every {interval_ms}ms)[/dim]")
    else:
        if not results:
            console.print("[red]snapshot mode needs --results[/red]"); raise typer.Exit(2)
        data = json.loads(Path(results).read_text(encoding="utf-8"))
        Path(output).write_text(snapshot_html(data), encoding="utf-8")
        console.print(f"[dim]wrote snapshot report {output}[/dim]")
    console.print("REPORT_COMPLETE")
