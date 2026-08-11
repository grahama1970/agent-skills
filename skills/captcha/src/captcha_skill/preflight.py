"""Surf, literal-loopback target/model, and sterile ReCAP preflights.

Preflights validate producer-owned Surf capabilities, a bounded synthetic
challenge endpoint, and an OpenAI-compatible local model catalog. They reject
redirects, ambient proxies, oversized responses, missing credentials, stale
Surf builds, and source-identity drift before ReCAP starts.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .dotenv_helper import load_skill_dotenv
from .constants import (
    CAPTCHA_ENDPOINTS,
    LOCAL_MODEL_API_KEY_ENV,
    RECAP_PASSTHROUGH_ENV_KEYS,
)
from .errors import CaptchaSkillError, ErrorCode
from .layout import surf_run_path
from .models import (
    AuthorizationManifest,
    CaptchaType,
    ModelEndpointProof,
    SeamValidation,
    SurfCapabilities,
    SurfTargetProof,
    TargetProof,
    TestMode,
)
from .policy import sha256_bytes, sha256_file, utc_now

load_skill_dotenv()


def _json_values_from_text(text: str) -> Iterator[Any]:
    """Yield complete JSON values embedded in otherwise noisy command output."""

    stripped = text.strip()
    if not stripped:
        return
    try:
        yield json.loads(stripped)
        return
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        next_object = text.find("{", index)
        next_array = text.find("[", index)
        starts = [item for item in (next_object, next_array) if item >= 0]
        if not starts:
            return
        candidate = min(starts)
        try:
            value, end = decoder.raw_decode(text, candidate)
        except json.JSONDecodeError:
            index = candidate + 1
            continue
        yield value
        index = max(end, candidate + 1)


def _parse_json_object(stdout: str) -> dict[str, Any]:
    """Return the final JSON object from a bounded Surf command response."""

    objects = [value for value in _json_values_from_text(stdout) if isinstance(value, dict)]
    if not objects:
        raise CaptchaSkillError(
            ErrorCode.SURF_CONTRACT_INVALID,
            "Surf output did not contain a JSON object",
            {"stdout_tail": stdout[-4000:]},
        )
    return objects[-1]


def _run_json_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    operation: str,
) -> dict[str, Any]:
    """Run one Surf command without a shell and require structured output."""

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command could not be started",
            {"argv": argv, "error": str(exc)},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command timed out",
            {"argv": argv, "timeout_seconds": timeout_seconds},
        ) from exc
    if result.returncode != 0:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            f"Surf {operation} command failed",
            {
                "argv": argv,
                "exit_code": result.returncode,
                "stderr": result.stderr[-4000:],
                "stdout_tail": result.stdout[-2000:],
            },
        )
    return _parse_json_object(result.stdout)


def collect_surf_capabilities() -> SurfCapabilities:
    """Run Surf's producer-owned capability command and validate its contract."""

    surf = surf_run_path()
    if not surf.is_file() or not os.access(surf, os.X_OK):
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf run.sh is missing or not executable",
            {"path": str(surf)},
        )
    value = _run_json_command(
        [str(surf), "capabilities", "--json"],
        cwd=surf.parent,
        timeout_seconds=30,
        operation="capabilities",
    )
    try:
        capabilities = SurfCapabilities.model_validate(value)
    except ValidationError as exc:
        raise CaptchaSkillError(
            ErrorCode.SURF_CONTRACT_INVALID,
            "Surf capabilities failed the captcha-side typed seam",
            {"errors": exc.errors(include_url=False)},
        ) from exc

    engine = capabilities.engine
    if not engine.dist_present or not engine.lock_present:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf vendored engine is incomplete",
            {
                "dist_present": engine.dist_present,
                "lock_present": engine.lock_present,
            },
        )
    if engine.dist_fresh is not True:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf vendored distribution is stale or freshness is unproven",
            {"dist_fresh": engine.dist_fresh},
        )
    if engine.content_identity_matches is not True:
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf vendored content identity does not match its lock",
            {"content_identity_matches": engine.content_identity_matches},
        )
    skill_digest = capabilities.skill.skill_md_sha256
    if skill_digest is None or len(skill_digest) != 64:
        raise CaptchaSkillError(
            ErrorCode.SURF_CONTRACT_INVALID,
            "Surf capability receipt lacks a valid SKILL.md digest",
        )
    if not (
        capabilities.transport.extension_socket_present
        or capabilities.transport.cdp_fallback
    ):
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf exposes neither extension transport nor CDP fallback",
        )
    return capabilities


def _target_probe_type(manifest: AuthorizationManifest) -> CaptchaType:
    if manifest.test_mode is TestMode.CUSTOM and manifest.captcha_name is not None:
        return manifest.captcha_name
    return CaptchaType.TEXT



