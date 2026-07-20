"""Opt-in live WebClaude sanity evals for the /ask skill directory.

This runner exercises the current low-level browser path for Claude:
browser-oracle binding, Surf tab identity, text round trip, zip upload, and
Claude inspection of a Markdown file plus PNG inside the zip.

It is intentionally not a default unit test. Live mode consumes Claude usage and
depends on an authenticated Claude tab.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer


ASK_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ASK_ROOT.parent
SURF_RUN = SKILLS_ROOT / "surf" / "run.sh"
BROWSER_ORACLE_RUN = SKILLS_ROOT / "browser-oracle" / "run.sh"
DEFAULT_OUTPUT_ROOT = ASK_ROOT / ".ask_artifacts" / "webclaude-sanity"
DEFAULT_PROJECT = "webclaude"
DEFAULT_EXPECT_URL = "https://claude.ai/chat/3cdf38d5-2c6c-4727-b5b9-eb7fd95f5146"
SCHEMA = "ask.webclaude_sanity_eval.v1"

app = typer.Typer(add_completion=False, help="Run opt-in WebClaude sanity evals.")


@dataclass
class CmdResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 3),
            "timed_out": self.timed_out,
            "stdout_excerpt": excerpt(self.stdout),
            "stderr_excerpt": excerpt(self.stderr),
        }


class EvalFailure(RuntimeError):
    """Raised when a required eval gate fails."""


@app.command()
def main(
    output_root: str = typer.Option(str(DEFAULT_OUTPUT_ROOT), "--output-root", help="Directory for eval artifacts."),
    project: str = typer.Option(DEFAULT_PROJECT, "--project", help="browser-oracle project binding name."),
    tab_id: str = typer.Option("", "--tab-id", help="Explicit Claude Chrome tab id. Overrides browser-oracle resolve."),
    expect_url: str = typer.Option(DEFAULT_EXPECT_URL, "--expect-url", help="Expected Claude conversation URL."),
    allow_live: bool = typer.Option(False, "--allow-live", help="Run live Claude browser checks."),
    plan_only: bool = typer.Option(False, "--plan-only", help="Write an eval plan without touching Claude."),
    timeout_seconds: int = typer.Option(180, "--timeout", help="Per-response wait timeout."),
    stable_polls: int = typer.Option(2, "--stable-polls", help="Stable polls required after Claude stops responding."),
) -> None:
    if not allow_live and not plan_only:
        typer.echo(
            "Refusing to run live WebClaude checks without --allow-live. "
            "Use --plan-only to write the eval plan without touching Claude.",
            err=True,
        )
        raise typer.Exit(code=2)
    run_dir = Path(output_root).resolve() / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    if plan_only:
        result = build_plan(run_dir=run_dir, project=project, tab_id=tab_id, expect_url=expect_url)
        write_reports(run_dir, result)
        print(json.dumps({"run_dir": str(run_dir), "status": result["status"], "planned_cases": len(result["cases"])}, indent=2))
        return

    result = run_live_eval(
        run_dir=run_dir,
        project=project,
        tab_id=tab_id,
        expect_url=expect_url,
        timeout_seconds=timeout_seconds,
        stable_polls=stable_polls,
    )
    write_reports(run_dir, result)
    print(json.dumps({"run_dir": str(run_dir), "status": result["status"], "passed": result["passed"]}, indent=2))
    raise typer.Exit(0 if result["passed"] else 1)


def build_plan(*, run_dir: Path, project: str, tab_id: str, expect_url: str) -> dict[str, Any]:
    cases = [
        plan_case("browser_oracle_binding", "Resolve/verify the webclaude browser-oracle binding."),
        plan_case("surf_tab_identity", "Confirm Surf sees the expected Claude tab id and URL."),
        plan_case("text_roundtrip", "Send a unique text sentinel and require Claude to echo it."),
        plan_case("zip_bundle_local", "Create a zip containing one Markdown file and one PNG; verify listing/checksums."),
        plan_case("zip_upload_visible", "Upload the zip through Claude's file input and require a visible attachment chip."),
        plan_case("zip_response_markers", "Require Claude to report both filenames, Markdown sentinel, and PNG image text."),
        plan_case("visual_receipt", "Capture a final same-tab screenshot after the response."),
    ]
    return base_result(
        run_dir=run_dir,
        project=project,
        tab_id=tab_id,
        expect_url=expect_url,
        status="planned",
        passed=False,
        cases=cases,
        artifacts=[],
        failures=["plan-only: live Claude checks were not executed"],
    )


def run_live_eval(
    *,
    run_dir: Path,
    project: str,
    tab_id: str,
    expect_url: str,
    timeout_seconds: int,
    stable_polls: int,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    artifacts: list[str] = []
    failures: list[str] = []
    commands: list[dict[str, Any]] = []
    requested_tab_id = tab_id.strip()
    active_tab_id = requested_tab_id
    url = expect_url.strip()
    markers = make_markers()

    def record(name: str, status: str, detail: str, **extra: Any) -> None:
        case = {"name": name, "status": status, "detail": detail, **extra}
        cases.append(case)
        if status != "pass":
            failures.append(f"{name}: {detail}")

    try:
        if not active_tab_id:
            resolved = resolve_browser_oracle(project, commands)
            active_tab_id = str(resolved.get("tab_id") or "")
            url = str(resolved.get("conversation_url") or url)
            if not active_tab_id:
                raise EvalFailure("browser-oracle resolve returned no tab_id")
            record("browser_oracle_binding", "pass", "Resolved webclaude binding.", resolved=resolved)
        else:
            verified = verify_browser_oracle(project, commands)
            record("browser_oracle_binding", "pass", "Verified configured webclaude binding.", verified=verified)

        tab = assert_surf_tab_identity(active_tab_id, url, commands)
        record("surf_tab_identity", "pass", "Surf tab.list matched requested Claude tab and URL.", tab=tab)

        text_prompt = f"Reply with exactly: {markers['text']}"
        submit_prompt(active_tab_id, text_prompt, commands)
        text_capture = wait_for_text(
            active_tab_id,
            markers["text"],
            run_dir / "text-roundtrip.txt",
            commands,
            timeout_seconds=timeout_seconds,
            stable_polls=stable_polls,
        )
        artifacts.append(str(text_capture))
        record("text_roundtrip", "pass", "Claude returned the text sentinel.", marker=markers["text"])

        bundle = create_zip_bundle(run_dir, markers)
        artifacts.extend(str(path) for path in bundle["artifacts"])
        record(
            "zip_bundle_local",
            "pass",
            "Created local zip and verified it contains Markdown plus PNG.",
            zip_path=str(bundle["zip_path"]),
            zip_sha256=bundle["zip_sha256"],
            files=bundle["files"],
        )

        upload_ref = expose_upload_input(active_tab_id, commands)
        run_surf(["upload", "--ref", upload_ref, "--files", str(bundle["zip_path"]), "--tab-id", active_tab_id], commands, timeout=60)
        upload_text = wait_for_attachment(active_tab_id, bundle["zip_path"].name, run_dir / "after-upload.txt", commands)
        artifacts.append(str(upload_text))
        record("zip_upload_visible", "pass", "Claude page showed the uploaded zip attachment.", filename=bundle["zip_path"].name)

        zip_prompt = (
            "Inspect only the newly attached zip bundle. Reply with exactly four lines. "
            f"ZIP_PROOF_RESPONSE: {markers['zip_response']}. "
            "FILES: list the filenames in the zip. "
            "MD_SENTINEL: quote the Markdown sentinel. "
            "IMAGE_SENTINEL: quote the exact large text visible in the PNG image."
        )
        submit_prompt(active_tab_id, zip_prompt, commands)
        zip_capture = wait_for_text(
            active_tab_id,
            markers["zip_response"],
            run_dir / "zip-response.txt",
            commands,
            timeout_seconds=timeout_seconds,
            stable_polls=stable_polls,
        )
        artifacts.append(str(zip_capture))
        response_text = zip_capture.read_text(encoding="utf-8")
        missing = validate_zip_response(response_text, markers, bundle["files"])
        if missing:
            raise EvalFailure("Claude zip response missing expected markers: " + ", ".join(missing))
        record(
            "zip_response_markers",
            "pass",
            "Claude reported both zip files, Markdown sentinel, and PNG image sentinel.",
            marker=markers["zip_response"],
        )

        screenshot = run_dir / "final-screenshot.png"
        run_surf(["snap", "--tab-id", active_tab_id, "--output", str(screenshot)], commands, timeout=60)
        artifacts.append(str(screenshot))
        record("visual_receipt", "pass", "Captured same-tab final screenshot.", screenshot=str(screenshot))
    except Exception as exc:
        failures.append(str(exc))

    result = base_result(
        run_dir=run_dir,
        project=project,
        tab_id=active_tab_id,
        expect_url=url,
        status="pass" if not failures else "fail",
        passed=not failures,
        cases=cases,
        artifacts=artifacts,
        failures=failures,
    )
    result["commands"] = commands
    result["markers"] = markers
    return result


def base_result(
    *,
    run_dir: Path,
    project: str,
    tab_id: str,
    expect_url: str,
    status: str,
    passed: bool,
    cases: list[dict[str, Any]],
    artifacts: list[str],
    failures: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "run_dir": str(run_dir),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": status,
        "passed": passed,
        "mocked": False,
        "live": status != "planned",
        "project": project,
        "tab_id": tab_id,
        "expect_url": expect_url,
        "cases": cases,
        "artifacts": artifacts,
        "failures": failures,
        "claims": {
            "proves": [
                "browser-oracle can resolve or verify a webclaude binding",
                "Surf can target the bound Claude tab by id",
                "Claude can receive and answer a text prompt in the controlled tab",
                "Claude can receive a zip attachment containing Markdown and PNG",
                "Claude can inspect the uploaded zip and report file plus content sentinels",
            ],
            "does_not_prove": [
                "a reusable surf claude.submit/webclaude.submit wrapper exists",
                "background/no-activate focus invariants for Claude",
                "multi-round reviewer orchestration through /ask",
                "large bundle or multi-file production review behavior",
            ],
        },
    }


def plan_case(name: str, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "planned",
        "detail": detail,
        "execution_status": "not_run",
        "assertion_status": "not_run",
    }


def resolve_browser_oracle(project: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    result = run_cmd(
        [str(BROWSER_ORACLE_RUN), "resolve", "--backend", "webclaude", "--project", project, "--json"],
        cwd=BROWSER_ORACLE_RUN.parent,
        timeout=60,
    )
    commands.append(result.summary())
    if result.returncode != 0:
        raise EvalFailure(f"browser-oracle resolve failed: {result.stderr or result.stdout}")
    return parse_json(result.stdout)


def verify_browser_oracle(project: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    result = run_cmd(
        [str(BROWSER_ORACLE_RUN), "verify", project, "--backend", "webclaude", "--json"],
        cwd=BROWSER_ORACLE_RUN.parent,
        timeout=60,
    )
    commands.append(result.summary())
    if result.returncode != 0:
        raise EvalFailure(f"browser-oracle verify failed: {result.stderr or result.stdout}")
    return parse_json(result.stdout)


def assert_surf_tab_identity(tab_id: str, expect_url: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    result = run_surf(["tab.list", "--json"], commands, timeout=60)
    tabs = parse_json(result.stdout)
    if isinstance(tabs, dict):
        tabs = tabs.get("tabs", [])
    if not isinstance(tabs, list):
        raise EvalFailure("surf tab.list did not return a tab list")
    for tab in tabs:
        if str(tab.get("id")) == str(tab_id):
            url = str(tab.get("url") or "")
            if expect_url and normalize_url(url) != normalize_url(expect_url):
                raise EvalFailure(f"tab {tab_id} URL mismatch: expected {expect_url}, saw {url}")
            if "claude.ai" not in url:
                raise EvalFailure(f"tab {tab_id} is not a Claude tab: {url}")
            return tab
    raise EvalFailure(f"Claude tab {tab_id} not found in surf tab.list")


def submit_prompt(tab_id: str, prompt: str, commands: list[dict[str, Any]]) -> None:
    read = run_surf(["read", "--tab-id", tab_id], commands, timeout=60)
    textbox_ref = find_ref(read.stdout, r'textbox "Write your prompt to Claude" \[(e\d+)\]')
    if not textbox_ref:
        raise EvalFailure("Claude prompt textbox not found")
    run_surf(["click", textbox_ref, "--tab-id", tab_id], commands, timeout=60)
    run_surf(["type", prompt, "--ref", textbox_ref, "--tab-id", tab_id], commands, timeout=60)
    read_after = run_surf(["read", "--tab-id", tab_id], commands, timeout=60)
    send_ref = find_ref(read_after.stdout, r'button "Send message" \[(e\d+)\]')
    if send_ref:
        run_surf(["click", send_ref, "--tab-id", tab_id], commands, timeout=60)
    else:
        run_surf(["key", "Enter", "--tab-id", tab_id], commands, timeout=60)


def expose_upload_input(tab_id: str, commands: list[dict[str, Any]]) -> str:
    script = (
        "const input=document.querySelector('input[type=file][data-testid=file-upload],"
        "input[type=file][aria-label=\"Upload files\"]');"
        "if(!input) throw new Error('Claude file input not found');"
        "input.id='webclaude-sanity-upload-input';"
        "input.removeAttribute('aria-hidden');"
        "input.tabIndex=0;"
        "Object.assign(input.style,{position:'fixed',left:'20px',bottom:'20px',width:'240px',"
        "height:'44px',opacity:'1',zIndex:'2147483647',background:'white',color:'black'});"
        "return JSON.stringify({ok:true,id:input.id,type:input.type,multiple:input.multiple});"
    )
    run_surf(["js", script, "--tab-id", tab_id], commands, timeout=60)
    read = run_surf(["read", "--filter", "all", "--tab-id", tab_id], commands, timeout=60)
    upload_ref = find_ref(read.stdout, r'button "Upload files" \[(e\d+)\] type="file"')
    if not upload_ref:
        raise EvalFailure("Claude upload file input ref not found after expose step")
    return upload_ref


def wait_for_attachment(tab_id: str, filename: str, output_path: Path, commands: list[dict[str, Any]]) -> Path:
    deadline = time.time() + 60
    last_text = ""
    while time.time() < deadline:
        result = run_surf(["read", "--tab-id", tab_id], commands, timeout=60)
        last_text = result.stdout
        if filename in last_text:
            output_path.write_text(last_text, encoding="utf-8")
            return output_path
        time.sleep(2)
    output_path.write_text(last_text, encoding="utf-8")
    raise EvalFailure(f"uploaded attachment {filename!r} did not appear in Claude page text")


def wait_for_text(
    tab_id: str,
    marker: str,
    output_path: Path,
    commands: list[dict[str, Any]],
    *,
    timeout_seconds: int,
    stable_polls: int,
) -> Path:
    deadline = time.time() + timeout_seconds
    previous_hash = ""
    stable = 0
    last_text = ""
    while time.time() < deadline:
        result = run_surf(["text", "--tab-id", tab_id], commands, timeout=60)
        last_text = result.stdout
        output_path.write_text(last_text, encoding="utf-8")
        if marker in last_text and "Claude is responding" not in last_text:
            current_hash = hashlib.sha256(last_text.encode("utf-8")).hexdigest()
            if current_hash == previous_hash:
                stable += 1
            else:
                stable = 0
                previous_hash = current_hash
            if stable >= stable_polls:
                return output_path
        time.sleep(2)
    output_path.write_text(last_text, encoding="utf-8")
    raise EvalFailure(f"timed out waiting for marker {marker!r}")


def create_zip_bundle(run_dir: Path, markers: dict[str, str]) -> dict[str, Any]:
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    md_path = source_dir / "webclaude-sanity-proof.md"
    image_path = source_dir / "webclaude-sanity-proof-image.png"
    zip_path = run_dir / "webclaude-sanity-proof-bundle.zip"
    md_path.write_text(
        "\n".join(
            [
                "# WebClaude Sanity Proof",
                "",
                f"MARKDOWN_SENTINEL: {markers['md']}",
                "IMAGE_FILENAME_EXPECTED: webclaude-sanity-proof-image.png",
                f"ZIP_SENTINEL: {markers['zip']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    require_cmd(
        [
            "convert",
            "-size",
            "1100x440",
            "xc:white",
            "-font",
            "DejaVu-Sans-Mono-Bold",
            "-fill",
            "black",
            "-gravity",
            "center",
            "-pointsize",
            "42",
            "-annotate",
            "0",
            markers["image"],
            str(image_path),
        ],
        cwd=run_dir,
        timeout=60,
    )
    require_cmd(["zip", "-q", str(zip_path), md_path.name, image_path.name], cwd=source_dir, timeout=60)
    listing = require_cmd(["unzip", "-l", str(zip_path)], cwd=run_dir, timeout=60).stdout
    if md_path.name not in listing or image_path.name not in listing:
        raise EvalFailure("local zip listing is missing Markdown or PNG file")
    zip_sha = sha256_file(zip_path)
    (run_dir / "webclaude-sanity-proof-bundle.zip.sha256").write_text(f"{zip_sha}  {zip_path}\n", encoding="utf-8")
    (run_dir / "unzip-list.txt").write_text(listing, encoding="utf-8")
    return {
        "zip_path": zip_path,
        "zip_sha256": zip_sha,
        "files": [md_path.name, image_path.name],
        "artifacts": [md_path, image_path, zip_path, run_dir / "webclaude-sanity-proof-bundle.zip.sha256", run_dir / "unzip-list.txt"],
    }


def validate_zip_response(response_text: str, markers: dict[str, str], filenames: list[str]) -> list[str]:
    required = [markers["zip_response"], markers["md"], markers["image"], *filenames]
    return [item for item in required if item not in response_text]


def make_markers() -> dict[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "text": f"WEBCLAUDE_TEXT_SENTINEL_{stamp}",
        "zip": f"WEBCLAUDE_ZIP_SENTINEL_{stamp}",
        "md": f"WEBCLAUDE_MD_SENTINEL_{stamp}",
        "image": f"WEBCLAUDE_IMAGE_SENTINEL_{stamp}",
        "zip_response": f"WEBCLAUDE_ZIP_UPLOAD_RESPONSE_{stamp}",
    }


def run_surf(args: list[str], commands: list[dict[str, Any]], *, timeout: int) -> CmdResult:
    result = run_cmd([str(SURF_RUN), *args], cwd=SURF_RUN.parent, timeout=timeout)
    commands.append(result.summary())
    if result.returncode != 0:
        raise EvalFailure(f"surf {' '.join(args[:2])} failed: {result.stderr or result.stdout}")
    return result


def run_cmd(command: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    started = time.time()
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return CmdResult(command, proc.returncode, proc.stdout, proc.stderr, time.time() - started)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CmdResult(command, -2, stdout, stderr, time.time() - started, timed_out=True)


def require_cmd(command: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    result = run_cmd(command, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        raise EvalFailure(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr or result.stdout}")
    return result


def parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise EvalFailure("empty JSON output")
    start_candidates = [idx for idx in (stripped.find("{"), stripped.find("[")) if idx >= 0]
    start = min(start_candidates) if start_candidates else 0
    try:
        return json.loads(stripped[start:])
    except json.JSONDecodeError as exc:
        raise EvalFailure(f"invalid JSON output: {exc}") from exc


def find_ref(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excerpt(text: str, limit: int = 500) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def write_reports(run_dir: Path, result: dict[str, Any]) -> None:
    (run_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# WebClaude Sanity Eval",
        "",
        f"- schema: `{result['schema']}`",
        f"- status: `{result['status']}`",
        f"- mocked: `{str(result['mocked']).lower()}`",
        f"- live: `{str(result['live']).lower()}`",
        f"- tab_id: `{result.get('tab_id') or ''}`",
        f"- expect_url: `{result.get('expect_url') or ''}`",
        "",
        "## Cases",
    ]
    for case in result.get("cases", []):
        lines.append(f"- `{case['name']}`: `{case['status']}` - {case.get('detail', '')}")
    if result.get("failures"):
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in result["failures"])
    if result.get("artifacts"):
        lines.extend(["", "## Artifacts"])
        lines.extend(f"- `{artifact}`" for artifact in result["artifacts"])
    lines.extend(["", "## Claims", "", "Proves:"])
    lines.extend(f"- {item}" for item in result["claims"]["proves"])
    lines.extend(["", "Does not prove:"])
    lines.extend(f"- {item}" for item in result["claims"]["does_not_prove"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app()
