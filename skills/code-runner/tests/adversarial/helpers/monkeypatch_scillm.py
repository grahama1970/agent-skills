from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import pytest


def tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args),
                },
            }
        ],
    }


def final_message(text: str = "done") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text,
    }


class FakeScillm:
    """Fast deterministic fake for code_runner.scillm.stream_chat()."""

    def __init__(self, messages: Iterable[dict[str, Any]] | None = None, *, error: Exception | None = None) -> None:
        self.messages = list(messages or [])
        self.error = error
        self.requests: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakeScillm":
        import code_runner.scillm as scillm

        def fake_stream_chat(payload: dict[str, Any], task_id: str, round_num: int) -> dict[str, Any]:
            self.requests.append(
                {
                    "payload": payload,
                    "task_id": task_id,
                    "round_num": round_num,
                }
            )
            if self.error is not None:
                raise self.error
            if self.messages:
                message = self.messages.pop(0)
            else:
                message = final_message("fake transcript exhausted")
            return {"choices": [{"message": message, "finish_reason": "stop"}]}

        monkeypatch.setattr(scillm, "stream_chat", fake_stream_chat)
        return self
