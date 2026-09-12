#!/usr/bin/env python3
"""Conversation-arc macro — the culmination of chatterbox-speak.

Agent A (fast, ~0ms) maps a WHOLE conversation turn into an ordered timeline of
VERIFIED elements — fused-hmm opener, progress lines, mood-matched hums (bone-dry
beds), and an emotional answer-arc delivery — shaped to cover the PREDICTED
Agent B solve latency so there is never dead air, and Embry lands the answer with
the right emotional shape from beginning to end.

Composes only elements the banks already verify (no new render tricks):
  fixtures/progress_macros.json   (stage lines)
  fixtures/song_hum_macros.json   (mood/tempo hums; bone-dry beds via hum_render.py)
  outputs/sfx-library/fused-hmm/manifest.json  (thinking openers)
  speak.py ARCS                   (answer / reassure delivery phases)

Timeline = [opener] -> [progress+hum cover sized to latency] -> [answer arc] -> [close].
Emits JSON (the plan Agent A executes) and a self-contained SVG (so the project
agent SEES how elements mix). Deterministic: variant/hum choice seeded by the
situation hash, band chosen by intensity+complexity. stdlib only; self-check wired.

Boundary: this PLANS the arc; the concurrent runtime + barge-in live in
embry-voice-control. Renderer tags are compiled by Agent A at playback, never
stored in $memory canonical text.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, wave
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FUSED = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library/fused-hmm/manifest.json")
HUMS = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library/song-hums")

# element timing (ms) — conservative floors so cover never underfills
OPENER_MS, LINE_MS, PAUSE_MS = 2500, 1400, 600
HUM_GAP_MS = 7000        # a projected gap wider than this gets a hum bed
HUM_BED_GAIN_DB = -3.0   # under speech (filler_gain fits exactly at playback)
ANSWER_PHASE_MS = 1800

# emotion -> which answer-delivery arc (grief/fear/sad reassure; else answer)
REASSURE = {"grief", "sad", "sadness", "fear", "afraid", "mourning", "loss", "distress"}
# default cover stage sequence for a memory-grounded solve
STAGE_SEQ = ["intent", "recall", "searching", "answer"]


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _dur_ms(wav: Path, default: int) -> int:
    try:
        with wave.open(str(wav)) as w:
            return int(1000 * w.getnframes() / w.getframerate())
    except Exception:
        return default


def _band(intensity: int, complexity: int) -> str:
    if intensity >= 8 or complexity >= 3:
        return "high"
    return "low" if intensity <= 3 else "medium"


def _pick(seq: list, seed: str):
    if not seq:
        return None
    return seq[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(seq)]


def _hum_for(emotion: str, seed: str, songs: list[dict]) -> dict | None:
    e = emotion.lower()
    matches = [s for s in songs
               if any(e in m.lower() or m.lower() in e for m in (s.get("mood") or []))
               or e in str(s.get("evokes", "")).lower()]
    return _pick(matches or songs, seed + "hum")


# --- Reactive runtime policy -------------------------------------------------
# The RUNTIME is not a frozen timeline. Agent A calls next_element(state) each
# time it finishes speaking, passing Agent B's latest event (b_stage) and updated
# remaining ETA (b_eta_ms). The arc EMERGES from B's real progress: A extends
# cover if B is slow, barges in when B signals answer_ready, and never runs out
# of arc on a bad latency guess. plan_arc() below is this policy SIMULATED against
# a predicted latency -- the instant floor + preview, not the runtime truth.
# The concurrent runtime that feeds real b_stage/b_eta events lives in
# embry-voice-control; this function is the deterministic element policy it drives.

def next_element(state: dict) -> dict | None:
    """Return the next arc element given live solver progress, or None when done.

    state (mutated by the caller between calls):
      emotion, intensity, complexity, request, answer_text, situation
      b_stage: latest Agent-B event, e.g. 'working:recall'/'working:debugging'/'answer_ready'
      b_eta_ms: B's CURRENT estimate of remaining solve time (updated each call)
      started/restated/answered: bools; last_kind: str; spoken: list (no-repeat)
    """
    emotion = state.get("emotion", "neutral")
    intensity = int(state.get("intensity", 5))
    complexity = int(state.get("complexity", 1))
    seed = state.get("situation") or emotion
    band = _band(intensity, complexity)
    songs = _load(SKILL / "fixtures" / "song_hum_macros.json")["songs"]
    prog = _load(SKILL / "fixtures" / "progress_macros.json")["stages"]
    spoken = state.setdefault("spoken", [])

    def mk(kind, **kw):
        state["last_kind"] = kind
        return {"kind": kind, **kw}

    # 1. instant opener
    if not state.get("started"):
        state["started"] = True
        fused = [e for e in _load(FUSED)["entries"] if e["band"] == band] or _load(FUSED)["entries"]
        op = _pick(fused, seed + "open")
        return mk("fused_hmm", source=op["id"], text=op["text"], band=band, tags=["thinking"])
    # 2. restate only for multi-part problems
    if complexity >= 2 and state.get("request") and not state.get("restated"):
        state["restated"] = True
        # The fast agent GENERATES this line (natural restate in simple steps) with
        # its low-reasoning model from the request + B's streamed decomposition.
        # The template is only the instant FALLBACK when the model can't beat the
        # speech deadline. Structure is deterministic; wording is not.
        fallback = state.get("restate_text") or f"Okay, so — you're asking: {state['request']}"
        return mk("restate", source="restate", tone="neutral_warm", text=fallback, tags=["restate"],
                  gen={"role": "restate", "model": "zai/glm-5.3-flash",
                       "context": {"request": state.get("request"), "steps": state.get("restate_steps")},
                       "instruction": "Restate the request warmly in simple steps, <=25 words, no tags.",
                       "fallback": fallback})
    # 3. B is done -> deliver the answer once, then end
    if state.get("b_stage") == "answer_ready":
        if state.get("answered"):
            return None
        state["answered"] = True
        arc_name = "reassure" if emotion.lower() in REASSURE else "answer"
        phases = ["careful_concerned", "calm_precise", "memory_confident", "playful_light"] \
            if arc_name == "answer" else ["careful_concerned", "neutral_warm", "relieved"]
        return mk("answer", source=f"arc:{arc_name}", arc=arc_name, phase_tones=phases,
                  text=state.get("answer_text") or "<answer>", tags=["answer"] + phases)
    # 4. still working -> cover. After a spoken line, a WIDE remaining ETA gets a
    #    hum bed, else a short pause; otherwise say where B is.
    stage = str(state.get("b_stage", "working:recall")).split(":", 1)[-1]
    if stage not in prog:
        stage = "recall"
    if state.get("last_kind") in ("fused_hmm", "restate", "progress"):
        if int(state.get("b_eta_ms", 0)) > HUM_GAP_MS and state.get("last_kind") != "hum":
            hum = _hum_for(emotion, seed + str(len(spoken)), songs)
            if hum:
                return mk("hum", source=f"hum:{hum['id']}", title=hum.get("title"),
                          gain_db=HUM_BED_GAIN_DB, mood=hum.get("mood"),
                          memory_links=hum.get("memory_links", []), tags=["hum", "under_speech"])
        return mk("pause", source="pause:beat", dur_ms=PAUSE_MS, tags=["hold"])
    line = _pick(prog[stage]["pool"], seed + stage + str(len(spoken)))
    spoken.append(line)
    # Cover line is likewise model-generated at runtime (natural, stage-aware);
    # the pooled line is the deterministic fallback floor.
    return mk("progress", source=f"progress:{stage}", text=line, tone=prog[stage].get("tone"), tags=[stage],
              gen={"role": "cover", "model": "zai/glm-5.3-flash", "stage": stage,
                   "instruction": f"One short natural line for the '{stage}' work stage, <=12 words, no tags.",
                   "fallback": line})


def plan_arc(latency_ms: int, emotion: str, intensity: int = 5, complexity: int = 1,
             situation: str = "", answer_text: str = "", request: str = "") -> dict:
    if latency_ms < 0:
        raise ValueError("latency_ms must be >= 0")
    seed = situation or emotion
    band = _band(intensity, complexity)
    prog = _load(SKILL / "fixtures" / "progress_macros.json")["stages"]
    songs = _load(SKILL / "fixtures" / "song_hum_macros.json")["songs"]
    fused = [e for e in _load(FUSED)["entries"] if e["band"] == band] or _load(FUSED)["entries"]

    els: list[dict] = []
    t = 0

    def add(phase, lane, kind, dur, **kw):
        nonlocal t
        els.append({"seq": len(els), "phase": phase, "lane": lane, "kind": kind,
                    "start_ms": t, "dur_ms": dur, **kw})
        t += dur

    # 1. OPENER — fused-hmm thinking line in Embry's clone voice
    op = _pick(fused, seed + "open")
    add("open", "speech", "fused_hmm", _dur_ms(Path(op["wav"]), OPENER_MS),
        source=op["id"], text=op["text"], band=band, emotion=emotion, tags=["thinking"])

    # RESTATE only for multi-part problems (complexity >= 2). Single-step turns
    # don't need the request echoed back.
    if request and complexity >= 2:
        add("restate", "speech", "restate", LINE_MS, source="restate", tone="neutral_warm",
            text=f"Let me make sure I've got it — you said: {request}", tags=["restate"])

    # 2. COVER — progress lines paced to fill latency; hum bed on wide gaps
    si = 0
    while t < latency_ms and si < len(STAGE_SEQ) - 1:  # keep 'answer' for imminence marker
        stage = STAGE_SEQ[si]
        line = _pick(prog[stage]["pool"], seed + stage)
        add("cover", "speech", "progress", LINE_MS, source=f"progress:{stage}",
            text=line, tone=prog[stage].get("tone"), tags=[stage])
        remaining = latency_ms - t
        if remaining > HUM_GAP_MS:  # long wait -> fill with a mood-matched hum bed
            hum = _hum_for(emotion, seed, songs)
            if hum:
                add("cover", "sfx", "hum", min(remaining - PAUSE_MS, 12000),
                    source=f"hum:{hum['id']}", title=hum.get("title"), gain_db=HUM_BED_GAIN_DB,
                    mood=hum.get("mood"), memory_links=hum.get("memory_links", []),
                    tags=["hum", "under_speech"])
        else:
            add("cover", "pause", "pause", PAUSE_MS, source="pause:beat", tags=["hold"])
        si += 1

    # imminence beat right before the answer
    imm = _pick(prog["answer"]["pool"], seed + "imm")
    add("cover", "speech", "progress", LINE_MS, source="progress:answer",
        text=imm, tone=prog["answer"].get("tone"), tags=["answer_imminent"])

    # 3. ANSWER — emotional-arc delivery of Agent B's solution
    arc_name = "reassure" if emotion.lower() in REASSURE else "answer"
    phases = ["careful_concerned", "calm_precise", "memory_confident", "playful_light"] \
        if arc_name == "answer" else ["careful_concerned", "neutral_warm", "relieved"]
    # ONE answer utterance delivered across the tone arc (speak --arc phases the
    # single text). Never repeat the whole answer once per phase.
    add("answer", "speech", "answer", ANSWER_PHASE_MS * len(phases),
        source=f"arc:{arc_name}", arc=arc_name, phase_tones=phases,
        text=answer_text or "<answer>", tags=["answer"] + phases)

    return {
        "schema": "chatterbox_speak.conversation_arc.v1",
        "predicted_latency_ms": latency_ms, "planned_total_ms": t,
        "covers_latency": t >= latency_ms, "emotion": emotion, "intensity": intensity,
        "complexity": complexity, "band": band, "answer_arc": arc_name,
        "situation": situation, "elements": els,
        "note": "Agent A executes this ordered plan; renderer tags compiled at playback, never stored in $memory.",
    }


def _safe(s: str) -> str:
    """phart node ids must be safe identifiers (alnum + _). Sanitize + collapse."""
    out = "".join(c if c.isalnum() else "_" for c in str(s))
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:44]


def stream(events: list[dict], base: dict) -> list[dict]:
    """Drive the arc from Agent B's JSON event stream (solver_event.v1).

    Each event: {stage, eta_ms, answer_text?, done}. The fast agent speaks its
    quick initial arc (opener[+restate]) before the first event, then emits one
    cover beat per incoming event, and barges to the answer when B sends done/
    answer_ready. If B outruns the events, A keeps covering (never dry).
    """
    st = dict(base)
    st.setdefault("b_eta_ms", 0)
    st.setdefault("b_stage", "working:recall")
    out: list[dict] = []

    # Quick initial arc: just the opener, instantly, before any solver event.
    out.append(next_element(st))
    for ev in events:
        if ev.get("stage"):
            st["b_stage"] = ev["stage"]
        if ev.get("eta_ms") is not None:
            st["b_eta_ms"] = ev["eta_ms"]
        if ev.get("answer_text"):
            st["answer_text"] = ev["answer_text"]
        # B's early parse: a simple-steps decomposition A voices as the restate.
        if ev.get("restate"):
            st["restate_text"] = ev["restate"]
        elif ev.get("steps"):
            steps = ev["steps"]
            st["restate_steps"] = steps  # passed to the fast model as generation context
            joined = ", then ".join(steps)
            st["restate_text"] = f"Okay, so — first {joined}." if steps else None  # fallback only
        if ev.get("done") or ev.get("stage") == "answer_ready":
            st["b_stage"] = "answer_ready"
        el = next_element(st)
        while el and el["kind"] in ("fused_hmm", "restate"):
            out.append(el)
            el = next_element(st)
        if el:
            out.append(el)
        if el and el["kind"] == "answer":
            return out
    # events exhausted but B not done: keep covering, then close if answer known
    while not st.get("answered"):
        el = next_element(st)
        if el is None:
            break
        out.append(el)
        if len(out) > 40:
            break
    return out


def _label(el: dict, descriptive: bool) -> str:
    """Node id for the phart chart. Descriptive (safe) labels show timing + kind +
    which element, so a human can check the arc structure against the real
    conversation; the exact line stays in the node input and the SVG."""
    if not descriptive:
        return f"{el['seq']:02d}_{el['kind']}"
    secs = el["start_ms"] // 1000
    if el["kind"] == "hum":
        tail = f"hum_{el.get('title', el.get('source'))}_{el.get('gain_db')}dB"
    elif el["kind"] in ("answer", "answer_phase"):
        tail = f"answer_{el.get('arc', el.get('phase_tone', ''))}"
    elif el["kind"] == "progress":
        tail = (el.get("source") or "progress").replace("progress:", "say_")
    elif el["kind"] == "fused_hmm":
        tail = f"open_{el.get('source', 'hmm')}"
    else:
        tail = el["kind"]
    return _safe(f"{el['seq']:02d}_{secs}s_{tail}")


def to_dag(plan: dict, descriptive: bool = False) -> dict:
    """Emit the arc as ask.dag.v1 so $phart-dag-chart renders it in the terminal.

    Each element is a node; the arc is a linear chain (each depends on the prior).
    Node type is skill.run (a valid ask.dag.v1 type); the real element is in input.
    descriptive=True gives node ids that show timing + the actual line, so the
    terminal chart is checkable against the real conversation.
    """
    nodes = []
    prev = None
    for el in plan["elements"]:
        nid = _label(el, descriptive)
        nodes.append({
            "id": nid, "type": "skill.run", "depends_on": [prev] if prev else [],
            "input": {"skill": "chatterbox-speak",
                      "lane": el["lane"], "kind": el["kind"], "source": el.get("source"),
                      "start_ms": el["start_ms"], "dur_ms": el["dur_ms"],
                      "text": (el.get("text") or "")[:60]},
        })
        prev = nid
    return {"schema_version": "ask.dag.v1",
            "graph_id": f"arc-{plan['emotion']}-{plan['band']}",
            "description": f"Embry conversation arc ({plan['emotion']}, {plan['answer_arc']} arc) "
                           f"covering {plan['predicted_latency_ms']}ms Agent-B latency in {plan['planned_total_ms']}ms",
            "max_concurrency": 1, "nodes": nodes}


LANE_Y = {"speech": 70, "sfx": 120, "pause": 170}
KIND_COLOR = {"fused_hmm": "#7c5cff", "progress": "#2d9cdb", "answer": "#27ae60",
              "answer_phase": "#27ae60", "hum": "#f2994a", "pause": "#9aa0a6"}


def to_svg(plan: dict, px_per_sec: int = 60) -> str:
    total = max(plan["planned_total_ms"], plan["predicted_latency_ms"], 1000)
    w = 120 + int(total / 1000 * px_per_sec)
    h = 230
    x0 = 110

    def x(ms): return x0 + int(ms / 1000 * px_per_sec)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="11">',
             f'<rect width="{w}" height="{h}" fill="#111318"/>',
             f'<text x="12" y="20" fill="#e8eaed" font-size="13">Conversation arc — {plan["emotion"]} '
             f'(band {plan["band"]}, arc {plan["answer_arc"]}) — covers {plan["predicted_latency_ms"]}ms '
             f'in {plan["planned_total_ms"]}ms</text>']
    # predicted-latency marker (where the answer must land)
    lx = x(plan["predicted_latency_ms"])
    parts.append(f'<line x1="{lx}" y1="34" x2="{lx}" y2="{h-20}" stroke="#eb5757" stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{lx+3}" y="46" fill="#eb5757">answer due</text>')
    for lane, y in LANE_Y.items():
        parts.append(f'<text x="10" y="{y+14}" fill="#9aa0a6">{lane}</text>')
        parts.append(f'<line x1="{x0}" y1="{y+18}" x2="{w-10}" y2="{y+18}" stroke="#2a2d33"/>')
    for el in plan["elements"]:
        y = LANE_Y[el["lane"]]
        ex, ew = x(el["start_ms"]), max(6, int(el["dur_ms"] / 1000 * px_per_sec) - 2)
        c = KIND_COLOR.get(el["kind"], "#888")
        parts.append(f'<rect x="{ex}" y="{y}" width="{ew}" height="26" rx="3" fill="{c}" opacity="0.9"/>')
        lbl = (el.get("source") or el["kind"])[:22]
        parts.append(f'<text x="{ex+3}" y="{y+17}" fill="#0b0c0f">{lbl}</text>')
    # legend
    lx2 = 12
    for k, c in KIND_COLOR.items():
        parts.append(f'<rect x="{lx2}" y="{h-16}" width="10" height="10" fill="{c}"/>'
                     f'<text x="{lx2+13}" y="{h-7}" fill="#9aa0a6">{k}</text>')
        lx2 += 90
    parts.append("</svg>")
    return "\n".join(parts)


def self_check() -> None:
    p = plan_arc(30000, "grief", intensity=4, complexity=3, situation="loss of Kai",
                 answer_text="Here is what SC-7 requires.")
    assert p["elements"][0]["kind"] == "fused_hmm", "arc must open with a thinking beat"
    assert p["covers_latency"], f"plan {p['planned_total_ms']}ms must cover {p['predicted_latency_ms']}ms"
    assert p["answer_arc"] == "reassure", "grief must route to the reassure delivery arc"
    assert any(e["kind"] == "hum" for e in p["elements"]), "a long wait must insert a hum bed"
    assert p["elements"][-1]["kind"] == "answer", "arc must end on the single answer delivery"
    assert sum(1 for e in p["elements"] if e["kind"] == "answer") == 1, "answer must be ONE element, not repeated per phase"
    # progress/pause are plain lexical Turbo lines (no tags); fused_hmm/answer render
    # lines MAY carry tags — those are render instructions, never written to $memory.
    assert all("[" not in str(e.get("text", "")) for e in p["elements"]
               if e["kind"] in ("progress", "pause")), "progress/pause lines must be tag-free"
    svg = to_svg(p)
    assert svg.startswith("<svg") and "answer due" in svg and "</svg>" in svg
    dag = to_dag(p)
    assert dag["schema_version"] == "ask.dag.v1" and len(dag["nodes"]) == len(p["elements"])
    assert dag["nodes"][0]["depends_on"] == [] and dag["nodes"][1]["depends_on"] == [dag["nodes"][0]["id"]]
    # happy/short-latency path takes the answer arc and still covers
    q = plan_arc(4000, "happy", intensity=6)
    assert q["answer_arc"] == "answer" and q["covers_latency"]
    assert dag["nodes"][-1]["input"]["kind"] == "answer"
    # streamed runtime: drive next_element with live events (slow solver, then done)
    st = {"emotion": "grief", "intensity": 4, "complexity": 3, "request": "what does SC-7 require?",
          "answer_text": "SC-7 guards the boundary.", "situation": "stream-test",
          "b_stage": "working:recall", "b_eta_ms": 20000}
    seq = []
    for _ in range(30):
        if len(seq) == 6:
            st["b_stage"] = "answer_ready"  # B finishes mid-stream; A must barge to the answer
        el = next_element(st)
        if el is None:
            break
        seq.append(el)
    kinds = [e["kind"] for e in seq]
    assert kinds[0] == "fused_hmm", "stream must open with a thinking beat"
    assert "restate" in kinds, "complex turn must restate"
    assert "hum" in kinds, "a long live ETA must insert a hum bed"
    assert kinds[-1] == "answer", "stream must end on the answer when B signals ready"
    assert next_element(st) is None, "after the answer the stream is done"
    print(f"conversation_arc self-check PASS (grief: {len(p['elements'])} elements, "
          f"{p['planned_total_ms']}ms covers 30000ms; hum bed + reassure arc)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "stream", "self-check"])
    ap.add_argument("--events", help="JSONL of solver_event.v1 {stage,eta_ms,answer_text?,done} (stream mode)")
    ap.add_argument("--request", default="")
    ap.add_argument("--latency-ms", type=int, default=20000, help="predicted Agent B solve time")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--intensity", type=int, default=5)
    ap.add_argument("--complexity", type=int, default=1, help="parts in the problem (>=3 -> high band)")
    ap.add_argument("--situation", default="")
    ap.add_argument("--answer-text", default="")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--svg", dest="svg_out")
    ap.add_argument("--dag", dest="dag_out", help="emit ask.dag.v1 JSON for $phart-dag-chart terminal rendering")
    ap.add_argument("--descriptive-dag", action="store_true", help="node labels show timing + actual line (checkable against the conversation)")
    a = ap.parse_args()
    if a.cmd == "self-check":
        self_check()
        sys.exit(0)
    if a.cmd == "stream":
        raw = Path(a.events).read_text() if a.events else sys.stdin.read()
        events = [json.loads(x) for x in raw.splitlines() if x.strip()]
        base = {"emotion": a.emotion, "intensity": a.intensity, "complexity": a.complexity,
                "request": a.request, "answer_text": a.answer_text, "situation": a.situation}
        beats = stream(events, base)
        for i, e in enumerate(beats):
            txt = e.get("text") or e.get("title") or e.get("source", "")
            print(f"  {i:>2} {e['kind']:<11} {str(txt)[:60]}")
        print(f"  ({len(beats)} beats; ended on {beats[-1]['kind'] if beats else 'none'})")
        sys.exit(0)
    plan = plan_arc(a.latency_ms, a.emotion, a.intensity, a.complexity, a.situation, a.answer_text)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(plan, indent=2) + "\n")
    if a.svg_out:
        Path(a.svg_out).write_text(to_svg(plan) + "\n")
    if a.dag_out:
        Path(a.dag_out).write_text(json.dumps(to_dag(plan, a.descriptive_dag), indent=2) + "\n")
    print(json.dumps({k: plan[k] for k in ("planned_total_ms", "covers_latency", "band", "answer_arc")}, indent=2))
    if a.svg_out:
        print("svg:", a.svg_out)
    if a.dag_out:
        print("dag:", a.dag_out, "(render: phart-dag-chart chart", a.dag_out + ")")
