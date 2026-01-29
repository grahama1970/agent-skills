"""
Panel Generator for create-storyboard skill.

Generates visual panels at multiple fidelity levels:
- sketch: ASCII/text diagrams with shot annotations
- reference: Placeholder panels with composition guides
- generated: AI-generated images via /create-image
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


@dataclass  
class PanelConfig:
    """Configuration for panel generation."""
    width: int = 640
    height: int = 360  # 16:9 aspect ratio
    bg_color: tuple = (40, 40, 50)
    text_color: tuple = (220, 220, 220)
    accent_color: tuple = (100, 150, 200)
    grid_color: tuple = (60, 60, 70)


def draw_rule_of_thirds(draw: ImageDraw.Draw, config: PanelConfig):
    """Draw rule of thirds grid overlay."""
    w, h = config.width, config.height
    
    # Vertical lines
    draw.line([(w // 3, 0), (w // 3, h)], fill=config.grid_color, width=1)
    draw.line([(2 * w // 3, 0), (2 * w // 3, h)], fill=config.grid_color, width=1)
    
    # Horizontal lines
    draw.line([(0, h // 3), (w, h // 3)], fill=config.grid_color, width=1)
    draw.line([(0, 2 * h // 3), (w, 2 * h // 3)], fill=config.grid_color, width=1)


def draw_center_guides(draw: ImageDraw.Draw, config: PanelConfig):
    """Draw center crosshairs."""
    w, h = config.width, config.height
    cx, cy = w // 2, h // 2
    
    # Center cross
    draw.line([(cx - 20, cy), (cx + 20, cy)], fill=config.grid_color, width=1)
    draw.line([(cx, cy - 20), (cx, cy + 20)], fill=config.grid_color, width=1)


def draw_safe_area(draw: ImageDraw.Draw, config: PanelConfig):
    """Draw action safe / title safe areas."""
    w, h = config.width, config.height
    
    # Action safe (90%)
    margin_a = int(min(w, h) * 0.05)
    draw.rectangle(
        [margin_a, margin_a, w - margin_a, h - margin_a],
        outline=config.grid_color, width=1
    )
    
    # Title safe (80%)
    margin_t = int(min(w, h) * 0.10)
    draw.rectangle(
        [margin_t, margin_t, w - margin_t, h - margin_t],
        outline=config.grid_color, width=1
    )


def generate_sketch_panel(shot: dict, config: PanelConfig, output_path: Path) -> Path:
    """
    Generate a sketch-fidelity panel with composition guides.
    
    This is fast and shows shot type, framing, and notes.
    """
    img = Image.new('RGB', (config.width, config.height), config.bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw composition guides
    draw_rule_of_thirds(draw, config)
    draw_center_guides(draw, config)
    draw_safe_area(draw, config)
    
    # Draw frame border
    draw.rectangle(
        [2, 2, config.width - 3, config.height - 3],
        outline=config.accent_color, width=2
    )
    
    # Shot type indicator (large, center)
    shot_code = shot.get('shot_code', 'MS')
    shot_name = shot.get('shot_name', 'Medium Shot')
    
    # Try to use a font, fall back to default
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Center shot code
    bbox = draw.textbbox((0, 0), shot_code, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (config.width - text_width) // 2
    y = (config.height - text_height) // 2 - 20
    draw.text((x, y), shot_code, fill=config.text_color, font=font_large)
    
    # Shot name below
    bbox = draw.textbbox((0, 0), shot_name, font=font_medium)
    text_width = bbox[2] - bbox[0]
    x = (config.width - text_width) // 2
    draw.text((x, y + text_height + 10), shot_name, fill=config.accent_color, font=font_medium)
    
    # Scene/shot number (top left)
    scene_shot = f"Scene {shot.get('scene_number', 1)} - Shot {shot.get('shot_number', 1)}"
    draw.text((10, 10), scene_shot, fill=config.text_color, font=font_small)
    
    # Duration (top right)
    duration = f"{shot.get('duration', 0):.1f}s"
    bbox = draw.textbbox((0, 0), duration, font=font_small)
    draw.text((config.width - bbox[2] - 10, 10), duration, fill=config.text_color, font=font_small)
    
    # Camera movement (bottom left)
    movement = shot.get('camera_movement', 'static')
    draw.text((10, config.height - 25), f"[{movement}]", fill=config.accent_color, font=font_small)
    
    # Lens (bottom right)
    lens = shot.get('lens_suggestion', '50mm')
    bbox = draw.textbbox((0, 0), lens, font=font_small)
    draw.text((config.width - bbox[2] - 10, config.height - 25), lens, fill=config.accent_color, font=font_small)
    
    # Description (bottom, truncated)
    description = shot.get('description', '')[:60]
    if len(shot.get('description', '')) > 60:
        description += '...'
    bbox = draw.textbbox((0, 0), description, font=font_small)
    text_width = bbox[2] - bbox[0]
    x = (config.width - text_width) // 2
    draw.text((x, config.height - 45), description, fill=(180, 180, 180), font=font_small)
    
    # Save
    img.save(output_path)
    return output_path


def generate_reference_panel(shot: dict, config: PanelConfig, output_path: Path) -> Path:
    """
    Generate a reference-fidelity panel.
    
    Includes framing guide visualization (stick figure placeholders).
    """
    img = Image.new('RGB', (config.width, config.height), config.bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw guides
    draw_rule_of_thirds(draw, config)
    
    shot_code = shot.get('shot_code', 'MS')
    
    # Draw stick figure placeholder based on shot type
    cx, cy = config.width // 2, config.height // 2
    
    if shot_code in ['EWS', 'WS']:
        # Small figure, lots of environment
        head_radius = 8
        body_height = 30
        y_offset = 20
    elif shot_code in ['FS', 'MWS']:
        # Medium figure
        head_radius = 15
        body_height = 80
        y_offset = 0
    elif shot_code in ['MS', 'MCU']:
        # Larger figure
        head_radius = 25
        body_height = 120
        y_offset = -30
    elif shot_code in ['CU', 'ECU']:
        # Just face
        head_radius = 60
        body_height = 0
        y_offset = -20
    else:
        head_radius = 20
        body_height = 80
        y_offset = 0
    
    # Draw stick figure
    figure_color = (150, 150, 160)
    head_y = cy + y_offset
    
    # Head
    draw.ellipse(
        [cx - head_radius, head_y - head_radius, 
         cx + head_radius, head_y + head_radius],
        outline=figure_color, width=2
    )
    
    # Body (if not extreme close-up)
    if body_height > 0:
        draw.line(
            [(cx, head_y + head_radius), (cx, head_y + head_radius + body_height)],
            fill=figure_color, width=2
        )
        # Arms
        arm_y = head_y + head_radius + body_height // 4
        draw.line([(cx - 30, arm_y + 20), (cx, arm_y), (cx + 30, arm_y + 20)], 
                  fill=figure_color, width=2)
        # Legs
        leg_y = head_y + head_radius + body_height
        draw.line([(cx, leg_y), (cx - 20, leg_y + 40)], fill=figure_color, width=2)
        draw.line([(cx, leg_y), (cx + 20, leg_y + 40)], fill=figure_color, width=2)
    
    # Add shot overlay info
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()
    
    # Semi-transparent info bar at bottom
    info_bar = Image.new('RGBA', (config.width, 40), (0, 0, 0, 180))
    img_rgba = img.convert('RGBA')
    img_rgba.paste(info_bar, (0, config.height - 40), info_bar)
    
    # Convert back and draw text
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)
    
    info_text = f"S{shot.get('scene_number', 1)}-{shot.get('shot_number', 1)} | {shot.get('shot_name', '')} | {shot.get('duration', 0):.1f}s | {shot.get('camera_movement', 'static')}"
    draw.text((10, config.height - 30), info_text, fill=(200, 200, 200), font=font)
    
    img.save(output_path)
    return output_path


def generate_panels(
    shot_plan: dict,
    output_dir: Path,
    fidelity: str = 'sketch',
    config: Optional[PanelConfig] = None
) -> list[Path]:
    """
    Generate all panels from a shot plan.
    
    Args:
        shot_plan: Shot plan dict from camera_planner
        output_dir: Directory to save panels
        fidelity: 'sketch', 'reference', or 'generated'
        config: Panel configuration
        
    Returns:
        List of generated panel paths
    """
    if config is None:
        config = PanelConfig()
    
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths = []
    
    for shot in shot_plan.get('shots', []):
        scene_num = shot.get('scene_number', 1)
        shot_num = shot.get('shot_number', 1)
        filename = f"panel_s{scene_num:02d}_sh{shot_num:02d}.png"
        output_path = output_dir / filename
        
        if fidelity == 'sketch':
            generate_sketch_panel(shot, config, output_path)
        elif fidelity == 'reference':
            generate_reference_panel(shot, config, output_path)
        elif fidelity == 'generated':
            # Explicitly fail to avoid silent stub behavior; orchestrator will emit a structured error.
            raise RuntimeError(
                "fidelity='generated' requires /create-image skill integration (not yet implemented).\n"
                "Handoff hint: Call /create-image with --prompt and --add-dir context for each panel."
            )
        else:
            generate_sketch_panel(shot, config, output_path)
        
        generated_paths.append(output_path)
    
    return generated_paths


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        # Demo
        sample_shot_plan = {
            "title": "Test",
            "shots": [
                {
                    "scene_number": 1,
                    "shot_number": 1,
                    "shot_code": "WS",
                    "shot_name": "Wide Shot",
                    "description": "Sarah enters the apartment",
                    "duration": 3.0,
                    "camera_movement": "static",
                    "framing_guide": "Full body with environment",
                    "lens_suggestion": "24mm"
                },
                {
                    "scene_number": 1,
                    "shot_number": 2,
                    "shot_code": "CU",
                    "shot_name": "Close-Up",
                    "description": "Fear in her eyes",
                    "duration": 2.0,
                    "camera_movement": "push_in",
                    "framing_guide": "Face fills frame",
                    "lens_suggestion": "85mm"
                }
            ]
        }
        
        output_dir = Path("./test_panels")
        paths = generate_panels(sample_shot_plan, output_dir, fidelity='sketch')
        print(f"Generated {len(paths)} panels in {output_dir}")
        for p in paths:
            print(f"  - {p}")
    else:
        # Load shot plan from file
        filepath = Path(sys.argv[1])
        shot_plan = json.loads(filepath.read_text())
        
        fidelity = 'sketch'
        output_dir = Path('./panels')
        
        for i, arg in enumerate(sys.argv):
            if arg == '--fidelity' and i + 1 < len(sys.argv):
                fidelity = sys.argv[i + 1]
            elif arg == '--output-dir' and i + 1 < len(sys.argv):
                output_dir = Path(sys.argv[i + 1])
        
        paths = generate_panels(shot_plan, output_dir, fidelity=fidelity)
        print(f"Generated {len(paths)} panels in {output_dir}")
