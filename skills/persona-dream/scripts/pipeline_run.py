#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema
import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
ASK_RUN = REPO_ROOT / "skills" / "ask" / "run.sh"
SCHEMA_PATH = SKILL_ROOT / "schemas" / "crew_contract.schema.json"
DEFAULT_PERSONA_POOL = Path("/mnt/storage12tb/media/personas")
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/persona-dream/outputs")
DEFAULT_ASK_ROOT = Path("/mnt/storage12tb/skills/ask/outputs/persona-dream-crew-casting")
ROLE_DIRS = {
    "producer": ("producers",),
    "scriptwriter": ("writers", "directors"),
    "director": ("directors",),
}
ROLE_ORDER = ("producer", "scriptwriter", "director")


class CrewCastingBlocked(RuntimeError):
    def __init__(self, reason: str, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def _now_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "scene"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _candidate_pool_hash(pool: dict[str, list[dict[str, Any]]]) -> str:
    canonical = json.dumps(pool, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _short_text(value: Any, max_chars: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_chars]


def _read_candidate_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text()
    try:
        loaded = yaml.safe_load(text) or {}
        if isinstance(loaded, dict):
            return loaded
    except yaml.YAMLError:
        pass
    fallback: dict[str, Any] = {}
    for line in text.splitlines():
        match = re.match(r"^(name|template|crew_role|scope):\s*(.+?)\s*$", line)
        if match:
            fallback[match.group(1)] = match.group(2).strip().strip("\"'")
    fallback["source_parse_status"] = "line_fallback_after_yaml_parse_error"
    fallback["summary"] = _short_text(text)
    return fallback


def load_candidate_pool(persona_pool_root: Path) -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLE_ORDER}
    for role, dirs in ROLE_DIRS.items():
        seen: set[str] = set()
        for dir_name in dirs:
            role_dir = persona_pool_root / dir_name
            if not role_dir.is_dir():
                continue
            for path in sorted(role_dir.glob("*.yaml")):
                doc = _read_candidate_yaml(path)
                persona_id = path.stem
                if persona_id in seen:
                    continue
                seen.add(persona_id)
                roles = sorted({role, str(doc.get("template") or ""), str(doc.get("crew_role") or "")} - {""})
                summary_parts = [
                    doc.get("visual_philosophy"),
                    doc.get("writing_philosophy"),
                    doc.get("production_fit"),
                    doc.get("use_when"),
                    doc.get("known_for"),
                    doc.get("summary"),
                ]
                pool[role].append(
                    {
                        "persona_id": persona_id,
                        "name": str(doc.get("name") or persona_id.replace("_", " ").title()),
                        "role": role,
                        "roles": roles,
                        "source_paths": [str(path)],
                        "summary": _short_text(" ".join(json.dumps(part) for part in summary_parts if part)),
                    }
                )
    missing_roles = [role for role, candidates in pool.items() if not candidates]
    if missing_roles:
        raise CrewCastingBlocked(
            "candidate_pool_missing",
            {"missing_roles": missing_roles, "persona_pool_root": str(persona_pool_root)},
        )
    return pool


def _selection_prompt(scene: str, pool: dict[str, list[dict[str, Any]]]) -> str:
    prompt_pool: dict[str, list[dict[str, Any]]] = {}
    for role, candidates in pool.items():
        prompt_pool[role] = [
            {
                "persona_id": candidate["persona_id"],
                "name": candidate["name"],
                "role": candidate["role"],
                "roles": candidate.get("roles", []),
                "summary": candidate.get("summary", ""),
            }
            for candidate in candidates
        ]
    return f"""Select the phase_03 Persona Dream crew for this scene.

Scene:
{scene}

Allowed candidate pool JSON:
{json.dumps(prompt_pool, indent=2, sort_keys=True)}

Return exactly one JSON object and no prose. The JSON object must match:
{{
  "schema": "persona_dream.phase_03_crew_selection_response.v1",
  "scene": "...",
  "selected_crew": {{
    "producer": {{"persona_id": "id from allowed producer pool", "rationale": "why"}},
    "scriptwriter": {{"persona_id": "id from allowed scriptwriter pool", "rationale": "why"}},
    "director": {{"persona_id": "id from allowed director pool", "rationale": "why"}}
  }},
  "selection_order": ["producer", "scriptwriter", "director"]
}}

Do not choose anyone outside the allowed pool. Do not invent names. Do not add markdown fences.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1)
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise CrewCastingBlocked("selector_response_missing_json")
        stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise CrewCastingBlocked("selector_response_invalid_json", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise CrewCastingBlocked("selector_response_not_object")
    return payload


def _run_ask_tau(
    *,
    scene: str,
    pool: dict[str, list[dict[str, Any]]],
    handler: str,
    handler_project: str | None,
    ask_root: Path,
    timeout_seconds: int,
) -> tuple[dict[str, Any], Path, Path]:
    ask_id = f"persona-dream-crew-casting-{_slug(scene)}-{_now_id()}"
    run_dir = ask_root / ask_id
    command = [
        "bash",
        str(ASK_RUN),
        "tau-dag",
        _selection_prompt(scene, pool),
        "--repo",
        "grahama1970/agent-skills",
        "--target",
        "skills/persona-dream#1327",
        "--immutable-goal",
        "select producer/scriptwriter/director from the allowed candidate pool and return strict JSON",
        "--handler",
        handler,
        "--execute",
        "--run-output-root",
        str(ask_root),
        "--ask-id",
        ask_id,
        "--json",
    ]
    if handler_project is None and handler == "webgpt":
        handler_project = "webgpt=skill-cinematic-technique-selector"
    if handler_project:
        command.extend(["--handler-project", handler_project])
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    if result.returncode != 0:
        raise CrewCastingBlocked(
            "ask_tau_dag_failed",
            {
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-2000:],
                "stderr_tail": result.stderr[-2000:],
                "run_dir": str(run_dir),
            },
        )
    node_dir = run_dir / "node-artifacts" / f"handler-{handler}"
    if not node_dir.is_dir():
        handlers = sorted((run_dir / "node-artifacts").glob("handler-*"))
        if len(handlers) == 1:
            node_dir = handlers[0]
    response_path = node_dir / "response.md"
    node_receipt_path = node_dir / "node-receipt.json"
    if not response_path.is_file() or not node_receipt_path.is_file():
        raise CrewCastingBlocked(
            "ask_tau_dag_artifacts_missing",
            {"response_path": str(response_path), "node_receipt_path": str(node_receipt_path)},
        )
    node_receipt = json.loads(node_receipt_path.read_text())
    provider_receipt = node_receipt.get("provider_receipt", {})
    if node_receipt.get("ok") is not True and provider_receipt.get("ok") is not True:
        raise CrewCastingBlocked(
            "selector_node_receipt_not_ok",
            {"node_receipt_path": str(node_receipt_path), "node_receipt": node_receipt},
        )
    selection = _extract_json_object(response_path.read_text())
    return selection, run_dir, node_receipt_path


def _load_fixture_selection(path: Path) -> tuple[dict[str, Any], Path, Path]:
    payload = json.loads(path.read_text())
    receipt_path = path.parent / "fixture_node_receipt.json"
    if not receipt_path.exists():
        _write_json(
            receipt_path,
            {
                "schema": "persona_dream.fixture_selector_node_receipt.v1",
                "ok": True,
                "status": "PASS_FIXTURE_SELECTOR",
                "mocked": True,
                "live": False,
            },
        )
    return payload, path.parent, receipt_path


def _role_candidates(pool: dict[str, list[dict[str, Any]]], role: str) -> dict[str, dict[str, Any]]:
    return {candidate["persona_id"]: candidate for candidate in pool[role]}


def build_contract(
    *,
    scene: str,
    pool: dict[str, list[dict[str, Any]]],
    selection: dict[str, Any],
    tau_run_dir: Path,
    node_receipt_path: Path,
    handler: str,
    mocked: bool,
) -> dict[str, Any]:
    selected = selection.get("selected_crew")
    if not isinstance(selected, dict):
        raise CrewCastingBlocked("selection_missing_selected_crew")
    contract_crew: dict[str, Any] = {}
    rationales: dict[str, str] = {}
    for role in ROLE_ORDER:
        member = selected.get(role)
        if not isinstance(member, dict):
            raise CrewCastingBlocked("selection_missing_role", {"role": role})
        persona_id = str(member.get("persona_id") or "").strip()
        candidates = _role_candidates(pool, role)
        if persona_id not in candidates:
            raise CrewCastingBlocked(
                "selection_outside_candidate_pool",
                {"role": role, "persona_id": persona_id, "allowed": sorted(candidates)},
            )
        candidate = dict(candidates[persona_id])
        rationale = str(member.get("rationale") or "").strip()
        if rationale:
            candidate["rationale"] = rationale
            rationales[role] = rationale
        contract_crew[role] = candidate

    try:
        node_receipt_doc = json.loads(node_receipt_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise CrewCastingBlocked("node_receipt_unreadable", {"path": str(node_receipt_path), "error": str(exc)}) from exc
    provider_receipt = node_receipt_doc.get("provider_receipt", {})
    node_ok = node_receipt_doc.get("ok") is True or provider_receipt.get("ok") is True
    if not node_ok:
        raise CrewCastingBlocked("node_receipt_not_ok", {"path": str(node_receipt_path)})

    return {
        "schema": "persona_dream.phase_03_crew_contract.v1",
        "schema_version": "1.0",
        "status": "CREW_SELECTED",
        "scene": scene,
        "created_at": _now_id(),
        "selection_order": list(ROLE_ORDER),
        "selected_crew": contract_crew,
        "rationales": rationales,
        "candidate_pool_size": sum(len(candidates) for candidates in pool.values()),
        "tau_run_dir": str(tau_run_dir),
        "node_receipt": {
            "path": str(node_receipt_path),
            "ok": True,
            "node_id": node_receipt_doc.get("node_id", "crew_casting"),
            "handler": handler,
            "status": node_receipt_doc.get("status") or provider_receipt.get("status") or "PASS",
        },
        "validation_status": "schema_validated",
        "mocked": mocked,
        "live": not mocked,
        "provider_live": bool(provider_receipt.get("provider_live") or provider_receipt.get("live")),
        "provenance": {
            "selector_runtime": "fixture" if mocked else "ask_tau_dag",
            "selector_handler": handler,
            "agent_bespoke_selection": False,
            "candidate_pool_root": str(DEFAULT_PERSONA_POOL),
            "candidate_pool_sha256": _candidate_pool_hash(pool),
        },
        "quality_checks": {
            "selected_every_required_role": True,
            "selected_from_candidate_pool": True,
            "node_receipt_ok": True,
            "schema_validated": True,
        },
        "downstream_required": [
            "cinematic-technique-selector",
            "camera_lighting_look_lock",
            "script_dna",
        ],
    }


def validate_contract(contract: dict[str, Any], contract_dir: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(contract)
    receipt_path = Path(contract["node_receipt"]["path"])
    if not receipt_path.is_absolute():
        receipt_path = contract_dir / receipt_path
    receipt = json.loads(receipt_path.read_text())
    provider_receipt = receipt.get("provider_receipt", {})
    if receipt.get("ok") is not True and provider_receipt.get("ok") is not True:
        raise CrewCastingBlocked("node_receipt_not_ok", {"path": str(receipt_path)})


def run_crew_casting(args: argparse.Namespace) -> int:
    scene = args.scene.strip()
    run_root = args.run_root or DEFAULT_OUTPUT_ROOT / f"crew-casting-{_slug(scene)}-{_now_id()}"
    run_root.mkdir(parents=True, exist_ok=True)
    try:
        pool = load_candidate_pool(args.persona_pool_root)
        if args.selector_fixture:
            selection, tau_run_dir, node_receipt_path = _load_fixture_selection(args.selector_fixture)
            handler = "fixture"
            mocked = True
        else:
            handler = args.handler
            selection, tau_run_dir, node_receipt_path = _run_ask_tau(
                scene=scene,
                pool=pool,
                handler=handler,
                handler_project=args.handler_project,
                ask_root=args.ask_root,
                timeout_seconds=args.timeout_seconds,
            )
            mocked = False
        contract = build_contract(
            scene=scene,
            pool=pool,
            selection=selection,
            tau_run_dir=tau_run_dir,
            node_receipt_path=node_receipt_path,
            handler=handler,
            mocked=mocked,
        )
        contract_path = run_root / "crew_contract.json"
        _write_json(contract_path, contract)
        validate_contract(contract, run_root)
        receipt = {
            "schema": "persona_dream.pipeline_crew_casting_receipt.v1",
            "status": "PASS_CREW_CASTING",
            "mocked": mocked,
            "live": not mocked,
            "scene": scene,
            "run_root": str(run_root),
            "contract_path": str(contract_path),
            "contract_sha256": _sha256_file(contract_path),
            "tau_run_dir": str(tau_run_dir),
            "node_receipt_path": str(node_receipt_path),
            "claims": {
                "proves": [
                    "crew_casting selected producer, scriptwriter, and director from the local candidate pool",
                    "crew_contract.json validates against crew_contract.schema.json",
                    "crew_contract.json references a readable node receipt whose ok field is true",
                ],
                "does_not_prove": [
                    "look_lock, script_dna, storyboard, or full 42-step per-step Tau execution",
                    "the corrected Persona Dream emotion/dream immutable goal",
                ],
            },
        }
        _write_json(run_root / "crew_casting_receipt.json", receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        blocked = {
            "schema": "persona_dream.pipeline_crew_casting_receipt.v1",
            "status": "BLOCKED_CREW_CASTING",
            "reason": getattr(exc, "reason", type(exc).__name__),
            "details": getattr(exc, "details", {"error": str(exc)}),
            "mocked": bool(args.selector_fixture),
            "live": False,
            "scene": scene,
            "run_root": str(run_root),
        }
        _write_json(run_root / "crew_casting_blocked.json", blocked)
        print(json.dumps(blocked, indent=2, sort_keys=True), file=sys.stderr)
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persona Dream per-step pipeline runner.")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    run = sub.add_parser("run", help="Run one fail-closed pipeline step.")
    run.add_argument("--step", required=True, choices=["crew_casting"])
    run.add_argument("--scene", required=True)
    run.add_argument("--run-root", type=Path)
    run.add_argument("--persona-pool-root", type=Path, default=DEFAULT_PERSONA_POOL)
    run.add_argument("--handler", default=os.environ.get("PERSONA_DREAM_CREW_CASTING_HANDLER", "claude-fable-low"))
    run.add_argument("--handler-project", default=os.environ.get("PERSONA_DREAM_CREW_CASTING_HANDLER_PROJECT"))
    run.add_argument("--ask-root", type=Path, default=DEFAULT_ASK_ROOT)
    run.add_argument("--timeout-seconds", type=int, default=420)
    run.add_argument("--selector-fixture", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not ASK_RUN.is_file() and not args.selector_fixture:
        print(f"BLOCKED_ASK_RUN_NOT_FOUND: {ASK_RUN}", file=sys.stderr)
        return 3
    if args.subcommand == "run" and args.step == "crew_casting":
        return run_crew_casting(args)
    parser.error("unsupported pipeline command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
