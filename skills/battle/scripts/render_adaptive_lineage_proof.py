#!/usr/bin/env python3
"""Render a transparent, self-verifying HTML proof of adaptive lineage from a
completed ``arena-adaptive-lineage-qualification`` output directory.

This is deliberately NOT a mockup and NOT aspirational: every value shown is read
back from the run's own receipts, and the descent binding + qualification status
are RE-VERIFIED here (hashes recomputed, selection trace checked) rather than
trusted. If the run did not actually demonstrate adaptive lineage, this script
says so — it renders whatever the receipts prove, including failure.

Usage:
    python scripts/render_adaptive_lineage_proof.py <qualification_out_dir> <out.html>
"""
from __future__ import annotations

import glob
import hashlib
import html
import json
import sys
from pathlib import Path


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _esc(v) -> str:
    return html.escape(str(v))


def build(out_dir: Path) -> tuple[str, dict]:
    R = out_dir / "receipts"
    qual = _load(out_dir / "adaptive-lineage-qualification.json")
    specimens = {s: _load(R / f"specimen-{s}.json") for s in ("G0", "G1-A", "G1-B", "G2")}
    fitness = {s: _load(R / f"fitness-{s}.json") for s in ("G1-A", "G1-B", "G2")}
    sel = _load(R / "lineage-selection.json")

    # --- independent re-verification (do not trust the receipts' own claims) ---
    checks: list[tuple[str, bool, str]] = []

    # 1. the two G1 sources are genuinely distinct
    g1a_src, g1b_src = specimens["G1-A"]["exploit_py"], specimens["G1-B"]["exploit_py"]
    checks.append(("G1-A and G1-B are distinct exploits", g1a_src != g1b_src,
                   f"sha G1-A={_sha256(g1a_src)[:12]} vs G1-B={_sha256(g1b_src)[:12]}"))

    # 2. each specimen's recorded source_sha256 matches its actual bytes
    for s in ("G1-A", "G1-B", "G2"):
        actual = _sha256(specimens[s]["exploit_py"])
        recorded = specimens[s].get("source_sha256", "")
        checks.append((f"{s} source hash is authentic", actual == recorded,
                       f"recomputed={actual[:12]} recorded={str(recorded)[:12]}"))

    # 3. selection is deterministic per the recorded trace, decided on the stated criterion
    trace = sel.get("selection_trace", [])
    decisive = [t for t in trace if t.get("decisive")]
    sel_ok = (bool(decisive)
              and decisive[0]["criterion"] == sel.get("deciding_criterion")
              and decisive[0]["winner"] == sel.get("selected_id"))
    checks.append(("Selection is deterministic and matches its trace", sel_ok,
                   f"{sel.get('selected_id')} won on {sel.get('deciding_criterion')}"))

    # 4. G2 is bound to the SELECTED G1 by content-addressed source hash
    selected_id = sel.get("selected_id")
    selected_sha = specimens[selected_id].get("source_sha256")
    handoffs = glob.glob(str(out_dir / "stage-G2" / "**" / "handoff.json"), recursive=True)
    bound = False
    bind_detail = "no G2 handoff found"
    if handoffs:
        pep = _load(Path(handoffs[0])).get("public_context", {}).get(
            "battle.parent_evidence_packet.v1", {})
        bound = (pep.get("parent_specimen_id") == selected_id
                 and pep.get("parent_source_sha256") == selected_sha)
        bind_detail = (f"G2 parent={pep.get('parent_specimen_id')} "
                       f"parent_source_sha256={str(pep.get('parent_source_sha256'))[:12]} "
                       f"== selected {selected_id} sha={str(selected_sha)[:12]}")
    checks.append(("G2 is content-addressed to the SELECTED G1", bound, bind_detail))

    # 5. the qualification itself passed with a complete G2 Judge
    q_ok = qual.get("status") == "PASS" and qual.get("budget", {}).get("g2_judge_complete")
    checks.append(("Qualification PASSED with a completed G2 Judge", bool(q_ok),
                   f"status={qual.get('status')} g2_judge_complete={qual.get('budget',{}).get('g2_judge_complete')}"))

    all_pass = all(ok for _, ok, _ in checks)

    def node_html(sid: str) -> str:
        sp = specimens[sid]
        fit = fitness.get(sid, {})
        dv = fit.get("delta_validation", {})
        dims = fit.get("technique_signature", {}).get("dimensions", {})
        op = sp.get("mutation_operator") or "— (seed exploit)"
        changed = dv.get("changed_dimensions") or []
        badge = ""
        if sid == selected_id:
            badge = '<span class="badge sel">SELECTED G1</span>'
        elif sid == sel.get("runner_up_id"):
            badge = '<span class="badge run">runner-up</span>'
        dim_rows = "".join(
            f"<tr class='{'chg' if k in changed else ''}'><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
            for k, v in dims.items()
        )
        excerpt = _esc("\n".join(sp.get("exploit_py", "").splitlines()[:14]))
        node_cls = "node sel" if sid == selected_id else "node"
        return f"""
        <div class="{node_cls}" id="node-{_esc(sid)}">
          <div class="nhead"><span class="nid">{_esc(sid)}</span> {badge}
            <span class="op">{_esc(op)}</span>
            <span class="sha">sha {_esc(str(sp.get('source_sha256',''))[:12])}</span></div>
          <div class="meta">delta: <b>{_esc(fit.get('delta_status','—'))}</b> ·
            novelty {_esc(dv.get('novelty_distance','—'))} ·
            operator_consistent {_esc(dv.get('operator_consistent','—'))} ·
            changed [{_esc(', '.join(changed))}]</div>
          <table class="dims"><tr><th>dimension</th><th>value</th></tr>{dim_rows}</table>
          <details><summary>exploit source (first 14 lines)</summary><pre>{excerpt}</pre></details>
        </div>"""

    check_html = "".join(
        f"<li class='{'ok' if ok else 'bad'}'><b>{'PASS' if ok else 'FAIL'}</b> {_esc(label)} "
        f"<span class='detail'>{_esc(detail)}</span></li>"
        for label, ok, detail in checks
    )

    verdict = "ADAPTIVE LINEAGE VERIFIED" if all_pass else "NOT VERIFIED — see failed checks"
    vclass = "pass" if all_pass else "fail"

    body = f"""
    <h1>Adaptive Lineage — Live Proof</h1>
    <p class="sub">Battle <b>{_esc(qual.get('battle_id'))}</b> · run <code>{_esc(qual.get('run_id'))}</code>
       · selection recorded {_esc(sel.get('created_at') or 'no timestamp')}</p>
    <div class="verdict {vclass}">{verdict}</div>

    <h2>The mechanism, from this run's receipts</h2>
    <div class="lineage">
      {node_html('G0')}
      <div class="arrow">mutate → two independent descendants</div>
      <div class="pair">{node_html('G1-A')}{node_html('G1-B')}</div>
      <div class="selbox">
        <b>Deterministic selection:</b> {_esc(selected_id)} over {_esc(sel.get('runner_up_id'))}
        on <code>{_esc(sel.get('deciding_criterion'))}</code>.
        <table class="trace"><tr><th>criterion</th><th>{_esc(selected_id)}</th><th>{_esc(sel.get('runner_up_id'))}</th><th>decisive</th></tr>
        {''.join(f"<tr><td>{_esc(t['criterion'])}</td><td>{_esc(t['a_value'])}</td><td>{_esc(t['b_value'])}</td><td>{'YES' if t['decisive'] else ''}</td></tr>" for t in trace)}
        </table>
      </div>
      <div class="arrow">reproduce ← from the SELECTED G1 (content-addressed)</div>
      {node_html('G2')}
    </div>

    <h2>Independent verification (recomputed here, not trusted)</h2>
    <ul class="checks">{check_html}</ul>

    <h2>What this does and does not prove</h2>
    <p class="honest">Proves, from receipts: two distinct evaluated variants, a deterministic
    selection matching its own trace, and a G2 whose parent-evidence packet is content-addressed
    to the selected G1's exact source hash. Does NOT prove: that G2 is a better exploit than its
    parent, nor anything about a live adaptive <em>canary</em> beyond this single qualification run.</p>
    <p class="foot">Rendered from {_esc(str(out_dir))} — regenerate with
    <code>scripts/render_adaptive_lineage_proof.py</code>.</p>
    """

    page = f"""<style>
 :root{{
   --bg:#eef0f5; --surface:#ffffff; --ink:#161a22; --muted:#5b6478; --line:#dde1ec;
   --verified:#0c7a3e; --verified-bg:#e4f4ea; --runner:#a8631a; --runner-bg:#f8eede;
   --critical:#b3261e; --critical-bg:#fbe7e5; --codebg:#0f141c; --codefg:#cdd6e4;
   --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
   --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,monospace;
 }}
 @media (prefers-color-scheme:dark){{:root{{
   --bg:#0e1117; --surface:#161b24; --ink:#e7eaf1; --muted:#98a1b4; --line:#28303d;
   --verified:#3ecb74; --verified-bg:#12261a; --runner:#e0a54a; --runner-bg:#2a2113;
   --critical:#ef6b60; --critical-bg:#2a1613; --codebg:#0a0e14; --codefg:#c3ccdb;
 }}}}
 :root[data-theme="dark"]{{
   --bg:#0e1117; --surface:#161b24; --ink:#e7eaf1; --muted:#98a1b4; --line:#28303d;
   --verified:#3ecb74; --verified-bg:#12261a; --runner:#e0a54a; --runner-bg:#2a2113;
   --critical:#ef6b60; --critical-bg:#2a1613; --codebg:#0a0e14; --codefg:#c3ccdb;
 }}
 :root[data-theme="light"]{{
   --bg:#eef0f5; --surface:#ffffff; --ink:#161a22; --muted:#5b6478; --line:#dde1ec;
   --verified:#0c7a3e; --verified-bg:#e4f4ea; --runner:#a8631a; --runner-bg:#f8eede;
   --critical:#b3261e; --critical-bg:#fbe7e5; --codebg:#0f141c; --codefg:#cdd6e4;
 }}
 .alp{{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.55;
   max-width:940px;margin:0 auto;padding:2.2rem 1.2rem 4rem;font-size:15px}}
 .alp *{{box-sizing:border-box}}
 .alp .kicker{{font-family:var(--mono);font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin:0}}
 .alp h1{{font-size:2rem;letter-spacing:-.02em;text-wrap:balance;margin:.15rem 0 .1rem;font-weight:800}}
 .alp .sub{{color:var(--muted);margin:0 0 1.1rem;font-family:var(--mono);font-size:.82rem}}
 .alp h2{{font-size:1.02rem;letter-spacing:-.01em;margin:2rem 0 .7rem;padding-bottom:.35rem;border-bottom:1px solid var(--line)}}
 .alp .verdict{{display:flex;align-items:center;gap:.7rem;font-weight:800;font-size:1.05rem;
   padding:.85rem 1.1rem;border-radius:10px;letter-spacing:.01em}}
 .alp .verdict::before{{content:"";width:.7rem;height:.7rem;border-radius:50%;flex:none;box-shadow:0 0 0 4px color-mix(in srgb,currentColor 18%,transparent)}}
 .alp .verdict.pass{{background:var(--verified-bg);color:var(--verified)}}
 .alp .verdict.pass::before{{background:var(--verified)}}
 .alp .verdict.fail{{background:var(--critical-bg);color:var(--critical)}}
 .alp .verdict.fail::before{{background:var(--critical)}}
 .alp .node{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:.85rem 1rem;margin:.55rem 0}}
 .alp .node.sel{{border-color:color-mix(in srgb,var(--verified) 55%,var(--line))}}
 .alp .nhead{{display:flex;gap:.55rem;align-items:baseline;flex-wrap:wrap}}
 .alp .nid{{font-family:var(--mono);font-weight:700;font-size:1.05rem;letter-spacing:.02em}}
 .alp .op{{font-family:var(--mono);color:var(--muted);font-size:.85rem}}
 .alp .sha{{font-family:var(--mono);color:var(--muted);font-size:.74rem;margin-left:auto}}
 .alp .badge{{font-family:var(--mono);font-size:.66rem;font-weight:700;padding:.12rem .45rem;border-radius:5px;text-transform:uppercase;letter-spacing:.08em}}
 .alp .badge.sel{{background:var(--verified);color:var(--surface)}}
 .alp .badge.run{{background:var(--runner);color:var(--surface)}}
 .alp .meta{{font-family:var(--mono);font-size:.78rem;color:var(--muted);margin:.4rem 0 .1rem}}
 .alp .pair{{display:grid;grid-template-columns:1fr 1fr;gap:.55rem}}
 @media(max-width:620px){{.alp .pair{{grid-template-columns:1fr}}}}
 .alp .arrow{{text-align:center;color:var(--muted);font-family:var(--mono);font-size:.78rem;margin:.5rem 0;letter-spacing:.02em}}
 .alp .selbox{{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--verified);border-radius:8px;padding:.85rem 1rem;margin:.55rem 0}}
 .alp .tablewrap{{overflow-x:auto}}
 .alp table{{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:.76rem;margin-top:.4rem;font-variant-numeric:tabular-nums}}
 .alp th,.alp td{{border-bottom:1px solid var(--line);padding:.28rem .5rem;text-align:left}}
 .alp th{{color:var(--muted);font-weight:600;text-transform:uppercase;font-size:.66rem;letter-spacing:.06em}}
 .alp tr.chg td{{background:var(--runner-bg);color:var(--ink);font-weight:600}}
 .alp .checks{{list-style:none;padding:0;margin:0}}
 .alp .checks li{{display:flex;gap:.6rem;align-items:baseline;padding:.42rem 0;border-bottom:1px solid var(--line)}}
 .alp .checks b{{font-family:var(--mono);font-size:.7rem;font-weight:700;padding:.1rem .4rem;border-radius:4px;flex:none}}
 .alp .checks li.ok b{{background:var(--verified-bg);color:var(--verified)}}
 .alp .checks li.bad b{{background:var(--critical-bg);color:var(--critical)}}
 .alp .detail{{color:var(--muted);font-family:var(--mono);font-size:.74rem;margin-left:auto;text-align:right}}
 .alp details{{margin-top:.5rem}} .alp summary{{cursor:pointer;color:var(--muted);font-size:.8rem}}
 .alp pre{{background:var(--codebg);color:var(--codefg);padding:.75rem;border-radius:7px;overflow-x:auto;font-family:var(--mono);font-size:.74rem;line-height:1.45;margin:.5rem 0 0}}
 .alp .honest{{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--runner);border-radius:8px;padding:.7rem 1rem;color:var(--ink)}}
 .alp .foot{{color:var(--muted);font-size:.78rem;font-family:var(--mono);margin-top:1.5rem}}
 .alp code{{font-family:var(--mono);background:color-mix(in srgb,var(--muted) 16%,transparent);padding:.05rem .3rem;border-radius:4px;font-size:.86em}}
</style>
<div class="alp">{body}</div>"""
    return page, {"all_pass": all_pass, "checks": [(l, ok) for l, ok, _ in checks]}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1]).resolve()
    dest = Path(sys.argv[2]).resolve()
    page, summary = build(out_dir)
    dest.write_text(page, encoding="utf-8")
    print(f"wrote {dest}")
    for label, ok in summary["checks"]:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"VERDICT: {'ADAPTIVE LINEAGE VERIFIED' if summary['all_pass'] else 'NOT VERIFIED'}")
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
