#!/usr/bin/env python3
"""
Image handling utilities for Interview Skill v2.

Provides:
- Image validation and file path detection
- Terminal graphics protocol detection (Kitty, iTerm2, Sixel)
- [Image X] placeholder generation for TUI
- Base64 data URI generation for HTML
- Custom image handling for "Other" responses
"""
from __future__ import annotations

import base64
import os
import re
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


# =============================================================================
# Terminal Graphics Protocol Detection
# =============================================================================

def detect_graphics_protocol() -> str | None:
    """Detect which graphics protocol the terminal supports.

    Returns:
        'kitty', 'iterm2', 'sixel', or None if no graphics support
    """
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "")
    colorterm = os.environ.get("COLORTERM", "").lower()

    # Kitty terminal
    if "kitty" in term or os.environ.get("KITTY_WINDOW_ID"):
        return "kitty"

    # iTerm2
    if term_program == "iTerm.app" or os.environ.get("ITERM_SESSION_ID"):
        return "iterm2"

    # WezTerm supports Kitty protocol
    if term_program == "WezTerm":
        return "kitty"

    # Check for Sixel support (many terminals)
    # foot, mlterm, xterm (with config), Windows Terminal 1.22+
    if any(t in term for t in ["foot", "mlterm", "xterm-direct"]):
        return "sixel"

    # Ghostty supports Kitty protocol
    if "ghostty" in term:
        return "kitty"

    return None


def has_textual_image() -> bool:
    """Check if textual-image package is available."""
    try:
        import textual_image
        return True
    except ImportError:
        return False


def has_rich_pixels() -> bool:
    """Check if rich-pixels package is available."""
    try:
        import rich_pixels
        return True
    except ImportError:
        return False


# =============================================================================
# Image Validation and Detection
# =============================================================================

def validate_image(path: str | Path) -> bool:
    """Check if file exists and is a valid image.

    Args:
        path: Path to image file

    Returns:
        True if valid image, False otherwise
    """
    path = Path(path)
    if not path.exists():
        return False

    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()  # Verify it's a valid image
        return True
    except Exception:
        return False


def looks_like_image_path(text: str) -> bool:
    """Check if text looks like an image file path.

    Args:
        text: User input text

    Returns:
        True if text appears to be an image path
    """
    if not text:
        return False

    text = text.strip()

    # Check for common image extensions
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.ico', '.svg'}

    # Check if it ends with an image extension
    lower_text = text.lower()
    if any(lower_text.endswith(ext) for ext in image_extensions):
        # Additional checks to confirm it's a path
        if text.startswith('/') or text.startswith('~') or text.startswith('./'):
            return True
        if re.match(r'^[a-zA-Z]:\\', text):  # Windows path
            return True
        if '/' in text or '\\' in text:
            return True
        # Just a filename like "image.png"
        return True

    return False


def resolve_image_path(text: str, base_path: Path | None = None) -> Path | None:
    """Resolve and validate an image path from user input.

    Args:
        text: User input that might be an image path
        base_path: Base path for resolving relative paths

    Returns:
        Resolved Path if valid image, None otherwise
    """
    if not looks_like_image_path(text):
        return None

    text = text.strip()

    # Expand ~ to home directory
    if text.startswith('~'):
        text = os.path.expanduser(text)

    path = Path(text)

    # Try as absolute path first
    if path.is_absolute() and validate_image(path):
        return path

    # Try relative to base_path
    if base_path:
        resolved = base_path / path
        if validate_image(resolved):
            return resolved

    # Try relative to current directory
    if validate_image(path):
        return path.resolve()

    return None


# =============================================================================
# Basic Image Operations
# =============================================================================

def get_image_placeholder(index: int) -> str:
    """Get placeholder text for image in TUI.

    Args:
        index: 1-based image index

    Returns:
        Placeholder string like "[Image 1]"
    """
    return f"[Image {index}]"


