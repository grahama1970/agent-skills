"""
HorusShotSpec Compiler: YAML → Veo API JSON

Transforms HorusShotSpec YAML files into Veo API-compatible JSON requests.
Includes validation layer for API constraints.
"""

import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


# Veo API constraints (from sanity/veo_references.py)
VEO_CONSTRAINTS = {
    "valid_durations": [4, 8, 16],
    "valid_aspect_ratios": ["16:9", "9:16", "1:1"],
    "max_references": 6,
    "weight_range": (0.0, 1.0),
    "max_prompt_length": 4000,
    "default_model": "veo-3.1-generate-preview",
    "supported_params": ["negative_prompt", "seed"],
}

# Default permissive constraints for non-Veo renderers.
# Accepts any duration (renderers clamp internally).
PERMISSIVE_CONSTRAINTS = {
    "valid_durations": list(range(1, 61)),  # 1-60s, renderer clamps
    "valid_aspect_ratios": ["16:9", "9:16", "1:1"],
    "max_references": 6,
    "weight_range": (0.0, 1.0),
    "max_prompt_length": 4000,
    "default_model": "generic",
    "supported_params": ["negative_prompt", "seed", "steps", "guidance_scale", "fps"],
}


class ValidationError(Exception):
    """Raised when shot spec fails validation."""
    pass


class CompilationError(Exception):
    """Raised when compilation to Veo JSON fails."""
    pass


@dataclass
class ReferenceImage:
    """Reference image for subject consistency."""
    path: str
    weight: float = 0.5
    
    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "weight": self.weight}


@dataclass
class ShotPrompt:
    """Shot prompt with positive and negative text."""
    text: str
    negative: str = "text overlays, watermarks, shaky camera, distorted faces, garbled speech"


@dataclass
class ShotReferences:
    """Reference images and frames for shot consistency."""
    subject_images: list[ReferenceImage] = field(default_factory=list)
    first_frame: str | None = None
    last_frame: str | None = None


@dataclass
class ShotControls:
    """Generation controls for reproducibility and safety."""
    seed: int | None = None
    safety: str = "default"


@dataclass
class RendererConfig:
    """Renderer configuration."""
    name: str = "veo"
    model: str = "veo-3.1-generate-preview"


@dataclass
class ShotMetadata:
    """Metadata for scene organization."""
    scene: str | None = None
    act: str | None = None
    sequence_order: int | None = None
    notes: str | None = None


@dataclass
class HorusShotSpec:
    """Complete shot specification."""
    shot_id: str
    prompt: ShotPrompt
    duration_s: int
    aspect_ratio: str
    resolution: str = "1080p"
    references: ShotReferences | None = None
    controls: ShotControls | None = None
    renderer: RendererConfig | None = None
    metadata: ShotMetadata | None = None


def validate_shot_spec(spec: dict[str, Any], constraints: dict[str, Any] | None = None) -> list[str]:
    """
    Validate a shot spec dictionary against renderer constraints.

    Args:
        spec: Shot spec dict
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS)

    Returns list of validation errors (empty if valid).
    """
    c = constraints or VEO_CONSTRAINTS
    errors: list[str] = []

    # Required fields
    if "shot_id" not in spec:
        errors.append("Missing required field: shot_id")

    if "prompt" not in spec:
        errors.append("Missing required field: prompt")
    elif not isinstance(spec["prompt"], dict):
        errors.append("prompt must be an object with 'text' field")
    elif "text" not in spec["prompt"]:
        errors.append("prompt.text is required")
    elif len(spec["prompt"].get("text", "")) > c["max_prompt_length"]:
        errors.append(f"prompt.text exceeds max length of {c['max_prompt_length']}")

    if "duration_s" not in spec:
        errors.append("Missing required field: duration_s")
    elif spec["duration_s"] not in c["valid_durations"]:
        errors.append(f"duration_s must be one of {c['valid_durations']}, got {spec['duration_s']}")

    if "aspect_ratio" not in spec:
        errors.append("Missing required field: aspect_ratio")
    elif spec["aspect_ratio"] not in c["valid_aspect_ratios"]:
        errors.append(f"aspect_ratio must be one of {c['valid_aspect_ratios']}, got {spec['aspect_ratio']}")

    # Optional field validation
    if "references" in spec and spec["references"]:
        refs = spec["references"]
        if "subject_images" in refs and refs["subject_images"]:
            if len(refs["subject_images"]) > c["max_references"]:
                errors.append(f"subject_images count ({len(refs['subject_images'])}) exceeds max of {c['max_references']}")

            for i, img in enumerate(refs["subject_images"]):
                if isinstance(img, dict):
                    weight = img.get("weight", 0.5)
                    min_w, max_w = c["weight_range"]
                    if not (min_w <= weight <= max_w):
                        errors.append(f"subject_images[{i}].weight ({weight}) must be between {min_w} and {max_w}")

    if "controls" in spec and spec["controls"]:
        safety = spec["controls"].get("safety", "default")
        if safety not in ["default", "strict"]:
            errors.append(f"controls.safety must be 'default' or 'strict', got '{safety}'")

    return errors


