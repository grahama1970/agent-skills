from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(no_args_is_help=True, help="Buzz relay wrapper for skill notifications.")
config_app = typer.Typer(help="Inspect ops-buzz configuration.")
messages_app = typer.Typer(help="Read/search Buzz messages through buzz-cli.")
app.add_typer(config_app, name="config")
app.add_typer(messages_app, name="messages")


MESSAGE_SCHEMA = "ops_buzz.message.v1"
AGENT_REQUEST_SCHEMA = "ops_buzz.agent_request.v1"
MESSAGE_SEAM_VALIDATION = {"kind": MESSAGE_SCHEMA, "status": "PASS"}
AGENT_REQUEST_SEAM_VALIDATION = {"kind": AGENT_REQUEST_SCHEMA, "status": "PASS"}


class ContractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class MessageItem:
    title: str
    subtitle: str | None = None
    url: str | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Any, index: int) -> "MessageItem":
        if not isinstance(raw, dict):
            raise ContractError("ITEM_INVALID", f"items[{index}] must be an object")
        title = _required_str(raw, "title", f"items[{index}]")
        subtitle = _optional_str(raw, "subtitle", f"items[{index}]")
        url = _optional_str(raw, "url", f"items[{index}]")
        notes_raw = raw.get("notes", [])
        if notes_raw is None:
            notes_raw = []
        if not isinstance(notes_raw, list) or not all(isinstance(item, str) for item in notes_raw):
            raise ContractError("ITEM_NOTES_INVALID", f"items[{index}].notes must be a list of strings")
        return cls(title=title, subtitle=subtitle, url=url, notes=list(notes_raw))


@dataclass
class BuzzMessage:
    title: str
    body: str
    external_effects: bool
    source_skill: str | None = None
    source_run_id: str | None = None
    source_url: str | None = None
    items: list[MessageItem] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "BuzzMessage":
        if raw.get("schema") != MESSAGE_SCHEMA:
            raise ContractError("SCHEMA_INVALID", f"schema must be {MESSAGE_SCHEMA}")
        title = _required_str(raw, "title", "message")
        body = _required_str(raw, "body", "message")
        external_effects = raw.get("external_effects")
        if not isinstance(external_effects, bool):
            raise ContractError("EXTERNAL_EFFECTS_INVALID", "external_effects must be true or false")
        items_raw = raw.get("items", [])
        if items_raw is None:
            items_raw = []
        if not isinstance(items_raw, list):
            raise ContractError("ITEMS_INVALID", "items must be a list")
        return cls(
            title=title,
            body=body,
            external_effects=external_effects,
            source_skill=_optional_str(raw, "source_skill", "message"),
            source_run_id=_optional_str(raw, "source_run_id", "message"),
            source_url=_optional_str(raw, "source_url", "message"),
            items=[MessageItem.from_raw(item, index) for index, item in enumerate(items_raw)],
        )

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", self.body.strip(), ""]
        if self.items:
            lines.append("## Items")
            for index, item in enumerate(self.items, start=1):
                head = f"{index}. {item.title}"
                if item.subtitle:
                    head += f" - {item.subtitle}"
                lines.append(head)
                if item.url:
                    lines.append(f"   {item.url}")
                for note in item.notes:
                    lines.append(f"   - {note}")
            lines.append("")
        lines.append("## Source")
        if self.source_skill:
            lines.append(f"- Skill: {self.source_skill}")
        if self.source_run_id:
            lines.append(f"- Run: {self.source_run_id}")
        if self.source_url:
            lines.append(f"- URL: {self.source_url}")
        lines.append(f"- External effects: {str(self.external_effects).lower()}")
        lines.append("")
        return "\n".join(lines)


