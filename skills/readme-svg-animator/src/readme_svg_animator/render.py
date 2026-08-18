"""Deterministic SVG builders for the bounded semantic scene templates.

The module accepts only validated models. It uses lxml element constructors for user
content, never concatenates user-authored XML, and emits a complete static base state with
animation isolated behind the reduced-motion media query.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from lxml import etree

from .io import load_scene, load_theme
from .models import (
    FanoutAnatomyScene,
    PositiveNegativeScene,
    Scene,
    Theme,
    Timeline,
    TimelineEvent,
)
from .timeline import CompiledTimeline, compile_timeline

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {None: SVG_NS}


def _qname(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def _element(parent: etree._Element, tag: str, **attrs: object) -> etree._Element:
    element = etree.SubElement(parent, _qname(tag))
    for key, value in attrs.items():
        if value is None:
            continue
        element.set(key.replace("_", "-"), str(value))
    return element


def _rgba(hex_color: str, opacity: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        raise ValueError(f"expected six-digit hex color: {hex_color}")
    red, green, blue = (int(color[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red},{green},{blue},{opacity:g})"


def _font_stack(values: Iterable[str]) -> str:
    rendered: list[str] = []
    for value in values:
        if " " in value and not value.startswith("'"):
            rendered.append(f"'{value}'")
        else:
            rendered.append(value)
    return ",".join(rendered)


def _base_css(theme: Theme) -> str:
    return "".join(
        [
            f".rsa-sans{{font-family:{_font_stack(theme.fonts.display)}}}",
            f".rsa-mono{{font-family:{_font_stack(theme.fonts.mono)}}}",
            f".rsa-shadow{{filter:{theme.shadows.text}}}",
            f".rsa-shadow-strong{{filter:{theme.shadows.strong}}}",
            ".rsa-target{transform-box:fill-box;transform-origin:center}",
        ]
    )


def _classes(compiled: CompiledTimeline, target: str, base: str = "") -> str:
    names = [name for name in base.split() if name]
    names.append("rsa-target")
    names.extend(compiled.classes_by_target.get(target, ()))
    return " ".join(names)


def _target(
    element: etree._Element,
    compiled: CompiledTimeline,
    target: str,
    base: str = "",
) -> None:
    element.set("data-target", target)
    element.set("class", _classes(compiled, target, base))


def _default_positive_timeline(theme: Theme) -> Timeline:
    cycle = theme.animation.ambient_cycle_ms
    return Timeline(
        cycle_ms=cycle,
        events=(
            TimelineEvent(
                target="left-glow",
                recipe="halo-pulse",
                start_ms=0,
                end_ms=cycle,
                peak_opacity=theme.opacity.halo_peak,
            ),
            TimelineEvent(
                target="right-glow",
                recipe="halo-pulse",
                start_ms=0,
                end_ms=cycle,
                delay_ms=cycle // 2,
                peak_opacity=theme.opacity.halo_peak,
            ),
        ),
    )


def _default_fanout_timeline(scene: FanoutAnatomyScene, theme: Theme) -> Timeline:
    cycle = theme.animation.narrative_cycle_ms
    events: list[TimelineEvent] = [
        TimelineEvent(
            target="source-node",
            recipe="fade-slide-y",
            start_ms=150,
            end_ms=900,
            from_y=-24,
        )
    ]
    for index, _target_card in enumerate(scene.targets):
        start = 900 + index * 200
        events.append(
            TimelineEvent(
                target=f"connector-{index}",
                recipe="draw-stroke",
                start_ms=start,
                end_ms=start + 450,
            )
        )
        events.append(
            TimelineEvent(
                target=f"target-card-{index}",
                recipe="fade",
                start_ms=start + 450,
                end_ms=start + 900,
            )
        )
    events.append(
        TimelineEvent(
            target="source-glow",
            recipe="halo-pulse",
            start_ms=7800,
            end_ms=11600,
            peak_opacity=theme.opacity.halo_peak,
        )
    )
    return Timeline(cycle_ms=cycle, events=tuple(events))


def _make_root(scene: Scene, theme: Theme, compiled: CompiledTimeline) -> etree._Element:
    canvas = theme.canvas
    root = etree.Element(_qname("svg"), nsmap=NSMAP)
    root.set("viewBox", " ".join(f"{value:g}" for value in canvas.view_box))
    root.set("width", str(canvas.width))
    root.set("height", str(canvas.height))
    root.set("role", "img")
    root.set("aria-labelledby", "rsa-title rsa-desc")

    title = _element(root, "title", id="rsa-title")
    title.text = scene.metadata.title
    description = _element(root, "desc", id="rsa-desc")
    description.text = scene.metadata.description
    style = _element(root, "style")
    style.text = _base_css(theme) + compiled.css
    _element(
        root,
        "rect",
        width=canvas.width,
        height=canvas.height,
        rx=canvas.radius,
        fill=canvas.background,
    )
    return root


def _add_text(
    parent: etree._Element,
    text: str,
    x: float,
    y: float,
    *,
    css_class: str,
    size: float,
    fill: str,
    anchor: str = "start",
    tracking: float | None = None,
    weight: int | None = None,
) -> etree._Element:
    element = _element(
        parent,
        "text",
        x=x,
        y=y,
        **{
            "class": css_class,
            "font-size": size,
            "fill": fill,
            "text-anchor": anchor,
            "dominant-baseline": "central",
            "letter-spacing": tracking,
            "font-weight": weight,
        },
    )
    element.text = text
    return element


def _render_positive_negative(
    root: etree._Element,
    scene: PositiveNegativeScene,
    theme: Theme,
    compiled: CompiledTimeline,
) -> None:
    palette = theme.palette
    typography = theme.typography
    strokes = theme.strokes
    left_color = getattr(palette, scene.left.accent)
    right_color = getattr(palette, scene.right.accent)

    header_data = [
        (scene.left.heading, 380, 170, left_color, True),
        (scene.right.heading, 1240, 170, right_color, False),
    ]
    for heading, circle_x, y, color, positive in header_data:
        _element(
            root,
            "circle",
            cx=circle_x,
            cy=y,
            r=30,
            fill="none",
            stroke=color,
            **{"stroke-width": strokes.emphasis},
        )
        if positive:
            _element(
                root,
                "path",
                d=f"M {circle_x - 14} {y + 1} L {circle_x - 4} {y + 12} L {circle_x + 15} {y - 12}",
                fill="none",
                stroke=color,
                **{
                    "stroke-width": strokes.icon,
                    "stroke-linecap": strokes.linecap,
                    "stroke-linejoin": strokes.linejoin,
                },
            )
        else:
            _element(
                root,
                "path",
                d=f"M {circle_x - 11} {y - 11} L {circle_x + 11} {y + 11} M {circle_x + 11} {y - 11} L {circle_x - 11} {y + 11}",
                fill="none",
                stroke=color,
                **{
                    "stroke-width": strokes.icon,
                    "stroke-linecap": strokes.linecap,
                },
            )
        _add_text(
            root,
            heading,
            circle_x + 60,
            y,
            css_class="rsa-sans rsa-shadow",
            size=typography.title_size,
            fill=color,
            tracking=typography.title_tracking,
        )

    cards = [
        (scene.left, left_color, 139, 150, "left-glow", "left-card", True),
        (scene.right, right_color, 999, 1010, "right-glow", "right-card", False),
    ]
    for column, color, glow_x, card_x, glow_target, card_target, positive in cards:
        glow = _element(
            root,
            "rect",
            x=glow_x,
            y=249,
            width=782,
            height=682,
            rx=theme.radii.outer_card,
            fill="none",
            stroke=color,
            opacity=theme.opacity.halo_peak,
            **{"stroke-width": strokes.thin},
        )
        _target(glow, compiled, glow_target)
        card = _element(
            root,
            "rect",
            x=card_x,
            y=260,
            width=760,
            height=660,
            rx=theme.radii.card,
            fill=_rgba(color, theme.opacity.soft_panel_accent),
            stroke=color,
            **{"stroke-width": strokes.normal},
        )
        _target(card, compiled, card_target)
        icon_x = card_x + 50
        text_x = card_x + 110
        for index, item in enumerate(column.items):
            y = 360 + index * 110
            _add_text(
                root,
                item,
                text_x,
                y,
                css_class="rsa-sans rsa-shadow",
                size=typography.body_size,
                fill=palette.white if positive else _rgba(palette.white, 0.85),
            )
            if positive:
                _element(
                    root,
                    "path",
                    d=f"M {icon_x} {y} L {icon_x + 12} {y + 12} L {icon_x + 32} {y - 14}",
                    fill="none",
                    stroke=color,
                    **{
                        "stroke-width": strokes.emphasis,
                        "stroke-linecap": strokes.linecap,
                        "stroke-linejoin": strokes.linejoin,
                    },
                )
            else:
                _element(
                    root,
                    "path",
                    d=f"M {icon_x} {y - 12} L {icon_x + 24} {y + 12} M {icon_x + 24} {y - 12} L {icon_x} {y + 12}",
                    fill="none",
                    stroke=color,
                    **{
                        "stroke-width": strokes.emphasis,
                        "stroke-linecap": strokes.linecap,
                    },
                )

    _add_text(
        root,
        scene.caption,
        960,
        1000,
        css_class="rsa-sans",
        size=typography.caption_size,
        fill=_rgba(palette.white, theme.opacity.secondary_text),
        anchor="middle",
        tracking=typography.caption_tracking,
    )


def _render_fanout(
    root: etree._Element,
    scene: FanoutAnatomyScene,
    theme: Theme,
    compiled: CompiledTimeline,
) -> None:
    palette = theme.palette
    typography = theme.typography
    strokes = theme.strokes
    source_glow = _element(
        root,
        "rect",
        x=629,
        y=119,
        width=662,
        height=222,
        rx=26,
        fill="none",
        stroke=palette.cyan,
        opacity=theme.opacity.halo_peak,
        **{"stroke-width": strokes.thin},
    )
    _target(source_glow, compiled, "source-glow")
    source_group = _element(root, "g")
    _target(source_group, compiled, "source-node")
    _element(
        source_group,
        "rect",
        x=640,
        y=130,
        width=640,
        height=200,
        rx=theme.radii.card,
        fill=_rgba(palette.deep_panel, theme.opacity.panel_fill),
        stroke=palette.cyan,
        **{"stroke-width": strokes.emphasis},
    )
    _add_text(
        source_group,
        scene.source.title,
        960,
        196,
        css_class="rsa-mono rsa-shadow",
        size=36,
        fill=palette.cyan,
        anchor="middle",
    )
    _add_text(
        source_group,
        scene.source.subtitle,
        960,
        272,
        css_class="rsa-sans",
        size=26,
        fill=_rgba(palette.white, theme.opacity.secondary_text),
        anchor="middle",
    )

    count = len(scene.targets)
    card_width = 360
    gap = 60 if count == 4 else 100
    total = count * card_width + (count - 1) * gap
    start_x = (theme.canvas.width - total) / 2
    centers = [start_x + card_width / 2 + index * (card_width + gap) for index in range(count)]

    for index, center_x in enumerate(centers):
        path = _element(
            root,
            "path",
            d=f"M 960 341 V 440 H {center_x:g} V 630",
            fill="none",
            stroke=palette.cyan,
            opacity=0.9,
            pathLength=1,
            **{
                "stroke-width": strokes.normal,
                "stroke-linecap": strokes.linecap,
                "stroke-dasharray": 1,
                "stroke-dashoffset": 0,
            },
        )
        _target(path, compiled, f"connector-{index}")

    for index, target in enumerate(scene.targets):
        x = start_x + index * (card_width + gap)
        color = getattr(palette, target.accent)
        group = _element(root, "g")
        _target(group, compiled, f"target-card-{index}")
        _element(
            group,
            "rect",
            x=x,
            y=640,
            width=card_width,
            height=220,
            rx=16,
            fill=_rgba(palette.deep_panel, theme.opacity.panel_fill),
            stroke=_rgba(palette.white, theme.opacity.secondary_border),
            **{"stroke-width": strokes.thin},
        )
        _element(group, "circle", cx=x + 60, cy=700, r=26, fill=color)
        _add_text(
            group,
            str(target.number),
            x + 60,
            700,
            css_class="rsa-sans",
            size=34,
            fill=palette.dark_text,
            anchor="middle",
            weight=700,
        )
        _add_text(
            group,
            target.heading,
            x + card_width / 2,
            770,
            css_class="rsa-sans rsa-shadow",
            size=typography.heading_size,
            fill=palette.white,
            anchor="middle",
            tracking=typography.heading_tracking,
        )
        _add_text(
            group,
            target.detail,
            x + card_width / 2,
            820,
            css_class="rsa-mono",
            size=typography.supporting_size,
            fill=_rgba(palette.white, theme.opacity.secondary_text),
            anchor="middle",
        )

    _add_text(
        root,
        scene.caption,
        960,
        960,
        css_class="rsa-sans",
        size=typography.caption_size,
        fill=_rgba(palette.white, theme.opacity.secondary_text),
        anchor="middle",
        tracking=typography.caption_tracking,
    )


def render_scene(scene: Scene, theme: Theme) -> str:
    """Render one validated scene to deterministic UTF-8 SVG text."""

    if isinstance(scene, PositiveNegativeScene):
        timeline = scene.timeline or _default_positive_timeline(theme)
    elif isinstance(scene, FanoutAnatomyScene):
        timeline = scene.timeline or _default_fanout_timeline(scene, theme)
    else:
        raise TypeError(f"unsupported scene model: {type(scene).__name__}")

    compiled = compile_timeline(timeline, theme.animation)
    if isinstance(scene, PositiveNegativeScene):
        allowed_targets = {"left-glow", "right-glow", "left-card", "right-card"}
    else:
        allowed_targets = {"source-node", "source-glow"}
        allowed_targets.update(f"connector-{index}" for index in range(len(scene.targets)))
        allowed_targets.update(f"target-card-{index}" for index in range(len(scene.targets)))
    unknown = sorted(set(compiled.classes_by_target) - set(allowed_targets))
    if unknown:
        raise ValueError(f"timeline contains unknown targets: {', '.join(unknown)}")

    root = _make_root(scene, theme, compiled)
    if isinstance(scene, PositiveNegativeScene):
        _render_positive_negative(root, scene, theme, compiled)
    else:
        _render_fanout(root, scene, theme, compiled)

    return etree.tostring(
        root,
        encoding="unicode",
        pretty_print=True,
        xml_declaration=False,
    )


def render_scene_file(scene_path: Path, output_path: Path) -> tuple[str, Theme]:
    """Load, validate, render, and write one scene."""

    scene = load_scene(scene_path)
    theme = load_theme(scene.theme, scene_path.parent)
    svg = render_scene(scene, theme)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return svg, theme
