#!/usr/bin/env python3
"""Scenario bank for testing the conversation arc — deterministic check + audible render.

`check`  : plan every scenario and assert it covers the predicted latency and
           produces the expected answer arc + band. Deterministic, non-vacuous
           (a wrong expectation fails). This is the $agentic-evals path.
`render`  : assemble a scenario's arc into one playable WAV and play it, so a
           human can ear-verify the WHOLE turn (opener -> cover/hum -> answer arc).
           Live: needs the Chatterbox service; perceived delivery stays human-owned.
`self-check`: dry validation (bank parses, every scenario plans, expectations match,
           render step-list builds) with no service calls.

stdlib only for check/self-check so the agentic-evals runner can execute them.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
import conversation_arc as arc  # noqa: E402

BANK = SKILL / "fixtures" / "arc_scenarios.json"
PHART = SKILL.parent / "phart-dag-chart" / "run.sh"  # sibling skill in the repo
FUSED = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library/fused-hmm")
HUMS = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library/song-hums")
OUT = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/arc-scenarios")


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())["scenarios"]


def plan_of(s: dict) -> dict:
    return arc.plan_arc(s["predicted_latency_ms"], s["emotion"], s["intensity"],
                        s["complexity"], s["id"], s.get("answer_text", ""),
                        request=s.get("user_request", ""))


def check(path: Path) -> int:
    scen = load(path)
    if not scen:
        print("FAIL: no scenarios", file=sys.stderr)
        return 1
    bad = 0
    for s in scen:
        p = plan_of(s)
        errs = []
        if not p["covers_latency"]:
            errs.append(f"total {p['planned_total_ms']}ms < latency {p['predicted_latency_ms']}ms")
        if p["answer_arc"] != s["expected_arc"]:
            errs.append(f"arc {p['answer_arc']} != expected {s['expected_arc']}")
        if p["band"] != s["expected_band"]:
            errs.append(f"band {p['band']} != expected {s['expected_band']}")
        status = "OK" if not errs else "FAIL"
        if errs:
            bad += 1
        print(f"  [{status}] {s['id']:<26} {s['tier']:<7} {len(p['elements'])} els "
              f"{p['planned_total_ms']:>6}ms/{p['predicted_latency_ms']}ms arc={p['answer_arc']} band={p['band']}"
              + (f"  <- {'; '.join(errs)}" if errs else ""))
    if bad:
        print(f"FAIL: {bad}/{len(scen)} scenarios mis-planned", file=sys.stderr)
        return 1
    print(f"PASS: all {len(scen)} scenarios plan correctly (cover latency + expected arc/band)")
    return 0


def chart(scenario_id: str | None) -> int:
    """Emit each scenario's arc as a descriptive ask.dag.v1 and render it with
    $phart-dag-chart, so the arc is checkable graphically against the conversation."""
    scen = {s["id"]: s for s in load(BANK)}
    ids = list(scen) if scenario_id in (None, "all") else [scenario_id]
    if any(i not in scen for i in ids):
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        s = scen[sid]
        p = plan_of(s)
        dag = arc.to_dag(p, descriptive=True)
        dag["graph_id"] = sid
        dag["description"] = (f"CONTEXT {s['user_request']!r} | emotion={s['emotion']} "
                              f"intensity={s['intensity']}/10 complexity={s['complexity']} "
                              f"| arc={p['answer_arc']} band={p['band']} | "
                              f"covers {s['predicted_latency_ms']}ms in {p['planned_total_ms']}ms")
        f = OUT / f"{sid}.dag.json"
        f.write_text(json.dumps(dag, indent=2) + "\n")
        print(f"\n=== {sid} [{s['tier']}] user: {s['user_request']!r}")
        print(f"    arc={p['answer_arc']} band={p['band']} covers {p['predicted_latency_ms']}ms in {p['planned_total_ms']}ms")
        subprocess.run(["bash", str(PHART), "chart", str(f)], check=False)
    return 0


def script(scenario_id: str | None) -> int:
    """Print the concrete render script per element so a human can VERIFY the arc:
    exact text WITH emotion tags, pause/delay durations, and SFX/hum + gain."""
    scen = {s["id"]: s for s in load(BANK)}
    ids = list(scen) if scenario_id in (None, "all") else [scenario_id]
    if any(i not in scen for i in ids):
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2
    for sid in ids:
        s = scen[sid]
        p = plan_of(s)
        print(f"\n=== {sid} [{s['tier']}]")
        print(f"  CONTEXT : {s.get('context', '(none)')}")
        print(f"  LISTENER: {s.get('listener', '(unknown)')}")
        print(f"  REQUEST : {s['user_request']!r}")
        print(f"  DERIVED : emotion={s['emotion']} intensity={s['intensity']}/10 complexity={s['complexity']} "
              f"(from context via /intent + /speaker/resolve)  ->  arc={p['answer_arc']} band={p['band']} "
              f"covers {s['predicted_latency_ms']}ms in {p['planned_total_ms']}ms")
        hdr = f"  {'#':>2}  {'time':>6}  {'element':<9} {'voice/tone':<18} payload (text incl. [tags] / delay / sfx+gain)"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for i, e in enumerate(p["elements"]):
            t = f"{e['start_ms']/1000:.1f}s"
            k = e["kind"]
            if k == "fused_hmm":
                elem, voice, payload = "OPENER", f"v3:{e['source']}", f'"{e["text"]}"'
            elif k == "restate":
                elem, voice, payload = "RESTATE", f"turbo:{e.get('tone')}", f'"{e["text"]}"'
            elif k == "progress":
                elem, voice, payload = "SAY", f"turbo:{e.get('tone')}", f'"{e["text"]}"'
            elif k == "pause":
                elem, voice, payload = "PAUSE", e["source"], f"{e['dur_ms']}ms silence"
            elif k == "hum":
                elem, voice = "SFX HUM", f"bed {e.get('gain_db')}dB"
                payload = f"{e.get('title')} ({e['dur_ms']/1000:.0f}s dry) evokes {e.get('memory_links')}"
            elif k == "answer":
                elem, voice = "ANSWER", "turbo arc:" + ">".join(e.get("phase_tones", []))
                payload = f'"{e["text"]}"'
            else:
                elem, voice, payload = k, "", str(e.get("text", ""))
            print(f"  {i:>2}  {t:>6}  {elem:<9} {voice:<18} {payload}")
        tags = sorted({x.strip("[]") for e in p["elements"]
                       for x in str(e.get("text", "")).split() if x.startswith("[")})
        print(f"  inline emotion tags: {tags or 'none (low-band/plain-turbo lines carry no tags)'}")
    return 0


def render_steps(plan: dict) -> list[dict]:
    """Ordered concrete render actions for one arc (dry data; render executes them)."""
    steps = []
    for el in plan["elements"]:
        if el["kind"] == "fused_hmm":
            steps.append({"do": "play_wav", "wav": str(FUSED / f"{el['source']}.wav"), "why": "opener"})
        elif el["kind"] == "hum":
            hid = el["source"].split(":", 1)[1]
            steps.append({"do": "play_wav", "wav": str(HUMS / f"{hid}.wav"), "gain_db": el.get("gain_db"), "why": "hum bed"})
        elif el["kind"] == "pause":
            steps.append({"do": "silence", "ms": el["dur_ms"]})
        elif el["kind"] in ("progress", "restate"):
            steps.append({"do": "speak", "text": el["text"], "tone": el.get("tone", "neutral_warm"), "why": el["source"]})
        elif el["kind"] == "answer":
            tones = el.get("phase_tones") or ["neutral_warm"]
            steps.append({"do": "speak", "text": el["text"], "tone": tones[0], "why": el["source"]})
    return steps


def _speak_wav(text: str, tone: str, context: str) -> str | None:
    """Render one line via the live speak CLI and return the produced wav path."""
    r = subprocess.run(["bash", str(SKILL / "run.sh"), "speak", "--voice", "embry",
                        "--text", text, "--tone", tone, "--context", context],
                       capture_output=True, text=True)
    # speak prints pretty (multi-line) JSON; grab the wav path directly.
    m = re.search(r'"wav":\s*"([^"]+\.wav)"', r.stdout)
    return m.group(1) if m else None


def render(scenario_id: str, play: bool) -> int:
    scen = {s["id"]: s for s in load(BANK)}
    if scenario_id not in scen:
        print(f"unknown scenario: {scenario_id}", file=sys.stderr)
        return 2
    s = scen[scenario_id]
    plan = plan_of(s)
    OUT.mkdir(parents=True, exist_ok=True)
    chart(scenario_id)  # show the arc graphically first, to check against what you hear
    steps = render_steps(plan)
    seq = []
    answered = False
    for i, st in enumerate(steps):
        wav = OUT / f"{scenario_id}-{i:02d}.wav"
        if st["do"] == "play_wav":
            if not Path(st["wav"]).exists():
                print(f"  [skip] missing {st['wav']}", file=sys.stderr)
                continue
            subprocess.run(["cp", st["wav"], str(wav)], check=True)
        elif st["do"] == "silence":
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            "anullsrc=r=44100:cl=stereo", "-t", f"{st['ms']/1000:.2f}", str(wav)], check=True)
        elif st["do"] == "speak":
            # answer phases all carry the whole answer text; speak it ONCE (lead tone).
            if str(st.get("why", "")).startswith("arc:"):
                if answered:
                    continue
                answered = True
            src = _speak_wav(st["text"], st["tone"], f"arc scenario {scenario_id}")
            if not src or not Path(src).exists():
                print(f"  [skip] speak produced no wav for: {st['text'][:40]}", file=sys.stderr)
                continue
            subprocess.run(["cp", src, str(wav)], check=True)
        seq.append(str(wav))
    if not seq:
        print("no renderable steps (service down?)", file=sys.stderr)
        return 1
    combined = OUT / f"{scenario_id}-arc.wav"
    lst = OUT / f"{scenario_id}.concat.txt"
    lst.write_text("".join(f"file '{w}'\n" for w in seq))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-ar", "44100", "-ac", "2", str(combined)], check=True)
    print(f"assembled: {combined} ({len(seq)} elements, arc={plan['answer_arc']}, band={plan['band']})")
    if play:
        subprocess.run(["pw-play", str(combined)], check=False)
    return 0


def self_check() -> None:
    scen = load(BANK)
    assert 10 <= len(scen) <= 12, f"want 10-12 scenarios, have {len(scen)}"
    tiers = {s["tier"] for s in scen}
    assert {"simple", "medium", "complex"} <= tiers, f"missing tiers: {tiers}"
    for s in scen:
        p = plan_of(s)
        assert p["covers_latency"], f"{s['id']} does not cover latency"
        assert p["answer_arc"] == s["expected_arc"], f"{s['id']} arc {p['answer_arc']} != {s['expected_arc']}"
        assert p["band"] == s["expected_band"], f"{s['id']} band {p['band']} != {s['expected_band']}"
        assert render_steps(p), f"{s['id']} produced no render steps"
    print(f"arc_scenarios self-check PASS ({len(scen)} scenarios; tiers {sorted(tiers)}; all plan + build render steps)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "render", "chart", "script", "self-check"])
    ap.add_argument("--scenarios", default=str(BANK))
    ap.add_argument("--id", dest="scenario_id")
    ap.add_argument("--play", action="store_true")
    a = ap.parse_args()
    if a.cmd == "self-check":
        self_check()
        sys.exit(0)
    if a.cmd == "check":
        sys.exit(check(Path(a.scenarios)))
    if a.cmd == "chart":
        sys.exit(chart(a.scenario_id))
    if a.cmd == "script":
        sys.exit(script(a.scenario_id))
    if a.cmd == "render":
        if not a.scenario_id:
            print("render needs --id <scenario>", file=sys.stderr)
            sys.exit(2)
        sys.exit(render(a.scenario_id, a.play))
