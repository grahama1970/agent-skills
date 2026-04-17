#!/usr/bin/env python3
"""Stream Deck Lab — evaluate, generate, mutate, and push page layouts.

Static evaluation:
    python streamdeck_lab.py evaluate --template sentinel_hud
    python streamdeck_lab.py evaluate-all

Dynamic page generation (for chaotic environments):
    python streamdeck_lab.py generate --context sentinel_hud --events missile_warning,fuel_bingo
    python streamdeck_lab.py mutate --template sentinel_hud --event threat_popup
    python streamdeck_lab.py push --template compliance_dashboard --page 10

Promotion:
    python streamdeck_lab.py promote --template compliance_dashboard
"""

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

# Add project to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent / "workspace" / "streamdeck"
if not PROJECT_ROOT.exists():
    PROJECT_ROOT = Path.home() / "workspace" / "streamdeck"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from streamdeck.utils.page_builder import ButtonDef, build_page, push_page
from streamdeck.utils.page_memory import (
    load_template,
    load_template_metadata,
    list_templates,
    save_template,
    tag_template,
)
from streamdeck.widgets.nvis_base import (
    C_AMBER,
    C_BG,
    C_BLUE,
    C_DIM,
    C_GREEN,
    C_RED,
    C_WHITE,
    C_YELLOW,
)

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth" / "contexts.json"
RESULTS_DIR = Path(__file__).parent / "results"
LAYOUTS_DIR = Path(__file__).parent / "layouts"

# NVIS palette set for validation
NVIS_PALETTE = {C_BG, C_GREEN, C_RED, C_AMBER, C_BLUE, C_WHITE, C_DIM, C_YELLOW}

WEIGHTS = {
    "workflow_coverage": 0.40,
    "icon_appropriateness": 0.20,
    "navigation": 0.15,
    "layout_density": 0.15,
    "palette_compliance": 0.10,
}

ICON_DIR = PROJECT_ROOT / "icon"


def validate_icons(buttons: list[dict]) -> dict:
    """Check that all referenced icon paths exist on disk.

    Returns dict with 'missing' (list of {position, path}), 'valid' count,
    'widget' count (empty icon on widget button = expected), 'empty' count.
    """
    missing = []
    valid = 0
    widget = 0
    empty = 0

    for i, b in enumerate(buttons):
        icon = b.get("icon", "")
        has_widget = bool(b.get("widget"))

        if not icon:
            if has_widget:
                widget += 1  # widget service renders icon dynamically
            else:
                empty += 1
            continue

        icon_path = Path(icon)
        if icon_path.exists():
            valid += 1
        else:
            missing.append({"position": i, "path": icon})

    return {
        "missing": missing,
        "valid": valid,
        "widget": widget,
        "empty": empty,
        "total_referenced": valid + len(missing),
    }

# ============================================================================
# MIL-STD-1472 Information Hierarchy
# Primary:   scanned first, critical flight/safety data
# Secondary: tactical awareness, weapons, subsystems
# Tertiary:  navigation links, diagnostics, support
# ============================================================================

INFORMATION_HIERARCHY = {
    "sentinel_hud": {
        "primary": ["alt_tas", "heading", "fuel", "g_force", "threats", "missile"],
        "secondary": ["subsystems", "weapons", "cca_0", "cca_1", "comms"],
        "tertiary": ["comms_page", "diag_page", "back"],
    },
    "compliance_review": {
        "primary": ["cmmc", "sparta", "cui", "gap"],
        "secondary": ["oscal", "timeline", "nist", "drift", "datalake"],
        "tertiary": ["review", "ingest", "audit", "back"],
    },
    "f36_plant_floor": {
        "primary": ["torque", "thermal", "ndi", "inspect", "pass", "fail"],
        "secondary": ["log", "escalate", "photo", "scan", "next_part"],
        "tertiary": ["shift", "comply", "vendor", "back"],
    },
}

# ============================================================================
# Dynamic Event Definitions (for chaotic AO environments)
# ============================================================================

