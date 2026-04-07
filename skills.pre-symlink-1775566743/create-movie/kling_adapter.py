#!/usr/bin/env python3
# /// script
# dependencies = [
#     "pyyaml",
# ]
# ///
"""
Kling Adapter (KSML v0.1 Implementation)

Converts create-movie output into Kling Shot Markup Language (KSML)
for ingestion by the Kling Video API / Studio.

Implements:
- KSML v0.1 Schema (YAML)
- Intent/Gear Separation
- Prompt Compilation Rules
"""

import json
import shutil
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

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
            
            # Map script data to KSML Shot
            shot_entry = self._map_scene_to_shot(scene, scene_idx)
            
            # Compile the "Final Prompt" for reference (Kling uses this)
            # In KSML, the 'intent' is structured, but we can also pre-compile
            # the flat prompt if we want to bypass the KSML compiler.
            # But here we emit pure KSML.
            
            ksml["shots"].append(shot_entry)

        # Write YAML
        with open(self.ksml_file, "w") as f:
            yaml.dump(ksml, f, sort_keys=False, indent=2, default_flow_style=False)
            
        print(f"[KlingAdapter] Exported KSML v0.1 to {self.ksml_file}")

    def _map_scene_to_shot(self, scene: Dict, idx: int) -> Dict:
        """Map generic scene dict to KSML shot structure."""
        
        # Extract fields
        visual = scene.get("visual", "")
        action = " ".join(scene.get("action", []))
        shot_type = scene.get("shot_type", "static")
        lighting = scene.get("lighting", "cinematic lighting") # Standard field check
        
        # Construct KSML Shot
        shot = {
            "id": f"sh_{idx:03d}",
            "mode": "storyboard_then_i2v", # Default recommended mode
            "duration_s": scene.get("duration_seconds", 5),
            "intent": {
                "beat": f"Scene {idx}",
                "emotion": "neutral", # Default if not parsed
                "end_state": "hold on final pose" # Good default for Kling
            },
            "visual": {
                "subject": visual, # We might need to handle splitting subject/env if possible
                "action": action,
                "environment": "" # If visual contains it, we leave it in subject for now or split
            },
            "camera": {
                "framing": self._map_framing(shot_type),
                "movement": self._map_movement(shot_type),
                "lens_intent": "cinematic 50mm",
                "stabilization": "tripod" if "static" in shot_type.lower() else "gimbal"
            },
            "lighting": {
                "key": lighting,
                "fill": "soft cinematic"
            },
            "audio": {
                "dialog": [],
                "sfx": [],
                "music": "ambient score"
            }
        }
        
        # If we have image assets, we link them in 'storyboard' section
        # Logic to find image path handled by caller matching logic, 
        # but here we generate the structure.
        shot["storyboard"] = {
            "model": "fal-ai/nano-banana-pro",
            "keyframes": ["start"]
        }
        
        return shot

    def _map_framing(self, shot_type: str) -> str:
        """Map generic shot types to KSML framing."""
        st = shot_type.lower()
        if "close" in st or "cu" in st: return "Close-Up"
        if "wide" in st or "ws" in st: return "Wide Shot"
        if "medium" in st or "ms" in st: return "Medium Shot"
        return "Medium Shot"

    def _map_movement(self, shot_type: str) -> str:
        """Map generic shot types to camera movement."""
        st = shot_type.lower()
        if "pan" in st: return "Slow Pan"
        if "dolly" in st or "push" in st: return "Dolly In"
        if "track" in st: return "Tracking Shot"
        if "static" in st: return "Static"
        return "Slow Push-In" # Default safe movement

    def add_image_asset(self, source_path: Path, shot_id: str) -> Optional[str]:
        """Copy image asset and update KSML."""
        if not source_path.exists():
            return None
            
        filename = f"{shot_id}_start_frame{source_path.suffix}"
        dest_path = self.assets_dir / filename
        shutil.copy2(source_path, dest_path)
        
        # Update KSML file with relative path
        # Note: This requires re-reading/writing or holding state
        # For simplicity, we assume this is called during/after the main loop
        # We will return the relative path, and the caller is responsibly for
        # updating the structure if they are holding the dict.
        
        return str(dest_path.relative_to(self.export_dir))

def export_to_kling(project_dir: Path, script_path: Path, assets_dir: Path):
    """Main export entry point."""
    adapter = KlingAdapter(project_dir)
    
    with open(script_path) as f:
        script_data = json.load(f)
        
    project_assets = [] # Not used in this version yet
    
    # 1. Prepare Structure
    adapter.prepare_export(script_data, project_assets)
    
    # 2. Asset Matching & Linking
    # Re-open KSML to inject image paths
    with open(adapter.ksml_file) as f:
        ksml = yaml.safe_load(f)
        
    for shot in ksml["shots"]:
        sid = shot["id"]
        # Parse index from sh_001
        idx = int(sid.split("_")[1])
        
        # Find asset candidate
        candidates = [
            assets_dir / f"scene_{idx:03d}.png",
            assets_dir / f"keyframe_{idx:03d}.png",
            assets_dir / f"{idx:03d}.png"
        ]
        
        found_image = None
        for cand in candidates:
            if cand.exists():
                found_image = cand
                break
        
        if found_image:
            rel_path = adapter.add_image_asset(found_image, sid)
            # Inject into storyboard section
            shot["storyboard"]["image_path"] = rel_path
            
    # Write back
    with open(adapter.ksml_file, "w") as f:
        yaml.dump(ksml, f, sort_keys=False, indent=2, default_flow_style=False)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: python kling_adapter.py <project_dir> <script.json> <assets_dir>")
        sys.exit(1)
        
    export_to_kling(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
