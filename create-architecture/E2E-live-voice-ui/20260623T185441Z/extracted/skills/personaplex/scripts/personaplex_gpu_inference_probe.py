#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P10 GPU inference proof probe.

This is a focused proof adapter around the existing
``personaplex_golden_state_server.py`` seam.  It never claims GPU proof from a
mock or deterministic fixture.  ``real_gpu_personaplex=true`` requires a payload
that says an actual ``LMGen.step(...)`` path ran on a GPU and produced a bounded
step output.

The probe supports three integration modes, in order:

1. Explicit ``PERSONAPLEX_P10_COMMAND``/``--command`` returning JSON.
2. Importing the golden-state server and calling a known probe hook if present.
3. Running the golden-state server with ``--probe-lmgen-step --json`` as a
   best-effort CLI hook.

If no real proof is available, it writes a deterministic fallback receipt with
``real_gpu_personaplex=false``.
"""

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

from personaplex_p3_p5_live_services import DEFAULT_SANITY_ROOT, body_excerpt, utc_now_iso, write_json

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "p8_p9_p10" / "gpu_inference_fallback.json"
HOOK_NAMES = (
    "probe_lmgen_step",
    "run_lmgen_step_probe",
    "run_gpu_personaplex_probe",
    "p10_lmgen_step_probe",
)


def load_gpu_fixture() -> dict[str, Any]:
    if FIXTURE_PATH.exists():
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        "schema": "personaplex.p10.gpu_inference_fallback.v1",
        "real_gpu_personaplex": False,
        "lmgen_step_called": False,
        "claim_boundary": "Deterministic fallback is not GPU PersonaPlex proof.",
    }


def discover_personaplex_root(explicit: str | Path | None = None) -> Path | None:
    for value in (explicit, os.environ.get("PERSONAPLEX_ROOT")):
        if value:
            candidate = Path(value).expanduser()
            if candidate.exists():
                return candidate.resolve()
    cwd = Path.cwd()
    for candidate in (cwd, cwd / "personaplex", cwd.parent / "personaplex"):
        if (candidate / "assets").exists() or (candidate / "personaplex_golden_state_server.py").exists():
            return candidate.resolve()
    return None


def discover_server_path(explicit: str | Path | None = None, personaplex_root: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    for value in (explicit, os.environ.get("PERSONAPLEX_GOLDEN_STATE_SERVER")):
        if value:
            candidates.append(Path(value).expanduser())
    root = discover_personaplex_root(personaplex_root)
    if root is not None:
        candidates.extend(
            [
                root / "personaplex_golden_state_server.py",
                root / "scripts" / "personaplex_golden_state_server.py",
                root / "skills" / "personaplex" / "scripts" / "personaplex_golden_state_server.py",
            ]
        )
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd / "personaplex_golden_state_server.py",
            cwd / "skills" / "personaplex" / "scripts" / "personaplex_golden_state_server.py",
        ]
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved.exists() and resolved.is_file():
            return resolved
    return candidates[0] if candidates else None


def _json_from_text(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Accept a final JSON object printed after logs.
    start = stripped.rfind("{")
    if start >= 0:
        try:
            return json.loads(stripped[start:])
        except json.JSONDecodeError:
            return None
    return None


def _coerce_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = _json_from_text(value)
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {"raw_result": repr(value)}


def validate_real_gpu_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Validate that a returned payload is actual bounded LMGen GPU proof."""
    missing: list[str] = []
    if payload.get("real_gpu_personaplex") is not True:
        missing.append("real_gpu_personaplex_true")
    if payload.get("lmgen_step_called") is not True and payload.get("LMGen.step_called") is not True:
        missing.append("lmgen_step_called_true")
    device = str(payload.get("device") or payload.get("gpu_device") or payload.get("torch_device") or "").lower()
    gpu_available = payload.get("gpu_available") is True or payload.get("cuda_available") is True or device.startswith("cuda") or "gpu" in device
    if not gpu_available:
        missing.append("gpu_device_or_cuda_available")
    output_present = any(
        key in payload
        for key in (
            "output_token_id",
            "output_token_ids",
            "generated_token_id",
            "generated_token_ids",
            "logits_shape",
            "step_result_sha256",
            "step_output_sha256",
        )
    )
    if not output_present:
        missing.append("bounded_step_output")
    return not missing, missing