def _walk_json(value: Any) -> Iterator[Any]:
    """Depth-first traversal for producer-owned, extra-field JSON payloads."""

    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("{", "[")):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                return
            yield from _walk_json(parsed)


def _extract_surf_tab_id(value: dict[str, Any]) -> int:
    """Extract Surf's controlled tab identifier without accepting a generic id."""

    for item in _walk_json(value):
        if not isinstance(item, dict):
            continue
        for key in ("tabId", "tab_id", "tabID", "controlled_tab_id"):
            candidate = item.get(key)
            if isinstance(candidate, int) and candidate > 0:
                return candidate
            if isinstance(candidate, str) and candidate.isdigit() and int(candidate) > 0:
                return int(candidate)
    raise CaptchaSkillError(
        ErrorCode.SURF_CONTRACT_INVALID,
        "Surf window.new response did not identify the created tab",
        {"response": value},
    )


def _extract_surf_target_record(value: dict[str, Any]) -> tuple[str, str]:
    """Extract the exact browser URL and challenge identifier from Surf JS output."""

    for item in _walk_json(value):
        if not isinstance(item, dict):
            continue
        final_url = item.get("final_url")
        challenge_id = item.get("challenge_id")
        if isinstance(final_url, str) and isinstance(challenge_id, str):
            return final_url, challenge_id
    raise CaptchaSkillError(
        ErrorCode.SURF_CONTRACT_INVALID,
        "Surf JS response lacked final_url and challenge_id",
        {"response": value},
    )


def _assert_same_local_challenge(*, expected_url: str, final_url: str) -> None:
    """Reject redirects, query injection, or path/origin drift after navigation."""

    try:
        expected = urlsplit(expected_url)
        actual = urlsplit(final_url)
        expected_port = expected.port
        actual_port = actual.port
    except ValueError as exc:
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "Surf returned a malformed final URL",
            {"expected_url": expected_url, "final_url": final_url},
        ) from exc
    if (
        actual.scheme != expected.scheme
        or actual.hostname != expected.hostname
        or actual_port != expected_port
        or actual.path.rstrip("/") != expected.path.rstrip("/")
        or actual.query
        or actual.fragment
        or actual.username is not None
        or actual.password is not None
    ):
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "Surf navigation did not remain on the exact authorized local challenge",
            {"expected_url": expected_url, "final_url": final_url},
        )