EVENT_CATALOG = {
    # SENTINEL events
    "missile_warning": {
        "context": "sentinel_hud",
        "action": "inject_button",
        "position": 10,
        "button": {"text": "MISSILE", "icon": "", "command": ""},
        "alert_tier": "critical",
        "flash": True,
        "requires_ack": True,
        "description": "Inbound missile — flash button 10, override to CRITICAL",
    },
    "fuel_bingo": {
        "context": "sentinel_hud",
        "action": "modify_button",
        "position": 2,
        "modifications": {"text": "BINGO!"},
        "alert_tier": "warning",
        "description": "Fuel below bingo — change fuel button to warning",
    },
    "comms_degraded": {
        "context": "sentinel_hud",
        "action": "modify_button",
        "position": 9,
        "modifications": {"text": "DEGRADED"},
        "alert_tier": "advisory",
        "description": "Comms degraded — mark comms button",
    },
    "threat_popup": {
        "context": "sentinel_hud",
        "action": "modify_button",
        "position": 4,
        "modifications": {"text": "3 HOSTILE"},
        "alert_tier": "warning",
        "description": "New hostile contact detected",
    },
    "mode_a2a": {
        "context": "sentinel_hud",
        "action": "mode_switch",
        "mode": "a2a",
        "description": "Switch to air-to-air combat mode",
    },
    "mode_a2g": {
        "context": "sentinel_hud",
        "action": "mode_switch",
        "mode": "a2g",
        "description": "Switch to air-to-ground mode",
    },
    "mode_nav": {
        "context": "sentinel_hud",
        "action": "mode_switch",
        "mode": "nav",
        "description": "Switch to navigation mode",
    },
    # Compliance events
    "drift_detected": {
        "context": "compliance_review",
        "action": "inject_button",
        "position": 12,
        "button": {"text": "DRIFT!", "command": "pi monitor-drift-sensors --alert"},
        "alert_tier": "warning",
        "description": "Compliance drift detected — inject alert button",
    },
    "cui_violation": {
        "context": "compliance_review",
        "action": "modify_button",
        "position": 2,
        "modifications": {"text": "CUI VIOL"},
        "alert_tier": "critical",
        "description": "CUI marking violation found",
    },
    # F36 events
    "test_failure": {
        "context": "f36_plant_floor",
        "action": "modify_button",
        "position": 9,
        "modifications": {"text": "FAIL 3"},
        "alert_tier": "warning",
        "description": "Multiple test failures — escalation needed",
    },
    "qa_hold": {
        "context": "f36_plant_floor",
        "action": "inject_button",
        "position": 12,
        "button": {"text": "QA HOLD", "command": "pi f36 qa-hold"},
        "alert_tier": "critical",
        "requires_ack": True,
        "description": "QA hold — production line stop",
    },
}


# ============================================================================
# EVALUATION (existing static evaluator)
# ============================================================================


def load_ground_truth() -> list[dict]:
    if not GROUND_TRUTH_PATH.exists():
        print(f"Ground truth not found: {GROUND_TRUTH_PATH}")
        return []
    return json.loads(GROUND_TRUTH_PATH.read_text())


def evaluate_template(template_name: str, ground_truth: dict) -> dict:
    """Evaluate a template against a ground truth test case."""
    try:
        meta = load_template_metadata(template_name)
    except FileNotFoundError:
        return {"template": template_name, "error": "not found", "score": 0.0}

    buttons = meta.get("buttons", [])
    scores = {}

    # 1. Workflow coverage (40%)
    required = ground_truth.get("required_workflows", [])
    if required:
        all_text = " ".join(
            f"{b.get('text', '')} {b.get('icon', '')} {b.get('command', '')}"
            for b in buttons
        ).lower()
        found = sum(1 for w in required if w.lower() in all_text)
        scores["workflow_coverage"] = found / len(required)
    else:
        scores["workflow_coverage"] = 1.0

    # 2. Icon appropriateness (20%)
    forbidden = ground_truth.get("forbidden", [])
    all_text = " ".join(
        f"{b.get('text', '')} {b.get('icon', '')}" for b in buttons
    ).lower()
    violations = sum(1 for f in forbidden if f.lower() in all_text)
    scores["icon_appropriateness"] = (
        1.0 if violations == 0 else max(0, 1.0 - violations * 0.5)
    )

    # 3. Navigation (15%)
    has_back = any(
        "back" in b.get("icon", "").lower() or b.get("switch_page") is not None
        for b in buttons
        if b.get("icon") or b.get("switch_page") is not None
    )
    switch_pages_valid = all(
        isinstance(b.get("switch_page"), (int, type(None))) for b in buttons
    )
    scores["navigation"] = (0.5 if has_back else 0) + (0.5 if switch_pages_valid else 0)

    # 4. Layout density (15%)
    non_empty = sum(
        1 for b in buttons if b.get("icon") or b.get("text") or b.get("command")
    )
    if 6 < non_empty < 24:
        scores["layout_density"] = 1.0
    elif non_empty <= 6:
        scores["layout_density"] = non_empty / 6.0
    else:
        scores["layout_density"] = max(0, 1.0 - (non_empty - 24) * 0.1)

    # 5. Palette compliance (10%)
    palette = ground_truth.get("palette", "standard")
    max_label = ground_truth.get("max_label_chars", 999)
    if palette == "nvis":
        long_labels = sum(
            1
            for b in buttons
            if b.get("text") and len(b["text"]) > max_label
        )
        scores["palette_compliance"] = (
            1.0 if long_labels == 0 else max(0, 1.0 - long_labels * 0.2)
        )
    else:
        scores["palette_compliance"] = 1.0

    # 6. Bonus: command coverage (informational, not scored)
    commands_present = sum(1 for b in buttons if b.get("command"))
    has_hierarchy = bool(meta.get("information_hierarchy") or meta.get("operator_workflow"))

    # 7. Icon validation (informational — missing icons are a red flag)
    icon_check = validate_icons(buttons)

    total = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

    return {
        "template": template_name,
        "context": ground_truth.get("context", ""),
        "scores": scores,
        "total_score": round(total, 4),
        "pass": total >= 0.85,
        "non_empty_buttons": non_empty,
        "commands_wired": commands_present,
        "has_hierarchy": has_hierarchy,
        "icons_valid": icon_check["valid"],
        "icons_missing": len(icon_check["missing"]),
        "icons_missing_detail": icon_check["missing"],
    }