@dataclass
class AgentRequest:
    channel: str
    target_agent: str
    prompt: str
    expected_response: str
    source_skill: str | None = None
    source_run_id: str | None = None
    source_url: str | None = None
    source_artifact: str | None = None
    mention_pubkey: str | None = None
    reply_to: str | None = None
    timeout_seconds: int = 0
    poll_interval_seconds: int = 5
    readback_limit: int = 20

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "AgentRequest":
        if raw.get("schema") != AGENT_REQUEST_SCHEMA:
            raise ContractError("SCHEMA_INVALID", f"schema must be {AGENT_REQUEST_SCHEMA}")
        channel = _required_str(raw, "channel", "agent_request")
        target_agent = _required_str(raw, "target_agent", "agent_request")
        prompt = _required_str(raw, "prompt", "agent_request")
        expected_response = _required_str(raw, "expected_response", "agent_request")
        return cls(
            channel=channel,
            target_agent=target_agent,
            prompt=prompt,
            expected_response=expected_response,
            source_skill=_optional_str(raw, "source_skill", "agent_request"),
            source_run_id=_optional_str(raw, "source_run_id", "agent_request"),
            source_url=_optional_str(raw, "source_url", "agent_request"),
            source_artifact=_optional_str(raw, "source_artifact", "agent_request"),
            mention_pubkey=_optional_str(raw, "mention_pubkey", "agent_request"),
            reply_to=_optional_str(raw, "reply_to", "agent_request"),
            timeout_seconds=_int_range(raw, "timeout_seconds", 0, 600, default=0),
            poll_interval_seconds=_int_range(raw, "poll_interval_seconds", 1, 60, default=5),
            readback_limit=_int_range(raw, "readback_limit", 1, 100, default=20),
        )

    def to_markdown(self) -> str:
        mention = f"@{self.target_agent}"
        lines = [
            f"{mention} request from ops-buzz",
            "",
            self.prompt.strip(),
            "",
            "## Expected response contract",
            self.expected_response.strip(),
            "",
        ]
        source_lines = []
        if self.source_skill:
            source_lines.append(f"- Skill: {self.source_skill}")
        if self.source_run_id:
            source_lines.append(f"- Run: {self.source_run_id}")
        if self.source_url:
            source_lines.append(f"- URL: {self.source_url}")
        if self.source_artifact:
            source_lines.append(f"- Artifact: {self.source_artifact}")
        if source_lines:
            lines.append("## Source")
            lines.extend(source_lines)
            lines.append("")
        return "\n".join(lines)


