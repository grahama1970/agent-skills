from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from .server import ClarifyServer
from .tui import prompt_single_question
from .types import ClarifyOption, ClarifyQuestion


class ClarifyError(Exception):
    """Base class for clarifying UI errors."""


class ClarifyTimeout(ClarifyError):
    """Raised when the clarifying UI times out."""


@dataclass
class ClarifySession:
    out_dir: Path
    step_name: str
    attempt: int
    questions: List[ClarifyQuestion]
    timeout_sec: int
    event: threading.Event = field(default_factory=threading.Event)
    responses: Optional[List[dict[str, Any]]] = None
    payload: Optional[dict[str, Any]] = None

    @property
    def response_path(self) -> Path:
        target_dir = self.out_dir / "clarifications" / self.step_name
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"attempt_{self.attempt}.json"

    def save_responses(
        self, responses: List[dict[str, Any]], extra: Optional[dict[str, Any]] = None
    ) -> Path:
        self.responses = responses
        payload = {
            "step": self.step_name,
            "attempt": self.attempt,
            "responses": responses,
        }
        if extra:
            payload.update({k: v for k, v in extra.items() if k not in payload})
        self.payload = payload
        self.response_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.response_path


def _dict_to_question(idx: int, data: dict[str, Any]) -> ClarifyQuestion:
    qid = data.get("id") or f"q{idx+1}"
    prompt = data.get("prompt") or str(data)
    kind = data.get("kind") or ("single-choice" if data.get("options") else "text")
    allow_multiple = bool(data.get("allow_multiple"))
    options_data = data.get("options") or []
    options = [
        ClarifyOption(
            id=opt.get("id") or f"{qid}_opt_{i+1}",
            label=opt.get("label") or str(opt),
            description=opt.get("description"),
        )
        for i, opt in enumerate(options_data)
    ]
    artifact_paths = list(data.get("artifact_paths") or [])
    visuals = list(data.get("visual_assets") or [])
    docs_link = data.get("docs_link")
    required = data.get("required", True)
    return ClarifyQuestion(
        id=qid,
        prompt=prompt,
        kind=kind,
        options=options,
        docs_link=docs_link,
        artifact_paths=artifact_paths,
        visual_assets=visuals,
        required=required,
        allow_multiple=allow_multiple,
    )


def normalize_questions(raw: Iterable[Any]) -> List[ClarifyQuestion]:
    questions: List[ClarifyQuestion] = []
    for idx, item in enumerate(raw or []):
        if isinstance(item, ClarifyQuestion):
            questions.append(item)
            continue
        if isinstance(item, dict):
            questions.append(_dict_to_question(idx, item))
            continue
        qid = f"q{idx+1}"
        prompt = str(item)
        questions.append(ClarifyQuestion(id=qid, prompt=prompt))
    return questions


def run_clarification_flow(
    out_dir: Path,
    step_name: str,
    attempt: int,
    raw_questions: Sequence[Any],
    timeout_sec: int,
    *,
    tui_handler=None,
    flask_runner=None,
) -> Optional[Path]:
    questions = normalize_questions(raw_questions)
    if not questions:
        return None

    session = ClarifySession(
        out_dir=out_dir,
        step_name=step_name,
        attempt=attempt,
        questions=questions,
        timeout_sec=timeout_sec,
    )

    if len(questions) == 1:
        response = prompt_single_question(questions[0], handler=tui_handler)
        session.save_responses(
            [
                {
                    "id": questions[0].id,
                    **response,
                }
            ]
        )
        return session.response_path

    runner = flask_runner or _run_flask_session
    runner(session)
    if not session.responses:
        raise ClarifyError("Clarification UI exited without responses.")
    return session.response_path


def _run_flask_session(session: ClarifySession) -> None:
    server = ClarifyServer(session.step_name, session.attempt, session.questions)
    port = server.start()
    url = f"http://127.0.0.1:{port}/"
    print(f"ℹ️ Clarify UI for {session.step_name}: {url}")
    finished = server.wait(session.timeout_sec)
    server.stop()
    if not finished or not server.responses:
        raise ClarifyTimeout(
            f"Clarifying UI timed out after {session.timeout_sec // 60} minutes."
        )
    session.save_responses(server.responses, extra=server.payload)
