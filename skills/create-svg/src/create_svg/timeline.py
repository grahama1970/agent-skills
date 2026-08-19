"""Compile validated millisecond timeline events into synchronized CSS keyframes.

The compiler owns timing arithmetic. Renderers only attach returned class names to
semantic SVG targets. Unsupported targets are rejected by the renderer before emission.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AnimationTheme, Timeline, TimelineEvent


@dataclass(frozen=True, slots=True)
class CompiledTimeline:
    css: str
    classes_by_target: dict[str, tuple[str, ...]]


def percent(milliseconds: int | float, cycle_ms: int) -> str:
    """Convert a time to a compact, deterministic CSS percentage."""

    value = round(float(milliseconds) / float(cycle_ms) * 100.0, 3)
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _frame(offset: str, declarations: str) -> str:
    return f"{offset}%{{{declarations}}}"


def _event_keyframes(event: TimelineEvent, cycle_ms: int, easing: AnimationTheme) -> str:
    start = percent(event.start_ms, cycle_ms)
    end = percent(event.end_ms, cycle_ms)
    midpoint = percent((event.start_ms + event.end_ms) / 2.0, cycle_ms)
    enter = easing.enter_easing

    if event.recipe == "fade":
        return "".join(
            [
                _frame("0", "opacity:0"),
                _frame(start, f"opacity:0;animation-timing-function:{enter}"),
                _frame(end, "opacity:1"),
                _frame("100", "opacity:1"),
            ]
        )
    if event.recipe == "fade-slide-x":
        return "".join(
            [
                _frame("0", f"opacity:0;transform:translateX({event.from_x}px)"),
                _frame(
                    start,
                    f"opacity:0;transform:translateX({event.from_x}px);"
                    f"animation-timing-function:{enter}",
                ),
                _frame(end, "opacity:1;transform:translateX(0)"),
                _frame("100", "opacity:1;transform:translateX(0)"),
            ]
        )
    if event.recipe == "fade-slide-y":
        return "".join(
            [
                _frame("0", f"opacity:0;transform:translateY({event.from_y}px)"),
                _frame(
                    start,
                    f"opacity:0;transform:translateY({event.from_y}px);"
                    f"animation-timing-function:{enter}",
                ),
                _frame(end, "opacity:1;transform:translateY(0)"),
                _frame("100", "opacity:1;transform:translateY(0)"),
            ]
        )
    if event.recipe == "draw-stroke":
        return "".join(
            [
                _frame("0", "opacity:0;stroke-dashoffset:1"),
                _frame(
                    start,
                    f"opacity:0;stroke-dashoffset:1;animation-timing-function:{enter}",
                ),
                _frame(end, "opacity:1;stroke-dashoffset:0"),
                _frame("100", "opacity:1;stroke-dashoffset:0"),
            ]
        )
    if event.recipe in {"pulse", "halo-pulse"}:
        peak = event.peak_opacity
        pulse_easing = easing.pulse_easing
        return "".join(
            [
                _frame("0", "opacity:0"),
                _frame(start, f"opacity:0;animation-timing-function:{pulse_easing}"),
                _frame(midpoint, f"opacity:{peak};animation-timing-function:{pulse_easing}"),
                _frame(end, "opacity:0"),
                _frame("100", "opacity:0"),
            ]
        )
    if event.recipe == "color-pin":
        prop = event.color_property
        return "".join(
            [
                _frame("0", f"{prop}:{event.from_color}"),
                _frame(
                    start,
                    f"{prop}:{event.from_color};animation-timing-function:{enter}",
                ),
                _frame(end, f"{prop}:{event.to_color}"),
                _frame("100", f"{prop}:{event.to_color}"),
            ]
        )
    raise ValueError(f"unsupported animation recipe: {event.recipe}")


def compile_timeline(timeline: Timeline, animation_theme: AnimationTheme) -> CompiledTimeline:
    """Compile one synchronized timeline and return target-to-class bindings."""

    duration_s = timeline.cycle_ms / 1000.0
    class_map: dict[str, list[str]] = {}
    rules: list[str] = ["@media (prefers-reduced-motion: no-preference){"]

    for index, event in enumerate(timeline.events):
        animation_name = f"rsa_k{index:03d}"
        class_name = f"rsa_a{index:03d}"
        keyframes = _event_keyframes(event, timeline.cycle_ms, animation_theme)
        delay_s = event.delay_ms / 1000.0
        rules.append(f"@keyframes {animation_name}{{{keyframes}}}")
        extra = "stroke-dasharray:1;stroke-dashoffset:1;" if event.recipe == "draw-stroke" else ""
        rules.append(
            f".{class_name}{{{extra}animation:{animation_name} {duration_s:g}s linear "
            f"{delay_s:g}s infinite both}}"
        )
        class_map.setdefault(event.target, []).append(class_name)

    rules.append("}")
    frozen_map = {target: tuple(classes) for target, classes in class_map.items()}
    return CompiledTimeline(css="".join(rules), classes_by_target=frozen_map)
