"""Opt-in live WebKimi sanity evals for the /ask skill directory.

This runner exercises the current WebKimi path used by /ask:
browser-oracle binding, Surf tab identity, kimi.submit text round trips, and
attachment attempts through kimi.submit --attach-file.

It is intentionally not a default unit test. Live mode depends on an
authenticated Kimi tab and records failing attachment semantics instead of
treating a sentinel-only transport receipt as file-intake proof.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
DEFAULT_OUTPUT_ROOT = ASK_ROOT / ".ask_artifacts" / "webkimi-sanity"
DEFAULT_PROJECT = "webkimi"
DEFAULT_EXPECT_URL = "https://www.kimi.ai/"
SCHEMA = "ask.webkimi_sanity_eval.v1"

app = typer.Typer(add_completion=False, help="Run opt-in WebKimi sanity evals.")


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
    tab_id: str = typer.Option("", "--tab-id", help="Explicit Kimi Chrome tab id. Overrides browser-oracle resolve."),
    expect_url: str = typer.Option(DEFAULT_EXPECT_URL, "--expect-url", help="Expected Kimi conversation URL."),
    allow_live: bool = typer.Option(False, "--allow-live", help="Run live Kimi browser checks."),
    plan_only: bool = typer.Option(False, "--plan-only", help="Write an eval plan without touching Kimi."),
    timeout_seconds: int = typer.Option(240, "--timeout", help="Per-response wait timeout."),
    stable_polls: int = typer.Option(2, "--stable-polls", help="Stable polls required after Kimi emits the sentinel."),
) -> None:
    if not allow_live and not plan_only:
        typer.echo(
            "Refusing to run live WebKimi checks without --allow-live. "
            "Use --plan-only to write the eval plan without touching Kimi.",
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
        plan_case("browser_oracle_binding", "Resolve/verify the webkimi browser-oracle binding."),
        plan_case("surf_tab_identity", "Confirm Surf sees the expected Kimi tab id and URL."),
        plan_case("text_roundtrip_no_activate", "Use surf kimi.submit --no-activate for a unique text sentinel."),
        plan_case("markdown_attachment_roundtrip", "Attach Markdown with a hidden sentinel and require Kimi to report it."),
        plan_case("image_attachment_roundtrip", "Attach PNG with visible hidden sentinel text and require Kimi to report it."),
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
        failures=["plan-only: live Kimi checks were not executed"],
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
    active_tab_id = tab_id.strip()
    url = expect_url.strip()
    markers = make_markers()

    def record(name: str, status: str, detail: str, **extra: Any) -> None:
        case = {"name": name, "status": status, "detail": detail, **extra}
        cases.append(case)
        if status != "pass":
            failures.append(f"{name}: {detail}")

    try:
        if active_tab_id:
            verified = verify_browser_oracle(project, commands)
            record("browser_oracle_binding", "pass", "Verified configured webkimi binding.", verified=verified)
        else:
            resolved = resolve_browser_oracle(project, commands)
            active_tab_id = str(resolved.get("tab_id") or "")
            url = str(resolved.get("conversation_url") or url)
            if not active_tab_id:
                raise EvalFailure("browser-oracle resolve returned no tab_id")
            record("browser_oracle_binding", "pass", "Resolved webkimi binding.", resolved=resolved)

        tab = assert_surf_tab_identity(active_tab_id, url, commands)
        record("surf_tab_identity", "pass", "Surf tab.list matched requested Kimi tab and URL.", tab=tab)
    except Exception as exc:
        failures.append(str(exc))
        return finish_result(run_dir, project, active_tab_id, url, cases, artifacts, failures, commands, markers)

    try:
        response_path, meta = run_kimi_submit(
            run_dir=run_dir,
            case_name="text_roundtrip_no_activate",
            tab_id=active_tab_id,
            prompt=f"Reply with exactly this token and no extra prose: {markers['text']}",
            commands=commands,
            timeout_seconds=timeout_seconds,
            stable_polls=stable_polls,
        )
        artifacts.extend(str(path) for path in sibling_artifacts(response_path))
        response_text = response_path.read_text(encoding="utf-8")
        missing = validate_submit_response(response_text, meta, [markers["text"]])
        if missing:
            record("text_roundtrip_no_activate", "fail", "Kimi text response missing expected markers.", missing=missing, meta=meta)
        else:
            record("text_roundtrip_no_activate", "pass", "Kimi returned the text sentinel through --no-activate.", meta=meta)
    except Exception as exc:
        record("text_roundtrip_no_activate", "fail", str(exc))

    try:
        md_path = create_markdown_attachment(run_dir, markers)
        artifacts.append(str(md_path))
        response_path, meta = run_kimi_submit(
            run_dir=run_dir,
            case_name="markdown_attachment_roundtrip",
            tab_id=active_tab_id,
            prompt=(
                "Inspect the attached Markdown file. Reply with exactly two lines: "
                f"the first line must be {markers['md_response']} and the second line "
                "must be the exact Attachment sentinel value from the attached file."
            ),
            commands=commands,
            timeout_seconds=timeout_seconds,
            stable_polls=stable_polls,
            attach_file=md_path,
        )
        artifacts.extend(str(path) for path in sibling_artifacts(response_path))
        response_text = response_path.read_text(encoding="utf-8")
        missing = validate_submit_response(response_text, meta, [markers["md_response"], markers["md_only"]])
        if missing:
            record(
                "markdown_attachment_roundtrip",
                "fail",
                "Kimi did not report the Markdown-only attachment sentinel.",
                missing=missing,
                response_excerpt=excerpt(response_text),
                meta=meta,
            )
        else:
            record("markdown_attachment_roundtrip", "pass", "Kimi reported the Markdown-only attachment sentinel.", meta=meta)
    except Exception as exc:
        record("markdown_attachment_roundtrip", "fail", str(exc))

    try:
        image_path = create_image_attachment(run_dir, markers)
        artifacts.append(str(image_path))
        response_path, meta = run_kimi_submit(
            run_dir=run_dir,
            case_name="image_attachment_roundtrip",
            tab_id=active_tab_id,
            prompt=(
                "Inspect the attached image. Reply with exactly two lines: "
                f"the first line must be {markers['image_response']} and the second line "
                "must be the exact sentinel text visible in the image."
            ),
            commands=commands,
            timeout_seconds=timeout_seconds,
            stable_polls=stable_polls,
            attach_file=image_path,
        )
        artifacts.extend(str(path) for path in sibling_artifacts(response_path))
        response_text = response_path.read_text(encoding="utf-8")
        missing = validate_submit_response(response_text, meta, [markers["image_response"], markers["image_only"]])
        if missing:
            record(
                "image_attachment_roundtrip",
                "fail",
                "Kimi did not report the image-only attachment sentinel.",
                missing=missing,
                response_excerpt=excerpt(response_text),
                meta=meta,
            )
        else:
            record("image_attachment_roundtrip", "pass", "Kimi reported the image-only attachment sentinel.", meta=meta)
    except Exception as exc:
        record("image_attachment_roundtrip", "fail", str(exc))

    try:
        screenshot = run_dir / "final-screenshot.png"
        run_surf(["snap", "--tab-id", active_tab_id, "--output", str(screenshot)], commands, timeout=60)
        artifacts.append(str(screenshot))
        record("visual_receipt", "pass", "Captured same-tab final screenshot.", screenshot=str(screenshot))
    except Exception as exc:
        record("visual_receipt", "fail", str(exc))

    return finish_result(run_dir, project, active_tab_id, url, cases, artifacts, failures, commands, markers)


def finish_result(
    run_dir: Path,
    project: str,
    tab_id: str,
    expect_url: str,
    cases: list[dict[str, Any]],
    artifacts: list[str],
    failures: list[str],
    commands: list[dict[str, Any]],
    markers: dict[str, str],
) -> dict[str, Any]:
    result = base_result(
        run_dir=run_dir,
        project=project,
        tab_id=tab_id,
        expect_url=expect_url,
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
                "browser-oracle can resolve or verify a webkimi binding",
                "Surf can target the bound Kimi tab by id",
                "surf kimi.submit --no-activate can submit text and recover a clean sentinel response when the text gate passes",
                "Kimi attachment intake only when file-only or image-only sentinels appear in the clean response",
            ],
            "does_not_prove": [
                "multi-round reviewer orchestration through /ask",
                "large bundle, zip bundle, or production review behavior",
                "attachment support when the attachment gates fail",
                "Kimi model quality beyond the sentinel fixtures",
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
        [str(BROWSER_ORACLE_RUN), "resolve", "--backend", "webkimi", "--project", project, "--json"],
        cwd=BROWSER_ORACLE_RUN.parent,
        timeout=60,
    )
    commands.append(result.summary())
    if result.returncode != 0:
        raise EvalFailure(f"browser-oracle resolve failed: {result.stderr or result.stdout}")
    return parse_json(result.stdout)


def verify_browser_oracle(project: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    result = run_cmd(
        [str(BROWSER_ORACLE_RUN), "verify", project, "--backend", "webkimi", "--json"],
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
            if "kimi.ai" not in url and "kimi.com" not in url:
                raise EvalFailure(f"tab {tab_id} is not a Kimi tab: {url}")
            return tab
    raise EvalFailure(f"Kimi tab {tab_id} not found in surf tab.list")


def run_kimi_submit(
    *,
    run_dir: Path,
    case_name: str,
    tab_id: str,
    prompt: str,
    commands: list[dict[str, Any]],
    timeout_seconds: int,
    stable_polls: int,
    attach_file: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    case_dir = run_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    input_path = case_dir / "request.md"
    output_path = case_dir / "response.md"
    raw_path = case_dir / "response.raw.md"
    meta_path = case_dir / "response.meta.json"
    submitted_path = case_dir / "response.submitted.md"
    input_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    args = [
        "kimi.submit",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--raw-output",
        str(raw_path),
        "--meta-output",
        str(meta_path),
        "--submitted-output",
        str(submitted_path),
        "--tab-id",
        tab_id,
        "--no-activate",
        "--timeout",
        str(timeout_seconds),
        "--stable-polls",
        str(stable_polls),
    ]
    if attach_file:
        args.extend(["--attach-file", str(attach_file)])
    result = run_surf(args, commands, timeout=timeout_seconds + 90)
    meta = parse_json(meta_path.read_text(encoding="utf-8"))
    if result.returncode != 0 or meta.get("status") != "completed":
        raise EvalFailure(f"kimi.submit did not complete for {case_name}: {meta}")
    return output_path, meta


def validate_submit_response(response_text: str, meta: dict[str, Any], required_markers: list[str]) -> list[str]:
    missing = [marker for marker in required_markers if marker not in response_text]
    if meta.get("status") != "completed":
        missing.append("meta.status=completed")
    if meta.get("clean_contains_sentinel"):
        missing.append("clean output must not contain terminal sentinel")
    if meta.get("clean_contamination_markers"):
        missing.append("clean output must not contain contamination markers")
    if meta.get("controlled_tab_id_mismatch"):
        missing.append("controlled_tab_id must match requested_tab_id")
    if meta.get("activation_violation"):
        missing.append("no-activate must not activate the tab")
    return missing


def create_markdown_attachment(run_dir: Path, markers: dict[str, str]) -> Path:
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    md_path = source_dir / "webkimi-sanity-proof.md"
    md_path.write_text(
        "\n".join(
            [
                "# WebKimi Sanity Proof",
                "",
                f"Attachment sentinel: {markers['md_only']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return md_path


def create_image_attachment(run_dir: Path, markers: dict[str, str]) -> Path:
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    image_path = source_dir / "webkimi-sanity-proof.png"
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        raise EvalFailure("ImageMagick magick/convert not found for PNG fixture generation")
    require_cmd(
        [
            magick,
            "-size",
            "1200x600",
            "xc:white",
            "-gravity",
            "center",
            "-fill",
            "black",
            "-font",
            "DejaVu-Sans",
            "-pointsize",
            "42",
            "-annotate",
            "0",
            markers["image_only"],
            str(image_path),
        ],
        cwd=run_dir,
        timeout=60,
    )
    return image_path


def sibling_artifacts(response_path: Path) -> list[Path]:
    case_dir = response_path.parent
    return [
        case_dir / "request.md",
        case_dir / "response.md",
        case_dir / "response.raw.md",
        case_dir / "response.meta.json",
        case_dir / "response.submitted.md",
    ]


def make_markers() -> dict[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "text": f"WEBKIMI_TEXT_SENTINEL_{stamp}",
        "md_response": f"WEBKIMI_MD_ATTACH_RESPONSE_{stamp}",
        "md_only": f"WEBKIMI_MD_ONLY_SENTINEL_{stamp}",
        "image_response": f"WEBKIMI_IMAGE_ATTACH_RESPONSE_{stamp}",
        "image_only": f"WEBKIMI_IMAGE_ONLY_SENTINEL_{stamp}",
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


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def excerpt(text: str, limit: int = 500) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "..."


def write_reports(run_dir: Path, result: dict[str, Any]) -> None:
    (run_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# WebKimi Sanity Eval",
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
