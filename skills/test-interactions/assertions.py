"""Playwright-inspired assertion engine with auto-retry.

All assertions retry until timeout (default 5s), eliminating flakiness
from async DOM updates in SPAs.

Supported assertions:
  assert_selector / assert_selector_not  — element exists/absent in DOM
  assert_visible / assert_visible_not    — element visible (not display:none/hidden/zero-size)
  assert_text / assert_text_not          — text in scoped element or page
  assert_absent                          — shorthand for assert_selector_not
  assert_count                           — element count in {min, max} range
  assert_attribute                       — element attribute value (exact or contains)
  assert_css                             — computed CSS property value
  assert_value                           — input/textarea/select current value
  assert_url                             — current page URL (exact or contains)
  assert_enabled / assert_disabled       — interactive element state
  assert_aria                            — ARIA attribute value
  assert_min_size                        — bounding rect >= threshold (COTS C02)
  assert_font_size                       — computed fontSize >= threshold (COTS C01)
  assert_contrast                        — WCAG contrast ratio >= threshold (COTS C03)
  assert_title                           — element has title attribute (COTS C14)
  assert_qs_action                       — element has data-qs-action attribute
  assert_focus_visible                   — Tab to element, verify focus indicator
  assert_qid_compliance                  — all [data-qid] elements pass 4-attribute rule
"""

import json
import time

from cdp_client import CDPClient


def _retry(fn, timeout_ms: int = 5000, poll_ms: int = 200):
    """Auto-retry fn() -> (passed, evidence) until it passes or times out."""
    deadline = time.time() + timeout_ms / 1000.0
    last_evidence = ""
    while True:
        passed, evidence = fn()
        if passed:
            return True, evidence
        last_evidence = evidence
        if time.time() >= deadline:
            return False, last_evidence
        time.sleep(poll_ms / 1000.0)


def _append(results: list, check: str, passed: bool, evidence: str):
    results.append({"check": check, "status": "PASS" if passed else "FAIL", "evidence": evidence})