def get_image_dimensions(path: str | Path) -> tuple[int, int] | None:
    """Get image dimensions.

    Args:
        path: Path to image file

    Returns:
        (width, height) tuple or None if invalid
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def load_image_for_html(path: str | Path, max_width: int = 600) -> str:
    """Load image and return as base64 data URI for HTML embedding.

    Args:
        path: Path to image file
        max_width: Maximum width to resize to (maintains aspect ratio)

    Returns:
        Data URI string like "data:image/png;base64,..."
        or empty string if loading fails
    """
    path = Path(path)
    if not path.exists():
        return ""

    try:
        from PIL import Image

        with Image.open(path) as img:
            # Convert to RGB if necessary (e.g., RGBA PNGs)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if too large
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Save to bytes
            buffer = BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)

            # Encode to base64
            b64_data = base64.b64encode(buffer.read()).decode('utf-8')
            return f"data:image/png;base64,{b64_data}"

    except Exception as e:
        print(f"Warning: Failed to load image {path}: {e}")
        return ""


# =============================================================================
# Custom Image Handling (for "Other" responses)
# =============================================================================

def save_custom_image_from_base64(data_uri: str, session_id: str) -> Path | None:
    """Save a base64 data URI as a temporary image file.

    Args:
        data_uri: Base64 data URI (data:image/png;base64,...)
        session_id: Session ID for naming

    Returns:
        Path to saved image or None if failed
    """
    if not data_uri.startswith('data:image/'):
        return None

    try:
        # Parse data URI
        header, b64_data = data_uri.split(',', 1)
        # Extract format (e.g., 'png' from 'data:image/png;base64')
        fmt_match = re.search(r'data:image/(\w+)', header)
        fmt = fmt_match.group(1) if fmt_match else 'png'

        # Decode and save
        image_data = base64.b64decode(b64_data)

        # Create temp file
        temp_dir = Path(tempfile.gettempdir()) / "interview_images"
        temp_dir.mkdir(exist_ok=True)

        filename = f"custom_{session_id}_{uuid.uuid4().hex[:8]}.{fmt}"
        filepath = temp_dir / filename

        filepath.write_bytes(image_data)
        return filepath

    except Exception as e:
        print(f"Warning: Failed to save custom image: {e}")
        return None


def create_custom_image_response(
    path: Path | None = None,
    data_uri: str | None = None,
    reason: str = ""
) -> dict:
    """Create a structured response for a custom image selection.

    Args:
        path: Path to image file (if from file)
        data_uri: Base64 data URI (if from clipboard)
        reason: User's reason for selecting this image

    Returns:
        Structured dict for response
    """
    result = {
        "source": "file_path" if path else "clipboard",
    }

    if path:
        path = Path(path)
        result["path"] = str(path.resolve())
        dims = get_image_dimensions(path)
        if dims:
            result["dimensions"] = list(dims)
        # Also generate data_uri for portability
        result["data_uri"] = load_image_for_html(path)
    elif data_uri:
        result["data_uri"] = data_uri

    if reason:
        result["reason"] = reason

    return result


# =============================================================================
# TUI Rendering
# =============================================================================

def render_images_for_tui(
    images: list[str] | None,
    base_path: Path | None = None,
    use_graphics: bool = True
) -> list[str]:
    """Render image placeholders for TUI display.

    Args:
        images: List of image paths
        base_path: Base path to resolve relative paths
        use_graphics: Try to use terminal graphics if available

    Returns:
        List of placeholder strings with validation status
    """
    if not images:
        return []

    protocol = detect_graphics_protocol() if use_graphics else None
    result = []

    for i, img_path in enumerate(images, 1):
        path = Path(img_path)
        if base_path and not path.is_absolute():
            path = base_path / path

        placeholder = get_image_placeholder(i)
        if validate_image(path):
            dims = get_image_dimensions(path)
            if dims:
                placeholder += f" ({dims[0]}x{dims[1]})"
            if protocol:
                placeholder += f" [{protocol}]"
        else:
            placeholder += " [NOT FOUND]"

        result.append(placeholder)

    return result


def render_image_widget(path: Path, protocol: str | None = None):
    """Create a Textual widget or Rich renderable for an image.

    Args:
        path: Path to image
        protocol: Graphics protocol to use (auto-detect if None)

    Returns:
        Widget/renderable or placeholder string
    """
    if protocol is None:
        protocol = detect_graphics_protocol()

    # Try textual-image first (best quality)
    if protocol in ("kitty", "iterm2") and has_textual_image():
        try:
            from textual_image.widget import Image as TextualImage
            return TextualImage(str(path))
        except Exception:
            pass

    # Try rich-pixels for unicode rendering
    if has_rich_pixels():
        try:
            from rich_pixels import Pixels
            return Pixels.from_image_path(str(path))
        except Exception:
            pass

    # Fallback to placeholder
    dims = get_image_dimensions(path)
    placeholder = f"[Image: {path.name}]"
    if dims:
        placeholder = f"[Image: {path.name}] ({dims[0]}x{dims[1]})"
    return placeholder


# =============================================================================
# HTML Rendering
# =============================================================================

def render_images_for_html(
    images: list[str] | None,
    base_path: Path | None = None
) -> list[dict]:
    """Render images for HTML display.

    Args:
        images: List of image paths
        base_path: Base path to resolve relative paths

    Returns:
        List of dicts with 'index', 'data_uri', 'alt' keys
    """
    if not images:
        return []

    result = []
    for i, img_path in enumerate(images, 1):
        path = Path(img_path)
        if base_path and not path.is_absolute():
            path = base_path / path

        data_uri = load_image_for_html(path)
        result.append({
            "index": i,
            "data_uri": data_uri,
            "alt": f"Image {i}" if data_uri else f"Image {i} (not found)",
            "valid": bool(data_uri),
            "path": str(path),
        })

    return result


# =============================================================================
# Image Comparison Support
# =============================================================================

def render_comparison_images_for_tui(
    images: list[dict],
    base_path: Path | None = None
) -> list[dict]:
    """Render images for comparison display in TUI.

    Args:
        images: List of dicts with 'path' and 'label' keys
        base_path: Base path to resolve relative paths

    Returns:
        List of dicts with rendering info
    """
    if not images:
        return []

    result = []
    for i, img_info in enumerate(images, 1):
        img_path = img_info.get("path", "")
        label = img_info.get("label", f"Option {i}")

        path = Path(img_path)
        if base_path and not path.is_absolute():
            path = base_path / path

        placeholder = f"[Image {i}: {label}]"
        valid = validate_image(path)

        if valid:
            dims = get_image_dimensions(path)
            if dims:
                placeholder += f" ({dims[0]}x{dims[1]})"
        else:
            placeholder += " [NOT FOUND]"

        result.append({
            "index": i,
            "label": label,
            "placeholder": placeholder,
            "path": str(path),
            "valid": valid,
        })

    return result


def render_comparison_images_for_html(
    images: list[dict],
    base_path: Path | None = None
) -> list[dict]:
    """Render images for comparison display in HTML.

    Args:
        images: List of dicts with 'path' and 'label' keys
        base_path: Base path to resolve relative paths

    Returns:
        List of dicts with 'index', 'label', 'data_uri', etc.
    """
    if not images:
        return []

    result = []
    for i, img_info in enumerate(images, 1):
        img_path = img_info.get("path", "")
        label = img_info.get("label", f"Option {i}")

        path = Path(img_path)
        if base_path and not path.is_absolute():
            path = base_path / path

        data_uri = load_image_for_html(path)
        result.append({
            "index": i,
            "label": label,
            "data_uri": data_uri,
            "alt": label if data_uri else f"{label} (not found)",
            "valid": bool(data_uri),
            "path": str(path),
        })

    return result
