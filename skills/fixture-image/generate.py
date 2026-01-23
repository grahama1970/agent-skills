#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "huggingface_hub>=0.26.0",
#     "pillow>=10.0.0",
#     "httpx>=0.25.0",
#     "typer>=0.9.0",
# ]
# ///
"""
Generate images for PDF test fixtures using HuggingFace FLUX.1-schnell (FREE).

Usage:
    uv run generate.py "hardware verification flow for microprocessor" --output test.png --size 800x600
"""

import os
from io import BytesIO
from pathlib import Path
from typing import Tuple

import typer

app = typer.Typer(help="Generate images for PDF test fixtures")


def parse_size(size_str: str) -> Tuple[int, int]:
    """Parse 'WxH' string into (width, height) tuple."""
    try:
        w, h = size_str.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise typer.BadParameter(f"Invalid size format: {size_str}. Use WxH (e.g., 400x600)")


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

        stderr = result.stderr.decode() if result.stderr else ""
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
            except Exception:
                pass
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
        help="Generation backend: ollama, flux, mermaid, placeholder, solid, auto",
    ),
):
    """Generate an image for a PDF test fixture."""
    width, height = parse_size(size)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Generating {width}x{height} image...")
    typer.echo(f"  Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

    backends = {
        "ollama": generate_ollama,
        "flux": generate_flux,
        "mermaid": generate_mermaid,
        "placeholder": generate_placeholder,
        "solid": generate_solid_color,
    }

    if backend == "auto":
        # Ollama image gen only works on macOS currently (MLX framework)
        # Linux/NVIDIA support "coming soon" per Ollama docs
        import platform
        if platform.system() == "Darwin":  # macOS
            order = ["ollama", "flux", "mermaid", "placeholder", "solid"]
        else:  # Linux/Windows - skip Ollama for now
            order = ["flux", "mermaid", "placeholder", "solid"]

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
            except Exception:
                pass

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

    # Check HF token for FLUX
    hf_token = os.getenv("HF_TOKEN")
    typer.echo(f"  FLUX (HF):     {'HF_TOKEN set (FREE remote)' if hf_token else 'No HF_TOKEN'}")

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
