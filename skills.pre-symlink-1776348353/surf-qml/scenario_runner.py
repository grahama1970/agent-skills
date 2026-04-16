#!/usr/bin/env python3
"""
Scenario runner for surf-qml.
Executes YAML/JSON scenario files against QML applications via AT-SPI.
Supports voice narration (PersonaPlex live / Qwen3-TTS recorded) with
Federated Taxonomy tagging on every utterance.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


SCENARIO_DIR = Path(__file__).parent / "scenarios"


def _load_scenario(path_or_name: str) -> dict:
    """Load scenario from file path or built-in name."""
    path = Path(path_or_name)

    candidates = [path]
    if not path.is_absolute():
        candidates.append(SCENARIO_DIR / path_or_name)
        for ext in (".yaml", ".yml", ".json"):
            candidates.append(SCENARIO_DIR / f"{path_or_name}{ext}")
            candidates.append(Path(path_or_name).with_suffix(ext))

    for candidate in candidates:
        if candidate.is_file():
            text = candidate.read_text()
            if candidate.suffix in (".yaml", ".yml"):
                if not YAML_AVAILABLE:
                    raise RuntimeError("PyYAML required for .yaml scenarios: pip install pyyaml")
                return yaml.safe_load(text)
            else:
                return json.loads(text)

    raise FileNotFoundError(f"Scenario not found: {path_or_name}")


def _make_output_dir(name: str) -> Path:
    """Create timestamped output directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_")
    out = Path(f"/tmp/surf-qml-scenarios/{safe_name}_{timestamp}")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _init_narration(scenario: dict, out_dir: Path):
    """Initialize narration engine if scenario requests it."""
    auto_narrate = scenario.get("auto_narrate", False)
    voice_mode = scenario.get("voice_mode", "live")
    persona = scenario.get("persona", "embry")

    if not auto_narrate and not any(
        isinstance(s, dict) and "narrate" in s for s in scenario.get("steps", [])
    ):
        return None, False

    try:
        from narration import NarrationEngine
        engine = NarrationEngine(
            persona=persona,
            mode=voice_mode,
            output_dir=out_dir,
            session_name=scenario.get("name", "scenario"),
        )
        return engine, auto_narrate
    except Exception as e:
        print(f"  [narration] Failed to init: {e}")
        return None, False


