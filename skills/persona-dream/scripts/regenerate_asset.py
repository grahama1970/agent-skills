#!/usr/bin/env python3
"""Build recreate bundles and regenerate persona-dream contact sheets and panels."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SCILLM_GENERATE = Path(os.getenv("SCILLM_GENERATE_IMAGE", "/home/graham/workspace/experiments/scillm/scripts/generate_image.py"))
PERSONA_DREAM_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def scillm_repo() -> Path:
    return SCILLM_GENERATE.resolve().parents[1]


def contact_sheet_meta_path(run_root: Path, file_name: str) -> Path:
    return run_root / "reference_sheets" / f"{Path(file_name).stem}.contact_sheet.meta.json"


def existing_embry_research_paths() -> list[Path]:
    paths = (
        "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_01_main_front_full_body.png",
        "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_02_three_quarter_full_body.png",
        "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_03_side_or_back_view.png",
        "/mnt/storage12tb/skills/persona-dream/outputs/20260611-horus-embry-casting/asset_packs/kling_reference_pack_v1/images/character_embry_04_face_or_detail_closeup.png",
        "/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated/research/bakeoff/reference_rebuild_20260610T2117Z/images/embry_character_reference_sheet.png",
    )
    return [Path(raw) for raw in paths if Path(raw).is_file()]


def collect_contact_sheet_research_paths(
    run_root: Path,
    meta: dict[str, Any],
    *,
    file_name: str,
) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    output_name = Path(file_name).name
    casting = meta.get("casting_context") or {}

    def add(raw: Any) -> None:
        path_raw = str((raw or {}).get("path") if isinstance(raw, dict) else raw or "").strip()
        if not path_raw:
            return
        path = Path(path_raw)
        if path.name == output_name or not path.is_file():
            return
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        paths.append(path.resolve())

    for ref in casting.get("provided_references") or []:
        add(ref)
    inline = meta.get("creation_prompt_inline_references") or {}
    for ref in inline.get("local_image_files") or []:
        add(ref)
    sheet_stem = Path(file_name).stem
    brave_dir = run_root / "pipeline_review_8892" / "assets" / "research" / "brave" / sheet_stem
    if brave_dir.is_dir():
        for img in sorted(brave_dir.iterdir()):
            if img.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                add(img)
    if str(casting.get("entity_id") or "") == "character_embry":
        for embry_path in existing_embry_research_paths():
            add(embry_path)
    return paths


def _zip_write_path(archive: zipfile.ZipFile, source: Path, arcname: str, used: set[str]) -> str:
    final_name = arcname
    if final_name in used:
        final_name = f"{Path(arcname).parent / ('dup_' + Path(arcname).name)}"
    used.add(final_name)
    archive.write(source, final_name)
    return final_name


def _regenerate_shell(*, kind: str, run_root: Path, bundle_path: Path) -> str:
    script = PERSONA_DREAM_ROOT / "scripts" / "regenerate_asset.py"
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f'RUN_ROOT="${{PERSONA_DREAM_RUN_ROOT:-{run_root}}}"',
            f'BUNDLE="{bundle_path.resolve()}"',
            f'SCRIPT="{script}"',
            f'echo "Regenerating {kind} from $BUNDLE into run root: $RUN_ROOT"',
            f'python3 "$SCRIPT" {kind} --bundle "$BUNDLE" --run-root "$RUN_ROOT"',
            "",
        ]
    )


def _bundle_is_fresh(bundle_path: Path, sources: list[Path]) -> bool:
    if not bundle_path.is_file():
        return False
    bundle_mtime = bundle_path.stat().st_mtime
    for source in sources:
        if source.is_file() and source.stat().st_mtime > bundle_mtime:
            return False
    return True


def build_contact_sheet_bundle(
    run_root: Path,
    file_name: str,
    meta: dict[str, Any],
    prompt_text: str,
) -> Path | None:
    sheet_stem = Path(file_name).stem
    bundle_dir = run_root / "pipeline_review_8892" / "assets" / "contact_sheet_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{sheet_stem}_recreate.zip"
    research_paths = collect_contact_sheet_research_paths(run_root, meta, file_name=file_name)
    meta_path = contact_sheet_meta_path(run_root, file_name)
    if _bundle_is_fresh(bundle_path, [meta_path, *research_paths]):
        return bundle_path.resolve()
    brave_artifacts = [
        Path(str(item.get("artifact_path")))
        for item in (meta.get("brave_search_grounding") or [])
        if str(item.get("artifact_path") or "").strip()
    ]
    gen = meta.get("generation_attempt") or {}
    manifest = {
        "schema": "persona_dream.contact_sheet_recreate_bundle.v1",
        "asset_kind": "contact_sheet",
        "sheet_stem": sheet_stem,
        "png_file": file_name,
        "run_root": str(run_root.resolve()),
        "output_relpath": f"reference_sheets/{file_name}",
        "entity_id": (meta.get("casting_context") or {}).get("entity_id"),
        "size": str(gen.get("size_requested") or "1600x1200"),
        "model": str(gen.get("model") or "gpt-image-2"),
        "research_image_paths": [str(path) for path in research_paths],
        "brave_artifact_paths": [str(path) for path in brave_artifacts if path.is_file()],
    }
    readme = (
        f"# Contact sheet recreate bundle: {sheet_stem}\n\n"
        "1. Copy this zip to clipboard from the pipeline report, or download it.\n"
        "2. Unzip anywhere, or run `./regenerate.sh` from an extracted copy.\n"
        "3. Or run:\n"
        f"   python3 skills/persona-dream/scripts/regenerate_asset.py contact-sheet \\\n"
        f"     --bundle {bundle_path} --run-root {run_root}\n"
    )
    used: set[str] = set()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("creation_prompt.md", (prompt_text or "").strip() + "\n")
        archive.writestr("README.md", readme)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("regenerate.sh", _regenerate_shell(kind="contact-sheet", run_root=run_root, bundle_path=bundle_path))
        meta_path = contact_sheet_meta_path(run_root, file_name)
        if meta_path.is_file():
            _zip_write_path(archive, meta_path, "contact_sheet.meta.json", used)
        for index, image_path in enumerate(research_paths):
            arcname = f"research_images/{image_path.name}"
            if arcname in used:
                arcname = f"research_images/{index:02d}_{image_path.name}"
            _zip_write_path(archive, image_path, arcname, used)
        for artifact_path in brave_artifacts:
            if artifact_path.is_file():
                _zip_write_path(archive, artifact_path, f"brave_grounding/{artifact_path.name}", used)
    return bundle_path.resolve() if bundle_path.is_file() else None


def _find_panel_prompt(run_root: Path, panel_num: int) -> Path | None:
    prompts_dir = run_root / "prompts"
    patterns = [
        f"panel_{panel_num:02d}*_regeneration.prompt.md",
        f"panel_{panel_num:02d}*.prompt.md",
        f"panel_{panel_num}_*_regeneration.prompt.md",
        f"panel_{panel_num}_*.prompt.md",
    ]
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(sorted(prompts_dir.glob(pattern)))
    return matches[-1] if matches else None


def _panel_scene_payload(run_root: Path, panel_num: int) -> dict[str, Any]:
    payloads = load_json(run_root / "storyboard" / "kling_scene_payloads.json")
    for panel in payloads.get("panels") or []:
        if int(panel.get("panel") or 0) == panel_num:
            return panel
    return {}


def _panel_reference_sheets(run_root: Path) -> list[Path]:
    ref_dir = run_root / "reference_sheets"
    if not ref_dir.is_dir():
        return []
    paths = sorted(ref_dir.glob("*.png"))
    return [path.resolve() for path in paths if path.is_file()]


def _panel_image_path(run_root: Path, panel_num: int) -> Path | None:
    candidates = [
        run_root / "storyboard" / "kling_direction_board" / "panels" / f"panel_{panel_num}.png",
        run_root / "storyboard" / "kling_direction_board" / "panels" / f"panel_{panel_num:02d}.png",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
        if candidate.is_symlink() and candidate.resolve().is_file():
            return candidate.resolve()
    regen = sorted((run_root / "storyboard" / "regenerated_panels").glob(f"panel_{panel_num:02d}*.png"))
    return regen[-1].resolve() if regen else None


def build_panel_bundle(run_root: Path, panel_num: int) -> Path | None:
    bundle_dir = run_root / "pipeline_review_8892" / "assets" / "panel_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"panel_{panel_num:02d}_recreate.zip"
    prompt_path = _find_panel_prompt(run_root, panel_num)
    scene = _panel_scene_payload(run_root, panel_num)
    if prompt_path and prompt_path.is_file():
        prompt_text = prompt_path.read_text(encoding="utf-8")
    elif scene.get("provider_text"):
        prompt_text = str(scene["provider_text"]).strip() + "\n"
    else:
        prompt_text = json.dumps(scene, indent=2)
    research_paths = _panel_reference_sheets(run_root)
    panel_image = _panel_image_path(run_root, panel_num)
    prompt_source = prompt_path if prompt_path and prompt_path.is_file() else run_root / "storyboard" / "kling_scene_payloads.json"
    fresh_sources = [p for p in [prompt_source, panel_image, *research_paths] if p and p.is_file()]
    if _bundle_is_fresh(bundle_path, fresh_sources):
        return bundle_path.resolve()
    output_name = f"panel_{panel_num:02d}_regenerated.png"
    manifest = {
        "schema": "persona_dream.panel_recreate_bundle.v1",
        "asset_kind": "panel",
        "panel_number": panel_num,
        "run_root": str(run_root.resolve()),
        "output_relpath": f"storyboard/regenerated_panels/{output_name}",
        "panel_board_relpath": f"storyboard/kling_direction_board/panels/panel_{panel_num}.png",
        "size": "1536x1024",
        "model": "gpt-image-2",
        "prompt_source": str(prompt_path) if prompt_path else "kling_scene_payloads.json",
        "research_image_paths": [str(path) for path in research_paths],
        "current_panel_image": str(panel_image) if panel_image else None,
    }
    readme = (
        f"# Panel recreate bundle: panel {panel_num}\n\n"
        "Contains the panel prompt, Kling scene payload, contact-sheet references, and current panel image.\n\n"
        f"Regenerate:\n"
        f"  python3 skills/persona-dream/scripts/regenerate_asset.py panel \\\n"
        f"    --bundle {bundle_path} --run-root {run_root}\n"
    )
    used: set[str] = set()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("panel_prompt.md", prompt_text.strip() + "\n")
        archive.writestr("README.md", readme)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("panel_scene_payload.json", json.dumps(scene, indent=2) + "\n")
        archive.writestr("regenerate.sh", _regenerate_shell(kind="panel", run_root=run_root, bundle_path=bundle_path))
        if prompt_path and prompt_path.is_file():
            _zip_write_path(archive, prompt_path, f"source_prompts/{prompt_path.name}", used)
        for index, image_path in enumerate(research_paths):
            arcname = f"reference_sheets/{image_path.name}"
            if arcname in used:
                arcname = f"reference_sheets/{index:02d}_{image_path.name}"
            _zip_write_path(archive, image_path, arcname, used)
        if panel_image and panel_image.is_file():
            _zip_write_path(archive, panel_image, f"current_panel/{panel_image.name}", used)
    return bundle_path.resolve() if bundle_path.is_file() else None


def build_all_panel_bundles(run_root: Path, *, panel_count: int = 10) -> list[Path]:
    bundles: list[Path] = []
    for panel_num in range(1, panel_count + 1):
        bundle = build_panel_bundle(run_root, panel_num)
        if bundle is not None:
            bundles.append(bundle)
    return bundles


def _read_zip_text(bundle: Path, name: str) -> str:
    with zipfile.ZipFile(bundle, "r") as archive:
        try:
            return archive.read(name).decode("utf-8")
        except KeyError:
            return ""


def _prompt_with_references(prompt: str, bundle: Path) -> str:
    refs: list[str] = []
    with zipfile.ZipFile(bundle, "r") as archive:
        for name in sorted(archive.namelist()):
            if name.startswith(("research_images/", "reference_sheets/")) and name.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
            ):
                refs.append(name)
    if not refs:
        return prompt
    block = ["", "Reference images bundled with this recreate package:"]
    block.extend(f"- {name}" for name in refs)
    return prompt.rstrip() + "\n" + "\n".join(block) + "\n"


def _run_scillm_generate(
    *,
    prompt_text: str,
    output_path: Path,
    size: str,
    model: str,
    caller_skill: str,
) -> dict[str, Any]:
    if not SCILLM_GENERATE.is_file():
        raise FileNotFoundError(f"scillm generate_image.py not found: {SCILLM_GENERATE}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = output_path.with_name(f"{output_path.stem}_receipt.json")
    events = output_path.with_name(f"{output_path.stem}_events.jsonl")
    env = os.environ.copy()
    scillm_src = scillm_repo() / "src"
    env["PYTHONPATH"] = str(scillm_src) if not env.get("PYTHONPATH") else f"{scillm_src}:{env['PYTHONPATH']}"
    with tempfile.NamedTemporaryFile("w", suffix=".prompt.md", delete=False, encoding="utf-8") as handle:
        handle.write(prompt_text)
        prompt_file = Path(handle.name)
    try:
        cmd = [
            sys.executable,
            str(SCILLM_GENERATE),
            "--prompt-file",
            str(prompt_file),
            "--out",
            str(output_path),
            "--receipt",
            str(receipt),
            "--events-out",
            str(events),
            "--auth",
            os.getenv("PERSONA_DREAM_REGEN_AUTH", "codex-oauth"),
            "--model",
            model,
            "--quality",
            os.getenv("PERSONA_DREAM_REGEN_QUALITY", "high"),
            "--size",
            size,
            "--caller-skill",
            caller_skill,
            "--timeout-s",
            os.getenv("PERSONA_DREAM_REGEN_TIMEOUT_S", "600"),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=scillm_repo())
        return {
            "cmd": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "output_path": str(output_path),
            "receipt_path": str(receipt),
            "ok": completed.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0,
        }
    finally:
        prompt_file.unlink(missing_ok=True)


def _bundle_manifest(bundle: Path) -> dict[str, Any]:
    raw = _read_zip_text(bundle, "manifest.json")
    if not raw.strip():
        raise ValueError(f"manifest.json missing in bundle: {bundle}")
    return json.loads(raw)


def regenerate_contact_sheet(*, bundle: Path, run_root: Path | None, out: Path | None, dry_run: bool) -> dict[str, Any]:
    manifest = _bundle_manifest(bundle)
    root = Path(run_root or manifest.get("run_root") or ".").expanduser().resolve()
    prompt = _read_zip_text(bundle, "creation_prompt.md") or _read_zip_text(bundle, "panel_prompt.md")
    prompt = _prompt_with_references(prompt, bundle)
    output = out or (root / str(manifest.get("output_relpath") or "reference_sheets/output.png"))
    output = output.resolve()
    payload = {
        "asset_kind": "contact_sheet",
        "bundle": str(bundle.resolve()),
        "run_root": str(root),
        "output": str(output),
        "dry_run": dry_run,
    }
    if dry_run:
        payload["prompt_preview"] = prompt[:500]
        return payload
    result = _run_scillm_generate(
        prompt_text=prompt,
        output_path=output,
        size=str(manifest.get("size") or "1600x1200"),
        model=str(manifest.get("model") or "gpt-image-2"),
        caller_skill="persona-dream-regenerate-contact-sheet",
    )
    payload["generation"] = result
    if result.get("ok"):
        sync = subprocess.run(
            [
                sys.executable,
                str(PERSONA_DREAM_ROOT / "scripts" / "sync_contact_sheet_sidecars.py"),
                "--run-root",
                str(root),
                "--write",
                "--only",
                output.name,
            ],
            capture_output=True,
            text=True,
        )
        payload["sidecar_sync"] = {"returncode": sync.returncode, "stdout": sync.stdout, "stderr": sync.stderr}
        patch = subprocess.run(
            [sys.executable, str(PERSONA_DREAM_ROOT / "scripts" / "patch_pipeline_report_ui.py"), "--run-root", str(root)],
            capture_output=True,
            text=True,
        )
        payload["report_patch"] = {"returncode": patch.returncode, "stdout": patch.stdout[-500:], "stderr": patch.stderr[-500:]}
    return payload


def regenerate_panel(*, bundle: Path, run_root: Path | None, out: Path | None, dry_run: bool) -> dict[str, Any]:
    manifest = _bundle_manifest(bundle)
    root = Path(run_root or manifest.get("run_root") or ".").expanduser().resolve()
    prompt = _read_zip_text(bundle, "panel_prompt.md") or _read_zip_text(bundle, "creation_prompt.md")
    prompt = _prompt_with_references(prompt, bundle)
    output = out or (root / str(manifest.get("output_relpath") or "storyboard/regenerated_panels/panel_regenerated.png"))
    output = output.resolve()
    payload = {
        "asset_kind": "panel",
        "bundle": str(bundle.resolve()),
        "run_root": str(root),
        "output": str(output),
        "dry_run": dry_run,
    }
    if dry_run:
        payload["prompt_preview"] = prompt[:500]
        return payload
    result = _run_scillm_generate(
        prompt_text=prompt,
        output_path=output,
        size=str(manifest.get("size") or "1536x1024"),
        model=str(manifest.get("model") or "gpt-image-2"),
        caller_skill="persona-dream-regenerate-panel",
    )
    payload["generation"] = result
    if result.get("ok"):
        board_target = root / str(manifest.get("panel_board_relpath") or output.name)
        board_target.parent.mkdir(parents=True, exist_ok=True)
        if board_target.exists() or board_target.is_symlink():
            board_target.unlink()
        board_target.symlink_to(output.resolve())
        payload["panel_board_symlink"] = str(board_target)
        patch = subprocess.run(
            [sys.executable, str(PERSONA_DREAM_ROOT / "scripts" / "patch_pipeline_report_ui.py"), "--run-root", str(root)],
            capture_output=True,
            text=True,
        )
        payload["report_patch"] = {"returncode": patch.returncode, "stdout": patch.stdout[-500:], "stderr": patch.stderr[-500:]}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    cs = sub.add_parser("contact-sheet", help="Regenerate a contact sheet from a recreate bundle")
    cs.add_argument("--bundle", type=Path, required=True)
    cs.add_argument("--run-root", type=Path, default=None)
    cs.add_argument("--out", type=Path, default=None)
    cs.add_argument("--dry-run", action="store_true")

    pn = sub.add_parser("panel", help="Regenerate a panel image from a recreate bundle")
    pn.add_argument("--bundle", type=Path, required=True)
    pn.add_argument("--run-root", type=Path, default=None)
    pn.add_argument("--out", type=Path, default=None)
    pn.add_argument("--dry-run", action="store_true")

    bcs = sub.add_parser("bundle-contact-sheets", help="Build recreate bundles for all contact sheets")
    bcs.add_argument("--run-root", type=Path, required=True)

    bp = sub.add_parser("bundle-panels", help="Build recreate bundles for all panels")
    bp.add_argument("--run-root", type=Path, required=True)
    bp.add_argument("--panel-count", type=int, default=10)

    args = parser.parse_args()
    if args.command == "contact-sheet":
        payload = regenerate_contact_sheet(bundle=args.bundle.expanduser().resolve(), run_root=args.run_root, out=args.out, dry_run=args.dry_run)
    elif args.command == "panel":
        payload = regenerate_panel(bundle=args.bundle.expanduser().resolve(), run_root=args.run_root, out=args.out, dry_run=args.dry_run)
    elif args.command == "bundle-contact-sheets":
        run_root = args.run_root.expanduser().resolve()
        ref_dir = run_root / "reference_sheets"
        bundles = []
        for png in sorted(ref_dir.glob("*.png")):
            meta = load_json(contact_sheet_meta_path(run_root, png.name))
            prompt = str(meta.get("creation_prompt") or "").strip()
            if not prompt:
                prompt_link = meta.get("prompt_link_path") or meta.get("prompt_path")
                if prompt_link and Path(str(prompt_link)).exists():
                    prompt = Path(str(prompt_link)).read_text(encoding="utf-8").strip()
            bundle = build_contact_sheet_bundle(run_root, png.name, meta, prompt)
            if bundle:
                bundles.append(str(bundle))
        payload = {"bundles": bundles}
    else:
        payload = {"bundles": [str(path) for path in build_all_panel_bundles(args.run_root.expanduser().resolve(), panel_count=args.panel_count)]}
    print(json.dumps(payload, indent=2))
    ok = payload.get("generation", {}).get("ok", True) if isinstance(payload.get("generation"), dict) else True
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