def run_assertions(cdp: CDPClient, interaction: dict, wait_ms: int) -> list[dict]:
    """Run all assertions on an interaction with auto-retry."""
    results = []
    timeout = interaction.get("assert_timeout_ms", 5000)

    time.sleep(wait_ms / 1000.0)

    # wait_for
    wait_for = interaction.get("wait_for")
    if wait_for:
        wf_timeout = interaction.get("wait_for_timeout_ms", timeout)
        found = cdp.wait_for_selector(wait_for, wf_timeout)
        _append(results, f"wait_for({wait_for})", found,
                f"{'found' if found else 'NOT found'} within {wf_timeout}ms")

    # assert_selector
    assert_sel = interaction.get("assert_selector")
    if assert_sel:
        negate = interaction.get("assert_selector_not", False)
        def check():
            exists = cdp.selector_exists(assert_sel)
            if negate:
                return (not exists, "correctly absent" if not exists else "unexpectedly present")
            text = cdp.get_text_content(assert_sel)[:100] if exists else ""
            return (exists, f"text={text!r}" if exists else "element not found")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_selector{'_not' if negate else ''}({assert_sel})", passed, evidence)

    # assert_visible
    assert_vis = interaction.get("assert_visible")
    if assert_vis:
        negate = interaction.get("assert_visible_not", False)
        def check():
            visible = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(assert_vis)});"
                f"  if (!el) return false;"
                f"  var r = el.getBoundingClientRect();"
                f"  if (r.width === 0 || r.height === 0) return false;"
                f"  var s = getComputedStyle(el);"
                f"  return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';"
                f"}})()"
            )
            if negate:
                return (not visible, "correctly hidden" if not visible else "unexpectedly visible")
            return (bool(visible), "visible" if visible else "not visible (hidden/zero-size/display:none)")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_visible{'_not' if negate else ''}({assert_vis})", passed, evidence)

    # assert_text (single string)
    assert_text = interaction.get("assert_text")
    if assert_text:
        scope_sel = interaction.get("assert_text_scope")
        negate = interaction.get("assert_text_not", False)
        def check():
            text = cdp.get_text_content(scope_sel) if scope_sel else cdp.get_inner_text()
            scope_label = scope_sel or "page"
            found = assert_text in text
            if negate:
                return (not found, f"correctly absent from {scope_label}" if not found else f"unexpectedly found in {scope_label}")
            return (found, f"found in {scope_label}" if found else f"NOT found in {scope_label}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_text{'_not' if negate else ''}({assert_text!r})", passed, evidence)

    # assert_texts (array — all must be present)
    assert_texts = interaction.get("assert_texts")
    if assert_texts:
        scope_sel = interaction.get("assert_text_scope")
        for expected in assert_texts:
            def check(exp=expected):
                text = cdp.get_text_content(scope_sel) if scope_sel else cdp.get_inner_text()
                scope_label = scope_sel or "page"
                found = exp in text
                return (found, f"found in {scope_label}" if found else f"NOT found in {scope_label}")
            passed, evidence = _retry(check, timeout)
            _append(results, f"assert_texts({expected!r})", passed, evidence)

    # assert_absent
    assert_absent = interaction.get("assert_absent")
    if assert_absent:
        def check():
            exists = cdp.selector_exists(assert_absent)
            return (not exists, "correctly absent" if not exists else "UNEXPECTEDLY present")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_absent({assert_absent})", passed, evidence)

    # assert_count
    assert_count = interaction.get("assert_count")
    if assert_count:
        sel = assert_count["selector"]
        min_c, max_c = assert_count.get("min", 0), assert_count.get("max", 999999)
        def check():
            count = cdp.selector_count(sel)
            return (min_c <= count <= max_c, f"count={count}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_count({sel}, {min_c}..{max_c})", passed, evidence)

    # assert_attribute
    assert_attr = interaction.get("assert_attribute")
    if assert_attr:
        sel, attr = assert_attr["selector"], assert_attr["attribute"]
        expected, contains = assert_attr.get("value"), assert_attr.get("contains")
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? el.getAttribute({json.dumps(attr)}) : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element or attribute not found")
            if expected is not None:
                ok = val == expected
                return (ok, f"{attr}={val!r} {'==' if ok else '!='} {expected!r}")
            if contains is not None:
                ok = contains in str(val)
                return (ok, f"{attr}={val!r} {'contains' if ok else 'missing'} {contains!r}")
            return (True, f"{attr}={val!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_attribute({sel}, {attr})", passed, evidence)

    # assert_css
    assert_css = interaction.get("assert_css")
    if assert_css:
        sel, prop = assert_css["selector"], assert_css["property"]
        expected, contains = assert_css.get("value"), assert_css.get("contains")
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? getComputedStyle(el).getPropertyValue({json.dumps(prop)}) : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element not found")
            if expected is not None:
                ok = val.strip() == expected.strip()
                return (ok, f"{prop}: {val!r} {'==' if ok else '!='} {expected!r}")
            if contains is not None:
                ok = contains in str(val)
                return (ok, f"{prop}: {val!r} {'contains' if ok else 'missing'} {contains!r}")
            return (True, f"{prop}: {val!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_css({sel}, {prop})", passed, evidence)

    # assert_value
    assert_value = interaction.get("assert_value")
    if assert_value:
        sel, expected = assert_value["selector"], assert_value["value"]
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? el.value : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element not found")
            ok = str(val) == str(expected)
            return (ok, f"value={val!r} {'==' if ok else '!='} {expected!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_value({sel})", passed, evidence)

    # assert_url
    assert_url = interaction.get("assert_url")
    if assert_url:
        url_spec = {"contains": assert_url} if isinstance(assert_url, str) else assert_url
        def check():
            url = cdp.evaluate("window.location.href") or ""
            if "exact" in url_spec:
                ok = url == url_spec["exact"]
                return (ok, f"url={url!r} {'==' if ok else '!='} {url_spec['exact']!r}")
            if "contains" in url_spec:
                ok = url_spec["contains"] in url
                return (ok, f"url={url!r} {'contains' if ok else 'missing'} {url_spec['contains']!r}")
            return (True, f"url={url!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_url({url_spec})", passed, evidence)

    # assert_enabled / assert_disabled
    for key, expect_disabled in [("assert_enabled", False), ("assert_disabled", True)]:
        sel = interaction.get(key)
        if sel:
            def check(ed=expect_disabled):
                disabled = cdp.evaluate(
                    f"(function() {{"
                    f"  var el = document.querySelector({json.dumps(sel)});"
                    f"  if (!el) return null;"
                    f"  return el.disabled === true || el.getAttribute('aria-disabled') === 'true';"
                    f"}})()"
                )
                if disabled is None:
                    return (False, "element not found")
                is_disabled = bool(disabled)
                if ed:
                    return (is_disabled, "disabled" if is_disabled else "NOT disabled")
                return (not is_disabled, "enabled" if not is_disabled else "NOT enabled (disabled)")
            passed, evidence = _retry(check, timeout)
            _append(results, f"{key}({sel})", passed, evidence)

    # assert_aria
    assert_aria = interaction.get("assert_aria")
    if assert_aria:
        sel, attr = assert_aria["selector"], assert_aria["attribute"]
        expected = str(assert_aria["value"])
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? el.getAttribute({json.dumps(attr)}) : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element or attribute not found")
            ok = str(val) == expected
            return (ok, f"{attr}={val!r} {'==' if ok else '!='} {expected!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_aria({sel}, {attr}={expected})", passed, evidence)

    # --- COTS deterministic assertions (C01, C02, C03, C14) ---

    # assert_min_size — COTS C02: touch target >= threshold (default 44x44)
    assert_min_size = interaction.get("assert_min_size")
    if assert_min_size:
        sel = assert_min_size["selector"]
        min_w = assert_min_size.get("min_width", 44)
        min_h = assert_min_size.get("min_height", 44)
        def check():
            rect = cdp.get_bounding_rect(sel)
            if not rect:
                return (False, "element not found")
            w, h = rect["width"], rect["height"]
            ok = w >= min_w and h >= min_h
            return (ok, f"{w:.0f}x{h:.0f}px {'>=' if ok else '<'} {min_w}x{min_h}px")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_min_size({sel}, {min_w}x{min_h})", passed, evidence)

    # assert_font_size — COTS C01: font >= threshold (default 12px)
    assert_font_size = interaction.get("assert_font_size")
    if assert_font_size:
        sel = assert_font_size["selector"]
        min_px = assert_font_size.get("min_px", 12)
        def check():
            size = cdp.get_computed_font_size(sel)
            if size is None:
                return (False, "element not found")
            ok = size >= min_px
            return (ok, f"fontSize={size}px {'>=' if ok else '<'} {min_px}px")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_font_size({sel}, >={min_px}px)", passed, evidence)

    # assert_contrast — COTS C03: WCAG contrast >= threshold (default 4.5)
    assert_contrast = interaction.get("assert_contrast")
    if assert_contrast:
        sel = assert_contrast["selector"]
        min_ratio = assert_contrast.get("min_ratio", 4.5)
        def check():
            ratio = cdp.get_contrast_ratio(sel)
            if ratio is None:
                return (False, "element not found or colors unparseable")
            ok = ratio >= min_ratio
            return (ok, f"contrast={ratio}:1 {'>=' if ok else '<'} {min_ratio}:1")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_contrast({sel}, >={min_ratio}:1)", passed, evidence)

    # assert_title — COTS C14: element has title attribute (tooltip)
    assert_title = interaction.get("assert_title")
    if assert_title:
        sel = assert_title if isinstance(assert_title, str) else assert_title["selector"]
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? el.getAttribute('title') : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element not found or no title attribute")
            return (bool(val), f"title={val!r}" if val else "title is empty")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_title({sel})", passed, evidence)

    # assert_qs_action — element has data-qs-action attribute
    assert_qs = interaction.get("assert_qs_action")
    if assert_qs:
        sel = assert_qs if isinstance(assert_qs, str) else assert_qs["selector"]
        def check():
            val = cdp.evaluate(
                f"(function() {{"
                f"  var el = document.querySelector({json.dumps(sel)});"
                f"  return el ? el.getAttribute('data-qs-action') : null;"
                f"}})()"
            )
            if val is None:
                return (False, "element not found or no data-qs-action")
            return (bool(val), f"data-qs-action={val!r}")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_qs_action({sel})", passed, evidence)

    # assert_focus_visible — Tab to selector, check focus indicator (COTS C06)
    assert_focus = interaction.get("assert_focus_visible")
    if assert_focus:
        sel = assert_focus if isinstance(assert_focus, str) else assert_focus["selector"]
        def check():
            has_focus = cdp.evaluate(
                f"(function() {{"
                f"  var target = document.querySelector({json.dumps(sel)});"
                f"  if (!target) return null;"
                f"  target.focus();"
                f"  if (document.activeElement !== target) return false;"
                f"  var s = getComputedStyle(target);"
                f"  var outline = s.outlineStyle;"
                f"  var boxShadow = s.boxShadow;"
                f"  return outline !== 'none' || (boxShadow && boxShadow !== 'none');"
                f"}})()"
            )
            if has_focus is None:
                return (False, "element not found")
            return (bool(has_focus), "focus indicator visible" if has_focus else "NO focus indicator (outline/boxShadow)")
        passed, evidence = _retry(check, timeout)
        _append(results, f"assert_focus_visible({sel})", passed, evidence)

    return results


