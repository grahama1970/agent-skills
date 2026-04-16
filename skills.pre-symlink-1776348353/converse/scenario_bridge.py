"""Async scenario bridge: connects surf-qml AT-SPI automation to the
conversation orchestrator.

Runs scenario steps in a thread (AT-SPI is synchronous), emits
ScenarioStepResult events to an async queue. The orchestrator consumes
these events and has Embry speak/react through her own pipeline
(thinker → speaker → mixer), not surf-qml's standalone NarrationEngine.

This means all audio goes through a single mixer → PipeWire path,
so humming, speech, and scenario narration blend naturally.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger as log

from emotion import EmotionState

SKILLS_ROOT = Path(__file__).resolve().parent.parent
SURF_QML_DIR = SKILLS_ROOT / "surf-qml"
SCENARIO_DIR = SURF_QML_DIR / "scenarios"

# Ensure surf-qml is importable
sys.path.insert(0, str(SURF_QML_DIR))


@dataclass
class ScenarioStepResult:
    """Result of a single scenario step, consumed by the orchestrator."""
    step_num: int
    total_steps: int
    action: str           # find, focus, click, read, verify, snap, narrate, wait, ...
    value: Any            # the step's argument
    status: str           # ok, fail, error
    detail: str           # human-readable outcome
    narration: str        # what Embry should say about this step
    emotion_hint: Optional[EmotionState] = None  # suggested emotion shift
    is_final: bool = False
    timestamp: float = 0.0
    artifacts: dict = field(default_factory=dict)  # screenshots, recordings, etc.


# Maps (action, status) → narration template
# Embry speaks naturally about what she's doing — not robotic status reports
STEP_NARRATIONS = {
    # Success
    ("find", "ok"): "Found it. Let me take a look at {value}.",
    ("focus", "ok"): "Okay, I've got {value} in focus now.",
    ("click", "ok"): "Clicked {value}.",
    ("type", "ok"): "Typed that in. Let's see what happens.",
    ("snap", "ok"): "Captured a screenshot.",
    ("record", "ok"): "Got the recording.",
    ("verify", "ok"): "Good — that checks out.",
    ("read", "ok"): "{detail}.",
    ("key", "ok"): None,   # too frequent
    ("wait", "ok"): None,  # silence is fine

    # Failure — these are where Embry's personality shows
    ("find", "fail"): "I can't find {value}. Where did it go?",
    ("focus", "fail"): "Hmm, I can't focus that window. That's... not great.",
    ("click", "fail"): "The click didn't land. Is that element actually there?",
    ("type", "fail"): "Text didn't go in. Something's blocking input.",
    ("verify", "fail"): "That's not right. I expected something different here.",
    ("snap", "fail"): "Screenshot failed. That's unexpected.",
    ("record", "fail"): "Recording failed. Probably a display access issue.",

    # Errors
    ("find", "error"): "Something broke trying to find {value}. Let me check.",
    ("focus", "error"): "Error focusing the window. AT-SPI might be having issues.",
}

# Emotion suggestions based on step outcomes
OUTCOME_EMOTIONS = {
    ("verify", "ok"): EmotionState.PLEASED,
    ("verify", "fail"): EmotionState.FRUSTRATED,
    ("find", "fail"): EmotionState.CONFUSED,
    ("focus", "fail"): EmotionState.CONFUSED,
    ("click", "fail"): EmotionState.FRUSTRATED,
    ("snap", "ok"): EmotionState.FOCUSED,
    ("read", "ok"): EmotionState.CURIOUS,
}


class AsyncScenarioExecutor:
    """Runs surf-qml scenarios asynchronously, yielding step results.

    Executes AT-SPI operations in a thread pool (they're synchronous),
    emits ScenarioStepResult objects to a queue that the conversation
    orchestrator consumes.
    """

    def __init__(self, scenario_path: str):
        self.scenario_path = scenario_path
        self._scenario: Optional[dict] = None
        self._surf = None
        self._out_dir: Optional[Path] = None
        self._queue: asyncio.Queue[ScenarioStepResult] = asyncio.Queue()
        self._running = False
        self._report: list[dict] = []

    @property
    def queue(self) -> asyncio.Queue[ScenarioStepResult]:
        return self._queue

    def _load_scenario(self) -> dict:
        """Load scenario from YAML/JSON file."""
        path = Path(self.scenario_path)
        candidates = [path]
        if not path.is_absolute():
            candidates.append(SCENARIO_DIR / self.scenario_path)
            for ext in (".yaml", ".yml", ".json"):
                candidates.append(SCENARIO_DIR / f"{self.scenario_path}{ext}")

        for candidate in candidates:
            if candidate.is_file():
                text = candidate.read_text()
                if candidate.suffix in (".yaml", ".yml"):
                    try:
                        import yaml
                        return yaml.safe_load(text)
                    except ImportError:
                        raise RuntimeError("PyYAML required: pip install pyyaml")
                return json.loads(text)

        raise FileNotFoundError(f"Scenario not found: {self.scenario_path}")

    def _init_surf(self):
        """Initialize SurfQML for AT-SPI interaction."""
        from surf_qml import SurfQML
        self._surf = SurfQML(timeout=5.0)

    def _make_output_dir(self, name: str) -> Path:
        """Create timestamped output directory."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = name.replace(" ", "_").replace("/", "_")
        out = Path(f"/tmp/surf-qml-scenarios/{safe}_{ts}")
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _execute_step_sync(self, step: dict) -> dict:
        """Execute a single scenario step synchronously (runs in thread).

        Returns raw result dict with action, status, detail, artifacts.
        """
        if not isinstance(step, dict):
            return {"action": "unknown", "status": "error", "detail": "invalid step format"}

        action = next(iter(step))
        value = step[action]
        result = {"action": action, "value": value, "status": "ok", "detail": "", "artifacts": {}}

        try:
            surf = self._surf

            if action == "narrate":
                # narrate steps become direct speech — just pass the text through
                opts = value if isinstance(value, dict) else {"text": str(value)}
                result["detail"] = opts.get("text", str(value))

            elif action == "find":
                window = surf.find_window(str(value))
                if not window:
                    result["status"] = "fail"
                    result["detail"] = f"Window not found: {value}"
                else:
                    result["detail"] = f"Found: {window.get_name()}"

            elif action == "focus":
                if not surf.focus_window(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to focus: {value}"
                else:
                    result["detail"] = f"Focused: {value}"
                import time as _t
                _t.sleep(0.3)

            elif action == "read":
                kwargs = {}
                if isinstance(value, dict):
                    kwargs["role_filter"] = value.get("role")
                    kwargs["name_filter"] = value.get("name")
                    kwargs["max_depth"] = value.get("depth", 10)
                elements = surf.read_tree(**kwargs)
                count = len(elements)
                if count == 0:
                    result["detail"] = "No elements found"
                elif count > 20:
                    result["detail"] = f"Found {count} elements. A lot going on here"
                else:
                    result["detail"] = f"Found {count} elements"

            elif action == "click":
                surf.read_tree()
                if not surf.click(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to click: {value}"
                else:
                    result["detail"] = f"Clicked: {value}"

            elif action == "type":
                if not surf.type_text(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Failed to type"
                else:
                    result["detail"] = f"Typed: {str(value)[:30]}"

            elif action == "key":
                if not surf.press_key(str(value)):
                    result["status"] = "fail"
                    result["detail"] = f"Key failed: {value}"
                else:
                    result["detail"] = f"Pressed: {value}"

            elif action == "snap":
                opts = value if isinstance(value, dict) else {}
                filename = opts.get("output", f"step.png")
                out_path = str(self._out_dir / filename)
                element_ref = opts.get("element")
                if element_ref:
                    surf.read_tree()
                path = surf.take_screenshot(output=out_path, element_ref=element_ref)
                if path:
                    result["detail"] = f"Screenshot saved"
                    result["artifacts"]["screenshot"] = path
                else:
                    result["status"] = "fail"
                    result["detail"] = "Screenshot failed"

            elif action == "record":
                opts = value if isinstance(value, dict) else {}
                duration = opts.get("duration", 5)
                filename = opts.get("output", f"step.mp4")
                out_path = str(self._out_dir / filename)
                path = surf.record_video(output=out_path, duration=duration)
                if path:
                    result["detail"] = f"Recorded {duration}s"
                    result["artifacts"]["recording"] = path
                else:
                    result["status"] = "fail"
                    result["detail"] = "Recording failed"

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

            elif action == "wait":
                duration = float(value) if not isinstance(value, dict) else float(value.get("seconds", 1))
                import time as _t
                _t.sleep(duration)
                result["detail"] = f"Waited {duration}s"

            else:
                result["status"] = "error"
                result["detail"] = f"Unknown action: {action}"

        except Exception as e:
            result["status"] = "error"
            result["detail"] = str(e)

        return result

    def _generate_narration(self, action: str, value: Any, status: str, detail: str) -> str:
        """Generate natural narration text for a step result."""
        # narrate steps are direct speech
        if action == "narrate":
            if isinstance(value, dict):
                return value.get("text", str(value))
            return str(value)

        template = STEP_NARRATIONS.get((action, status))
        if template is None:
            return ""  # no narration for this step

        # Format template with available context
        try:
            value_str = str(value) if not isinstance(value, dict) else json.dumps(value)
            return template.format(value=value_str, detail=detail)
        except (KeyError, IndexError):
            return template

    async def run(self):
        """Load scenario and execute all steps, emitting results to queue."""
        self._running = True
        loop = asyncio.get_event_loop()

        try:
            # Load scenario
            self._scenario = await loop.run_in_executor(None, self._load_scenario)
            name = self._scenario.get("name", "scenario")
            steps = self._scenario.get("steps", [])
            if not steps:
                log.warning(f"Scenario '{name}' has no steps")
                return

            # Init output dir
            self._out_dir = self._make_output_dir(name)

            # Init AT-SPI
            await loop.run_in_executor(None, self._init_surf)

            log.info(f"Running scenario: {name} ({len(steps)} steps)")
            log.info(f"Output: {self._out_dir}")

            # Execute steps
            for i, step in enumerate(steps):
                if not self._running:
                    break

                step_num = i + 1
                is_final = (step_num == len(steps))

                # Run step in thread (AT-SPI is synchronous)
                raw = await loop.run_in_executor(None, self._execute_step_sync, step)

                action = raw["action"]
                value = raw.get("value", "")
                status = raw["status"]
                detail = raw["detail"]

                # Generate narration text
                narration = self._generate_narration(action, value, status, detail)

                # Suggest emotion
                emotion_hint = OUTCOME_EMOTIONS.get((action, status))

                result = ScenarioStepResult(
                    step_num=step_num,
                    total_steps=len(steps),
                    action=action,
                    value=value,
                    status=status,
                    detail=detail,
                    narration=narration,
                    emotion_hint=emotion_hint,
                    is_final=is_final,
                    timestamp=time.time(),
                    artifacts=raw.get("artifacts", {}),
                )

                log.info(f"  Step {step_num}/{len(steps)}: {action} → {status}: {detail}")
                await self._queue.put(result)

                # Small pause between steps to let orchestrator speak
                if narration and not is_final:
                    await asyncio.sleep(0.5)

            # Write report
            report_path = self._out_dir / "report.json"
            summary = {
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "total_steps": len(steps),
                "output_dir": str(self._out_dir),
            }
            report_path.write_text(json.dumps(summary, indent=2))
            log.info(f"Scenario complete. Report: {report_path}")

        except Exception as e:
            log.error(f"Scenario execution failed: {e}")
            # Emit error as final step
            await self._queue.put(ScenarioStepResult(
                step_num=0, total_steps=0, action="error", value="",
                status="error", detail=str(e),
                narration=f"Something went wrong with the scenario. {e}",
                is_final=True, timestamp=time.time(),
            ))
        finally:
            self._running = False

    def stop(self):
        """Stop scenario execution."""
        self._running = False
