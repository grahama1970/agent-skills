"""Streaming stage-1 resolver: decide readiness without waiting for completion.

The gate decision is emitted as soon as the gating fields arrive, not when the
response finishes. Measured on live captured audio: the model emits
``{"ready_to_answer":false,"blocking_reason":"truncated"`` in its first content
delta, so a decision is available at time-to-first-token -- 2.3s on the common
"still truncated, keep listening" path against 3.85s for the full response, and
5.9s against 8.95s when a question completes.

That ordering is not incidental. The prompt pins the gating keys first and
pushes ``clarifying_questions`` to the tail precisely so a streaming consumer
can act before the long field arrives. Reordering the schema silently costs the
latency this module exists to recover.

Transport is a direct SciLLM call. See SKILL.md "Provider boundary: two tiers"
for why stage 1 does not route through ``$ask tau-dag``: Tau adds ~27s of
orchestration to an ~11s call, and a readiness verdict is worthless three
seconds later, so none of what Tau guarantees applies to this tier.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .readiness import ClarifyingQuestion, ReadinessVerdict

DEFAULT_URL = "http://127.0.0.1:4001"
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "low"

# Gating keys first, clarifying_questions last. Do not reorder.
PROMPT_HEADER = (
    "You are stage 1 of a live interview copilot. Below is a raw speech-to-text "
    "buffer. Punctuation is unreliable and speaker labels may be absent. Decide "
    "whether a LEGITIMATE, COMPLETE question has been asked YET.\n\n"
    "Return ONLY JSON with keys in EXACTLY this order:\n"
    '{"ready_to_answer":bool,"blocking_reason":"none|truncated|awaiting_more_speech|'
    'needs_clarification|not_a_question","question_type":"research|code|leetcode|'
    'client|none","actionable":bool,"question_asked_yet":bool,'
    '"canonical_question":str,"clarifying_questions":[str],"confidence":float,'
    '"action_candidates":[{"kind":"fact_check|remember_fact|open_artifact",'
    '"payload":str,"summary":str}]}\n\n'
    "Rules:\n"
    "- A statement cut off mid-sentence is NOT complete; ready_to_answer=false, "
    "blocking_reason=truncated.\n"
    "- A buffer may end at a grammatical sentence boundary and still be an "
    "incomplete question. Judge the question, not the punctuation.\n"
    "- Social pleasantries are questions but actionable=false, question_type=none.\n"
    "- Narration addressed to an audience is not_a_question.\n"
    "- A declarative problem statement that requests work IS a question.\n"
    "- ALWAYS populate clarifying_questions for an actionable question, even when\n"
    "  ready_to_answer is true: give the 2-4 constraints a candidate should confirm\n"
    "  with the interviewer before committing to an approach (input bounds,\n"
    "  character set, return contract, edge cases, scale). These are what the human\n"
    "  should ASK, not things you need. Leave empty only when not actionable.\n"
    "- Do not answer the question. Only judge readiness and what to clarify.\n"
    "- action_candidates (usually empty; at most 3): a checkable factual CLAIM\n"
    "  someone stated (kind=fact_check, payload=the claim), an explicit DECISION\n"
    "  or commitment worth remembering (kind=remember_fact, payload=the decision),\n"
    "  or a NAMED file/artifact someone referenced (kind=open_artifact,\n"
    "  payload=the artifact name). Only propose what was literally said.\n\n"
    "BUFFER:\n"
)

_GATE_RE = re.compile(
    r'"ready_to_answer"\s*:\s*(true|false).*?"blocking_reason"\s*:\s*"([a-z_]+)"',
    re.S,
)
_TYPE_RE = re.compile(r'"question_type"\s*:\s*"([a-z]+)"')
_JSON_RE = re.compile(r"\{.*\}", re.S)


def resolver_key() -> str | None:
    """Resolve the SciLLM key, most authoritative first.

    SCILLM_PROXY_KEY in the shell profile has drifted from the running
    container's SCILLM_MASTER_KEY on this machine, so it is tried last. A stale
    key returns 401 and trips the proxy abuse guard after 5 errors in 30s.
    """

    # SCILLM_PROXY_KEY is deliberately NOT in this chain. It is exported from
    # the shell profile on this machine and has drifted from the running
    # container's master key, so picking it up made every resolver call a
    # doomed 401 round trip on the card critical path -- which blew the 8s
    # window sanity_live.py allows for a card to appear, and tripped the proxy
    # abuse guard. Stage 1 is opt-in: configure LIVE_EVIDENCE_SCILLM_KEY.
    for name in ("LIVE_EVIDENCE_SCILLM_KEY", "SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY"):
        value = os.getenv(name)
        if value:
            return value
    return None


@dataclass
class GateEvent:
    """Earliest actionable signal: emitted before the response completes."""

    ready_to_answer: bool
    blocking_reason: str
    question_type: str | None
    elapsed_s: float


@dataclass
class ResolverOutcome:
    gate: GateEvent | None = None
    verdict: ReadinessVerdict | None = None
    raw: str = ""
    error: str | None = None
    gate_elapsed_s: float | None = None
    total_elapsed_s: float | None = None
    events: list[str] = field(default_factory=list)


class StreamingResolver:
    """Call SciLLM with stream=true and surface the gate at first token."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._url = (url or os.getenv("LIVE_EVIDENCE_SCILLM_URL") or DEFAULT_URL).rstrip("/")
        self._model = model or os.getenv("LIVE_EVIDENCE_RESOLVER_MODEL") or DEFAULT_MODEL
        self._effort = effort or os.getenv("LIVE_EVIDENCE_RESOLVER_EFFORT") or DEFAULT_EFFORT
        self._timeout_s = timeout_s

    def _stream_fixture(self, path: Path) -> Iterator[GateEvent | ResolverOutcome]:
        yield from _stream_fixture_verdicts(path)

    def stream(self, buffer_text: str) -> Iterator[GateEvent | ResolverOutcome]:
        """Yield a GateEvent as soon as it is parseable, then the final outcome."""

        import time

        fixture = os.getenv("LIVE_EVIDENCE_RESOLVER_FIXTURE")
        if fixture:
            yield from self._stream_fixture(Path(fixture))
            return

        key = resolver_key()
        if not key:
            yield ResolverOutcome(error="no_scillm_key_configured")
            return

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": PROMPT_HEADER + buffer_text}],
            "reasoning_effort": self._effort,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "X-Caller-Skill": "live-evidence",
            "Content-Type": "application/json",
        }

        accumulated = ""
        gate: GateEvent | None = None
        start = time.monotonic()
        # urllib rather than httpx: httpx builds an SSL context eagerly in its
        # transport even for a plain-http URL, and on this machine that raises
        # FileNotFoundError from ssl.load_verify_locations when the venv has no
        # CA bundle. This endpoint is http://127.0.0.1 with no TLS, so the
        # stdlib client is both sufficient and one less environment dependency.
        request = urllib.request.Request(
            f"{self._url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if not piece:
                        continue
                    accumulated += piece
                    if gate is None:
                        match = _GATE_RE.search(accumulated)
                        if match is not None:
                            type_match = _TYPE_RE.search(accumulated)
                            gate = GateEvent(
                                ready_to_answer=match.group(1) == "true",
                                blocking_reason=match.group(2),
                                question_type=type_match.group(1) if type_match else None,
                                elapsed_s=time.monotonic() - start,
                            )
                            yield gate
        except urllib.error.HTTPError as exc:
            yield ResolverOutcome(
                gate=gate,
                error=f"scillm_http_{exc.code}",
                raw=accumulated,
                total_elapsed_s=time.monotonic() - start,
            )
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            yield ResolverOutcome(
                gate=gate,
                error=f"scillm_transport:{type(exc).__name__}",
                raw=accumulated,
                total_elapsed_s=time.monotonic() - start,
            )
            return

        outcome = ResolverOutcome(
            gate=gate,
            raw=accumulated,
            gate_elapsed_s=gate.elapsed_s if gate else None,
            total_elapsed_s=time.monotonic() - start,
        )
        outcome.verdict = _parse_verdict(accumulated)
        if outcome.verdict is None:
            # Unparseable output must never read as permission to answer.
            outcome.error = outcome.error or "unparseable_verdict"
        yield outcome


def _fixture_index(path: Path) -> int:
    counter = path.with_suffix(path.suffix + ".idx")
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index + 1))
    return index


