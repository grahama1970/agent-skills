#!/usr/bin/env python3
# /// script
# dependencies = [
#     "pyyaml",
# ]
# ///
"""
Veo Adapter (HorusShotSpec v0.1 Implementation)

Converts create-movie output into HorusShotSpec YAML,
then compiles to Veo API JSON for video generation.

Implements:
- HorusShotSpec v0.1 Schema (YAML)
- Validation layer for Veo constraints
- Compilation to Veo API JSON
"""

import json
import shutil
import yaml
from pathlib import Path
from typing import Any
from datetime import datetime

from core.shot_compiler import (
    compile_yaml_to_veo_json,
    compile_shots_batch,
    VEO_CONSTRAINTS,
    ValidationError,
)


class VeoAdapter:
    """Adapts create-movie output to HorusShotSpec YAML and Veo API JSON."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.export_dir = output_dir / "veo_export"
        self.assets_dir = self.export_dir / "assets"
        self.shots_dir = self.export_dir / "shots"
        self.manifest_file = self.export_dir / "manifest.yaml"
        self.compiled_dir = self.export_dir / "compiled"

    def prepare_export(self, script_data: dict, project_assets: list[dict] | None = None, identity_packs: dict | None = None):
        """Prepare the export directory and HorusShotSpec files.

        Args:
            script_data: Parsed script.json with scenes
            project_assets: Optional list of project assets
            identity_packs: Optional dict mapping character names to identity pack paths
                           e.g., {"SARAH": {"front": Path(...), "three_quarter": Path(...)}}
        """
        if self.export_dir.exists():
            shutil.rmtree(self.export_dir)

        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.compiled_dir.mkdir(parents=True, exist_ok=True)

        # Copy identity pack images to assets directory
        identity_refs = {}
        if identity_packs:
            for char_name, pack in identity_packs.items():
                identity_refs[char_name] = []
                for angle, img_path in pack.items():
                    if img_path and Path(img_path).exists():
                        dest = self.assets_dir / f"{char_name.lower()}_{angle}.png"
                        shutil.copy2(img_path, dest)
                        identity_refs[char_name].append({
                            "path": str(dest.relative_to(self.export_dir)),
                            "weight": 0.7,
                            "angle": angle,
                        })
            print(f"[VeoAdapter] Copied identity packs for: {', '.join(identity_packs.keys())}")

        # Build manifest (project-level metadata)
        manifest = {
            "project": {
                "name": script_data.get("title", "Untitled"),
                "created_at": datetime.now().isoformat(),
                "schema_version": "HorusShotSpec v0.1",
                "renderer": "veo",
                "model": VEO_CONSTRAINTS["default_model"],
            },
            "defaults": {
                "aspect_ratio": "16:9",
                "duration_s": 8,
                "resolution": "1080p",
                "negative_prompt": "text overlays, watermarks, shaky camera, distorted faces, garbled speech",
            },
            "identity_packs": list(identity_refs.keys()) if identity_refs else [],
            "shots": [],
        }

        scenes = script_data.get("scenes", [])

        for i, scene in enumerate(scenes):
            scene_idx = i + 1
            shot_id = f"ACT1_SC{scene_idx:02d}_SHOT01"

            # Get characters in this scene for identity pack references
            scene_characters = scene.get("characters", [])
            scene_identity_refs = []
            for char_name in scene_characters:
                if char_name in identity_refs:
                    # Use front angle for most shots, or first available
                    for ref in identity_refs[char_name]:
                        if ref["angle"] == "front":
                            scene_identity_refs.append({"path": ref["path"], "weight": ref["weight"]})
                            break
                    else:
                        # No front angle, use first available
                        if identity_refs[char_name]:
                            ref = identity_refs[char_name][0]
                            scene_identity_refs.append({"path": ref["path"], "weight": ref["weight"]})

            # Create individual shot spec YAML
            shot_spec = self._map_scene_to_shot_spec(scene, shot_id, scene_idx, subject_images=scene_identity_refs)
            shot_file = self.shots_dir / f"{shot_id}.yaml"

            with open(shot_file, "w") as f:
                yaml.dump(shot_spec, f, sort_keys=False, indent=2, default_flow_style=False)

            # Add to manifest
            manifest["shots"].append({
                "id": shot_id,
                "file": f"shots/{shot_id}.yaml",
                "sequence_order": scene_idx,
                "characters": scene_characters,
            })

        # Write manifest
        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, sort_keys=False, indent=2, default_flow_style=False)

        print(f"[VeoAdapter] Exported HorusShotSpec v0.1 to {self.export_dir}")
        print(f"[VeoAdapter] {len(scenes)} shots written to {self.shots_dir}")

    def _map_scene_to_shot_spec(self, scene: dict, shot_id: str, idx: int, subject_images: list | None = None) -> dict:
        """Map generic scene dict to HorusShotSpec structure.

        Args:
            scene: Scene dict from script
            shot_id: Generated shot ID
            idx: Scene index
            subject_images: Optional list of identity pack references for characters in this scene
        """
        visual = scene.get("visual", "")
        action = " ".join(scene.get("action", []))
        shot_type = scene.get("shot_type", "medium shot")
        lighting = scene.get("lighting", "cinematic lighting")
        duration = scene.get("duration_seconds", 8)

        # Clamp duration to valid Veo values
        valid_durations = VEO_CONSTRAINTS["valid_durations"]
        if duration not in valid_durations:
            # Find closest valid duration
            duration = min(valid_durations, key=lambda x: abs(x - duration))

        # Build cinematic prompt
        prompt_parts = []
        if visual:
            prompt_parts.append(visual)
        if action:
            prompt_parts.append(action)
        if shot_type:
            prompt_parts.append(f"{shot_type} framing")
        if lighting:
            prompt_parts.append(lighting)

        prompt_text = ". ".join(prompt_parts) if prompt_parts else "A cinematic shot"

        # Build HorusShotSpec YAML structure
        shot_spec = {
            "shot_id": shot_id,
            "prompt": {
                "text": prompt_text,
                "negative": "text overlays, watermarks, shaky camera, distorted faces, garbled speech",
            },
            "duration_s": duration,
            "aspect_ratio": "16:9",
            "resolution": "1080p",
            "references": {
                "subject_images": subject_images or [],
                "first_frame": None,
                "last_frame": None,
            },
            "controls": {
                "seed": None,
                "safety": "default",
            },
            "renderer": {
                "name": "veo",
                "model": VEO_CONSTRAINTS["default_model"],
            },
            "metadata": {
                "scene": f"SC{idx:02d}",
                "act": "ACT1",
                "sequence_order": idx,
                "notes": scene.get("notes", ""),
                "characters": scene.get("characters", []),
            },
        }

        return shot_spec

    def add_reference_image(self, source_path: Path, shot_id: str, weight: float = 0.5) -> str | None:
        """Copy reference image and return relative path."""
        if not source_path.exists():
            return None

        filename = f"{shot_id}_ref{source_path.suffix}"
        dest_path = self.assets_dir / filename
        shutil.copy2(source_path, dest_path)

        return str(dest_path.relative_to(self.export_dir))

    def compile_all_shots(self, constraints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Compile all shot specs to renderer API JSON.

        Args:
            constraints: Renderer-specific constraints. If None, uses Veo defaults.
                        Use PERMISSIVE_CONSTRAINTS for non-Veo renderers.

        Returns:
            List of renderer API request dicts
        """
        compiled_requests = []
        errors = []

        # Load manifest
        with open(self.manifest_file) as f:
            manifest = yaml.safe_load(f)

        for shot_entry in manifest["shots"]:
            shot_file = self.export_dir / shot_entry["file"]

            with open(shot_file) as f:
                shot_spec = yaml.safe_load(f)

            try:
                veo_json = compile_yaml_to_veo_json(shot_spec, constraints)
                compiled_requests.append(veo_json)

                # Write compiled JSON
                compiled_file = self.compiled_dir / f"{shot_entry['id']}.json"
                with open(compiled_file, "w") as f:
                    json.dump(veo_json, f, indent=2)

            except ValidationError as e:
                errors.append(f"{shot_entry['id']}: {e}")

        if errors:
            print(f"[VeoAdapter] Compilation errors:\n" + "\n".join(errors))

        print(f"[VeoAdapter] Compiled {len(compiled_requests)} shots to {self.compiled_dir}")
        return compiled_requests

    def link_assets(self, assets_dir: Path):
        """Link storyboard images to shot specs."""
        # Load manifest
        with open(self.manifest_file) as f:
            manifest = yaml.safe_load(f)

        for shot_entry in manifest["shots"]:
            shot_id = shot_entry["id"]
            idx = shot_entry["sequence_order"]

            # Find asset candidate
            candidates = [
                assets_dir / f"scene_{idx:03d}.png",
                assets_dir / f"keyframe_{idx:03d}.png",
                assets_dir / f"{idx:03d}.png",
            ]

            found_image = None
            for cand in candidates:
                if cand.exists():
                    found_image = cand
                    break

            if found_image:
                rel_path = self.add_reference_image(found_image, shot_id, weight=0.7)

                # Update shot spec with reference
                shot_file = self.export_dir / shot_entry["file"]
                with open(shot_file) as f:
                    shot_spec = yaml.safe_load(f)

                shot_spec["references"]["subject_images"] = [
                    {"path": rel_path, "weight": 0.7}
                ]

                with open(shot_file, "w") as f:
                    yaml.dump(shot_spec, f, sort_keys=False, indent=2, default_flow_style=False)


