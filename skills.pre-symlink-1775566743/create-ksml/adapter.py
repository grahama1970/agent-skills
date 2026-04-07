#!/usr/bin/env python3
# /// script
# dependencies = [
#     "pyyaml",
#     "typer",
#     "python-dotenv",
# ]
# ///
"""
Kling Adapter (KSML v0.1 Implementation)

Converts create-movie output into Kling Shot Markup Language (KSML)
for ingestion by the Kling Video API / Studio.
"""

import json
import shutil
import yaml
import typer
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import os

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass  # python-dotenv optional; .env loaded by run.sh

# Non-destructive feature flags; all default to False to retain existing behavior
KSML_FEATURE_FLAGS = {
    "ENABLE_SCHEMA_VALIDATION": os.environ.get("KSML_ENABLE_SCHEMA_VALIDATION", "0") == "1",
    "STRICT_MODE": os.environ.get("KSML_STRICT_MODE", "0") == "1",
}

def _validate_ksml_schema(document: dict) -> bool:
    # Stub: only runs when ENABLE_SCHEMA_VALIDATION=1; returns True by default
    if not KSML_FEATURE_FLAGS["ENABLE_SCHEMA_VALIDATION"]:
        return True
    # TODO: Implement schema validation per acceptance criteria without breaking defaults
    return True

app = typer.Typer(help="Convert scripts to KSML")

@app.callback()
def main():
    """KSML Adapter CLI."""
    pass

class KlingAdapter:
    """Adapts create-movie output to KSML v0.1."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.export_dir = output_dir / "kling_export"
        self.assets_dir = self.export_dir / "assets"
        self.ksml_file = self.export_dir / "project.ksml"

    def prepare_export(self, script_data: Dict, project_assets: List[Dict]):
        """Prepare the export directory and KSML file."""
        if self.export_dir.exists():
            shutil.rmtree(self.export_dir)
        
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        
        # KSML Root Structure
        ksml = {
            "project": {
                "name": script_data.get("title", "Untitled Dream"),
                "created_at": datetime.now().isoformat(),
                "version": "0.1",
                "aspect_ratio": "16:9"
            },
            "style": {
                "overall_vibe": script_data.get("style", "Cinematic, Photorealistic, High Budget"),
                "base_gear": {
                    "camera": "Arri Alexa 65",
                    "film_stock": "Kodak Vision3 500T",
                    "lens": "Panavision Primo 70mm"
                }
            },
            "shots": []
        }

        scenes = script_data.get("scenes", [])
        
        for i, scene in enumerate(scenes):
            scene_idx = i + 1
            shot_entry = self._map_scene_to_shot(scene, scene_idx)
            ksml["shots"].append(shot_entry)

        # Write YAML
        with open(self.ksml_file, "w") as f:
            yaml.dump(ksml, f, sort_keys=False, indent=2, default_flow_style=False)
            
        print(f"[KlingAdapter] Exported KSML v0.1 to {self.ksml_file}")

    def _map_scene_to_shot(self, scene: Dict, idx: int) -> Dict:
        """Map generic scene dict to KSML shot structure."""
        visual = scene.get("visual", "")
        action = " ".join(scene.get("action", []))
        shot_type = scene.get("shot_type", "static")
        lighting = scene.get("lighting", "cinematic lighting")
        
        # Helper: Get param or default
        def p(key, default):
            return scene.get(key) or default

        shot = {
            "id": f"sh_{idx:03d}",
            "mode": "storyboard_then_i2v",
            "duration_s": scene.get("duration_seconds", 5),
            "intent": {
                "beat": f"Scene {idx}",
                "emotion": p("emotion", "neutral"),
                "end_state": "hold on final pose"
            },
            "visual": {
                "subject": visual,
                "action": action,
                "environment": ""
            },
            "camera": {
                "framing": p("shot_size", self._map_framing(shot_type)),
                "movement": p("camera_movement", self._map_movement(shot_type)),
                "lens_intent": p("lens_focal_length", "cinematic 50mm"),
                "stabilization": p("camera_stabilization", ("tripod" if "static" in shot_type.lower() else "gimbal"))
            },
            "lighting": {
                "key": p("lighting_key_type", lighting),
                "fill": p("lighting_fill", "soft cinematic")
            },
            "audio": {
                "dialog": [],
                "sfx": [],
                "music": "ambient score"
            }
        }
        
        # Add tech specs to intent for context if they exist
        if "lighting_key_angle" in scene:
            shot["lighting"]["angle"] = scene["lighting_key_angle"]
        if "lighting_contrast" in scene:
            shot["lighting"]["contrast"] = scene["lighting_contrast"]
        
        shot["storyboard"] = {
            "model": "fal-ai/nano-banana-pro",
            "keyframes": ["start"]
        }
        
        return shot

    def _map_framing(self, shot_type: str) -> str:
        st = shot_type.lower()
        if "close" in st or "cu" in st: return "Close-Up"
        if "wide" in st or "ws" in st: return "Wide Shot"
        if "medium" in st or "ms" in st: return "Medium Shot"
        return "Medium Shot"

    def _map_movement(self, shot_type: str) -> str:
        st = shot_type.lower()
        if "pan" in st: return "Slow Pan"
        if "dolly" in st or "push" in st: return "Dolly In"
        if "track" in st: return "Tracking Shot"
        if "static" in st: return "Static"
        return "Slow Push-In"

    def add_image_asset(self, source_path: Path, shot_id: str) -> Optional[str]:
        if not source_path.exists():
            return None
            
        filename = f"{shot_id}_start_frame{source_path.suffix}"
        dest_path = self.assets_dir / filename
        shutil.copy2(source_path, dest_path)
        
        return str(dest_path.relative_to(self.export_dir))

@app.command()
def convert(
    script: Path = typer.Option(..., "--script", "-s", help="Path to input script JSON"),
    assets: Path = typer.Option(..., "--assets", "-a", help="Directory containing asset images"),
    output: Path = typer.Option(Path("./output"), "--output", "-o", help="Output directory for KSML project"),
):
    """Convert a movie script to KSML project."""
    if not script.exists():
        typer.echo(f"Script not found: {script}", err=True)
        raise typer.Exit(1)
        
    if not assets.exists():
        typer.echo(f"Assets directory not found: {assets}", err=True)
        raise typer.Exit(1)

    adapter = KlingAdapter(output)
    
    with open(script) as f:
        script_data = json.load(f)
        
    project_assets = []
    
    # 1. Prepare Structure
    adapter.prepare_export(script_data, project_assets)
    
    # 2. Asset Matching & Linking
    with open(adapter.ksml_file) as f:
        ksml = yaml.safe_load(f)
        
    for shot in ksml["shots"]:
        sid = shot["id"]
        try:
            idx = int(sid.split("_")[1])
        except (IndexError, ValueError):
            continue
        
        candidates = [
            assets / f"scene_{idx:03d}.png",
            assets / f"keyframe_{idx:03d}.png",
            assets / f"{idx:03d}.png"
        ]
        
        found_image = None
        for cand in candidates:
            if cand.exists():
                found_image = cand
                break
        
        if found_image:
            rel_path = adapter.add_image_asset(found_image, sid)
            shot["storyboard"]["image_path"] = rel_path
            
    with open(adapter.ksml_file, "w") as f:
        yaml.dump(ksml, f, sort_keys=False, indent=2, default_flow_style=False)
        
    typer.echo(f"Conversion complete: {adapter.ksml_file}")

if __name__ == "__main__":
    app()
