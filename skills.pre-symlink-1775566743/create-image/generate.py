#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "huggingface_hub>=0.26.0",
#     "pillow>=10.0.0",
#     "httpx>=0.25.0",
#     "typer>=0.9.0",
#     "fal-client>=0.4.0",
#     "requests>=2.0.0",
#     "python-dotenv>=1.0.0",
#     "loguru>=0.7.0",
# ]
# ///
"""
Generate images using multiple backends (Google Gemini, Fal.ai, FLUX, Ollama, etc).

Usage:
    uv run generate.py "hardware verification flow for microprocessor" --output test.png --size 800x600
"""

import os
from io import BytesIO
from pathlib import Path
from typing import Tuple

# Load .env before any os.getenv() calls
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)
# Explicit fallback: walk up to repo root .env
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

import typer
import warnings
from typing import Optional, Dict, Any

# Backward-compatible parameter gating; defaults preserve existing outputs
CREATE_IMAGE_FLAGS = {
    "ENABLE_SAFE_DEFAULTS": os.environ.get("CREATE_IMAGE_ENABLE_SAFE_DEFAULTS", "0") == "1",
}

def _apply_safe_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    # Only apply when explicitly enabled; otherwise return params unchanged
    if not CREATE_IMAGE_FLAGS["ENABLE_SAFE_DEFAULTS"]:
        return params
    merged = dict(params)
    # Non-destructive defaults only fill missing values
    merged.setdefault("resolution", "1024x1024")
    merged.setdefault("format", "png")
    merged.setdefault("color_profile", "sRGB")
    return merged

# Suppress Pydantic V2 warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

app = typer.Typer(help="Generate images for PDF test fixtures")


def parse_size(size_str: str) -> Tuple[int, int]:
    """Parse 'WxH' string into (width, height) tuple."""
    try:
        w, h = size_str.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise typer.BadParameter(f"Invalid size format: {size_str}. Use WxH (e.g., 400x600)")


def generate_fal(prompt: str, width: int, height: int, output: Path, model_id: str = "fal-ai/flux/schnell") -> bool:
    """Generate image using Fal.ai (Nano Banana, FLUX, etc)."""
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        typer.echo("  No FAL_KEY set", err=True)
        return False

    try:
        import fal_client
        from PIL import Image as PILImage
        import httpx

        typer.echo(f"  Using Fal.ai ({model_id})...")

        # Map simplistic model aliases
        if model_id == "nano-banana":
            model_id = "fal-ai/nano-banana-pro"
        elif model_id == "flux":
            model_id = "fal-ai/flux/schnell"

        arguments = {
            "prompt": prompt,
            "image_size": {
                "width": width,
                "height": height
            },
            "num_inference_steps": 4, # Fast default
            "enable_safety_checker": False
        }

        result = fal_client.subscribe(
            model_id,
            arguments=arguments,
            with_logs=True,
        )

        if result and "images" in result and result["images"]:
             img_url = result["images"][0]["url"]

             # Download the image
             resp = httpx.get(img_url)
             resp.raise_for_status()

             with open(output, "wb") as f:
                 f.write(resp.content)

             typer.echo(f"  Saved to {output}")
             return True

    except Exception as e:
        typer.echo(f"  Fal.ai Error: {e}", err=True)
        return False



def generate_google(prompt: str, width: int, height: int, output: Path, model_id: str = "gemini-2.5-flash-image") -> bool:
    """Generate image using Google Gemini 2.5 Flash Image REST API."""
    import base64
    import json
    import subprocess as _sp
    import httpx

    # Get API key from KDE Wallet (Gemini Pro Plan)
    key_result = _sp.run(
        ["kwallet-query", "-r", "GEMINI_API_KEY", "-f", "Embry OS", "kdewallet"],
        capture_output=True, text=True, timeout=5,
    )
    api_key = key_result.stdout.strip()
    if not api_key or api_key.startswith("Failed") or api_key.startswith("Error"):
        typer.echo("  GEMINI_API_KEY not found in KDE Wallet (Embry OS folder)", err=True)
        return False

    try:
        typer.echo(f"  Using Google Imagen ({model_id})...")

        # Check for aliases
        if model_id == "imagen3": model_id = "gemini-2.5-flash-image"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"

        headers = {
            "Content-Type": "application/json",
        }

        data = {
            "contents": [{
                "parts": [
                    {"text": prompt}
                ]
            }]
        }

        response = httpx.post(url, headers=headers, json=data, timeout=120.0)

        if response.status_code != 200:
            typer.echo(f"  Google API Error ({response.status_code}): {response.text[:200]}", err=True)
            return False

        result = response.json()

        # Parse response for image data
        # Structure: candidates[0].content.parts[...].inline_data.data (base64)
        try:
            candidates = result.get("candidates", [])
            if not candidates:
                 typer.echo(f"  Google: No candidates returned", err=True)
                 return False

            parts = candidates[0].get("content", {}).get("parts", [])
            b64_data = None

            for part in parts:
                if "inlineData" in part:
                    b64_data = part["inlineData"]["data"]
                    break

            if not b64_data:
                typer.echo(f"  Google: No inlineData found in response", err=True)
                return False

            image_bytes = base64.b64decode(b64_data)

            with open(output, "wb") as f:
                f.write(image_bytes)

            typer.echo(f"  Saved to {output}")
            return True

        except (KeyError, IndexError) as e:
            typer.echo(f"  Parsing Error: {e}. Response: {str(result)[:200]}", err=True)
            return False

    except Exception as e:
        typer.echo(f"  Google Imagen Error: {e}", err=True)
        if "403" in str(e):
             typer.echo("  (Check if your API Key has access to Imagen 3)", err=True)
        return False