def preflight_surf_target(
    manifest: AuthorizationManifest,
    *,
    screenshot_path: Path,
) -> SurfTargetProof:
    """Use Surf to prove isolated navigation to the exact synthetic challenge.

    Surf owns browser transport, final-URL observation, challenge-identity
    observation, screenshot creation, and tab cleanup. ReCAP remains the owner of
    the subsequent model-driven Playwright benchmark.
    """

    surf = surf_run_path()
    if not surf.is_file() or not os.access(surf, os.X_OK):
        raise CaptchaSkillError(
            ErrorCode.SURF_UNAVAILABLE,
            "Surf run.sh is missing or not executable",
            {"path": str(surf)},
        )

    captcha_type = _target_probe_type(manifest)
    challenge_url = (
        f"{str(manifest.target_url).rstrip('/')}"
        f"{CAPTCHA_ENDPOINTS[captcha_type.value]}"
    )
    screenshot = screenshot_path.expanduser()
    if screenshot.name != "surf-target-preflight.png":
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "Surf preflight screenshot must use the fixed evidence filename",
            {"path": str(screenshot)},
        )
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    if screenshot.is_symlink():
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            "Surf preflight screenshot path must not be a symlink",
            {"path": str(screenshot)},
        )
    if screenshot.exists():
        try:
            screenshot.unlink()
        except OSError as exc:
            raise CaptchaSkillError(
                ErrorCode.IO_ERROR,
                "could not clear prior Surf preflight screenshot",
                {"path": str(screenshot), "error": str(exc)},
            ) from exc

    tab_id: int | None = None
    primary_error: CaptchaSkillError | None = None
    proof: SurfTargetProof | None = None
    try:
        opened = _run_json_command(
            [str(surf), "window.new", challenge_url, "--json"],
            cwd=surf.parent,
            timeout_seconds=30,
            operation="window.new",
        )
        tab_id = _extract_surf_tab_id(opened)
        _run_json_command(
            [
                str(surf),
                "emulate.viewport",
                "--width",
                "1000",
                "--height",
                "1000",
                "--tab-id",
                str(tab_id),
                "--json",
            ],
            cwd=surf.parent,
            timeout_seconds=20,
            operation="emulate.viewport",
        )
        observation_source = """
(() => {
  const input = document.querySelector('input[name="challenge_id"]');
  const dataNode = document.querySelector('[data-challenge-id]');
  const challengeId =
    (input && input.value) ||
    (dataNode && dataNode.getAttribute('data-challenge-id')) ||
    window.challengeId ||
    window.challenge_id ||
    '';
  return {
    final_url: String(window.location.href),
    challenge_id: String(challengeId || '')
  };
})()
""".strip()
        observed = _run_json_command(
            [
                str(surf),
                "js",
                observation_source,
                "--tab-id",
                str(tab_id),
                "--json",
            ],
            cwd=surf.parent,
            timeout_seconds=30,
            operation="js target observation",
        )
        final_url, challenge_id = _extract_surf_target_record(observed)
        _assert_same_local_challenge(
            expected_url=challenge_url,
            final_url=final_url,
        )
        if not challenge_id.strip():
            raise CaptchaSkillError(
                ErrorCode.TARGET_UNAVAILABLE,
                "Surf could not observe a ReCAP challenge identifier",
                {"challenge_url": challenge_url, "final_url": final_url},
            )

        _run_json_command(
            [
                str(surf),
                "screenshot",
                "--output",
                str(screenshot),
                "--full",
                "--tab-id",
                str(tab_id),
                "--json",
            ],
            cwd=surf.parent,
            timeout_seconds=45,
            operation="screenshot",
        )
        try:
            screenshot_bytes = screenshot.read_bytes()
        except OSError as exc:
            raise CaptchaSkillError(
                ErrorCode.IO_ERROR,
                "Surf screenshot evidence could not be read",
                {"path": str(screenshot), "error": str(exc)},
            ) from exc
        if (
            len(screenshot_bytes) < 9
            or len(screenshot_bytes) > 20 * 1024 * 1024
            or not screenshot_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            raise CaptchaSkillError(
                ErrorCode.SURF_CONTRACT_INVALID,
                "Surf screenshot evidence is missing, oversized, or not PNG",
                {"path": str(screenshot), "size_bytes": len(screenshot_bytes)},
            )

        proof = SurfTargetProof(
            schema_version="captcha.surf_target_preflight.v1",
            checked_at=utc_now(),
            challenge_url=challenge_url,
            final_url=final_url,
            tab_id=tab_id,
            challenge_id_present=True,
            screenshot_sha256=sha256_file(screenshot),
            seam_validation=SeamValidation(kind="captcha.surf_local_target"),
        )
    except CaptchaSkillError as exc:
        primary_error = exc
    finally:
        if tab_id is not None:
            try:
                _run_json_command(
                    [str(surf), "tab.close", str(tab_id), "--json"],
                    cwd=surf.parent,
                    timeout_seconds=20,
                    operation="tab.close",
                )
            except CaptchaSkillError as close_error:
                if primary_error is None:
                    primary_error = close_error

    if primary_error is not None:
        raise primary_error
    if proof is None:  # pragma: no cover - defensive invariant
        raise CaptchaSkillError(
            ErrorCode.SURF_CONTRACT_INVALID,
            "Surf target preflight ended without proof or a typed failure",
        )
    return proof


def preflight_target(manifest: AuthorizationManifest) -> TargetProof:
    """Prove the literal-loopback target serves an authorized ReCAP challenge."""

    captcha_type = _target_probe_type(manifest)
    base = str(manifest.target_url).rstrip("/")
    url = f"{base}{CAPTCHA_ENDPOINTS[captcha_type.value]}"
    timeout = httpx.Timeout(connect=3.0, read=7.0, write=3.0, pool=3.0)
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(url, headers={"Accept": "text/html"})
    except httpx.HTTPError as exc:
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "local ReCAP target preflight failed",
            {"url": url, "error": str(exc)},
        ) from exc
    if response.status_code != 200:
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "local ReCAP target did not return HTTP 200",
            {"url": url, "status_code": response.status_code},
        )
    content_type = response.headers.get("content-type")
    if content_type is None or not content_type.lower().startswith("text/html"):
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "local ReCAP target did not return HTML",
            {"url": url, "content_type": content_type},
        )
    body = response.content
    if len(body) > 1_048_576:
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "local challenge page exceeded the 1 MiB preflight bound",
            {"url": url, "body_bytes": len(body)},
        )
    lowered = body.lower()
    marker_present = b"challenge_id" in lowered or b"data-challenge-id" in lowered
    if not marker_present:
        raise CaptchaSkillError(
            ErrorCode.TARGET_UNAVAILABLE,
            "loopback service does not expose a ReCAP challenge identifier marker",
            {"url": url, "body_sha256": sha256_bytes(body)},
        )
    return TargetProof(
        schema_version="captcha.target_preflight.v1",
        checked_at=utc_now(),
        url=url,
        status_code=response.status_code,
        content_type=content_type,
        body_sha256=sha256_bytes(body),
        challenge_marker_present=True,
        seam_validation=SeamValidation(kind="captcha.local_target"),
    )


