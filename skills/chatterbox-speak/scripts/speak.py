# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "httpx", "pydantic", "loguru"]
# ///
"""chatterbox-speak: one-shot voiced line through the live Chatterbox service.

Validates the request and the service receipt with Pydantic, calls
POST /synthesize on the Chatterbox agent server, copies the WAV and writes a
JSON receipt to /mnt/storage12tb/skills/chatterbox-speak/outputs/.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import wave
from uuid import uuid4
from pathlib import Path
from typing import Literal

import httpx
import typer
from loguru import logger
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pronounce import normalize_pronunciation, load_lexicon  # noqa: E402
from pauses import resolve_pause_macros, load_macros  # noqa: E402
import speak_core as core  # noqa: E402

app = typer.Typer(add_completion=False)

BASE_URL = core.BASE_URL
OUT_DIR = core.OUT_DIR
# Container /out is host chatterbox/logs (see docker inspect chatterbox-fork-agent-server)
CONTAINER_OUT = core.CONTAINER_OUT
HOST_OUT = core.HOST_OUT

def _analyzer_path() -> Path:
    """Resolve the analyze-chatterbox-emotions runner.

    Prefer the globally broadcast skill; fall back to the sibling skill in
    this repo checkout so the live path does not depend on broadcast state
    (observed: global path missing while the repo skill exists).
    """
    candidates = [
        Path.home() / ".pi/agent/skills/analyze-chatterbox-emotions/run.sh",
        Path(__file__).resolve().parents[2] / "analyze-chatterbox-emotions" / "run.sh",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return candidates[0]


ANALYZER = _analyzer_path()
LEXICON_PATH = Path(__file__).resolve().parents[1] / "fixtures/pronunciation_lexicon.json"
PAUSE_MACROS_PATH = Path(__file__).resolve().parents[1] / "fixtures/pause_macros.json"

# Backend-aware fail-closed tag gate: ONE definition, in speak_core; the CLI
# imports it back (_UNSUPPORTED_TAGS / _KNOWN_EVENT_TAGS above).


MEMORY_URL = "http://127.0.0.1:8601"


# Turbo-safe singular event tag vocabulary and the backend-aware fail-closed
# gate live in speak_core (ONE definition); the CLI imports them back.
_UNSUPPORTED_TAGS = core.unsupported_tags
_KNOWN_EVENT_TAGS = core._KNOWN_EVENT_TAGS
VOICES = core.VOICES
INTENSITY = core.INTENSITY
SESSIONS = OUT_DIR / "sessions"
MOOD_BLEND = 0.5  # ponytail: bounded arc delta — mood moves halfway toward each request, clamped 0-1


class SessionState(BaseModel):
    """Persona-dream-style session mood: turn-scoped, bounded, decays by default.

    Not persona memory; never written to $memory unless separately promoted.
    """

    model_config = ConfigDict(extra="forbid")
    session_id: str
    speaker: str | None = None  # who Embry is speaking to (caller-asserted, not identity proof)
    mood_intensity: float | None = None
    last_tone: str | None = None
    turns: int = 0


def _load_session(session_id: str) -> SessionState:
    p = SESSIONS / f"{session_id}.json"
    if p.is_file():
        try:
            return SessionState.model_validate_json(p.read_text())
        except ValidationError as exc:
            _fail(f"corrupt session state {p}: {exc.json()}")
    return SessionState(session_id=session_id)


def _save_session(state: SessionState) -> None:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    (SESSIONS / f"{state.session_id}.json").write_text(state.model_dump_json(indent=2))


def _recall_context(query: str, speaker: str | None) -> dict:
    """Read-only $memory recall for speaker-scoped context; evidence for the receipt only."""
    tags = [f"speaker:{speaker}"] if speaker else None
    try:
        resp = httpx.post(
            f"{MEMORY_URL}/recall",
            json={"q": query, "k": 3, **({"tags": tags} if tags else {})},
            headers={"X-Caller-Skill": "chatterbox-speak"},
            timeout=httpx.Timeout(10.0, connect=2.0),
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "found": data.get("found"),
            "confidence": data.get("confidence"),
            "items": [
                {"problem": i.get("problem"), "solution": i.get("solution"), "tags": i.get("tags")}
                for i in data.get("items", [])[:3]
            ],
            "tags": tags,
        }
    except httpx.HTTPError as exc:
        return {"found": False, "error": f"memory recall unavailable: {exc}", "tags": tags}


# SpeakRequest / BatchReceipt / ServiceReceipt moved to speak_core (the core
# owns the request and typed service-response seams).


class RenderChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1)
    pause_after_ms: int = Field(ge=0, le=10000)
    tone: str
    role: str


class RenderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_id: Literal["best_practices_chatterbox.render_plan.v1"] = Field(alias="schema")
    answer_text: str
    render_chunks: list[RenderChunk] = Field(min_length=1)


# BatchReceipt / ServiceReceipt: see speak_core.


def _fail(msg: str) -> None:
    logger.error(msg)
    raise typer.Exit(code=1)


@app.command()
def voices() -> None:
    """List known voices and the service's live calibrated tones."""
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5).json()
        tones = sorted(health.get("tone_calibration", {}))
    except Exception as exc:  # noqa: BLE001
        tones = [f"service unreachable: {exc}"]
    print(json.dumps({"voices": VOICES, "tones": tones}, indent=2))