def evaluate_all() -> list[dict]:
    """Evaluate all templates that have ground truth."""
    gt_list = load_ground_truth()
    results = []
    for gt in gt_list:
        template_name = gt["template"]
        result = evaluate_template(template_name, gt)
        results.append(result)
    return results


# ============================================================================
# DYNAMIC PAGE GENERATION
# ============================================================================


def generate_page(
    context: str,
    events: list[str] | None = None,
    base_template: str | None = None,
) -> dict:
    """Generate a dynamic page layout based on context and active events.

    For chaotic environments (AO, plant floor alerts), this takes a base
    template and applies event mutations to produce a context-aware page.

    Args:
        context: Context identifier (e.g. "sentinel_hud", "f36_plant_floor")
        events: List of active event names from EVENT_CATALOG
        base_template: Override template name. If None, auto-detects from context.

    Returns:
        dict with 'buttons' (list of button dicts), 'mutations' (applied events),
        'template_name', and 'score' (if ground truth available).
    """
    events = events or []

    # Find base template from context
    if base_template is None:
        gt_list = load_ground_truth()
        match = next(
            (g for g in gt_list if g.get("context") == context),
            None,
        )
        if match:
            base_template = match["template"]
        else:
            # Try context as template name directly
            base_template = context

    try:
        meta = load_template_metadata(base_template)
    except FileNotFoundError:
        return {"error": f"Template not found: {base_template}", "buttons": []}

    buttons = copy.deepcopy(meta.get("buttons", []))
    mutations = []

    # Apply events
    for event_name in events:
        event = EVENT_CATALOG.get(event_name)
        if not event:
            mutations.append({"event": event_name, "status": "unknown_event"})
            continue

        action = event["action"]
        pos = event.get("position", -1)

        if action == "inject_button" and 0 <= pos < len(buttons):
            btn = event.get("button", {})
            buttons[pos] = {
                **buttons[pos],
                "text": btn.get("text", buttons[pos].get("text", "")),
                "command": btn.get("command", buttons[pos].get("command", "")),
                "icon": btn.get("icon", buttons[pos].get("icon", "")),
                "_alert_tier": event.get("alert_tier", ""),
                "_flash": event.get("flash", False),
                "_requires_ack": event.get("requires_ack", False),
            }
            mutations.append({"event": event_name, "action": "injected", "position": pos})

        elif action == "modify_button" and 0 <= pos < len(buttons):
            mods = event.get("modifications", {})
            for k, v in mods.items():
                buttons[pos][k] = v
            buttons[pos]["_alert_tier"] = event.get("alert_tier", "")
            mutations.append({"event": event_name, "action": "modified", "position": pos})

        elif action == "mode_switch":
            mode = event.get("mode")
            mode_variants = meta.get("mode_variants", {})
            variant = mode_variants.get(mode, {})
            if variant.get("auto_switch_page"):
                mutations.append({
                    "event": event_name,
                    "action": "redirect",
                    "target_page": variant["auto_switch_page"],
                })
            elif variant.get("priority_buttons"):
                # Mark priority buttons (downstream renderers can highlight)
                for btn_idx in variant["priority_buttons"]:
                    if 0 <= btn_idx < len(buttons):
                        buttons[btn_idx]["_mode_priority"] = True
                mutations.append({
                    "event": event_name,
                    "action": "mode_applied",
                    "mode": mode,
                    "priority_buttons": variant["priority_buttons"],
                })

    result = {
        "template_name": base_template,
        "context": context,
        "buttons": buttons,
        "mutations": mutations,
        "generated_at": datetime.now().isoformat(),
        "event_count": len(events),
    }

    # Score against ground truth if available
    gt_list = load_ground_truth()
    gt = next((g for g in gt_list if g["template"] == base_template), None)
    if gt:
        # Create a temp metadata dict for evaluation
        eval_result = evaluate_template(base_template, gt)
        result["base_score"] = eval_result.get("total_score", 0)

    return result