def _stream_fixture_verdicts(path: Path):
    """Deterministic resolver verdicts for agentic evals (#1454 proofs).

    The fixture is a JSON list of verdict objects consumed one per call via a
    sidecar counter, so an eval can script "not ready yet" then "ready with two
    blocking clarifications" without a model or a network. The last entry
    repeats once the list is exhausted.
    """

    verdicts = json.loads(path.read_text())
    index = min(_fixture_index(path), len(verdicts) - 1)
    payload = verdicts[index]
    verdict = _parse_verdict(json.dumps(payload))
    outcome = ResolverOutcome(raw=json.dumps(payload), verdict=verdict,
                              gate_elapsed_s=0.0, total_elapsed_s=0.0)
    if verdict is None:
        outcome.error = "unparseable_verdict"
    yield outcome


def _parse_verdict(raw: str) -> ReadinessVerdict | None:
    match = _JSON_RE.search(raw or "")
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    questions = payload.get("clarifying_questions") or []
    normalized: list[ClarifyingQuestion] = []
    for index, item in enumerate(questions):
        if isinstance(item, str) and item.strip():
            normalized.append(ClarifyingQuestion(id=f"clarify-{index + 1}", question=item.strip()[:400]))
        elif isinstance(item, dict) and str(item.get("question", "")).strip():
            normalized.append(
                ClarifyingQuestion(
                    id=str(item.get("id") or f"clarify-{index + 1}"),
                    question=str(item["question"]).strip()[:400],
                    why_it_matters=(str(item["why_it_matters"])[:400] if item.get("why_it_matters") else None),
                    default_assumption=(
                        str(item["default_assumption"])[:400] if item.get("default_assumption") else None
                    ),
                    blocking=bool(item.get("blocking", False)),
                )
            )
    payload["clarifying_questions"] = normalized
    try:
        return ReadinessVerdict.model_validate(payload)
    except Exception:
        return None