def export_to_veo(project_dir: Path, script_path: Path, assets_dir: Path, identity_packs: dict | None = None, constraints: dict | None = None) -> list[dict]:
    """
    Main export entry point.

    Args:
        project_dir: Project directory for export output
        script_path: Path to script.json
        assets_dir: Path to generated assets
        identity_packs: Optional dict mapping character names to their identity pack paths
                       e.g., {"SARAH": {"front": Path(...), "three_quarter": Path(...)}}
        constraints: Renderer-specific constraints for compilation.
                    Use PERMISSIVE_CONSTRAINTS for non-Veo renderers.

    Returns:
        List of compiled renderer API request dicts
    """
    adapter = VeoAdapter(project_dir)

    with open(script_path) as f:
        script_data = json.load(f)

    # 1. Prepare structure (creates YAML shot specs)
    adapter.prepare_export(script_data, identity_packs=identity_packs)

    # 2. Link assets to shots
    adapter.link_assets(assets_dir)

    # 3. Compile to renderer JSON (uses constraints for validation)
    compiled = adapter.compile_all_shots(constraints)

    return compiled


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python veo_adapter.py <project_dir> <script.json> <assets_dir>")
        sys.exit(1)

    requests = export_to_veo(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(f"Compiled {len(requests)} Veo API requests")