def generate_ollama(prompt: str, width: int, height: int, output: Path) -> bool:
    """Generate image using Ollama local models (z-image-turbo or flux2-klein)."""
    import subprocess
    import shutil

    # Check for local ollama or Docker container
    ollama_path = shutil.which("ollama")
    container = os.getenv("OLLAMA_CONTAINER", "ollama")

    # Detect backend: local binary or Docker
    use_docker = False
    if ollama_path:
        cmd_prefix = [ollama_path]
    else:
        # Check for Docker container
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=5
            )
            if container in result.stdout.split():
                use_docker = True
                cmd_prefix = ["docker", "exec", container, "ollama"]
            else:
                return False
        except Exception:
            return False

    try:
        # Check if image models are available
        result = subprocess.run(
            cmd_prefix + ["list"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        models = result.stdout.lower()
        if "z-image-turbo" in models:
            model = "x/z-image-turbo"
        elif "flux2-klein" in models:
            model = "x/flux2-klein"
        else:
            typer.echo("  No image model (run: ollama pull x/z-image-turbo)", err=True)
            return False

        backend_type = "Docker" if use_docker else "LOCAL"
        typer.echo(f"  Using Ollama {model} ({backend_type})...")

        # Run ollama with image generation
        result = subprocess.run(
            cmd_prefix + ["run", model, prompt],
            capture_output=True,
            timeout=120,
        )

        if result.returncode == 0 and result.stdout:
            # Ollama outputs image bytes directly
            from PIL import Image as PILImage

            img = PILImage.open(BytesIO(result.stdout))
            if img.size != (width, height):
                img = img.resize((width, height), PILImage.Resampling.LANCZOS)
            img.save(str(output), "PNG")
            return True

        stderr = result.stderr.decode() if result.returncode != 0 and result.stderr else ""
        if "libcuda" in stderr or "GPU" in stderr.upper():
            typer.echo("  Ollama needs GPU (run container with --gpus all)", err=True)
        else:
            typer.echo(f"  Ollama error: {stderr[:200]}", err=True)
        return False

    except subprocess.TimeoutExpired:
        typer.echo("  Ollama timed out", err=True)
        return False
    except Exception as e:
        typer.echo(f"  Ollama error: {e}", err=True)
        return False


def generate_flux(prompt: str, width: int, height: int, output: Path) -> bool:
    """Generate image using HuggingFace FLUX.1-schnell (FREE)."""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        typer.echo("  No HF_TOKEN set", err=True)
        return False

    try:
        from huggingface_hub import InferenceClient
        from PIL import Image as PILImage

        typer.echo("  Using FLUX.1-schnell (HuggingFace FREE)...")

        client = InferenceClient(token=hf_token)
        image = client.text_to_image(
            prompt=prompt,
            model="black-forest-labs/FLUX.1-schnell",
        )

        # Resize if needed
        if image.size != (width, height):
            image = image.resize((width, height), PILImage.Resampling.LANCZOS)

        image.save(str(output), "PNG")
        return True

    except Exception as e:
        typer.echo(f"  FLUX error: {e}", err=True)
        return False


def generate_mermaid(prompt: str, width: int, height: int, output: Path) -> bool:
    """Generate flowchart using mermaid-cli (mmdc)."""
    import subprocess
    import shutil
    import tempfile

    mmdc_path = shutil.which("mmdc")
    if not mmdc_path:
        return False

    try:
        terms = prompt.lower().split()

        if any(w in terms for w in ["verification", "flow", "process", "pipeline"]):
            mermaid_code = """graph TD
    A[Start] --> B[Input]
    B --> C{Validate}
    C -->|Pass| D[Process]
    C -->|Fail| E[Error]
    D --> F[Output]
    E --> B
    F --> G[End]"""
        elif any(w in terms for w in ["architecture", "system", "network"]):
            mermaid_code = """graph LR
    A[Client] --> B[Load Balancer]
    B --> C[Server 1]
    B --> D[Server 2]
    C --> E[(Database)]
    D --> E"""
        else:
            mermaid_code = """graph TD
    A[Start] --> B[Step 1]
    B --> C[Step 2]
    C --> D[Step 3]
    D --> E[End]"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
            f.write(mermaid_code)
            mmd_path = f.name

        result = subprocess.run(
            [mmdc_path, "-i", mmd_path, "-o", str(output), "-w", str(width), "-H", str(height)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        Path(mmd_path).unlink(missing_ok=True)

        if result.returncode == 0 and output.exists():
            try:
                from PIL import Image as PILImage
                img = PILImage.open(output)
                if img.size != (width, height):
                    img = img.resize((width, height), PILImage.Resampling.LANCZOS)
                    img.save(str(output), "PNG")
            except Exception as e:
                logger.debug("saving failed: {}", e)
            return True
        return False

    except subprocess.TimeoutExpired:
        typer.echo("  mermaid-cli timed out", err=True)
        return False
    except Exception as e:
        typer.echo(f"  Mermaid error: {e}", err=True)
        return False


def generate_placeholder(prompt: str, width: int, height: int, output: Path) -> bool:
    """Generate placeholder image from picsum.photos."""
    try:
        import httpx

        url = f"https://picsum.photos/{width}/{height}?grayscale"
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        if response.status_code == 200:
            output.write_bytes(response.content)
            return True
        return False

    except Exception as e:
        typer.echo(f"  Placeholder error: {e}", err=True)
        return False


def generate_solid_color(prompt: str, width: int, height: int, output: Path) -> bool:
    """Generate solid color placeholder with text (last resort)."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (width, height), color=(220, 220, 220))
        draw = ImageDraw.Draw(img)

        lines = [f"[Figure {width}x{height}]", prompt[:40] + "..." if len(prompt) > 40 else prompt]

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font = ImageFont.load_default()

        y = height // 2 - 30
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y), line, fill=(80, 80, 80), font=font)
            y += 30

        img.save(output)
        return True

    except ImportError:
        typer.echo("  Pillow not installed", err=True)
        return False
    except Exception as e:
        typer.echo(f"  Solid color error: {e}", err=True)
        return False