def run_scenario(surf, path_or_name: str) -> int:
    """Execute a scenario file. Returns 0 on success, 1 on failure."""
    try:
        scenario = _load_scenario(path_or_name)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    name = scenario.get("name", Path(path_or_name).stem)
    steps = scenario.get("steps", [])
    if not steps:
        print(f"Scenario '{name}' has no steps", file=sys.stderr)
        return 1

    out_dir = _make_output_dir(name)
    report: list[dict[str, Any]] = []
    failed = False

    # Initialize narration engine
    narrator, auto_narrate = _init_narration(scenario, out_dir)

    print(f"Running scenario: {name} ({len(steps)} steps)")
    print(f"Output: {out_dir}")
    if narrator:
        print(f"Voice: {narrator.mode} ({narrator.persona})")

    for i, step in enumerate(steps):
        step_num = i + 1
        result = {"step": step_num, "action": step, "status": "ok", "detail": ""}

        try:
            if isinstance(step, dict):
                action = next(iter(step))
                value = step[action]
            else:
                print(f"  Step {step_num}: Invalid step format: {step}", file=sys.stderr)
                result["status"] = "error"
                result["detail"] = "invalid format"
                report.append(result)
                failed = True
                continue

            print(f"  Step {step_num}: {action} {_summarize(value)}")

            # ── narrate step ────────────────────────────────────
            if action == "narrate":
                if narrator:
                    opts = value if isinstance(value, dict) else {"text": str(value)}
                    text = opts.get("text", str(value))
                    emotion = opts.get("emotion")
                    meta = narrator.speak(
                        text, step_num=step_num,
                        emotional_state=emotion,
                        context={"explicit": True},
                    )
                    result["detail"] = f"Narrated: {text[:50]}"
                    result["narration"] = {
                        "audio": meta.get("audio"),
                        "taxonomy": meta.get("taxonomy"),
                    }
                else:
                    result["detail"] = "Narration not available"

            elif action == "find":
                window = surf.find_window(str(value))
                if not window:
                    result["status"] = "fail"
                    result["detail"] = f"Window not found: {value}"
                    failed = True
                else:
                    result["detail"] = f"Found: {window.get_name()}"

            elif action == "focus":
                if not surf.focus_window(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to focus: {value}"
                    failed = True
                time.sleep(0.3)

            elif action == "read":
                kwargs = {}
                if isinstance(value, dict):
                    kwargs["role_filter"] = value.get("role")
                    kwargs["name_filter"] = value.get("name")
                    kwargs["max_depth"] = value.get("depth", 10)
                elements = surf.read_tree(**kwargs)
                result["detail"] = f"{len(elements)} elements"

            elif action == "click":
                surf.read_tree()
                if not surf.click(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to click: {value}"
                    failed = True

            elif action == "type":
                if not surf.type_text(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to type: {value}"
                    failed = True

            elif action == "key":
                if not surf.press_key(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to press: {value}"
                    failed = True

            elif action == "snap":
                opts = value if isinstance(value, dict) else {}
                filename = opts.get("output", f"step{step_num}.png")
                out_path = str(out_dir / filename)
                element_ref = opts.get("element")
                if element_ref:
                    surf.read_tree()
                path = surf.take_screenshot(output=out_path, element_ref=element_ref)
                if path:
                    result["detail"] = f"Saved: {path}"
                else:
                    result["status"] = "fail"
                    result["detail"] = "Screenshot failed"
                    failed = True

            elif action == "record":
                opts = value if isinstance(value, dict) else {}
                duration = opts.get("duration", 5)
                filename = opts.get("output", f"step{step_num}.mp4")
                out_path = str(out_dir / filename)
                element_ref = opts.get("element")
                window_name = opts.get("window")
                if element_ref:
                    surf.read_tree()
                path = surf.record_video(
                    output=out_path,
                    element_ref=element_ref,
                    window_name=window_name,
                    duration=duration,
                )
                if path:
                    result["detail"] = f"Saved: {path}"
                else:
                    result["status"] = "fail"
                    result["detail"] = "Recording failed"
                    failed = True

            elif action == "verify":
                opts = value if isinstance(value, dict) else {}
                surf.read_tree()
                role = opts.get("role")
                state = opts.get("state")
                name_match = opts.get("name")
                found = False
                for elem in surf._elements.values():
                    role_ok = not role or role.lower() in elem.role.lower()
                    state_ok = not state or state.lower() in [s.lower() for s in elem.states]
                    name_ok = not name_match or name_match.lower() in elem.name.lower()
                    if role_ok and state_ok and name_ok:
                        found = True
                        result["detail"] = f"Matched: [{elem.ref}] {elem.role} \"{elem.name}\""
                        break
                if not found:
                    result["status"] = "fail"
                    result["detail"] = f"No element matching: {opts}"
                    failed = True

            elif action == "wait":
                duration = float(value) if not isinstance(value, dict) else float(value.get("seconds", 1))
                time.sleep(duration)
                result["detail"] = f"{duration}s"

            else:
                result["status"] = "error"
                result["detail"] = f"Unknown action: {action}"
                failed = True

        except Exception as e:
            result["status"] = "error"
            result["detail"] = str(e)
            failed = True

        status_icon = "OK" if result["status"] == "ok" else "FAIL"
        print(f"    -> {status_icon}: {result['detail']}")
        report.append(result)

        # ── Auto-narration after step ───────────────────────
        if auto_narrate and narrator and action != "narrate":
            ctx = {}
            if action == "verify" and result["status"] == "fail":
                opts = value if isinstance(value, dict) else {}
                ctx = {"role": opts.get("role", ""), "state": opts.get("state", "")}
            elif action == "read" and result["status"] == "ok":
                try:
                    count = int(result["detail"].split()[0])
                    ctx = {"element_count": count}
                except (ValueError, IndexError):
                    pass

            narration_meta = narrator.react(
                step_type=action,
                outcome=result["status"],
                step_num=step_num,
                context=ctx,
            )
            if narration_meta:
                result["narration"] = {
                    "audio": narration_meta.get("audio"),
                    "taxonomy": narration_meta.get("taxonomy"),
                    "text": narration_meta.get("text"),
                }

    # Save narration session
    if narrator:
        narrator.save_session()

    # Write report
    report_path = out_dir / "report.json"
    summary = {
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "total_steps": len(steps),
        "passed": sum(1 for r in report if r["status"] == "ok"),
        "failed": sum(1 for r in report if r["status"] in ("fail", "error")),
        "output_dir": str(out_dir),
        "narration_storage": str(narrator.storage_dir) if narrator else None,
        "steps": report,
    }
    report_path.write_text(json.dumps(summary, indent=2))

    print(f"\nResult: {summary['passed']}/{summary['total_steps']} passed")
    print(f"Report: {report_path}")
    if narrator:
        print(f"Narration: {narrator.storage_dir}")

    return 1 if failed else 0


def _summarize(value: Any) -> str:
    """Short summary of a step value for logging."""
    if isinstance(value, str):
        return f'"{value}"' if len(value) < 40 else f'"{value[:37]}..."'
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)
