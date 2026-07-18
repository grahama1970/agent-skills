"""Agentic implementation chunk 6.

Loaded by lib/agentic.py to keep each Python source file below 800 lines.
"""

from dotenv import load_dotenv

load_dotenv()

def _severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)


def _load_document_family_preset(preset_path: Path | None) -> dict[str, Any] | None:
    if preset_path is None:
        return None
    path = preset_path.expanduser().resolve()
    if not path.exists() and not preset_path.is_absolute():
        repo_root = Path(os.environ.get("PDF_OXIDE_ROOT", "")).expanduser()
        candidate = (repo_root / preset_path).resolve() if repo_root.exists() else path
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise FileNotFoundError(f"Document-family preset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_preset_to_expected_payload(payload: dict[str, Any], preset: dict[str, Any] | None, preset_path: Path | None) -> None:
    if not preset:
        return
    payload["document_family_preset"] = _preset_metadata(preset, preset_path)
    overrides = preset.get("match_policy_overrides", {})
    if overrides:
        payload["match_policy"] = _deep_merge(payload.get("match_policy", {}), overrides)
    expected_transforms = preset.get("expected_element_transforms", {})
    if expected_transforms:
        elements = payload.get("elements", [])
        elements = _apply_text_replacements(elements, expected_transforms.get("text_replacements", []))
        elements = _filter_elements(elements, expected_transforms.get("drop_rules", []))
        elements = _apply_type_rules(elements, expected_transforms.get("type_rules", []))
        elements = _merge_same_line_elements(elements, expected_transforms.get("merge_same_line", {}))
        payload["elements"] = elements


def _apply_preset_to_actual_elements(elements: list[dict[str, Any]], preset: dict[str, Any]) -> list[dict[str, Any]]:
    extraction = preset.get("actual_element_transforms", {})
    text_replacements = extraction.get("text_replacements", [])
    type_rules = extraction.get("type_rules", [])
    bbox_expansion = extraction.get("bbox_expansion", {})
    drop_rules = extraction.get("drop_rules", [])
    embedded_rules = extraction.get("embedded_elements", [])
    revision_log_cells = extraction.get("revision_log_cells", {})
    transformed = []
    for element in elements:
        item = dict(element)
        text = str(item.get("text", ""))
        for replacement in text_replacements:
            pattern = replacement.get("pattern")
            value = replacement.get("replacement", "")
            if pattern:
                text = re.sub(pattern, value, text)
        item["text"] = text
        normalized = _normalize_text(text)
        for rule in type_rules:
            pattern = rule.get("pattern")
            target_type = rule.get("type")
            if pattern and target_type and re.search(pattern, normalized, re.I):
                item["type"] = target_type
                break
        expand_by = bbox_expansion.get(str(item.get("type")), bbox_expansion.get("default", 0.0))
        if expand_by and _valid_bbox(item.get("bbox")):
            item["bbox"] = _expand_bbox(item["bbox"], float(expand_by))
        item["preset_applied"] = preset.get("name", "document_family_preset")
        transformed.append(item)
        transformed.extend(_extract_embedded_elements(item, embedded_rules, preset))
    transformed = _filter_elements(transformed, drop_rules)
    transformed = _merge_same_line_elements(transformed, extraction.get("merge_same_line", {}))
    if revision_log_cells:
        generated_cells = []
        for item in transformed:
            generated_cells.extend(_extract_revision_log_cells(item, revision_log_cells, preset))
        transformed.extend(generated_cells)
    return transformed


def _extract_embedded_elements(element: dict[str, Any], rules: list[dict[str, Any]], preset: dict[str, Any]) -> list[dict[str, Any]]:
    if not rules or not _valid_bbox(element.get("bbox")):
        return []
    text = str(element.get("text", ""))
    created: list[dict[str, Any]] = []
    for rule in rules:
        source_text_regex = rule.get("source_text_regex")
        if source_text_regex and re.search(str(source_text_regex), text, re.I) is None:
            continue
        pattern = rule.get("extract_regex")
        target_type = rule.get("type")
        if not pattern or not target_type:
            continue
        for index, match in enumerate(re.finditer(str(pattern), text, re.I)):
            value = match.group(rule.get("group", 1))
            bbox = _embedded_bbox(element["bbox"], rule)
            created.append(
                {
                    "id": f"{element.get('id')}:embedded:{target_type}:{index}",
                    "page": element.get("page"),
                    "type": target_type,
                    "bbox": bbox,
                    "text": value,
                    "confidence": float(rule.get("confidence", 0.85)),
                    "source": f"{element.get('source', 'unknown')}+preset_embedded",
                    "preset_applied": preset.get("name", "document_family_preset"),
                    "embedded_from": element.get("id"),
                }
            )
    return created


def _embedded_bbox(source_bbox: BBox, rule: dict[str, Any]) -> BBox:
    x0, y0, x1, y1 = [float(value) for value in source_bbox]
    template = rule.get("bbox_template", {})
    return _clamp_bbox(
        [
            float(template.get("x0", x0)),
            y0 + float(template.get("y0_offset", 0.0)),
            float(template.get("x1", x1)),
            y1 + float(template.get("y1_offset", 0.0)),
        ]
    )


def _extract_revision_log_cells(element: dict[str, Any], config: dict[str, Any], preset: dict[str, Any]) -> list[dict[str, Any]]:
    if not config or not config.get("enabled", False) or not _valid_bbox(element.get("bbox")):
        return []
    text = re.sub(r"\s+", " ", str(element.get("text", "")).strip())
    date_pattern = str(config.get("date_regex", r"\d{2}-\d{2}-\d{4}"))
    row_pattern = re.compile(rf"^({date_pattern})\s+([A-Za-z]+)\s+(.+)$")
    match = row_pattern.match(text)
    if not match:
        return []
    row_type = match.group(2)
    allowed_types = {str(value).lower() for value in config.get("allowed_types", [])}
    if allowed_types and row_type.lower() not in allowed_types:
        return []

    remainder = match.group(3).strip()
    page_text = None
    page_match = re.search(r"\s+([0-9]+|[ivxlcdm]+)$", remainder, re.I)
    if page_match:
        page_text = page_match.group(1)
        revision_text = remainder[: page_match.start()].strip()
    else:
        revision_text = remainder
    if not revision_text:
        return []

    x0, y0, x1, y1 = [float(value) for value in element["bbox"]]
    columns = config.get("columns", {})
    cells = [
        ("date", "section_header", match.group(1), columns.get("date", [x0, x1])),
        ("type", "paragraph", row_type, columns.get("type", [x0, x1])),
        ("revision", "paragraph", revision_text, columns.get("revision", [x0, x1])),
    ]
    if page_text:
        cells.append(("page", "section_header", page_text, columns.get("page", [x0, x1])))

    created = []
    for cell_name, cell_type, cell_text, x_bounds in cells:
        cell_x0, cell_x1 = [float(value) for value in x_bounds]
        created.append(
            {
                "id": f"{element.get('id')}:revision_cell:{cell_name}",
                "page": element.get("page"),
                "type": cell_type,
                "bbox": _clamp_bbox([cell_x0, y0, cell_x1, y1]),
                "text": cell_text,
                "confidence": float(config.get("confidence", 0.9)),
                "source": f"{element.get('source', 'unknown')}+preset_revision_log_cell",
                "preset_applied": preset.get("name", "document_family_preset"),
                "embedded_from": element.get("id"),
            }
        )
    return created


def _filter_elements(elements: list[dict[str, Any]], drop_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not drop_rules:
        return elements
    return [element for element in elements if not any(_matches_drop_rule(element, rule) for rule in drop_rules)]


def _apply_text_replacements(elements: list[dict[str, Any]], text_replacements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not text_replacements:
        return elements
    updated = []
    for element in elements:
        item = dict(element)
        text = str(item.get("text", ""))
        for replacement in text_replacements:
            pattern = replacement.get("pattern")
            value = replacement.get("replacement", "")
            if pattern:
                text = re.sub(pattern, value, text)
        item["text"] = text
        updated.append(item)
    return updated


def _matches_drop_rule(element: dict[str, Any], rule: dict[str, Any]) -> bool:
    text = str(element.get("text", ""))
    element_type = str(element.get("type", ""))
    bbox = element.get("bbox")
    if "type" in rule and element_type != rule["type"]:
        return False
    if "types" in rule and element_type not in set(rule["types"]):
        return False
    if "text_regex" in rule and re.search(str(rule["text_regex"]), text, re.I) is None:
        return False
    if "text_equals" in rule and text.strip() != str(rule["text_equals"]):
        return False
    if _valid_bbox(bbox):
        x0, y0, x1, y1 = [float(value) for value in bbox]
        if "max_x1" in rule and x1 > float(rule["max_x1"]):
            return False
        if "min_x0" in rule and x0 < float(rule["min_x0"]):
            return False
        if "max_y1" in rule and y1 > float(rule["max_y1"]):
            return False
        if "min_y0" in rule and y0 < float(rule["min_y0"]):
            return False
    return True


def _apply_type_rules(elements: list[dict[str, Any]], type_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not type_rules:
        return elements
    updated = []
    for element in elements:
        item = dict(element)
        normalized = _normalize_text(str(item.get("text", "")))
        for rule in type_rules:
            pattern = rule.get("pattern")
            target_type = rule.get("type")
            if pattern and target_type and re.search(pattern, normalized, re.I):
                item["type"] = target_type
                break
        updated.append(item)
    return updated


def _merge_same_line_elements(elements: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config or not config.get("enabled", False):
        return elements
    merge_types = set(config.get("types", []))
    max_gap = float(config.get("max_gap", 0.03))
    max_y_delta = float(config.get("max_y_delta", 0.004))
    max_y_overlap_required = float(config.get("min_y_overlap", 0.55))
    pages: dict[int, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for element in elements:
        if merge_types and str(element.get("type")) not in merge_types:
            passthrough.append(element)
            continue
        if not _valid_bbox(element.get("bbox")):
            passthrough.append(element)
            continue
        pages.setdefault(int(element.get("page", 0)), []).append(element)

    merged: list[dict[str, Any]] = list(passthrough)
    for page, page_elements in pages.items():
        for ordered in _same_line_bands(page_elements, max_y_delta, max_y_overlap_required):
            current: dict[str, Any] | None = None
            for element in ordered:
                if current is None:
                    current = dict(element)
                    continue
                if _can_merge_same_line(current, element, max_gap, max_y_delta, max_y_overlap_required):
                    current = _merge_two_elements(current, element)
                else:
                    merged.append(current)
                    current = dict(element)
            if current is None:
                continue
            merged.append(current)
    return sorted(merged, key=lambda item: (int(item.get("page", 0)), item.get("bbox", [0, 0, 0, 0])[1], item.get("bbox", [0, 0, 0, 0])[0], str(item.get("id", ""))))


def _same_line_bands(elements: list[dict[str, Any]], max_y_delta: float, min_y_overlap: float) -> list[list[dict[str, Any]]]:
    bands: list[list[dict[str, Any]]] = []
    for element in sorted(elements, key=lambda item: (_bbox_center_y(item["bbox"]), item["bbox"][0])):
        placed = False
        for band in bands:
            representative = band[0]
            if abs(_bbox_center_y(representative["bbox"]) - _bbox_center_y(element["bbox"])) <= max_y_delta and _y_overlap_ratio(representative["bbox"], element["bbox"]) >= min_y_overlap:
                band.append(element)
                placed = True
                break
        if not placed:
            bands.append([element])
    return [sorted(band, key=lambda item: item["bbox"][0]) for band in bands]


def _can_merge_same_line(left: dict[str, Any], right: dict[str, Any], max_gap: float, max_y_delta: float, min_y_overlap: float) -> bool:
    if left.get("page") != right.get("page"):
        return False
    if left.get("type") != right.get("type"):
        return False
    left_bbox = left["bbox"]
    right_bbox = right["bbox"]
    if abs(_bbox_center_y(left_bbox) - _bbox_center_y(right_bbox)) > max_y_delta:
        return False
    if _y_overlap_ratio(left_bbox, right_bbox) < min_y_overlap:
        return False
    gap = float(right_bbox[0]) - float(left_bbox[2])
    return -0.005 <= gap <= max_gap


def _merge_two_elements(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    merged["id"] = f"{left.get('id')}+{right.get('id')}"
    merged["text"] = _join_fragments(str(left.get("text", "")), str(right.get("text", "")))
    merged["bbox"] = [
        min(float(left["bbox"][0]), float(right["bbox"][0])),
        min(float(left["bbox"][1]), float(right["bbox"][1])),
        max(float(left["bbox"][2]), float(right["bbox"][2])),
        max(float(left["bbox"][3]), float(right["bbox"][3])),
    ]
    merged["source"] = f"{left.get('source', 'unknown')}+preset_merge"
    merged["merged_from"] = [left.get("id"), right.get("id")]
    return merged


def _join_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if right.startswith("-") or left.endswith("-"):
        return f"{left}{right}"
    return f"{left} {right}"


def _bbox_center_y(bbox: BBox) -> float:
    return (float(bbox[1]) + float(bbox[3])) / 2.0


def _y_overlap_ratio(left: BBox, right: BBox) -> float:
    top = max(float(left[1]), float(right[1]))
    bottom = min(float(left[3]), float(right[3]))
    overlap = max(0.0, bottom - top)
    min_height = min(float(left[3]) - float(left[1]), float(right[3]) - float(right[1]))
    return overlap / min_height if min_height > 0 else 0.0


def _preset_metadata(preset: dict[str, Any] | None, preset_path: Path | None) -> dict[str, Any] | None:
    if not preset:
        return None
    return {
        "name": preset.get("name"),
        "schema_version": preset.get("schema_version"),
        "path": str(preset_path.expanduser().resolve()) if preset_path else None,
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_bbox(bbox: BBox, amount: float) -> BBox:
    x0, y0, x1, y1 = [float(value) for value in bbox]
    return _clamp_bbox([x0 - amount, y0 - amount, x1 + amount, y1 + amount])


def _default_match_policy() -> dict[str, Any]:
    return {
        "accuracy_formula": "matched_expected_elements / total_expected_elements",
        "verdict": "strict: missing/ambiguous/unwaived-extras/type-mismatch all block passed",
        "ambiguity_margin": 0.05,
        "text_similarity_threshold": 0.80,
        "bbox_iou_thresholds": {
            "default": 0.50,
            "running_header": 0.35,
            "running_footer": 0.35,
            "caption": 0.45,
            "table_candidate": 0.40,
        },
        "type_aliases": {
            "paragraph": ["paragraph", "table_candidate", "requirement"],
            "table_candidate": ["table_candidate", "table", "paragraph"],
            "requirement": ["requirement", "paragraph", "table_candidate"],
        },
    }


def _expected_confidence(element_type: str, text: str) -> float:
    if element_type in {"running_header", "running_footer", "requirement", "caption"}:
        return 0.9
    if element_type in {"table_candidate", "section_header", "list_item"}:
        return 0.8
    return 0.7


def _agent_reasoning(element_type: str, text: str, bbox: BBox) -> str:
    if element_type == "running_header":
        return "Element is in the top page band and should be recoverable as a running header."
    if element_type == "running_footer":
        return "Element is in the bottom page band and should be recoverable as footer/boilerplate."
    if element_type == "table_candidate":
        return "Line has multiple aligned whitespace gaps; verify deterministic grouping/classification."
    if element_type == "requirement":
        return "Line begins with a compliance-style control identifier."
    if element_type == "section_header":
        return "Short heading-like line detected by structural position/text cues."
    return "Expected text-bearing page element from independent bbox-layout scan."


def _table_text(table: Any) -> str:
    if isinstance(table, dict):
        if "text" in table:
            return str(table["text"])
        if "rows" in table:
            return " ".join(str(cell) for row in table["rows"] for cell in (row if isinstance(row, list) else [row]))
    return ""


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {key: _json_safe(item) for key, item in vars(value).items()}
    return str(value)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextmanager
def _suppress_native_stderr():
    """Suppress native extension writes to fd 2 while preserving Python errors."""
    saved_stderr = os.dup(2)
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)
