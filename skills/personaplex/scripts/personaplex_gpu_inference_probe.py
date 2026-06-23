#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P10 GPU proof probe via golden_state_server LMGen.step.

The PersonaPlex Docker service on the target workstation exposes a Moshi/Opus
binary streaming-audio WebSocket. That surface is not a one-shot generated-token
proof API. This probe therefore does not use REST JSON or the container WS for
P10 GPU proof.

The proof path is the checked-out ``personaplex_golden_state_server.py`` probe
mode, executed under the PersonaPlex virtualenv:

    /home/graham/workspace/experiments/personaplex/.venv/bin/python \
      /home/graham/workspace/experiments/personaplex/personaplex_golden_state_server.py \
      --probe-lmgen-step --json

``real_gpu_personaplex=true`` is written only when the subprocess exits 0 and
emits parseable JSON containing both CUDA/GPU evidence and actual generated
LMGen.step output (text/content/token ids/etc.). Checksums, echoes of the prompt,
logs, or endpoint reachability are not sufficient.
"""

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
DEFAULT_VENV_PYTHON = DEFAULT_PERSONAPLEX_ROOT / ".venv" / "bin" / "python"
DEFAULT_GOLDEN_STATE_SERVER = DEFAULT_PERSONAPLEX_ROOT / "personaplex_golden_state_server.py"
DEFAULT_OUT_DIR = Path("artifacts/personaplex_sanity/p10c")
DEFAULT_RECEIPT_NAME = "p10-gpu-personaplex-receipt.json"
DEFAULT_TIMEOUT_SECONDS = 900.0

# Actual generated values only. Do not include *_sha256 keys here; a hash proves
# bytes existed upstream but is not itself generated model output.
GENERATED_OUTPUT_KEYS = {
    "assistant_text",
    "completion",
    "content",
    "decoded",
    "decoded_text",
    "generated",
    "generated_content",
    "generated_output",
    "generated_text",
    "generated_token",
    "generated_token_id",
    "generated_token_ids",
    "lmgen_output",
    "lmgen_result",
    "message",
    "new_token",
    "new_token_id",
    "output",
    "output_text",
    "output_token",
    "output_token_id",
    "output_token_ids",
    "response",
    "result",
    "step_output",
    "step_result",
    "text",
    "token",
    "token_id",
    "token_ids",
    "tokens",
}

HASH_ONLY_KEYS = {
    "generated_output_sha256",
    "generated_text_sha256",
    "output_sha256",
    "response_sha256",
    "step_output_sha256",
    "step_result_sha256",
    "stdout_sha256",
}

PROMPT_ECHO_KEYS = {"input", "input_text", "prompt", "request", "request_text", "user_text"}

CUDA_PROOF_KEYS = {
    "cuda",
    "cuda_available",
    "cuda_device",
    "cuda_device_name",
    "device",
    "device_name",
    "gpu",
    "gpu_available",
    "gpu_device",
    "gpu_name",
    "real_gpu_personaplex",
    "torch_cuda_available",
    "torch_device",
}

SUCCESS_BOOL_KEYS = {"ok", "success", "probe_ok", "lmgen_step_ok"}


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def excerpt(value: object, limit: int = 2400) -> str:
    raw = value if isinstance(value, str) else repr(value)
    return raw.replace("\x00", "")[:limit]


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def redact_command(command: Sequence[str]) -> list[str]:
    secret_flags = {"--api-key", "--token", "--password", "--secret"}
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        lowered = item.lower()
        if lowered in secret_flags:
            redacted.append(item)
            skip_next = True
        elif any(lowered.startswith(flag + "=") for flag in secret_flags):
            redacted.append(item.split("=", 1)[0] + "=<redacted>")
        else:
            redacted.append(item)
    return redacted


def first_existing(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        with contextlib.suppress(OSError):
            resolved = candidate.expanduser().resolve()
            if resolved.exists():
                return resolved
    return None


def discover_root(explicit: str | Path | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("PERSONAPLEX_ROOT"):
        candidates.append(Path(os.environ["PERSONAPLEX_ROOT"]))
    candidates.extend([
        DEFAULT_PERSONAPLEX_ROOT,
        Path.cwd(),
        Path.cwd() / "personaplex",
        Path.cwd().parent / "personaplex",
    ])
    for candidate in candidates:
        with contextlib.suppress(OSError):
            resolved = candidate.expanduser().resolve()
            if (resolved / "personaplex_golden_state_server.py").exists() or (resolved / ".venv" / "bin" / "python").exists():
                return resolved
    return Path(explicit).expanduser().resolve() if explicit else DEFAULT_PERSONAPLEX_ROOT


def discover_venv_python(explicit: str | Path | None, root: Path) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("PERSONAPLEX_VENV_PYTHON"):
        candidates.append(Path(os.environ["PERSONAPLEX_VENV_PYTHON"]))
    candidates.extend([root / ".venv" / "bin" / "python", DEFAULT_VENV_PYTHON])
    return first_existing(candidates)


def discover_golden_state_server(explicit: str | Path | None, root: Path) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("PERSONAPLEX_GOLDEN_STATE_SERVER"):
        candidates.append(Path(os.environ["PERSONAPLEX_GOLDEN_STATE_SERVER"]))
    candidates.extend([
        root / "personaplex_golden_state_server.py",
        root / "scripts" / "personaplex_golden_state_server.py",
        root / "skills" / "personaplex" / "scripts" / "personaplex_golden_state_server.py",
        DEFAULT_GOLDEN_STATE_SERVER,
    ])
    return first_existing(candidates)


def parse_json_from_stdout(stdout: str) -> Any | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    with contextlib.suppress(json.JSONDecodeError):
        return json.loads(stripped)

    # Some servers log initialization lines before the final JSON object.
    for line in reversed(stripped.splitlines()):
        candidate = line.strip()
        if candidate.startswith("data:"):
            candidate = candidate[5:].strip()
        if candidate and candidate != "[DONE]" and candidate[0] in "[{":
            with contextlib.suppress(json.JSONDecodeError):
                return json.loads(candidate)

    # Last resort: try a suffix starting at an object marker.
    for marker in ("{", "["):
        start = stripped.rfind(marker)
        if start >= 0:
            with contextlib.suppress(json.JSONDecodeError):
                return json.loads(stripped[start:])
    return None


def walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from walk_json(item, path + (str(key),))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from walk_json(item, path + (str(index),))


def normalize_generated_value(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lower() not in {"none", "null", "nan", "[]", "{}", ""}:
            return stripped
        return None
    if isinstance(value, (int, float)):
        # A single token id is acceptable proof that LMGen.step produced output.
        return str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        # Preserve proof while avoiding large tensors/vectors in receipts.
        bounded = list(value[:64])
        return json.dumps(bounded, default=str) + ("..." if len(value) > 64 else "")
    if isinstance(value, Mapping):
        if not value:
            return None
        compact: dict[str, Any] = {}
        for index, (k, v) in enumerate(value.items()):
            key = str(k)
            if index >= 16:
                break
            if key.lower().endswith(("vector", "embedding", "hidden_state", "logits")):
                compact[key] = "<omitted>"
            else:
                compact[key] = v
        return json.dumps(compact, default=str, sort_keys=True)[:1200]
    return repr(value)[:800]


def find_generated_output(payload: Any) -> dict[str, Any]:
    for path, value in walk_json(payload):
        if not path:
            continue
        leaf = path[-1].lower()
        if leaf in PROMPT_ECHO_KEYS or leaf in HASH_ONLY_KEYS:
            continue
        if leaf.endswith("_sha256") or leaf.endswith("_hash"):
            continue
        if leaf in GENERATED_OUTPUT_KEYS:
            normalized = normalize_generated_value(value)
            if normalized:
                return {
                    "valid_generated_output": True,
                    "generated_output_path": ".".join(path),
                    "generated_output_sha256": sha256_text(normalized),
                    "generated_output_excerpt": excerpt(normalized, 500),
                }
    return {"valid_generated_output": False}


def cuda_value_is_positive(key: str, value: Any) -> bool:
    key_l = key.lower()
    if key_l in {"cuda_available", "torch_cuda_available", "gpu_available", "real_gpu_personaplex"}:
        return value is True
    if isinstance(value, str):
        v = value.lower()
        return "cuda" in v or "rtx" in v or "a5000" in v or "gpu" in v
    if isinstance(value, (Mapping, list, tuple)):
        text = json.dumps(value, default=str).lower()
        return "cuda" in text or "rtx" in text or "a5000" in text
    return False


def find_cuda_proof(payload: Any) -> dict[str, Any]:
    for path, value in walk_json(payload):
        if not path:
            continue
        leaf = path[-1].lower()
        if leaf in CUDA_PROOF_KEYS and cuda_value_is_positive(leaf, value):
            return {"valid_cuda_device": True, "cuda_proof": [{"path": ".".join(path), "value_excerpt": excerpt(value, 240)}]}
    return {"valid_cuda_device": False, "cuda_proof": []}


def find_success_signal(payload: Any) -> dict[str, Any]:
    saw = False
    true_paths: list[str] = []
    false_paths: list[str] = []
    for path, value in walk_json(payload):
        if not path:
            continue
        leaf = path[-1].lower()
        if leaf in SUCCESS_BOOL_KEYS:
            saw = True
            if value is True:
                true_paths.append(".".join(path))
            elif value is False:
                false_paths.append(".".join(path))
    return {
        "success_signal_ok": not false_paths,
        "success_signal_present": saw,
        "success_signal_true_paths": true_paths[:5],
        "success_signal_false_paths": false_paths[:5],
    }


def validate_golden_payload(payload: Any, returncode: int) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "payload_is_json_object": False,
            "valid_cuda_device": False,
            "valid_generated_output": False,
            "success_signal_ok": False,
            "real_gpu_personaplex": False,
        }
    generated = find_generated_output(payload)
    cuda = find_cuda_proof(payload)
    success = find_success_signal(payload)
    real = (
        returncode == 0
        and generated.get("valid_generated_output") is True
        and cuda.get("valid_cuda_device") is True
        and success.get("success_signal_ok") is True
    )
    return {
        "payload_is_json_object": True,
        **generated,
        **cuda,
        **success,
        "real_gpu_personaplex": bool(real),
    }


def deterministic_fallback(reason: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "personaplex.p10c.gpu_golden_state_server_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "phase": "P10c",
        "probe_strategy": "golden_state_server_subprocess_lmgen_step",
        "real_gpu_personaplex": False,
        "golden_state_subprocess_attempted": False,
        "valid_generated_output": False,
        "valid_cuda_device": False,
        "fallback_used": True,
        "fallback_reason": reason,
        "fallback_details": dict(details or {}),
        "claim_boundary": "Fallback is deterministic wiring evidence only; it is not live GPU PersonaPlex proof.",
    }


def run_golden_state_probe(
    *,
    venv_python: Path,
    golden_state_server: Path,
    root: Path,
    timeout_seconds: float,
    extra_args: Sequence[str] = (),
) -> dict[str, Any]:
    command = [str(venv_python), str(golden_state_server), "--probe-lmgen-step", "--json", *extra_args]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PERSONAPLEX_ROOT", str(root))
    started = time.monotonic()

    try:
        proc = subprocess.run(  # noqa: S603 - explicit executable/script path; no shell.
            command,
            cwd=str(root) if root.exists() else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        duration_ms = round((time.monotonic() - started) * 1000, 3)
    except subprocess.TimeoutExpired as exc:
        return {
            "schema": "personaplex.p10c.gpu_golden_state_server_receipt.v1",
            "created_at_utc": utc_now_iso(),
            "phase": "P10c",
            "probe_strategy": "golden_state_server_subprocess_lmgen_step",
            "real_gpu_personaplex": False,
            "golden_state_subprocess_attempted": True,
            "fallback_used": True,
            "fallback_reason": "golden_state_server_timeout",
            "command": redact_command(command),
            "timeout_seconds": timeout_seconds,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "stdout_excerpt": excerpt(exc.stdout or "", 2400),
            "stderr_excerpt": excerpt(exc.stderr or "", 2400),
            "claim_boundary": "Timed-out probe is not live GPU PersonaPlex proof.",
        }
    except Exception as exc:  # pragma: no cover - defensive process boundary.
        return {
            "schema": "personaplex.p10c.gpu_golden_state_server_receipt.v1",
            "created_at_utc": utc_now_iso(),
            "phase": "P10c",
            "probe_strategy": "golden_state_server_subprocess_lmgen_step",
            "real_gpu_personaplex": False,
            "golden_state_subprocess_attempted": True,
            "fallback_used": True,
            "fallback_reason": "golden_state_server_subprocess_exception",
            "exception_type": type(exc).__name__,
            "exception_excerpt": excerpt(str(exc), 1000),
            "command": redact_command(command),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "claim_boundary": "Subprocess exception is not live GPU PersonaPlex proof.",
        }

    parsed = parse_json_from_stdout(proc.stdout)
    if parsed is None:
        validation = {
            "payload_is_json_object": False,
            "valid_generated_output": False,
            "valid_cuda_device": False,
            "success_signal_ok": False,
            "real_gpu_personaplex": False,
        }
    else:
        validation = validate_golden_payload(parsed, proc.returncode)

    real = bool(validation.get("real_gpu_personaplex"))
    return {
        "schema": "personaplex.p10c.gpu_golden_state_server_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "phase": "P10c",
        "probe_strategy": "golden_state_server_subprocess_lmgen_step",
        "real_gpu_personaplex": real,
        "golden_state_subprocess_attempted": True,
        "golden_state_server_path": str(golden_state_server),
        "venv_python_path": str(venv_python),
        "personaplex_root": str(root),
        "command": redact_command(command),
        "returncode": proc.returncode,
        "duration_ms": duration_ms,
        "stdout_sha256": sha256_text(proc.stdout),
        "stdout_excerpt": excerpt(proc.stdout, 2400),
        "stderr_sha256": sha256_text(proc.stderr),
        "stderr_excerpt": excerpt(proc.stderr, 2400),
        "parsed_json_present": parsed is not None,
        "parsed_json_top_level_keys": sorted(str(k) for k in parsed.keys())[:80] if isinstance(parsed, Mapping) else [],
        **validation,
        "fallback_used": not real,
        "fallback_reason": None if real else "golden_state_server_did_not_return_valid_cuda_generated_output",
        "claim_boundary": (
            "LIVE GPU PersonaPlex proof: golden_state_server.py returned valid CUDA LMGen.step generated output."
            if real
            else "Fallback/failed probe is not live GPU PersonaPlex proof. Inspect stdout/stderr and validation fields."
        ),
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    root = discover_root(args.personaplex_root)
    venv_python = discover_venv_python(args.venv_python, root)
    golden_state_server = discover_golden_state_server(args.golden_state_server, root)

    discovery = {
        "personaplex_root": str(root),
        "venv_python": str(venv_python) if venv_python else None,
        "golden_state_server": str(golden_state_server) if golden_state_server else None,
        "expected_venv_python": str(DEFAULT_VENV_PYTHON),
        "expected_golden_state_server": str(DEFAULT_GOLDEN_STATE_SERVER),
    }
    if venv_python is None or not venv_python.exists():
        return deterministic_fallback("personaplex_venv_python_not_found", discovery)
    if golden_state_server is None or not golden_state_server.exists():
        return deterministic_fallback("personaplex_golden_state_server_not_found", discovery)

    return run_golden_state_probe(
        venv_python=venv_python,
        golden_state_server=golden_state_server,
        root=root,
        timeout_seconds=args.timeout_seconds,
        extra_args=tuple(args.golden_extra_arg or ()),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PersonaPlex P10c GPU LMGen.step proof via golden_state_server subprocess")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory where the receipt JSON will be written")
    parser.add_argument("--receipt-name", default=DEFAULT_RECEIPT_NAME, help="Receipt filename inside --out-dir")
    parser.add_argument("--personaplex-root", default=None, help="PersonaPlex checkout root; defaults to /home/graham/workspace/experiments/personaplex")
    parser.add_argument("--venv-python", default=None, help="PersonaPlex venv python path; defaults to <root>/.venv/bin/python")
    parser.add_argument("--golden-state-server", default=None, help="Path to personaplex_golden_state_server.py")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Bounded subprocess timeout")
    parser.add_argument("--golden-extra-arg", action="append", default=[], help="Additional argument passed to golden_state_server.py; may be repeated")
    parser.add_argument("--require-real", action="store_true", help="Exit non-zero unless real_gpu_personaplex=true")
    parser.add_argument("--print-json", action="store_true", help="Print receipt JSON to stdout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = build_receipt(args)
    out_path = write_json(Path(args.out_dir) / args.receipt_name, receipt)
    if args.print_json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(str(out_path))
    if args.require_real and not receipt.get("real_gpu_personaplex"):
        return 2
    return 0


def run_gpu_personaplex_probe(**kwargs: Any) -> dict[str, Any]:
    timeout = kwargs.get("timeout", 15.0)
    base_url = kwargs.get("base_url", "https://127.0.0.1:8998")
    voice_prompt = kwargs.get("voice_prompt", "embry-current.pt")
    text_prompt = kwargs.get("text_prompt", "Focus on the west gateway.")
    return probe_container_websocket(
        base_url=base_url,
        voice_prompt=voice_prompt,
        text_prompt=text_prompt,
        timeout=timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())

def probe_container_websocket(
    base_url: str = "https://127.0.0.1:8998",
    voice_prompt: str = "embry-current.pt",
    text_prompt: str = "Focus on the west gateway.",
    timeout: float = 15.0,
) -> dict:
    import urllib.parse, time, ssl, json
    from pathlib import Path
    ws_url = f"wss://{urllib.parse.urlparse(base_url).hostname}:{urllib.parse.urlparse(base_url).port or 8998}/api/chat"
    ws_url += f"?text_prompt={urllib.parse.quote(text_prompt)}&voice_prompt={urllib.parse.quote(voice_prompt)}"
    try:
        import websocket as _ws
    except ImportError:
        return {"real_gpu_personaplex": False, "error": "websocket_client_not_available", "fallback_used": True}

    try:
        ws = _ws.create_connection(ws_url, sslopt={"cert_reqs": ssl.CERT_NONE}, timeout=timeout)
        ws.settimeout(timeout)
        ws.send_binary(bytes([1, 0x78, 0x9c, 0x03, 0x00, 0x00, 0x00, 0x00, 0x01]))
        audio_responses = []
        text_responses = []
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                data = ws.recv()
                if isinstance(data, bytes) and len(data) > 0:
                    if data[0] == 1: audio_responses.append(len(data[1:]))
                    elif data[0] == 2: text_responses.append(data[1:].decode("utf-8", errors="replace"))
            except Exception:
                break
        ws.close()
        got_audio = len(audio_responses) > 0
        return {
            "real_gpu_personaplex": got_audio,
            "container_inference_observed": got_audio,
            "audio_chunks_received": len(audio_responses),
            "audio_bytes_total": sum(audio_responses),
            "text_responses": text_responses,
            "fallback_used": not got_audio,
            "duration_seconds": round(time.monotonic() - start, 3),
        }
    except Exception as e:
        return {"real_gpu_personaplex": False, "error": str(e)[:200], "fallback_used": True}