def _local_model_api_key() -> str:
    value = os.environ.get(LOCAL_MODEL_API_KEY_ENV, "").strip()
    if not value:
        raise CaptchaSkillError(
            ErrorCode.MODEL_CREDENTIAL_MISSING,
            f"{LOCAL_MODEL_API_KEY_ENV} is required for the loopback model endpoint",
        )
    return value


def preflight_model_endpoint(manifest: AuthorizationManifest) -> ModelEndpointProof:
    """Verify the loopback OpenAI-compatible endpoint advertises the requested model."""

    url = f"{str(manifest.model_base_url).rstrip('/')}/models"
    api_key = _local_model_api_key()
    timeout = httpx.Timeout(connect=3.0, read=7.0, write=3.0, pool=3.0)
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
    except httpx.HTTPError as exc:
        raise CaptchaSkillError(
            ErrorCode.MODEL_ENDPOINT_UNAVAILABLE,
            "local model endpoint preflight failed",
            {"url": url, "error": str(exc)},
        ) from exc
    if response.status_code != 200:
        raise CaptchaSkillError(
            ErrorCode.MODEL_ENDPOINT_UNAVAILABLE,
            "local model endpoint did not return HTTP 200",
            {"url": url, "status_code": response.status_code},
        )
    body = response.content
    if len(body) > 1_048_576:
        raise CaptchaSkillError(
            ErrorCode.MODEL_ENDPOINT_UNAVAILABLE,
            "local model catalog exceeded the 1 MiB preflight bound",
            {"url": url, "body_bytes": len(body)},
        )
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise CaptchaSkillError(
            ErrorCode.MODEL_ENDPOINT_UNAVAILABLE,
            "local model endpoint returned invalid JSON",
            {"url": url},
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CaptchaSkillError(
            ErrorCode.MODEL_ENDPOINT_UNAVAILABLE,
            "local model endpoint did not return an OpenAI-compatible model list",
            {"url": url},
        )
    advertised = sorted(
        {
            item.get("id")
            for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    )
    if manifest.model_id not in advertised:
        raise CaptchaSkillError(
            ErrorCode.MODEL_ID_MISMATCH,
            "authorized ReCAP model ID is not advertised by the loopback endpoint",
            {
                "url": url,
                "requested_model_id": manifest.model_id,
                "advertised_model_ids": advertised,
            },
        )
    return ModelEndpointProof(
        schema_version="captcha.model_endpoint_preflight.v1",
        checked_at=utc_now(),
        url=url,
        requested_model_id=manifest.model_id,
        advertised_model_ids=advertised,
        response_sha256=sha256_bytes(body),
        seam_validation=SeamValidation(kind="captcha.local_model_endpoint"),
    )


def build_recap_environment(
    manifest: AuthorizationManifest,
    *,
    recap_runs_root: Path,
) -> dict[str, str]:
    """Build a sterile environment for the pinned ReCAP subprocess."""

    env = {
        key: os.environ[key]
        for key in RECAP_PASSTHROUGH_ENV_KEYS
        if key in os.environ
    }
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "OPENAI_API_KEY": _local_model_api_key(),
            "OPENAI_BASE_URL": str(manifest.model_base_url),
            "OPENAI_MODEL": manifest.model_id,
            "DYNAMIC_PROVIDER_URL": str(manifest.target_url).rstrip("/"),
            "RUNS_DIR": str(recap_runs_root),
            "MAX_CALLS": str(manifest.max_calls),
            "DYNAMIC_MAX_CALLS_DEFAULT": str(manifest.max_calls),
            "DYNAMIC_MAX_CALLS_IMAGE_GRID": str(manifest.max_calls),
            "DYNAMIC_MAX_CALLS_PAGED": str(manifest.max_calls),
            "BROWSER_HEADLESS": "true",
            "BROWSER_SLOW_MO": "0",
            "BROWSER_VIEWPORT_WIDTH": "1200",
            "BROWSER_VIEWPORT_HEIGHT": "800",
            "MODEL_MAX_COMPLETION_TOKENS": "1024",
            "MODEL_TEMPERATURE": "0",
            "MODEL_TOP_P": "0.8",
            "ACTION_DELAY_MS": "100",
            "POST_ACTION_DELAY_MS": "250",
            "TEST_SEED": str(manifest.seed),
            "NO_PROXY": "127.0.0.1,::1",
            "no_proxy": "127.0.0.1,::1",
        }
    )
    return env