def _fallback_receipt(
    *,
    out_dir: Path,
    reason: str,
    attempted: bool = False,
    server_path: str | None = None,
    personaplex_root: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = load_gpu_fixture()
    fixture_path = write_json(out_dir / "p10-gpu-inference-fallback-used.json", fixture)
    receipt: dict[str, Any] = {
        "schema": "personaplex.p10.gpu_inference_probe_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "attempted": attempted,
        "real_gpu_personaplex": False,
        "lmgen_step_called": False,
        "fallback_used": True,
        "unavailable_reason": reason,
        "server_path": server_path,
        "personaplex_root": personaplex_root,
        "fixture_path": str(fixture_path),
        "claim_boundary": "Deterministic fallback is not GPU PersonaPlex proof because real_gpu_personaplex=false.",
    }
    if extra:
        receipt.update(dict(extra))
    write_json(out_dir / "p10-gpu-personaplex-receipt.json", receipt)
    return receipt


def _success_receipt(
    *,
    out_dir: Path,
    mode: str,
    payload: Mapping[str, Any],
    server_path: str | None,
    personaplex_root: str | None,
    duration_ms: float,
) -> dict[str, Any]:
    receipt = {
        "schema": "personaplex.p10.gpu_inference_probe_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "attempted": True,
        "real_gpu_personaplex": True,
        "lmgen_step_called": True,
        "fallback_used": False,
        "probe_mode": mode,
        "server_path": server_path,
        "personaplex_root": personaplex_root,
        "duration_ms": duration_ms,
        "proof_payload": dict(payload),
        "claim_boundary": "Real P10 proof: payload validated real_gpu_personaplex=true, LMGen.step called, GPU device available, and bounded step output present.",
    }
    write_json(out_dir / "p10-gpu-personaplex-receipt.json", receipt)
    return receipt


def _import_module_from_path(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("personaplex_golden_state_server_for_p10_probe", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_hook(func: Callable[..., Any], *, out_dir: Path, personaplex_root: Path | None, timeout: float) -> Any:
    attempts = [
        {"out_dir": str(out_dir), "personaplex_root": str(personaplex_root) if personaplex_root else None, "timeout": timeout, "max_steps": 1},
        {"out_dir": str(out_dir), "personaplex_root": str(personaplex_root) if personaplex_root else None, "timeout": timeout},
        {"out_dir": str(out_dir), "personaplex_root": str(personaplex_root) if personaplex_root else None},
        {"out_dir": str(out_dir)},
        {},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            return func(**clean_kwargs)
        except TypeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return func()


def _run_command(command: str, *, personaplex_root: Path | None, out_dir: Path, timeout: float) -> dict[str, Any]:
    env = os.environ.copy()
    if personaplex_root is not None:
        env["PERSONAPLEX_ROOT"] = str(personaplex_root)
    env["PERSONAPLEX_GPU_PROBE_RECEIPT"] = str(out_dir / "p10-command-receipt.json")
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603 - explicit user/project command only.
        shlex.split(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
        check=False,
    )
    parsed = _json_from_text(proc.stdout)
    if parsed is None and Path(env["PERSONAPLEX_GPU_PROBE_RECEIPT"]).exists():
        parsed = json.loads(Path(env["PERSONAPLEX_GPU_PROBE_RECEIPT"]).read_text(encoding="utf-8"))
    payload = _coerce_payload(parsed)
    payload.update(
        {
            "command": command,
            "returncode": proc.returncode,
            "stdout_excerpt": body_excerpt(proc.stdout, 4000),
            "stderr_excerpt": body_excerpt(proc.stderr, 4000),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
    )
    return payload


def run_gpu_personaplex_probe(
    *,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    server_path: str | Path | None = None,
    personaplex_root: str | Path | None = None,
    command: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    root = discover_personaplex_root(personaplex_root)
    root_str = str(root) if root else (str(personaplex_root) if personaplex_root else None)
    explicit_command = command or os.environ.get("PERSONAPLEX_P10_COMMAND")

    if explicit_command:
        try:
            payload = _run_command(explicit_command, personaplex_root=root, out_dir=out, timeout=timeout)
        except Exception as exc:
            return _fallback_receipt(
                out_dir=out,
                reason="p10_command_error",
                attempted=True,
                personaplex_root=root_str,
                extra={"command": explicit_command, "command_error": f"{type(exc).__name__}:{exc}"},
            )
        ok, missing = validate_real_gpu_payload(payload)
        if ok:
            return _success_receipt(
                out_dir=out,
                mode="external_command",
                payload=payload,
                server_path=None,
                personaplex_root=root_str,
                duration_ms=float(payload.get("duration_ms") or 0.0),
            )
        return _fallback_receipt(
            out_dir=out,
            reason="p10_command_did_not_prove_lmgen_gpu_step",
            attempted=True,
            personaplex_root=root_str,
            extra={"proof_validation_missing": missing, "proof_payload": payload},
        )

    server = discover_server_path(server_path, personaplex_root=root)
    server_str = str(server) if server else (str(server_path) if server_path else None)
    if server is None or not server.exists():
        return _fallback_receipt(
            out_dir=out,
            reason="golden_state_server_not_found",
            attempted=False,
            server_path=server_str,
            personaplex_root=root_str,
        )

    started = time.monotonic()
    try:
        module = _import_module_from_path(server)
        for name in HOOK_NAMES:
            hook = getattr(module, name, None)
            if callable(hook):
                payload = _coerce_payload(_call_hook(hook, out_dir=out, personaplex_root=root, timeout=timeout))
                ok, missing = validate_real_gpu_payload(payload)
                if ok:
                    return _success_receipt(
                        out_dir=out,
                        mode=f"module_hook:{name}",
                        payload=payload,
                        server_path=str(server),
                        personaplex_root=root_str,
                        duration_ms=round((time.monotonic() - started) * 1000, 3),
                    )
                return _fallback_receipt(
                    out_dir=out,
                    reason="module_hook_did_not_prove_lmgen_gpu_step",
                    attempted=True,
                    server_path=str(server),
                    personaplex_root=root_str,
                    extra={"hook_name": name, "proof_validation_missing": missing, "proof_payload": payload},
                )
    except Exception as exc:
        return _fallback_receipt(
            out_dir=out,
            reason="golden_state_server_import_or_hook_error",
            attempted=True,
            server_path=str(server),
            personaplex_root=root_str,
            extra={"server_error": f"{type(exc).__name__}:{exc}"},
        )

    # Best-effort CLI hook for an updated golden-state server that has a probe mode.
    cli_command = f"{shlex.quote(sys.executable)} {shlex.quote(str(server))} --probe-lmgen-step --json"
    try:
        payload = _run_command(cli_command, personaplex_root=root, out_dir=out, timeout=timeout)
    except Exception as exc:
        return _fallback_receipt(
            out_dir=out,
            reason="lmgen_step_hook_not_found",
            attempted=True,
            server_path=str(server),
            personaplex_root=root_str,
            extra={"attempted_cli_command": cli_command, "cli_error": f"{type(exc).__name__}:{exc}"},
        )
    ok, missing = validate_real_gpu_payload(payload)
    if ok:
        return _success_receipt(
            out_dir=out,
            mode="golden_state_server_cli_probe",
            payload=payload,
            server_path=str(server),
            personaplex_root=root_str,
            duration_ms=float(payload.get("duration_ms") or 0.0),
        )
    return _fallback_receipt(
        out_dir=out,
        reason="golden_state_server_cli_did_not_prove_lmgen_gpu_step",
        attempted=True,
        server_path=str(server),
        personaplex_root=root_str,
        extra={"attempted_cli_command": cli_command, "proof_validation_missing": missing, "proof_payload": payload},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P10 GPU LMGen.step proof probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--server-path", default=None)
    parser.add_argument("--personaplex-root", default=None)
    parser.add_argument("--command", default=None)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PERSONAPLEX_P10_TIMEOUT", "30")))
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_gpu_personaplex=true.")
    args = parser.parse_args(argv)
    receipt = run_gpu_personaplex_probe(
        out_dir=args.out_dir,
        server_path=args.server_path,
        personaplex_root=args.personaplex_root,
        command=args.command,
        timeout=args.timeout,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_gpu_personaplex"):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