# Conversation arc macros: progress -> (tone, pace). Like emotion macros,
# but each waypoint governs one PHASE of the answer's delivery.
ARCS: dict[str, list[dict[str, str]]] = {
    "answer": [
        {"tone": "careful_concerned", "pace": "slow"},
        {"tone": "calm_precise", "pace": "slow"},
        {"tone": "memory_confident", "pace": "brisk"},
        {"tone": "playful_light", "pace": "brisk"},
    ],
    "reassure": [
        {"tone": "careful_concerned", "pace": "slow"},
        {"tone": "neutral_warm", "pace": "slow"},
        {"tone": "relieved", "pace": "neutral"},
    ],
}

_SENTENCE_SPLIT = __import__("re").compile(r"(?<=[.!?])\s+")


class ArcPhaseInput(BaseModel):
    """Model-authored phase: text + delivery + complexity rating.

    The complexity judgment comes from the authoring model (the
    condense call of the compose-then-condense pattern), not from
    this skill. Pydantic-validated; this IS the contract.
    """

    text: str = Field(min_length=1)
    tone: str | None = None
    pace: str | None = None
    complexity: Literal["simple", "moderate", "complex"] | None = None


class ArcInput(BaseModel):
    schema_: str = Field(
        default="chatterbox_speak.arc_input.v1", alias="schema"
    )
    arc: str
    phases: list[ArcPhaseInput] = Field(min_length=1)


class ArcPhaseReceipt(BaseModel):
    phase: int
    text: str
    tone: str
    pace: str
    complexity: Literal["simple", "moderate", "complex"]
    complexity_source: Literal["model", "heuristic"]
    effective_pace: str
    wav: str | None
    duration_seconds: float | None


class ArcReceipt(BaseModel):
    schema_: str = Field(default="chatterbox_speak.arc.v3", alias="schema")
    arc: str
    phases: list[ArcPhaseReceipt]


_COMPLEX_TOKEN = __import__("re").compile(
    r"[a-z_]+\.[a-z_]+|_[a-z]+_|\b\d{2,}\b|underscore|line \d+"
)

_SPEED_RANK = {"slow": 0, "neutral": 1, "brisk": 2, "fast": 3}
_COMPLEXITY_FLOOR = {
    "complex": "slow",
    "moderate": "neutral",
    "simple": "neutral",
}


def _complexity(text: str) -> str:
    """Deterministic chunk complexity: technical-token density."""
    words = text.split()
    if not words:
        return "simple"
    hits = len(_COMPLEX_TOKEN.findall(text.lower()))
    long_sentences = sum(
        1 for s in _SENTENCE_SPLIT.split(text)
        if len(s.split()) >= 18
    )
    score = hits / max(1, len(words)) * 10 + long_sentences
    if score >= 1.2:
        return "complex"
    if score >= 0.4:
        return "moderate"
    return "simple"