def mutate_page(template_name: str, event_name: str) -> dict:
    """Apply a single event mutation to a template and return the result.

    Convenience wrapper around generate_page for single-event mutations.
    """
    try:
        meta = load_template_metadata(template_name)
    except FileNotFoundError:
        return {"error": f"Template not found: {template_name}"}

    context = meta.get("context_match", "")
    return generate_page(context, events=[event_name], base_template=template_name)


def push_generated_page(
    context: str,
    events: list[str] | None = None,
    page_idx: int = 10,
    navigate: bool = True,
    base_template: str | None = None,
) -> dict:
    """Generate a dynamic page and push it to the Stream Deck.

    This is the main entry point for agents pushing context-aware pages.

    Args:
        context: Context identifier
        events: Active events to apply
        page_idx: Target page (default 10, dynamic slot)
        navigate: Whether to auto-navigate to the page
        base_template: Override template name

    Returns:
        dict with generation result + page_idx
    """
    result = generate_page(context, events, base_template)
    if "error" in result:
        return result

    # Convert button dicts to ButtonDef objects
    button_defs = []
    for b in result["buttons"]:
        button_defs.append(
            ButtonDef(
                icon=b.get("icon", ""),
                command=b.get("command", ""),
                text=b.get("text", ""),
                switch_page=b.get("switch_page"),
                keys=b.get("keys", ""),
                write=b.get("write", ""),
            )
        )

    page = build_page(
        buttons=button_defs,
        page_idx=page_idx,
        back_page=0,
        navigate=navigate,
    )

    result["page_idx"] = page
    result["pushed"] = True
    return result


def list_events(context: str | None = None) -> list[dict]:
    """List available events, optionally filtered by context."""
    events = []
    for name, event in EVENT_CATALOG.items():
        if context and event.get("context") != context:
            continue
        events.append({
            "name": name,
            "context": event.get("context", ""),
            "action": event["action"],
            "alert_tier": event.get("alert_tier", ""),
            "description": event.get("description", ""),
        })
    return events


# ============================================================================
# OUTPUT
# ============================================================================


def print_results(results: list[dict]) -> None:
    """Pretty-print evaluation results."""
    for r in results:
        status = "PASS" if r.get("pass") else "FAIL"
        score = r.get("total_score", 0)
        cmds = r.get("commands_wired", 0)
        hier = "Y" if r.get("has_hierarchy") else "N"
        icons_ok = r.get("icons_valid", 0)
        icons_bad = r.get("icons_missing", 0)
        icon_tag = f"icons={icons_ok}ok" + (f"/{icons_bad}MISSING" if icons_bad else "")
        print(f"  [{status}] {r['template']}: {score:.2f}  (cmds={cmds}, hierarchy={hier}, {icon_tag})")
        if "scores" in r:
            for k, v in r["scores"].items():
                print(f"    {k}: {v:.2f} (weight: {WEIGHTS.get(k, 0):.0%})")
        if r.get("icons_missing_detail"):
            print(f"    MISSING ICONS:")
            for m in r["icons_missing_detail"]:
                print(f"      btn[{m['position']}]: {m['path']}")
        if "error" in r:
            print(f"    ERROR: {r['error']}")


