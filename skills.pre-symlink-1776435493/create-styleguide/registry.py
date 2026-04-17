"""Surface registry — canonical metadata for all Embry OS UX surfaces.

Surface IDs align with docs/MASTER_DESIGN_LANGUAGE.md and design board
directory names.  S4 (Launcher Overlay) is the only surface that shipped
with a complete design-tokens + styleguide pipeline.
"""

from __future__ import annotations

SURFACE_REGISTRY: dict[str, dict] = {
    "S1": {
        "name": "Ambient Wall",
        "app": "embry-ui",
        "component": "AmbientMonitor",
        "distance_mode": "far",
        "primary_persona": "paul_nakamura",
        "token_source": "apps/embry-ui/src/tokens/s1-ambient-wall.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s1-ambient/",
        "capture_guide": "docs/design-boards/s1-ambient/DESIGN_BOARD.md",
        "styleguide_section": "5.1",
        "debt_items": [],
        "ready": True,
    },
    "S2": {
        "name": "Voice Mid",
        "app": "embry-ui",
        "component": "MidView",
        "distance_mode": "mid",
        "primary_persona": "rob_armstrong",
        "token_source": "apps/embry-ui/src/tokens/s2-voice-mid.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s2-midview/",
        "capture_guide": "docs/design-boards/s2-midview/DESIGN_BOARD.md",
        "styleguide_section": "5.2",
        "debt_items": [],
        "ready": True,
    },
    "S3": {
        "name": "Desktop Close",
        "app": "embry-ui",
        "component": "CloseView",
        "distance_mode": "close",
        "primary_persona": "jennifer_cheung",
        "token_source": "apps/embry-ui/src/tokens/s3-desktop-close.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s3-closeview/",
        "capture_guide": "docs/design-boards/s3-closeview/DESIGN_BOARD.md",
        "styleguide_section": "5.3",
        "debt_items": [],
        "ready": True,
    },
    "S4": {
        "name": "Launcher Overlay",
        "app": "embry-overlay",
        "component": "EmbryOverlay",
        "distance_mode": "launcher",
        "primary_persona": "embry_lawson",
        "token_source": "apps/embry-overlay/src/ui/embry-design-tokens.json",
        "reference_dir": "apps/embry-overlay/src/ui/design-reference/raycast-reference/",
        "screenshots_dir": "apps/embry-overlay/screenshots/",
        "capture_guide": "apps/embry-overlay/src/ui/design-reference/CAPTURE_GUIDE.md",
        "styleguide_section": "5.4",
        "debt_items": ["D3", "D6"],
        "ready": True,
    },
    "S5": {
        "name": "Expert Deep",
        "app": "embry-ui",
        "component": "ExpertView",
        "distance_mode": "deep",
        "primary_persona": "all_domain",
        "token_source": "apps/embry-ui/src/tokens/s5-expert-deep.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s5-expertview/",
        "capture_guide": "docs/design-boards/s5-expertview/DESIGN_BOARD.md",
        "styleguide_section": "5.5",
        "debt_items": ["D-EXP-001"],
        "ready": False,
    },
    "S6": {
        "name": "SentinelHUD",
        "app": "embry-ui",
        "component": "SentinelHUD",
        "distance_mode": "hud",
        "primary_persona": "sentinel",
        "token_source": "apps/embry-ui/src/tokens/s6-sentinelhud.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s6-sentinelhud/",
        "capture_guide": "docs/design-boards/s6-sentinelhud/DESIGN_BOARD.md",
        "styleguide_section": "5.6",
        "debt_items": ["D8"],
        "ready": True,
    },
    "S7": {
        "name": "Phone/Discord",
        "app": "embry-ui",
        "component": "PhoneView",
        "distance_mode": "phone",
        "primary_persona": "embry_lawson",
        "token_source": "apps/embry-ui/src/tokens/s7-phone-discord.design-tokens.json",
        "screenshots_dir": "docs/screenshots/s7-phoneview/",
        "capture_guide": "docs/design-boards/s7-phoneview/DESIGN_BOARD.md",
        "styleguide_section": "5.7",
        "debt_items": ["D9"],
        "ready": True,
    },
    "QML": {
        "name": "Floor Wall",
        "app": "embry-floor",
        "component": "ComplianceBoard + AlertOverlay",
        "distance_mode": "far+",
        "primary_persona": "paul_nakamura",
        "token_source": "apps/embry-ui/src/tokens/qml-floor-wall.design-tokens.json",
        "screenshots_dir": "docs/screenshots/qml-floor/",
        "capture_guide": "docs/design-boards/qml-floor/DESIGN_BOARD.md",
        "styleguide_section": "5.8",
        "debt_items": ["D-EXP-002"],
        "ready": False,
    },
    "SD": {
        "name": "Stream Deck",
        "app": "streamdeck",
        "component": "IconRenderer + PageFactory",
        "distance_mode": "tactile",
        "primary_persona": "paul_nakamura",
        "token_source": "apps/embry-ui/src/tokens/sd-streamdeck.design-tokens.json",
        "screenshots_dir": "docs/screenshots/sd-streamdeck/",
        "capture_guide": "docs/design-boards/sd-streamdeck/DESIGN_BOARD.md",
        "styleguide_section": "5.9",
        "debt_items": [],
        "ready": False,
    },
    "CLI": {
        "name": "Developer Terminal",
        "app": "pi-cli",
        "component": "Pi CLI + /dashboard + /project-state",
        "distance_mode": "desk",
        "primary_persona": "nico_bailon",
        "token_source": None,
        "screenshots_dir": "docs/screenshots/cli-developer/",
        "capture_guide": "docs/design-boards/cli-developer/DESIGN_BOARD.md",
        "styleguide_section": "5.10",
        "debt_items": [],
        "ready": False,
    },
}


def get_surface(surface_id: str) -> dict:
    """Get surface config by ID (e.g. 'S4', 'QML', 'SD', 'CLI')."""
    sid = surface_id.upper()
    if sid not in SURFACE_REGISTRY:
        raise KeyError(f"Unknown surface: {surface_id}. Valid: {', '.join(SURFACE_REGISTRY)}")
    return SURFACE_REGISTRY[sid]


def ready_surfaces() -> list[str]:
    """Return list of surface IDs that have all prerequisites on disk."""
    return [sid for sid, cfg in SURFACE_REGISTRY.items() if cfg.get("ready")]