@app.command()
def generate(
    prompt: str = typer.Argument(..., help="Description of image to generate"),
    output: Path = typer.Option(
        Path("fixture_image.png"),
        "--output", "-o",
        help="Output file path",
    ),
    size: str = typer.Option(
        "512x512",
        "--size", "-s",
        help="Image dimensions (WxH)",
    ),
    backend: str = typer.Option(
        "auto",
        "--backend", "-b",
        help="Generation backend: ollama, flux, fal, google, mermaid, placeholder, solid, auto",
    ),
    model: str = typer.Option(
        "auto",
        "--model", "-m",
        help="Model ID for Fal.ai backend (e.g. 'nano-banana', 'flux') or Google (gemini-2.5-flash-image)",
    ),
):
    """Generate an image for a PDF test fixture."""
    width, height = parse_size(size)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Generating {width}x{height} image...")
    typer.echo(f"  Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

    # Dispatch Backend
    if backend == "mock":
        pass

    if backend == "google":
        if model == "auto": model = "gemini-2.5-flash-image"
        if generate_google(prompt, width, height, output, model): return
        typer.echo("Google generation failed.")
        raise typer.Exit(code=1)

    # Wrap generate_fal to match signature
    def run_fal(p, w, h, o):
        if model == "auto": m = "fal-ai/flux/schnell"
        else: m = model
        return generate_fal(p, w, h, o, m)

    backends = {
        "ollama": generate_ollama,
        "flux": generate_flux,
        "fal": run_fal,
        "google": lambda p, w, h, o: generate_google(p, w, h, o, model if model != "auto" else "gemini-2.5-flash-image"),
        "mermaid": generate_mermaid,
        "placeholder": generate_placeholder,
        "solid": generate_solid_color,
    }

    if backend == "auto":
        # Ollama image gen only works on macOS currently (MLX framework)
        import platform
        if platform.system() == "Darwin":  # macOS
            order = ["ollama", "google", "fal", "flux", "mermaid", "placeholder", "solid"]
        else:  # Linux/Windows - prefer Google Gemini, then Fal
            order = []
            if os.getenv("GEMINI_API_KEY"):
                order.append("google")
            if os.getenv("FAL_KEY"):
                order.append("fal")
            order.extend(["flux", "mermaid", "placeholder", "solid"])

        for name in order:
            typer.echo(f"  Trying {name}...", nl=False)
            if backends[name](prompt, width, height, output):
                typer.echo(f" success!")
                typer.echo(f"\nSaved: {output.resolve()}")
                return
            typer.echo(" failed")

        typer.echo("\nAll backends failed!", err=True)
        raise typer.Exit(1)

    elif backend in backends:
        if backends[backend](prompt, width, height, output):
            typer.echo(f"\nSaved: {output.resolve()}")
        else:
            typer.echo(f"\nBackend '{backend}' failed!", err=True)
            raise typer.Exit(1)
    else:
        typer.echo(f"Unknown backend: {backend}", err=True)
        raise typer.Exit(1)


@app.command()
def test():
    """Test available backends and show configuration."""
    import shutil

    typer.echo("Fixture Image Generator - Backend Status\n")

    # Check Ollama (macOS only for image gen - MLX framework)
    import subprocess
    import platform

    is_macos = platform.system() == "Darwin"
    ollama_path = shutil.which("ollama")
    container = os.getenv("OLLAMA_CONTAINER", "ollama")

    if not is_macos:
        typer.echo(f"  Ollama:        Skipped (image gen is macOS-only, Linux coming soon)")
    else:
        cmd_prefix = None
        backend_type = None

        if ollama_path:
            cmd_prefix = [ollama_path]
            backend_type = "LOCAL"
        else:
            try:
                result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=5)
                if container in result.stdout.split():
                    cmd_prefix = ["docker", "exec", container, "ollama"]
                    backend_type = "Docker"
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

        if cmd_prefix:
            try:
                result = subprocess.run(cmd_prefix + ["list"], capture_output=True, text=True, timeout=5)
                has_img_model = "z-image" in result.stdout.lower() or "flux2" in result.stdout.lower()
                status = f"Available ({backend_type}) with image model - BEST" if has_img_model else f"Installed ({backend_type}) - run: ollama pull x/z-image-turbo"
                typer.echo(f"  Ollama:        {status}")
            except Exception:
                typer.echo(f"  Ollama:        Error checking models")
        else:
            typer.echo(f"  Ollama:        Not found")

    # Check Google Gemini
    gemini_key = os.getenv("GEMINI_API_KEY")
    typer.echo(f"  Google Gemini: {'GEMINI_API_KEY set (gemini-2.5-flash-image)' if gemini_key else 'No GEMINI_API_KEY'}")

    # Check HF token for FLUX
    hf_token = os.getenv("HF_TOKEN")
    typer.echo(f"  FLUX (HF):     {'HF_TOKEN set (FREE remote)' if hf_token else 'No HF_TOKEN'}")

    # Check FAL_KEY
    fal_key = os.getenv("FAL_KEY")
    typer.echo(f"  Fal.ai:        {'FAL_KEY set (Nano Banana enabled)' if fal_key else 'No FAL_KEY'}")

    # Check mermaid-cli
    mmdc_path = shutil.which("mmdc")
    typer.echo(f"  Mermaid:       {'Available (FREE diagrams)' if mmdc_path else 'Not found'}")

    typer.echo(f"  Placeholder:   Always available (picsum.photos)")
    typer.echo(f"  Solid color:   Always available (requires Pillow)")

    typer.echo("\nDependencies:")
    try:
        import PIL
        typer.echo(f"  Pillow: v{PIL.__version__}")
    except ImportError:
        typer.echo("  Pillow: Not installed")

    try:
        import fal_client
        typer.echo(f"  fal-client: Installed")
    except ImportError:
        typer.echo("  fal-client: Not installed")

    try:
        from huggingface_hub import __version__ as hf_ver
        typer.echo(f"  huggingface_hub: v{hf_ver}")
    except ImportError:
        typer.echo("  huggingface_hub: Not installed")

    try:
        import httpx
        typer.echo(f"  httpx: v{httpx.__version__}")
    except ImportError:
        typer.echo("  httpx: Not installed")


@app.command()
def examples():
    """Show example prompts for different document types."""
    typer.echo("Example prompts for PDF test fixtures:\n")

    examples_dict = {
        "Security Documents": [
            "APT attack kill chain diagram with reconnaissance, weaponization, delivery, exploitation phases",
            "network intrusion detection system architecture with sensors, aggregator, and SIEM",
            "malware analysis workflow flowchart from sample collection to final report",
        ],
        "Engineering Documents": [
            "hardware verification flow for microprocessor showing RTL design, synthesis, timing analysis",
            "FPGA design pipeline from HDL source to bitstream generation",
            "embedded systems boot sequence diagram with bootloader stages",
        ],
        "Scientific Documents": [
            "machine learning pipeline diagram with data preprocessing, training, and inference stages",
            "experimental methodology flowchart with hypothesis, experiment, analysis, conclusion",
            "system architecture diagram with numbered components and data flow arrows",
        ],
    }

    for category, prompts in examples_dict.items():
        typer.echo(f"{category}:")
        for p in prompts:
            typer.echo(f"  - {p}")
        typer.echo()


if __name__ == "__main__":
    app()