def print_generated(result: dict) -> None:
    """Pretty-print a generated page result."""
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print(f"  Template: {result['template_name']}")
    print(f"  Context:  {result['context']}")
    print(f"  Events:   {result['event_count']}")
    if result.get("base_score"):
        print(f"  Score:    {result['base_score']:.2f}")
    if result.get("pushed"):
        print(f"  Page:     {result['page_idx']}")

    buttons = result.get("buttons", [])
    non_empty = [
        (i, b) for i, b in enumerate(buttons)
        if b.get("text") or b.get("icon") or b.get("command")
    ]
    print(f"  Buttons:  {len(non_empty)} active / {len(buttons)} total")

    if result.get("mutations"):
        print("  Mutations:")
        for m in result["mutations"]:
            tier = ""
            event = EVENT_CATALOG.get(m["event"], {})
            if event.get("alert_tier"):
                tier = f" [{event['alert_tier'].upper()}]"
            print(f"    - {m['event']}: {m['action']}{tier}")

    # Show alert buttons
    for i, b in non_empty:
        alert = b.get("_alert_tier")
        if alert:
            flash = " FLASH" if b.get("_flash") else ""
            ack = " ACK-REQ" if b.get("_requires_ack") else ""
            print(f"    btn[{i}] {b.get('text', '')}: {alert.upper()}{flash}{ack}")


# ============================================================================
# CLI
# ============================================================================


app = typer.Typer()


@app.command("evaluate")
def cmd_evaluate(
    template: str = typer.Option(..., help="Template name"),
):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    gt_list = load_ground_truth()
    gt = next((g for g in gt_list if g["template"] == template), None)
    if gt is None:
        print(f"No ground truth for template: {template}")
        raise typer.Exit(code=1)
    result = evaluate_template(template, gt)
    print_results([result])
    out = RESULTS_DIR / f"{template}_eval.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nSaved to {out}")


@app.command("evaluate-all")
def cmd_evaluate_all():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = evaluate_all()
    print(f"Evaluated {len(results)} templates:\n")
    print_results(results)
    passed = sum(1 for r in results if r.get("pass"))
    print(f"\n{passed}/{len(results)} passed (>= 0.85)")
    out = RESULTS_DIR / "all_eval.json"
    out.write_text(json.dumps(results, indent=2))


@app.command("generate")
def cmd_generate(
    context: str = typer.Option(..., help="Context identifier"),
    events: str = typer.Option("", help="Comma-separated event names"),
    template: Optional[str] = typer.Option(None, help="Override base template"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    result = generate_page(context, event_list, template)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print("Generated page:\n")
        print_generated(result)
    out = LAYOUTS_DIR / f"gen_{context}_{datetime.now().strftime('%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nSaved to {out}")


@app.command("mutate")
def cmd_mutate(
    template: str = typer.Option(..., help="Template name"),
    event: str = typer.Option(..., help="Event name from catalog"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    result = mutate_page(template, event)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Mutated {template} with {event}:\n")
        print_generated(result)


@app.command("push")
def cmd_push(
    context: Optional[str] = typer.Option(None, help="Context identifier"),
    template: Optional[str] = typer.Option(None, help="Template name"),
    events: str = typer.Option("", help="Comma-separated event names"),
    page: int = typer.Option(10, help="Target page (default: 10)"),
    no_navigate: bool = typer.Option(False, "--no-navigate", help="Don't navigate to page"),
):
    ctx = context or template
    if not ctx:
        print("Must provide --context or --template")
        raise typer.Exit(code=1)
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    result = push_generated_page(
        context=ctx,
        events=event_list,
        page_idx=page,
        navigate=not no_navigate,
        base_template=template,
    )
    print("Pushed page:\n")
    print_generated(result)


@app.command("events")
def cmd_events(
    context: Optional[str] = typer.Option(None, help="Filter by context"),
):
    event_list = list_events(context)
    if not event_list:
        print("No events found" + (f" for context '{context}'" if context else ""))
    else:
        print(f"Available events{' for ' + context if context else ''}:\n")
        for e in event_list:
            tier = f" [{e['alert_tier'].upper()}]" if e["alert_tier"] else ""
            print(f"  {e['name']:<20} {e['context']:<20} {e['action']:<15}{tier}")
            if e["description"]:
                print(f"    {e['description']}")


@app.command("promote")
def cmd_promote(
    template: str = typer.Option(..., help=""),
):
    tag_template(template, ["promoted", "lab-verified"])
    print(f"Promoted template: {template}")


if __name__ == "__main__":
    app()