def parse_shot_spec(yaml_content: str | dict[str, Any], constraints: dict[str, Any] | None = None) -> HorusShotSpec:
    """
    Parse YAML content or dict into HorusShotSpec dataclass.

    Args:
        yaml_content: YAML string or already-parsed dict
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS)

    Returns:
        HorusShotSpec instance

    Raises:
        ValidationError: If spec fails validation
    """
    if isinstance(yaml_content, str):
        spec = yaml.safe_load(yaml_content)
    else:
        spec = yaml_content

    # Validate
    errors = validate_shot_spec(spec, constraints)
    if errors:
        raise ValidationError(f"Shot spec validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    # Parse prompt
    prompt_data = spec["prompt"]
    prompt = ShotPrompt(
        text=prompt_data["text"],
        negative=prompt_data.get("negative", ShotPrompt.negative)
    )
    
    # Parse references
    references = None
    if "references" in spec and spec["references"]:
        refs_data = spec["references"]
        subject_images = []
        for img in refs_data.get("subject_images", []) or []:
            if isinstance(img, dict):
                subject_images.append(ReferenceImage(
                    path=img["path"],
                    weight=img.get("weight", 0.5)
                ))
            else:
                subject_images.append(ReferenceImage(path=img))
        
        references = ShotReferences(
            subject_images=subject_images,
            first_frame=refs_data.get("first_frame"),
            last_frame=refs_data.get("last_frame")
        )
    
    # Parse controls
    controls = None
    if "controls" in spec and spec["controls"]:
        ctrl_data = spec["controls"]
        controls = ShotControls(
            seed=ctrl_data.get("seed"),
            safety=ctrl_data.get("safety", "default")
        )
    
    # Parse renderer
    renderer = None
    if "renderer" in spec and spec["renderer"]:
        rend_data = spec["renderer"]
        renderer = RendererConfig(
            name=rend_data.get("name", "veo"),
            model=rend_data.get("model", VEO_CONSTRAINTS["default_model"])
        )
    
    # Parse metadata
    metadata = None
    if "metadata" in spec and spec["metadata"]:
        meta_data = spec["metadata"]
        metadata = ShotMetadata(
            scene=meta_data.get("scene"),
            act=meta_data.get("act"),
            sequence_order=meta_data.get("sequence_order"),
            notes=meta_data.get("notes")
        )
    
    return HorusShotSpec(
        shot_id=spec["shot_id"],
        prompt=prompt,
        duration_s=spec["duration_s"],
        aspect_ratio=spec["aspect_ratio"],
        resolution=spec.get("resolution", "1080p"),
        references=references,
        controls=controls,
        renderer=renderer,
        metadata=metadata
    )


def compile_to_veo_json(shot: HorusShotSpec, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Compile HorusShotSpec to renderer API JSON request format.

    Args:
        shot: Parsed shot specification
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS).
                     The "supported_params" key controls which optional params
                     are included in the compiled output.

    Returns:
        Dict ready to be serialized to JSON for the target renderer
    """
    c = constraints or VEO_CONSTRAINTS
    supported = set(c.get("supported_params", ["negative_prompt", "seed"]))

    # Build the API request structure
    veo_request: dict[str, Any] = {
        "prompt": shot.prompt.text.strip(),
        "config": {
            "duration_seconds": shot.duration_s,
            "aspect_ratio": shot.aspect_ratio,
        }
    }

    # Add negative prompt only if supported by target renderer
    if shot.prompt.negative and "negative_prompt" in supported:
        veo_request["config"]["negative_prompt"] = shot.prompt.negative

    # Add model
    model = c.get("default_model", VEO_CONSTRAINTS["default_model"])
    if shot.renderer:
        model = shot.renderer.model
    veo_request["model"] = model
    
    # Add reference images if present
    if shot.references and shot.references.subject_images:
        veo_request["references"] = {
            "subject_images": [img.to_dict() for img in shot.references.subject_images]
        }
        if shot.references.first_frame:
            veo_request["references"]["first_frame"] = shot.references.first_frame
        if shot.references.last_frame:
            veo_request["references"]["last_frame"] = shot.references.last_frame
    
    # Add controls
    if shot.controls:
        if shot.controls.seed is not None:
            veo_request["config"]["seed"] = shot.controls.seed
        if shot.controls.safety:
            veo_request["config"]["safety_filter"] = shot.controls.safety
    
    # Add metadata as separate field (not sent to API, but useful for tracking)
    if shot.metadata:
        veo_request["_metadata"] = {
            "shot_id": shot.shot_id,
            "scene": shot.metadata.scene,
            "act": shot.metadata.act,
            "sequence_order": shot.metadata.sequence_order,
            "notes": shot.metadata.notes
        }
    else:
        veo_request["_metadata"] = {"shot_id": shot.shot_id}
    
    return veo_request


def compile_yaml_to_veo_json(yaml_content: str | dict[str, Any], constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Convenience function: validate, parse, and compile YAML to JSON in one step.

    Args:
        yaml_content: YAML string or already-parsed dict
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS)

    Returns:
        Renderer API JSON request dict

    Raises:
        ValidationError: If spec fails validation
    """
    shot = parse_shot_spec(yaml_content, constraints)
    return compile_to_veo_json(shot, constraints)


def compile_yaml_file(yaml_path: str | Path, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Load and compile a YAML file to renderer JSON.

    Args:
        yaml_path: Path to YAML file
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS)

    Returns:
        Renderer API JSON request dict

    Raises:
        ValidationError: If spec fails validation
        FileNotFoundError: If file doesn't exist
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    with open(path) as f:
        content = f.read()

    return compile_yaml_to_veo_json(content, constraints)


def compile_shots_batch(yaml_contents: list[str | dict[str, Any]], constraints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    Compile multiple shots to renderer JSON.

    Args:
        yaml_contents: List of YAML strings or dicts
        constraints: Renderer-specific constraints (defaults to VEO_CONSTRAINTS)

    Returns:
        List of renderer API JSON requests

    Raises:
        ValidationError: If any spec fails validation (includes shot index)
    """
    results = []
    for i, content in enumerate(yaml_contents):
        try:
            results.append(compile_yaml_to_veo_json(content, constraints))
        except ValidationError as e:
            raise ValidationError(f"Shot {i}: {e}")
    return results


if __name__ == "__main__":
    # Demo: compile the example from the schema
    example_yaml = """
shot_id: "ACT1_SC02_SHOT03"
prompt:
  text: >
    A tense noir interrogation in a dim room. Slow dolly push toward the suspect.
    Hard side-key lighting, deep shadows. Subtle room tone.
    Dialogue: "Where were you last night?"
  negative: "text overlays, watermarks, shaky camera"
duration_s: 8
aspect_ratio: "16:9"
resolution: "1080p"
references:
  subject_images:
    - path: "./assets/detective.png"
      weight: 0.7
controls:
  seed: 42
  safety: "default"
renderer:
  name: "veo"
  model: "veo-3.1-generate-preview"
metadata:
  scene: "SC02"
  act: "ACT1"
  sequence_order: 3
"""
    
    try:
        veo_json = compile_yaml_to_veo_json(example_yaml)
        print("Compiled Veo API JSON:")
        print(json.dumps(veo_json, indent=2))
    except ValidationError as e:
        print(f"Validation failed: {e}")
