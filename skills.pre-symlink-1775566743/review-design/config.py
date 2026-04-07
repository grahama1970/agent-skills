"""
Configuration for review-design skill.

Defines vision-capable providers, models, and defaults.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Base output directory for review artifacts (surface subdirectory auto-derived from screenshots path)
OUTPUT_BASE = Path("/home/graham/workspace/experiments/embry-os/docs/review-output")
OUTPUT_DIR = OUTPUT_BASE  # Default; overridden at runtime by derive_output_dir()

# Maximum image dimension (providers have limits)
MAX_IMAGE_DIM = 2048

# Default number of rounds for iterative review
DEFAULT_ROUNDS = 2


@dataclass
class ProviderConfig:
    """Configuration for a vision-capable LLM provider."""
    name: str
    cli: str
    model: str
    supports_vision: bool = True
    supports_session: bool = False
    cost: str = "paid"
    max_images: int = 10
    notes: str = ""


# Vision-capable providers
PROVIDERS = {
    "claude": ProviderConfig(
        name="Anthropic Claude",
        cli="claude",
        model="claude-sonnet-4-20250514",
        supports_vision=True,
        supports_session=True,
        cost="paid",
        max_images=20,
        notes="Best for nuanced design critique. Supports --continue for session."
    ),
    "openai": ProviderConfig(
        name="OpenAI GPT-4o",
        cli="openai",  # or could use `chatgpt` CLI
        model="gpt-4o",
        supports_vision=True,
        supports_session=False,
        cost="paid",
        max_images=10,
        notes="Strong visual reasoning. No native session support."
    ),
    "gemini": ProviderConfig(
        name="Google Gemini",
        cli="gemini",
        model="gemini-2.0-flash",
        supports_vision=True,
        supports_session=False,
        cost="free-tier",
        max_images=50,
        notes="1M+ context window. Handles 50+ screenshots + burst filmstrips + source code. Free tier. Direct REST API (no CLI piping)."
    ),
    "subagent": ProviderConfig(
        name="scillm Proxy",
        cli="httpx",
        model="vlm",
        supports_vision=True,
        supports_session=False,
        cost="paid",
        max_images=50,
        notes="Routes through scillm proxy on localhost:4001. Uses VLM alias for vision + large context."
    ),
}

DEFAULT_PROVIDER = "subagent"


@dataclass
class ReviewRequest:
    """A design review request with all inputs."""
    screenshots_dir: Path
    persona: str = ""  # NON-NEGOTIABLE: Persona agent name (e.g. "brandon-bailey", "rob-armstrong")
    tokens_path: Optional[Path] = None
    reference_dir: Optional[Path] = None
    provider: str = DEFAULT_PROVIDER
    rounds: int = DEFAULT_ROUNDS
    title: str = "Design Review"
    description: str = ""
    focus_areas: list = field(default_factory=list)
    code_context_files: list = field(default_factory=list)  # Explicit source files for animation/implementation context

    def validate(self) -> list[str]:
        """Validate the request, return list of errors."""
        errors = []

        # Persona is NON-NEGOTIABLE — a review without persona context is pointless
        if not self.persona or not self.persona.strip():
            errors.append(
                "PERSONA REQUIRED: A design review without a persona is a failure. "
                "Specify --persona (e.g. brandon-bailey, rob-armstrong, margaret-chen, nico-bailon). "
                "Generic reviews produce generic, useless feedback."
            )

        if not self.screenshots_dir.exists():
            errors.append(f"Screenshots directory not found: {self.screenshots_dir}")
        else:
            # Screenshots are MANDATORY — check for at least one image file
            image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
            has_images = any(
                p.suffix.lower() in image_extensions
                for p in self.screenshots_dir.iterdir()
                if p.is_file()
            )
            if not has_images:
                errors.append(
                    f"No screenshots found in {self.screenshots_dir}. "
                    "A design review REQUIRES visual evidence — capture screenshots "
                    "first using /surf, /surf-qml, or flameshot."
                )
        if self.tokens_path and not self.tokens_path.exists():
            errors.append(f"Tokens file not found: {self.tokens_path}")
        if self.reference_dir and not self.reference_dir.exists():
            errors.append(f"Reference directory not found: {self.reference_dir}")
        if self.provider not in PROVIDERS:
            errors.append(f"Unknown provider: {self.provider}. Available: {list(PROVIDERS.keys())}")
        return errors


@dataclass
class AuditFinding:
    """A single design audit finding."""
    severity: str  # high, medium, low
    category: str  # color, typography, layout, spacing, animation, interaction
    element: str   # Which UI element
    issue: str     # Description of the gap
    current: str   # Current value/behavior
    recommended: str  # Suggested fix
    token_change: Optional[dict] = None  # { path, from, to }


@dataclass
class AuditResult:
    """Complete audit result from a review round."""
    summary: str
    findings: list[AuditFinding]
    token_changes: list[dict]
    praise: list[str]
    round_num: int
    step: int
    provider: str
    model: str