def _effective_pace(waypoint_pace: str, complexity: str) -> str:
    """More complex chunks speak more slowly: the slower of the arc
    waypoint pace and the complexity floor wins."""
    floor = _COMPLEXITY_FLOOR[complexity]
    slower = min(
        (waypoint_pace, floor), key=lambda p: _SPEED_RANK.get(p, 1)
    )
    return slower


def _arc_phases(text: str, waypoints: list[dict[str, str]]):
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s]
    if not sentences:
        raise SystemExit("--arc needs at least one sentence")
    n = len(waypoints)
    # distribute sentences evenly across phases; every phase non-empty
    # when there are >= n sentences, else clamp to sentence count.
    phases: list[tuple[str, dict[str, str]]] = []
    per = max(1, round(len(sentences) / n))
    idx = 0
    for w in waypoints:
        chunk = sentences[idx:idx + per] if idx < len(sentences) else []
        if chunk:
            phases.append((" ".join(chunk), w))
        idx += per
    if not phases:
        phases = [(text, waypoints[0])]
    return phases


@app.command()
def speak(
    text: str = typer.Option("", help="Text to speak; may contain native tags like [sigh]; optional when --arc-input supplies the phases"),
    voice: str = typer.Option("embry", help=f"Named voice: {sorted(VOICES)}"),
    ref_audio: str | None = typer.Option(None, help="Container path to reference WAV (overrides --voice)"),
    tone: str | None = typer.Option(None, help="Calibrated tone, e.g. neutral_warm, firm_boundary"),
    intensity: str | None = typer.Option(None, help="low|medium|high; routes to base-affect backend (tags become literal)"),
    context: str = typer.Option("", help="Grounding note stored in the receipt (does not change rendering)"),
    session: str | None = typer.Option(None, help="Session id; holds bounded mood + speaker across turns (persona-dream-style continuity)"),
    to: str | None = typer.Option(None, help="Who Embry is speaking to; stored in session/receipt and used as speaker:<id> recall tag"),
    recall_context: bool = typer.Option(False, help="Fetch speaker-scoped context from $memory /recall into the receipt"),
    play: bool = typer.Option(False, help="Play locally via pw-play"),
    analyze: bool = typer.Option(False, help="Run /analyze-chatterbox-emotions on the WAV and embed the result in the receipt"),
    planned_pauses: bool = typer.Option(False, help="Compile spaced ellipses/[pause:*] via best-practices-chatterbox and render exact chunk silence"),
    pace: str | None = typer.Option(None, help="Speaking pace via service time-stretch: slow|neutral|brisk|fast (slow ~= 0.85 tempo, ~18% longer); recorded in the receipt pace_effect"),
    arc: str | None = typer.Option(None, help=f"Conversation arc macro: phases the answer across tone+pace waypoints ({sorted(ARCS)}); overrides --tone/--pace per phase"),
    arc_input: Path | None = typer.Option(None, help="Model-authored arc input (chatterbox_speak.arc_input.v1 JSON): per-phase text/tone/pace/complexity; complexity_source=model in the receipt; waypoints fill any gaps"),
    normalize: bool = typer.Option(True, help="Rule-based pronunciation normalization before render: spell control ids (SC-7 -> S C seven), space acronyms (CUI -> C U I), apply the irregular-term lexicon. Deterministic; native [tags] untouched"),
    temperature: float | None = typer.Option(None, help="Turbo expressiveness knob, 0.05-1.5 (service-validated). Tone is request-only on Turbo; temperature is the audible affect knob"),
    render_chunks_plan: Path | None = typer.Option(None, help="Caller-owned render-chunk plan JSON {answer_text, render_chunks:[{text, tone?, pause_after_ms, ...}]}; bypasses pause compilation, pronunciation normalization still applied per chunk; extra chunk fields (e.g. sfx_after) pass through to the service"),
    allow_unknown_tags: bool = typer.Option(False, help="OPT-OUT: send unsupported bracket tags to the service anyway (they may be spoken as literal words); the opt-out switch and any allowed-through tags are always recorded in the receipt (allow_unknown_tags / unknown_tags_detected / unknown_tag_policy)")
) -> None:
    """Render one line and write WAV + receipt."""
    _LAUGH_TAGS = ("[laugh]", "[giggles]", "[giggles]", "[chuckle]", "[chuckles]")
    lowered = text.lower()
    if "interview" in (context or "").lower() and any(
        tag in lowered for tag in _LAUGH_TAGS
    ):
        _fail(
            "laugh tags are forbidden in interview contexts; "
            "remove [laugh]/[giggles]/[chuckle] or change --context"
        )
    original_text = text
    caller_plan: dict | None = None
    if render_chunks_plan is not None:
        try:
            caller_plan = json.loads(Path(render_chunks_plan).read_text())
        except Exception as exc:
            _fail(f"invalid --render-chunks file: {exc}")
        chunks_in = caller_plan.get("render_chunks")
        if not isinstance(chunks_in, list) or not chunks_in:
            _fail("--render-chunks requires a non-empty render_chunks list")
        if normalize:
            lex = load_lexicon(LEXICON_PATH)
            for chunk in chunks_in:
                if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                    chunk["text"] = normalize_pronunciation(chunk["text"], lex)
            if isinstance(caller_plan.get("answer_text"), str):
                caller_plan["answer_text"] = normalize_pronunciation(caller_plan["answer_text"], lex)
    if normalize and text:
        text = normalize_pronunciation(text, load_lexicon(LEXICON_PATH))
    if arc_input is not None or arc is not None:
        if arc_input is not None:
            try:
                supplied = ArcInput.model_validate(
                    json.loads(Path(arc_input).read_text())
                )
            except Exception as exc:
                _fail(f"invalid arc input: {exc}")
            arc = supplied.arc
            if arc not in ARCS:
                _fail(f"unknown arc '{arc}'; known: {sorted(ARCS)}")
            wps = ARCS[arc]
            phases = [
                (
                    ph.text,
                    {
                        "tone": ph.tone or wps[min(i, len(wps) - 1)]["tone"],
                        "pace": ph.pace or wps[min(i, len(wps) - 1)]["pace"],
                    },
                    ph.complexity,
                )
                for i, ph in enumerate(supplied.phases)
            ]
        else:
            if arc not in ARCS:
                _fail(f"unknown arc '{arc}'; known: {sorted(ARCS)}")
            phases = [
                (txt, wp, None)
                for txt, wp in _arc_phases(text, ARCS[arc])
            ]
        arc_phases: list[ArcPhaseReceipt] = []
        for i, (phase_text, waypoint, model_complexity) in enumerate(
            phases, 1
        ):
            comp = model_complexity or _complexity(phase_text)
            phase_ctx = (
                f"{context or 'arc'} "
                f"[arc {arc} phase {i}/{len(phases)}]"
            )
            runner = Path(__file__).resolve().parent.parent / "run.sh"
            rc = subprocess.run(
                ["bash", str(runner), "speak",
                 "--text", phase_text, "--voice", voice,
                 "--tone", waypoint["tone"],
                 "--pace", _effective_pace(waypoint["pace"], comp),
                 "--context", phase_ctx, "--no-normalize"]
                + (["--play"] if play else [])
                + (["--analyze"] if analyze else []),
                capture_output=True, text=True, timeout=600,
            )
            if rc.returncode != 0:
                _fail(f"arc phase {i} failed: {rc.stderr[-300:]}")
            marker = '"receipt": "'
            idx2 = rc.stdout.find(marker)
            rpath = rc.stdout[idx2 + len(marker):].split('"', 1)[0]
            r = json.loads(Path(rpath).read_text())
            arc_phases.append(ArcPhaseReceipt(
                phase=i,
                text=phase_text,
                tone=waypoint["tone"],
                pace=waypoint["pace"],
                complexity=comp,
                complexity_source=(
                    "model" if model_complexity else "heuristic"
                ),
                effective_pace=_effective_pace(waypoint["pace"], comp),
                wav=r.get("wav"),
                duration_seconds=r.get("duration_seconds"),
            ))
        receipt_obj = ArcReceipt(arc=arc, phases=arc_phases)
        out_dir = OUT_DIR / f"arc-{int(time.time())}-{arc}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "arc.json").write_text(
            receipt_obj.model_dump_json(indent=2, by_alias=True) + "\n"
        )
        chart = out_dir / "arc.svg"
        try:
            subprocess.run(
                ["python3",
                 str(Path(__file__).parent / "arc_chart.py"),
                 str(out_dir / "arc.json"), str(chart)],
                capture_output=True, text=True, timeout=30,
            )
        except Exception:
            pass
        print(receipt_obj.model_dump_json(indent=2, by_alias=True))
        if chart.is_file():
            print(json.dumps({"arc_chart": str(chart)}))
        return
    ref = ref_audio or VOICES.get(voice)
    if not ref:
        _fail(f"unknown voice '{voice}'; known: {sorted(VOICES)} (or pass --ref-audio)")
    if intensity is not None and intensity not in INTENSITY:
        _fail(f"intensity must be one of {sorted(INTENSITY)}")

    # Fail-closed tag gate, evaluated against the EFFECTIVE backend: an
    # explicit --intensity routes to the base-affect backend, which speaks
    # even known event tags as literal words, so on that route the whole
    # event vocabulary is unsupported. Runs before any POST; explicit
    # opt-out only, and the opt-out is always receipt-recorded.
    # The gate itself is the ONE definition in speak_core.
    gate_texts = [text]
    if caller_plan is not None:
        gate_texts.append(caller_plan.get("answer_text") or "")
        gate_texts += [c.get("text", "") for c in caller_plan["render_chunks"]
                       if isinstance(c, dict)]
    allow_event_tags = intensity is None  # explicit --intensity => base-affect route
    allow_named_pauses = planned_pauses
    unknown_found: list[str] = []
    for _gt in gate_texts:
        for _t in _UNSUPPORTED_TAGS(_gt, allow_event_tags=allow_event_tags,
                                    allow_named_pauses=allow_named_pauses):
            if _t not in unknown_found:
                unknown_found.append(_t)
    if unknown_found and not allow_unknown_tags:
        route_note = (
            "the explicit --intensity route uses the base-affect backend, which "
            "speaks inline event tags as literal spoken words; drop --intensity "
            "to use the Turbo tag route"
            if not allow_event_tags else
            "Plural forms ([laughs] [chuckles] [sighs]) are ElevenLabs-v3-only and "
            "would be spoken as literal words on the routed backend; use the "
            "singular form"
        )
        _fail(
            f"unsupported bracket tag(s) {unknown_found} for the effective "
            f"backend; supported event tags: {sorted(_KNOWN_EVENT_TAGS)}. {route_note}. "
            "Override only with --allow-unknown-tags."
        )

    state = _load_session(session) if session else None
    if state and to:
        state.speaker = to

    requested = INTENSITY.get(intensity) if intensity else None
    effective = requested
    if state:
        if requested is not None:
            prev = state.mood_intensity if state.mood_intensity is not None else requested
            effective = max(0.0, min(1.0, prev + MOOD_BLEND * (requested - prev)))
            state.mood_intensity = effective
        elif state.mood_intensity is not None:
            effective = state.mood_intensity  # hold session mood when this turn specifies none
        if tone is None:
            tone = state.last_tone

    delivery = None
    if effective is not None:
        delivery = {"intensity": round(effective, 3), "emotion_realization": "audible"}
    if pace is not None:
        delivery = {**(delivery or {}), "pace": pace}

    turn_id = f"cli-{uuid4().hex}"
    answer_text = None
    pause_plan_chunks = None
    compiled_answer_text = None
    if caller_plan is not None:
        answer_text = caller_plan.get("answer_text") or text
        chunks = caller_plan["render_chunks"]
        render_source = "caller_plan"
    elif planned_pauses:
        compiler = Path(__file__).resolve().parents[2] / "best-practices-chatterbox/run.sh"
        try:
            text = resolve_pause_macros(text, load_macros(PAUSE_MACROS_PATH))
        except ValueError as exc:
            _fail(str(exc))  # unknown [pause:<name>] macro fails closed, never spoken
        proc = subprocess.run([str(compiler), "plan-silence", "--text", text,
                               "--tone", tone or "neutral_warm"], capture_output=True, text=True, timeout=30)
        if proc.returncode:
            _fail(f"pause compiler failed: {proc.stderr}")
        compiled = RenderPlan.model_validate_json(proc.stdout)
        answer_text = compiled.answer_text
        compiled_answer_text = compiled.answer_text
        chunks = [c.model_dump() for c in compiled.render_chunks]
        pause_plan_chunks = chunks
        render_source = "compiled"
    else:
        chunks = None
        render_source = "single"

    # Gate + payload + POST + typed validation + host-WAV copy: the core's
    # single render seam. The gate re-fires here (defense in depth) and has
    # already passed above, so behavior is unchanged.
    try:
        plan = core.build_plan(
            turn_id=turn_id, text=text, answer_text=answer_text,
            render_chunks=chunks, voice=voice, ref_audio=ref, tone=tone,
            intensity=intensity, delivery=delivery, pace=pace,
            temperature=temperature, allow_unknown_tags=allow_unknown_tags,
            render_source=render_source,
        )
        result = core.render(plan)
    except core.UnsupportedTagError as exc:
        route_note = (
            "the explicit --intensity route uses the base-affect backend, which "
            "speaks inline event tags as literal spoken words; drop --intensity "
            "to use the Turbo tag route"
            if exc.base_affect_route else
            "Plural forms ([laughs] [chuckles] [sighs]) are ElevenLabs-v3-only and "
            "would be spoken as literal words on the routed backend; use the "
            "singular form"
        )
        _fail(
            f"unsupported bracket tag(s) {exc.tags} for the effective "
            f"backend; supported event tags: {sorted(core._KNOWN_EVENT_TAGS)}. {route_note}. "
            "Override only with --allow-unknown-tags."
        )
    except (core.UnknownVoiceError, ValueError, core.ServiceCallFailed,
            core.ServiceResponseInvalid) as exc:
        _fail(str(exc))

    if state:
        state.last_tone = tone
        state.turns += 1
        _save_session(state)

    memory_context = _recall_context(context or text, (state.speaker if state else to)) if recall_context else None

    record = core.build_receipt(
        plan, result, context=context, original_text=original_text,
        spoken_text=text, pronunciation_normalized=bool(normalize),
        requested_intensity=intensity,
        speaking_to=(state.speaker if state else to),
        session=(state.model_dump() if state else None),
        memory_context=memory_context,
        pause_plan_chunks=(pause_plan_chunks if pause_plan_chunks is not None
                           else (caller_plan or {}).get("render_chunks")),
    ).model_dump()
    receipt_path = result.wav_copy.parent / "receipt.json"
    receipt_path.write_text(json.dumps(record, indent=2))

    if analyze:
        proc = subprocess.run(
            [str(ANALYZER), "analyze", "--audio", str(result.wav_copy), "--json",
             "--expected-text", compiled_answer_text if compiled_answer_text is not None else text,
             "--render-plan", str(receipt_path)],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if proc.returncode:
            _fail(f"analyzer failed (rc={proc.returncode}): {proc.stderr[:500]}")
        try:
            record["analysis"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _fail(f"analyzer failed (rc={proc.returncode}): {proc.stderr[:500]}")
        receipt_path.write_text(json.dumps(record, indent=2))

    if play:
        rc = subprocess.run(["pw-play", str(result.wav_copy)], check=False, timeout=300).returncode
        record["playback"] = {"cmd": f"pw-play {result.wav_copy}", "returncode": rc}
        receipt_path.write_text(json.dumps(record, indent=2))
        if rc:
            _fail(f"playback failed (rc={rc})")

    print(json.dumps({"ok": True, "wav": str(result.wav_copy), "receipt": str(receipt_path),
                      "duration_seconds": result.receipt.duration_seconds,
                      "backend": (result.service_json.get("backend") or {}).get("id"),
                      "tags_interpreted": (result.service_json.get("tag_handling") or {}).get("tags_interpreted"),
                      "analysis": (record.get("analysis") or {}).get("affect")}, indent=2))


if __name__ == "__main__":
    app()