# --- Surface-level COTS compliance scan (runs once per surface) ---

# COTS thresholds — same as best-practices-cots/scanner.cjs
MIN_FONT_PX = 12       # MIL-STD-1472H
MIN_TOUCH_PX = 44      # WCAG 2.1 / Apple HIG
MIN_CONTRAST = 4.5     # WCAG 2.1 AA


def run_qid_compliance(cdp) -> list[dict]:
    """Scan all [data-qid] elements for the 4-attribute rule + COTS sizing.

    Returns list of {qid, check, status, evidence} dicts.
    No LLM. Pure CDP measurements against thresholds.
    """
    results = []
    elements = cdp.get_all_qid_elements()

    for el in elements:
        qid = el["qid"]
        sel = f"[data-qid='{qid}']"

        # 4-attribute rule: title required on interactive elements
        if el["interactive"] and not el["hasTitle"]:
            results.append({
                "qid": qid, "check": "title_missing",
                "status": "FAIL", "evidence": f"interactive {el['tag']} missing title attribute",
            })

        # 4-attribute rule: data-qs-action required on interactive elements
        if el["interactive"] and not el["hasQsAction"]:
            results.append({
                "qid": qid, "check": "qs_action_missing",
                "status": "FAIL", "evidence": f"interactive {el['tag']} missing data-qs-action attribute",
            })

        # C02: touch target size
        if el["interactive"] and (el["width"] < MIN_TOUCH_PX or el["height"] < MIN_TOUCH_PX):
            results.append({
                "qid": qid, "check": "C02_touch_target",
                "status": "FAIL",
                "evidence": f"{el['width']:.0f}x{el['height']:.0f}px < {MIN_TOUCH_PX}x{MIN_TOUCH_PX}px",
            })

    return results
