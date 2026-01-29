#!/usr/bin/env python3
"""Icon Creator - Fetch and style icons for Stream Deck.

Uses Lucide CDN (unpkg) for SVG icons, ImageMagick for conversion.
Generates 72x72 PNG icons with white (inactive) and colored (active) states.
"""
import sys
import os
import argparse
import subprocess
import shutil
import json
import base64
from pathlib import Path

# Default active color (cyan)
DEFAULT_ACTIVE_COLOR = "#00FFFF"

def load_lucide_list():
    """Load the list of Lucide icons from the local JSON file."""
    json_path = Path(__file__).parent / "lucide_icons.json"
    if json_path.exists():
        with open(json_path, 'r') as f:
            return json.load(f)
    return []

def search_lucide(query: str, limit: int = 10):
    """Search for icons matching the query."""
    icons = load_lucide_list()
    if not icons:
        return []
    
    # Simple substring match and fuzzy-ish match
    query = query.lower().replace(" ", "-")
    matches = [i for i in icons if query in i]
    
    # Sort by relevance (shorter names first)
    matches.sort(key=len)
    
    return matches[:limit]

def get_base64_image(image_path: Path):
    """Convert image to base64 for embedding in HTML."""
    import base64
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def generate_svg_ai(prompt: str, output_path: Path):
    """Generate SVG code using LLM (scillm, claude, or gemini)."""
    print(f"🎨 Generating custom SVG for: {prompt}")
    
    # System prompt for SVG generation
    system_prompt = (
        "You are an expert SVG designer. Create a clean, minimalist, high-contrast SVG icon "
        "based on the user prompt. Use a 24x24 viewBox. \n"
        "Design Rules:\n"
        "- Use thick strokes (stroke-width: 2 or more).\n"
        "- Use rounded corners (stroke-linejoin: round, stroke-linecap: round).\n"
        "- Use 'currentColor' for the stroke.\n"
        "- The icon should be centered and occupy most of the viewBox.\n"
        "- Return ONLY the raw <svg>...</svg> code, no markdown blocks, no explanations."
    )
    
    full_prompt = f"{system_prompt}\n\nUser prompt: {prompt}"
    
    import shutil
    # Try Claude first (usually best at SVG)
    try:
        if shutil.which("claude"):
            print("🤖 Using Claude for SVG generation...")
            result = subprocess.run(["claude", "-p", full_prompt], capture_output=True, text=True)
            if result.returncode == 0 and "<svg" in result.stdout:
                svg_code = result.stdout.strip()
                if "```svg" in svg_code:
                    svg_code = svg_code.split("```svg")[1].split("```")[0].strip()
                elif "```" in svg_code:
                    svg_code = svg_code.split("```")[1].split("```")[0].strip()
                output_path.write_text(svg_code)
                return True
    except Exception as e:
        print(f"⚠️ Claude generation failed: {e}")

    # Try Gemini next
    try:
        if shutil.which("gemini"):
            print("🤖 Using Gemini for SVG generation...")
            result = subprocess.run(["gemini", "-p", full_prompt], capture_output=True, text=True)
            if result.returncode == 0 and "<svg" in result.stdout:
                svg_code = result.stdout.strip()
                if "```svg" in svg_code:
                    svg_code = svg_code.split("```svg")[1].split("```")[0].strip()
                elif "```" in svg_code:
                    svg_code = svg_code.split("```")[1].split("```")[0].strip()
                output_path.write_text(svg_code)
                return True
    except Exception as e:
        print(f"⚠️ Gemini generation failed: {e}")

    # Fallback to scillm
    print("🤖 Using scillm for SVG generation...")
    scillm_script = Path(__file__).parent.parent / "scillm" / "run.sh"
    if not scillm_script.exists():
        scillm_script = Path(os.getcwd()) / ".pi" / "skills" / "scillm" / "run.sh"
    
    env = os.environ.copy()
    if "CHUTES_MODEL" in env and "CHUTES_MODEL_ID" not in env:
        env["CHUTES_MODEL_ID"] = env["CHUTES_MODEL"]
    
    cmd = [str(scillm_script), "batch", "single", full_prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    if result.returncode == 0 and "<svg" in result.stdout:
        svg_code = result.stdout.strip()
        if "```svg" in svg_code:
            svg_code = svg_code.split("```svg")[1].split("```")[0].strip()
        elif "```" in svg_code:
            svg_code = svg_code.split("```")[1].split("```")[0].strip()
        output_path.write_text(svg_code)
        return True
    
    print(f"❌ All AI generation methods failed.")
    return False

def check_dependencies():
    """Verify required tools are available."""
    missing = []
    for tool in ["identify", "convert", "curl"]:
        if not shutil.which(tool):
            missing.append(tool)
    
    if missing:
        print(f"❌ Missing required dependencies: {', '.join(missing)}")
        print("Install with: sudo apt install imagemagick curl")
        sys.exit(1)

def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def fetch_lucide_svg(icon_name: str, output_path: Path) -> bool:
    """Fetch SVG from Lucide CDN via unpkg."""
    # Lucide icons are available at unpkg
    url = f"https://unpkg.com/lucide-static@latest/icons/{icon_name}.svg"
    
    print(f"Fetching: {url}")
    result = subprocess.run(
        ["curl", "-s", "-f", "-L", "-o", str(output_path), url],
        capture_output=True
    )
    
    if result.returncode != 0:
        print(f"❌ Icon '{icon_name}' not found on Lucide CDN")
        return False
    
    # Verify it's actually an SVG
    if output_path.exists() and output_path.stat().st_size > 0:
        content = output_path.read_text()
        if "<svg" in content:
            return True
    
    print(f"❌ Downloaded file is not a valid SVG")
    return False

def svg_to_png(svg_path: Path, png_path: Path, color: str, size: int = 72):
    """Convert SVG to PNG with specified color using ImageMagick."""
    # ImageMagick convert with color replacement
    # The SVG stroke is typically "currentColor" or black - we colorize it
    cmd = [
        "convert",
        "-background", "none",
        "-density", "300",  # High density for crisp rendering
        str(svg_path),
        "-resize", f"{size}x{size}",
        "-gravity", "center",
        "-extent", f"{size}x{size}",
        "-fill", color,
        "-colorize", "100",
        str(png_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Conversion failed: {result.stderr}")
        return False
    return True

def generate_states_from_png(input_path: Path, output_name: str, target_dir: Path, active_color: str):
    """Generate white and active state PNGs from an existing image."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("❌ Pillow not installed. Install with: pip install Pillow")
        sys.exit(1)
    
    img = Image.open(input_path).convert("RGBA")
    img = ImageOps.contain(img, (72, 72))
    
    # Create empty 72x72 canvas
    final_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    offset = ((72 - img.width) // 2, (72 - img.height) // 2)
    final_img.paste(img, offset, img)
    
    # Generate Inactive (White)
    white_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    for x in range(72):
        for y in range(72):
            r, g, b, a = final_img.getpixel((x, y))
            if a > 0:
                white_img.putpixel((x, y), (255, 255, 255, a))
    
    # Generate Active (user-specified color)
    active_rgb = hex_to_rgb(active_color)
    active_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    for x in range(72):
        for y in range(72):
            r, g, b, a = final_img.getpixel((x, y))
            if a > 0:
                active_img.putpixel((x, y), (*active_rgb, a))
    
    # Save results
    target_dir.mkdir(parents=True, exist_ok=True)
    white_path = target_dir / f"{output_name}_white.png"
    active_path = target_dir / f"{output_name}_active.png"
    
    white_img.save(str(white_path))
    active_img.save(str(active_path))
    print(f"✓ Generated: {white_path}")
    print(f"✓ Generated: {active_path}")

def fetch_icon(icon_name: str, output_name: str, target_dir: Path, active_color: str):
    """Fetch icon from Lucide CDN and generate both states."""
    check_dependencies()
    
    # Temp paths
    svg_path = Path("/tmp") / f"{icon_name}.svg"
    white_png = Path("/tmp") / f"{output_name}_white.png"
    active_png = Path("/tmp") / f"{output_name}_active.png"
    
    # Fetch SVG
    if not fetch_lucide_svg(icon_name, svg_path):
        # Try with hyphens replaced by dashes (common naming)
        alt_name = icon_name.replace("_", "-")
        if alt_name != icon_name and fetch_lucide_svg(alt_name, svg_path):
            pass
        else:
            sys.exit(1)
    
    print(f"✓ Downloaded SVG: {svg_path}")
    
    # Convert to white PNG
    if not svg_to_png(svg_path, white_png, "#FFFFFF"):
        sys.exit(1)
    print(f"✓ Converted to white PNG")
    
    # Convert to active color PNG
    if not svg_to_png(svg_path, active_png, active_color):
        sys.exit(1)
    print(f"✓ Converted to active PNG ({active_color})")
    
    # Move to target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    final_white = target_dir / f"{output_name}_white.png"
    final_active = target_dir / f"{output_name}_active.png"
    
    shutil.move(str(white_png), str(final_white))
    shutil.move(str(active_png), str(final_active))
    
    # Verify size
    result = subprocess.run(
        ["identify", "-format", "%wx%h", str(final_white)],
        capture_output=True, text=True
    )
    size = result.stdout.strip()
    print(f"✓ Final size: {size}")
    print(f"✓ Output: {final_white}")
    print(f"✓ Output: {final_active}")

def generate_icon(input_path: str, output_name: str, target_dir: Path, active_color: str):
    """Generate icon states from a local file."""
    check_dependencies()
    
    path = Path(input_path)
    if not path.exists():
        print(f"❌ File not found: {input_path}")
        sys.exit(1)
    
    if path.suffix.lower() == ".svg":
        # Convert SVG directly
        white_png = Path("/tmp") / f"{output_name}_white.png"
        active_png = Path("/tmp") / f"{output_name}_active.png"
        
        svg_to_png(path, white_png, "#FFFFFF")
        svg_to_png(path, active_png, active_color)
        
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(white_png), str(target_dir / f"{output_name}_white.png"))
        shutil.move(str(active_png), str(target_dir / f"{output_name}_active.png"))
        
        print(f"✓ Generated from SVG: {target_dir}/{output_name}_*.png")
    else:
        # Use Pillow for raster images
        generate_states_from_png(path, output_name, target_dir, active_color)

def list_icons():
    """List popular Lucide icon names."""
    popular = [
        "folder", "file", "settings", "home", "user", "search",
        "play", "pause", "stop", "skip-forward", "skip-back",
        "volume-2", "volume-x", "mic", "mic-off", "camera",
        "monitor", "terminal", "code", "git-branch", "github",
        "chrome", "globe", "wifi", "bluetooth", "battery",
        "sun", "moon", "cloud", "download", "upload",
        "trash", "edit", "copy", "clipboard", "save",
        "refresh-cw", "power", "lock", "unlock", "eye",
        "bell", "message-square", "mail", "phone", "video",
    ]
    print("Popular Lucide icons:")
    for i, name in enumerate(popular, 1):
        print(f"  {name:<20}", end="")
        if i % 4 == 0:
            print()
    print("\n\nBrowse all: https://lucide.dev/icons")

def collaborative_workflow(query: str, output_name: str, target_dir: Path, active_color: str):
    """Multi-round collaborative icon selection workflow."""
    check_dependencies()
    
    print(f"🚀 Starting collaborative workflow for: {query}")
    
    current_query = query
    while True:
        candidates = search_lucide(current_query)
        if not candidates:
            print(f"❌ No icons found for '{current_query}'.")
            # Fallback: try to see if query is a direct name
            candidates = [current_query]
        
        # Prepare previews
        preview_dir = Path("/tmp/icon_previews")
        if preview_dir.exists():
            shutil.rmtree(preview_dir)
        preview_dir.mkdir(parents=True)
        
        questions = []
        candidate_map = {}
        
        print(f"Generating previews for {len(candidates)} candidates...")
        for i, icon in enumerate(candidates):
            svg_path = preview_dir / f"{icon}.svg"
            png_path = preview_dir / f"{icon}_preview.png"
            
            if fetch_lucide_svg(icon, svg_path):
                if svg_to_png(svg_path, png_path, "#555555", size=64):
                    b64 = get_base64_image(png_path)
                    candidate_map[str(i)] = icon
                    questions.append({
                        "id": str(i),
                        "text": f'<img src="data:image/png;base64,{b64} " width="64" height="64" class="mb-2"><br><b>{icon}</b>',
                        "type": "yes_no",
                        "recommendation": "yes" if i == 0 else "no",
                        "reason": "Top match" if i == 0 else "Alternative"
                    })
        
        # Add AI Generation option
        ai_svg_path = preview_dir / "ai_generated.svg"
        ai_png_path = preview_dir / "ai_generated_preview.png"
        
        # We'll offer to generate IF this is the first round OR if they specifically asked
        # For the very first round, we'll try to generate one matching the query
        if generate_svg_ai(current_query, ai_svg_path):
            if svg_to_png(ai_svg_path, ai_png_path, "#555555", size=64):
                b64 = get_base64_image(ai_png_path)
                candidate_map["ai"] = "ai_generated" # Marker for the temp file
                questions.append({
                    "id": "ai",
                    "text": f'<img src="data:image/png;base64,{b64} " width="64" height="64" class="mb-2"><br><b>AI Generated Custom Icon</b>',
                    "type": "yes_no",
                    "recommendation": "no",
                    "reason": "Custom design based on your prompt"
                })

        if not questions:
            print("❌ Failed to generate any previews.")
            return

        # Add a "None of these / Refine" question
        questions.append({
            "id": "refine",
            "text": "None of these work. Let's refine the search.",
            "type": "text",
            "recommendation": "",
            "reason": "Use this to search for something else"
        })

        # Run interview
        # We'll use the CLI tool to avoid complex imports
        questions_file = Path("/tmp/icon_questions.json")
        with open(questions_file, 'w') as f:
            json.dump({
                "title": f"Pick an icon for '{query}'",
                "context": f"Search results for '{current_query}'",
                "questions": questions
            }, f)
        
        # Call interview skill
        interview_script = Path(__file__).parent.parent / "interview" / "run.sh"
        if not interview_script.exists():
            # Try alternate path (if called from elsewhere)
            interview_script = Path(os.getcwd()) / ".pi" / "skills" / "interview" / "run.sh"

        print("Waiting for your selection in the interview form...")
        # Don't capture output so the user sees the URL/TUI
        subprocess.run([str(interview_script), "--file", str(questions_file)])
        
        # Parse response (last session)
        responses_dir = Path(__file__).parent.parent / "interview" / "sessions"
        if not responses_dir.exists():
            responses_dir = Path(os.getcwd()) / ".pi" / "skills" / "interview" / "sessions"
            
        sessions = sorted(responses_dir.glob("*.json"), key=os.path.getmtime)
        if not sessions:
            print("❌ No interview session found.")
            return
        
        with open(sessions[-1], 'r') as f:
            resp_data = json.load(f)
        
        responses = resp_data.get("responses", {})
        
        # Check if user refined
        refine_text = responses.get("refine", {}).get("value", "")
        if refine_text:
            current_query = refine_text
            print(f"Refining search to: {current_query}")
            continue
        
        # Find which one was picked
        picked_icon = None
        for qid, resp in responses.items():
            if qid != "refine" and resp.get("value") == "keep":
                picked_icon = candidate_map.get(qid)
                break
        
        if picked_icon:
            print(f"✅ Selected: {picked_icon}")
            if picked_icon == "ai_generated":
                # Process the temp AI SVG
                generate_icon(str(preview_dir / "ai_generated.svg"), output_name, target_dir, active_color)
            else:
                fetch_icon(picked_icon, output_name, target_dir, active_color)
            return
        else:
            print("No icon selected. Try again?")
            # If no selection and no refinement, maybe they just closed it?
            # We'll ask to refine or exit
            choice = input("No selection made. Search again? (y/n): ")
            if choice.lower() == 'y':
                current_query = input("New search term: ")
            else:
                return

def main():
    parser = argparse.ArgumentParser(
        description="Stream Deck icon creator using Lucide CDN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fetch folder --name my_folder
  %(prog)s fetch play --name play_button --active-color "#FF6600"
  %(prog)s generate ./icon.svg --name custom_icon
  %(prog)s list
        """
    )
    subparsers = parser.add_subparsers(dest="command")
    
    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch icon from Lucide CDN")
    fetch_parser.add_argument("icon", help="Lucide icon name (e.g., 'folder', 'play')")
    fetch_parser.add_argument("--name", required=True, help="Output filename (without extension)")
    fetch_parser.add_argument("--dir", default="./icon", help="Output directory (default: ./icon)")
    fetch_parser.add_argument("--active-color", default=DEFAULT_ACTIVE_COLOR, 
                              help=f"Active state color in hex (default: {DEFAULT_ACTIVE_COLOR})")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate states from local file")
    gen_parser.add_argument("path", help="Path to SVG or PNG file")
    gen_parser.add_argument("--name", required=True, help="Output filename (without extension)")
    gen_parser.add_argument("--dir", default="./icon", help="Output directory (default: ./icon)")
    gen_parser.add_argument("--active-color", default=DEFAULT_ACTIVE_COLOR,
                            help=f"Active state color in hex (default: {DEFAULT_ACTIVE_COLOR})")
    
    # List command
    subparsers.add_parser("list", help="List popular Lucide icon names")
    
    # Collaborative command
    collab_parser = subparsers.add_parser("collaborative", help="Collaborative search and selection")
    collab_parser.add_argument("query", help="Search keywords for the icon")
    collab_parser.add_argument("--name", required=True, help="Output filename (without extension)")
    collab_parser.add_argument("--dir", default="./icon", help="Output directory (default: ./icon)")
    collab_parser.add_argument("--active-color", default=DEFAULT_ACTIVE_COLOR,
                               help=f"Active state color in hex (default: {DEFAULT_ACTIVE_COLOR})")

    # Create command (direct AI)
    create_parser = subparsers.add_parser("create", help="Direct AI-driven icon creation")
    create_parser.add_argument("query", help="Prompt for AI generation")
    create_parser.add_argument("--name", required=True, help="Output filename (without extension)")
    create_parser.add_argument("--dir", default="./icon", help="Output directory (default: ./icon)")
    create_parser.add_argument("--active-color", default=DEFAULT_ACTIVE_COLOR,
                               help=f"Active state color in hex (default: {DEFAULT_ACTIVE_COLOR})")
    
    args = parser.parse_args()
    
    if args.command == "fetch":
        fetch_icon(args.icon, args.name, Path(args.dir), args.active_color)
    elif args.command == "generate":
        generate_icon(args.path, args.name, Path(args.dir), args.active_color)
    elif args.command == "collaborative":
        collaborative_workflow(args.query, args.name, Path(args.dir), args.active_color)
    elif args.command == "create":
        # Direct AI creation
        preview_dir = Path("/tmp/icon_creator_ai")
        preview_dir.mkdir(parents=True, exist_ok=True)
        svg_path = preview_dir / "created.svg"
        if generate_svg_ai(args.query, svg_path):
            generate_icon(str(svg_path), args.name, Path(args.dir), args.active_color)
    elif args.command == "list":
        list_icons()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