def _required_str(raw: dict[str, Any], key: str, context: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError("FIELD_REQUIRED", f"{context}.{key} must be a non-empty string")
    return value.strip()


def _optional_str(raw: dict[str, Any], key: str, context: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("FIELD_INVALID", f"{context}.{key} must be a string when present")
    return value.strip() or None


def _int_range(raw: dict[str, Any], key: str, minimum: int, maximum: int, default: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContractError("FIELD_INVALID", f"agent_request.{key} must be an integer")
    if value < minimum or value > maximum:
        raise ContractError(
            "FIELD_INVALID",
            f"agent_request.{key} must be between {minimum} and {maximum}",
        )
    return value


def _load_message(path: Path) -> tuple[dict[str, Any], BuzzMessage]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("INPUT_INVALID_JSON", f"cannot read message JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContractError("INPUT_INVALID", "message JSON must be an object")
    message = BuzzMessage.from_raw(raw)
    raw["seam_validation"] = dict(MESSAGE_SEAM_VALIDATION)
    return raw, message


def _load_agent_request(path: Path) -> tuple[dict[str, Any], AgentRequest]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("INPUT_INVALID_JSON", f"cannot read agent request JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContractError("INPUT_INVALID", "agent request JSON must be an object")
    request = AgentRequest.from_raw(raw)
    raw["seam_validation"] = dict(AGENT_REQUEST_SEAM_VALIDATION)
    return raw, request


def _buzz_bin() -> str:
    return os.environ.get("BUZZ_BIN", "buzz")


def _run_buzz(args: list[str], stdin: str | None = None) -> dict[str, Any]:
    cmd = [_buzz_bin(), *args]
    try:
        result = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ContractError("BUZZ_BIN_MISSING", f"buzz CLI not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ContractError("BUZZ_TIMEOUT", f"buzz CLI timed out: {' '.join(cmd)}") from exc
    parsed_stdout: Any = None
    if result.stdout.strip():
        try:
            parsed_stdout = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed_stdout = None
    return {
        "cmd": cmd,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_json": parsed_stdout,
    }


def _extract_event_id(send_stdout_json: Any) -> str | None:
    if not isinstance(send_stdout_json, dict):
        return None
    for key in ("id", "event_id"):
        value = send_stdout_json.get(key)
        if isinstance(value, str) and len(value) == 64:
            return value
    event = send_stdout_json.get("event")
    if isinstance(event, dict):
        value = event.get("id")
        if isinstance(value, str) and len(value) == 64:
            return value
    return None


def _event_mentions_request(event: dict[str, Any], request_event_id: str | None, target_agent: str) -> bool:
    content = event.get("content")
    request_prefix = f"@{target_agent} request from ops-buzz"
    if isinstance(content, str) and content.lower().startswith(request_prefix.lower()):
        return False
    if isinstance(content, str) and target_agent.lower() in content.lower():
        return True
    if request_event_id:
        tags = event.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if (
                    isinstance(tag, list)
                    and len(tag) >= 2
                    and tag[0] == "e"
                    and tag[1] == request_event_id
                ):
                    return True
    return False


def _readback_response(request: AgentRequest, request_event_id: str | None) -> dict[str, Any]:
    result = _run_buzz(["messages", "get", "--channel", request.channel, "--limit", str(request.readback_limit)])
    events = result.get("stdout_json")
    observed = None
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and _event_mentions_request(event, request_event_id, request.target_agent):
                event_id = event.get("id")
                if request_event_id and event_id == request_event_id:
                    continue
                observed = event
                break
    return {
        "buzz": result,
        "response_observed": observed is not None,
        "response_event": observed,
    }


def _poll_for_response(request: AgentRequest, request_event_id: str | None) -> dict[str, Any]:
    deadline = time.monotonic() + request.timeout_seconds
    attempts = []
    while True:
        readback = _readback_response(request, request_event_id)
        attempts.append(readback)
        if readback["response_observed"] or time.monotonic() >= deadline:
            return {
                "attempt_count": len(attempts),
                "latest": readback,
                "response_observed": readback["response_observed"],
            }
        time.sleep(min(request.poll_interval_seconds, max(0.0, deadline - time.monotonic())))


def _emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _fail(exc: ContractError) -> None:
    _emit({"schema": "ops_buzz.error.v1", "ok": False, "code": exc.code, "message": exc.message})
    raise typer.Exit(1)


@config_app.command("doctor")
def config_doctor(json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False) -> None:
    buzz_path = shutil.which(_buzz_bin())
    receipt = {
        "schema": "ops_buzz.config_doctor.v1",
        "buzz_bin": _buzz_bin(),
        "buzz_bin_path": buzz_path,
        "buzz_cli_found": buzz_path is not None,
        "buzz_relay_url_set": bool(os.environ.get("BUZZ_RELAY_URL")),
        "buzz_private_key_set": bool(os.environ.get("BUZZ_PRIVATE_KEY")),
        "needs_attention": [],
    }
    if buzz_path is None:
        receipt["needs_attention"].append(
            {
                "reason": "missing_buzz_cli",
                "safe_default": "render_or_dry_run_only",
                "resume_hint": "install buzz-cli or set BUZZ_BIN",
            }
        )
    if not os.environ.get("BUZZ_PRIVATE_KEY"):
        receipt["needs_attention"].append(
            {
                "reason": "missing_buzz_private_key",
                "safe_default": "do_not_post_live",
                "resume_hint": "export BUZZ_PRIVATE_KEY for buzz-cli signing",
            }
        )
    if not os.environ.get("BUZZ_RELAY_URL"):
        receipt["needs_attention"].append(
            {
                "reason": "missing_buzz_relay_url",
                "safe_default": "use buzz-cli default only if intentionally local",
                "resume_hint": "export BUZZ_RELAY_URL for the target relay",
            }
        )
    if json_output:
        _emit(receipt)
        return
    for key, value in receipt.items():
        print(f"{key}: {value}")


@app.command("render-message")
def render_message(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", dir_okay=False, writable=True)] = None,
) -> None:
    try:
        raw, message = _load_message(input_path)
    except ContractError as exc:
        _fail(exc)
    rendered = message.to_markdown()
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    receipt = {
        "schema": "ops_buzz.render_receipt.v1",
        "ok": True,
        "mocked": False,
        "live": False,
        "input": str(input_path),
        "output": str(output) if output else None,
        "message_chars": len(rendered),
        "seam_validation": raw["seam_validation"],
    }
    _emit(receipt)


@app.command("post")
def post_message(
    channel: Annotated[str, typer.Option("--channel", help="Buzz channel UUID.")],
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False, readable=True)],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Render and receipt without calling Buzz.")] = False,
) -> None:
    try:
        raw, message = _load_message(input_path)
    except ContractError as exc:
        _fail(exc)
    rendered = message.to_markdown()
    receipt: dict[str, Any] = {
        "schema": "ops_buzz.post_receipt.v1",
        "ok": True,
        "mocked": False,
        "live": False,
        "dry_run": dry_run,
        "attempted_network": False,
        "posted": False,
        "channel": channel,
        "input": str(input_path),
        "message_chars": len(rendered),
        "seam_validation": raw["seam_validation"],
    }
    if dry_run:
        _emit(receipt)
        return
    try:
        result = _run_buzz(["messages", "send", "--channel", channel, "--content", "-"], stdin=rendered)
    except ContractError as exc:
        _fail(exc)
    receipt.update(
        {
            "live": True,
            "attempted_network": True,
            "posted": result["exit_code"] == 0,
            "buzz": result,
        }
    )
    if result["exit_code"] != 0:
        receipt["ok"] = False
    _emit(receipt)
    if result["exit_code"] != 0:
        raise typer.Exit(result["exit_code"])


@app.command("ask-agent")
def ask_agent(
    input_path: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False, readable=True)],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Render and receipt without calling Buzz.")] = False,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Poll for a response after posting.")] = True,
    output_request: Annotated[Path | None, typer.Option("--output-request", dir_okay=False, writable=True)] = None,
) -> None:
    try:
        raw, request = _load_agent_request(input_path)
    except ContractError as exc:
        _fail(exc)
    rendered = request.to_markdown()
    if output_request is not None:
        output_request.write_text(rendered, encoding="utf-8")

    receipt: dict[str, Any] = {
        "schema": "ops_buzz.agent_request_receipt.v1",
        "ok": True,
        "status": "DRY_RUN" if dry_run else "NOT_STARTED",
        "mocked": False,
        "live": False,
        "dry_run": dry_run,
        "attempted_network": False,
        "request_posted": False,
        "response_observed": False,
        "input": str(input_path),
        "channel": request.channel,
        "target_agent": request.target_agent,
        "message_chars": len(rendered),
        "output_request": str(output_request) if output_request else None,
        "seam_validation": raw["seam_validation"],
    }
    if dry_run:
        _emit(receipt)
        return

    send_args = ["messages", "send", "--channel", request.channel, "--content", "-"]
    if request.reply_to:
        send_args.extend(["--reply-to", request.reply_to])
    if request.mention_pubkey:
        send_args.extend(["--mention", request.mention_pubkey])

    try:
        send_result = _run_buzz(send_args, stdin=rendered)
    except ContractError as exc:
        _fail(exc)

    request_event_id = _extract_event_id(send_result.get("stdout_json"))
    receipt.update(
        {
            "live": True,
            "attempted_network": True,
            "request_posted": send_result["exit_code"] == 0,
            "request_event_id": request_event_id,
            "send": send_result,
        }
    )
    if send_result["exit_code"] != 0:
        receipt["ok"] = False
        receipt["status"] = "REQUEST_FAILED"
        _emit(receipt)
        raise typer.Exit(send_result["exit_code"])

    if wait and request.timeout_seconds > 0:
        try:
            poll = _poll_for_response(request, request_event_id)
        except ContractError as exc:
            _fail(exc)
        receipt["readback"] = poll
        receipt["response_observed"] = bool(poll["response_observed"])
        receipt["status"] = "RESPONSE_OBSERVED" if poll["response_observed"] else "NO_RESPONSE"
    else:
        receipt["status"] = "REQUEST_POSTED_NO_READBACK"
    _emit(receipt)


@messages_app.command("get")
def messages_get(
    channel: Annotated[str, typer.Option("--channel", help="Buzz channel UUID.")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    try:
        result = _run_buzz(["messages", "get", "--channel", channel, "--limit", str(limit)])
    except ContractError as exc:
        _fail(exc)
    _emit({"schema": "ops_buzz.query_receipt.v1", "kind": "messages_get", "live": True, "buzz": result})
    if result["exit_code"] != 0:
        raise typer.Exit(result["exit_code"])


@messages_app.command("search")
def messages_search(query: Annotated[str, typer.Option("--query", help="Search query.")]) -> None:
    try:
        result = _run_buzz(["messages", "search", "--query", query])
    except ContractError as exc:
        _fail(exc)
    _emit({"schema": "ops_buzz.query_receipt.v1", "kind": "messages_search", "live": True, "buzz": result})
    if result["exit_code"] != 0:
        raise typer.Exit(result["exit_code"])


def main() -> None:
    try:
        app()
    except BrokenPipeError:
        sys.exit(1)


if __name__ == "__main__":
    main()
