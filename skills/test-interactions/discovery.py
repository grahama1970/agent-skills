"""Bounded live-DOM interaction discovery for test-interactions.

Discovery is deterministic and uses executable selectors only for live
`[data-qid]` elements. Missing or duplicate QIDs are findings, never a reason to
invent class, id, text, XPath, or positional selectors.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdp_client import CDPClient

DISCOVERY_FINDING_SCHEMA = "test-interactions.discovery-finding.v1"


DISCOVER_INTERACTIVES_JS = r"""
(function() {
  function isVisible(el) {
    var r = el.getBoundingClientRect();
    var cur = el;
    while (cur && cur.nodeType === 1) {
      var s = getComputedStyle(cur);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
      cur = cur.parentElement;
    }
    return r.width > 0 && r.height > 0;
  }
  function isInteractive(el) {
    if (!el || el.nodeType !== 1) return false;
    var tag = el.tagName;
    if (['BUTTON','A','INPUT','SELECT','TEXTAREA','SUMMARY'].indexOf(tag) >= 0) return true;
    var role = el.getAttribute('role');
    if (role && ['button','link','tab','menuitem','switch','checkbox','radio','combobox','textbox'].indexOf(role) >= 0) return true;
    if (el.getAttribute('tabindex') !== null && el.getAttribute('tabindex') !== '-1') return true;
    if (el.hasAttribute('data-qs-action')) return true;
    if (typeof el.onclick === 'function' || el.getAttribute('onclick')) return true;
    return false;
  }
  function cssPath(el) {
    var out = [];
    var cur = el;
    while (cur && cur.nodeType === 1 && out.length < 5) {
      out.unshift(cur.tagName.toLowerCase());
      cur = cur.parentElement;
    }
    return out.join('>');
  }
  var nodes = Array.from(document.querySelectorAll('button,a,input,select,textarea,summary,[role],[tabindex],[data-qid],[data-qs-action]'));
  var interactives = nodes.filter(isInteractive).map(function(el, index) {
    var r = el.getBoundingClientRect();
    var qid = el.getAttribute('data-qid') || '';
    var role = el.getAttribute('role') || '';
    var disabled = !!(el.disabled === true || el.getAttribute('aria-disabled') === 'true');
    return {
      index: index,
      qid: qid,
      selector: qid ? "[data-qid='" + qid.replace(/'/g, "\\'") + "']" : "",
      tag: el.tagName.toLowerCase(),
      role: role,
      title: el.getAttribute('title') || '',
      qsAction: el.getAttribute('data-qs-action') || '',
      visible: isVisible(el),
      enabled: !disabled,
      text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 120),
      bbox: {x: r.x, y: r.y, width: r.width, height: r.height},
      ariaExpanded: el.getAttribute('aria-expanded') || '',
      ariaControls: el.getAttribute('aria-controls') || '',
      cssPath: cssPath(el),
      expectedKeyboard: ['button','a','input','select','textarea','summary'].indexOf(el.tagName.toLowerCase()) >= 0 || !!role || el.getAttribute('tabindex') !== null
    };
  });
  var dialogs = Array.from(document.querySelectorAll('[role="dialog"],dialog,[aria-modal="true"]')).filter(isVisible).map(function(el) {
    var r = el.getBoundingClientRect();
    return {qid: el.getAttribute('data-qid') || '', role: el.getAttribute('role') || el.tagName.toLowerCase(), bbox: {x:r.x,y:r.y,width:r.width,height:r.height}};
  });
  return {
    url: location.href,
    title: document.title || '',
    bodyText: (document.body.innerText || '').slice(0, 4000),
    interactives: interactives,
    dialogs: dialogs
  };
})()
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_fingerprint(snapshot: dict[str, Any]) -> str:
    payload = {
        "url": snapshot.get("url"),
        "bodyText": snapshot.get("bodyText", "")[:1000],
        "qids": [
            {
                "qid": item.get("qid"),
                "visible": item.get("visible"),
                "enabled": item.get("enabled"),
                "expanded": item.get("ariaExpanded"),
                "text": item.get("text"),
            }
            for item in snapshot.get("interactives", [])
            if item.get("visible")
        ],
        "dialogs": snapshot.get("dialogs", []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _finding(run_id: str, kind: str, message: str, *, element: dict[str, Any] | None = None, state: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    element = element or {}
    payload = {
        "schema": DISCOVERY_FINDING_SCHEMA,
        "finding_id": "",
        "fingerprint": "",
        "run_id": run_id,
        "finding_kind": kind,
        "qid": element.get("qid") or "",
        "selector": element.get("selector") or "",
        "tag": element.get("tag") or "",
        "role": element.get("role") or "",
        "state_fingerprint": state,
        "message": message,
        "evidence": evidence or {},
    }
    fp_src = {
        "kind": kind,
        "qid": payload["qid"],
        "selector": payload["selector"],
        "tag": payload["tag"],
        "role": payload["role"],
        "message": message,
        "state": state,
    }
    fingerprint = hashlib.sha256(json.dumps(fp_src, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    payload["fingerprint"] = fingerprint
    payload["finding_id"] = f"disc-{fingerprint}"
    return payload


def _snapshot(cdp: CDPClient) -> dict[str, Any]:
    snap = cdp.evaluate(DISCOVER_INTERACTIVES_JS)
    if not isinstance(snap, dict):
        raise RuntimeError("live DOM discovery returned no snapshot")
    snap["state_fingerprint"] = state_fingerprint(snap)
    snap["captured_at"] = utc_now()
    return snap


def _manifest_coverage(manifest: dict[str, Any] | None) -> set[str]:
    covered: set[str] = set()
    if not manifest:
        return covered
    for surface in manifest.get("surfaces") or []:
        for element in surface.get("elements") or []:
            for interaction in element.get("interactions") or []:
                target = str(interaction.get("target") or "")
                if target.startswith("[data-qid="):
                    covered.add(target)
    return covered


def _manifest_selector_for_qid(qid: str) -> str:
    return f"[data-qid='{qid}']"


def _should_assert_visible_after_click(item: dict[str, Any]) -> bool:
    label = " ".join(str(item.get(key) or "").lower() for key in ("qid", "text", "title", "qsAction"))
    return not any(token in label for token in ("close", "dismiss", "cancel"))


def _events_to_findings(run_id: str, events: list[dict[str, Any]], element: dict[str, Any], state: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in events:
        method = event.get("method")
        params = event.get("params") or {}
        if method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails") or {}
            findings.append(_finding(
                run_id,
                "console_exception",
                "Console exception after interaction",
                element=element,
                state=state,
                evidence={"exception": details.get("text") or details},
            ))
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") in {"error", "warning"}:
                findings.append(_finding(
                    run_id,
                    "console_error",
                    "Console error/warning after interaction",
                    element=element,
                    state=state,
                    evidence={"entry": entry},
                ))
        elif method == "Network.loadingFailed":
            findings.append(_finding(
                run_id,
                "network_failure",
                "Network request failed after interaction",
                element=element,
                state=state,
                evidence={"requestId": params.get("requestId"), "errorText": params.get("errorText")},
            ))
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            status = int(response.get("status") or 0)
            if status >= 400:
                findings.append(_finding(
                    run_id,
                    "network_failure",
                    f"Network request returned HTTP {status} after interaction",
                    element=element,
                    state=state,
                    evidence={"url": response.get("url"), "status": status},
                ))
    return findings


def _keyboard_focusable(cdp: CDPClient, selector: str) -> bool:
    return bool(cdp.evaluate(
        f"(function(){{"
        f" var el=document.querySelector({json.dumps(selector)});"
        f" if(!el) return false;"
        f" el.focus();"
        f" return document.activeElement===el;"
        f"}})()"
    ))


def _build_manifest(url: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    by_qid: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        for item in snap.get("interactives") or []:
            qid = item.get("qid")
            if qid and item.get("visible") and item.get("enabled") and qid not in by_qid:
                by_qid[qid] = item

    elements = []
    for qid, item in by_qid.items():
        selector = _manifest_selector_for_qid(qid)
        interaction: dict[str, Any] = {
            "action": "click",
            "target": selector,
            "description": f"Discovered live interaction: {qid}",
        }
        if _should_assert_visible_after_click(item):
            interaction["assert_visible"] = selector
        if item.get("title"):
            interaction["assert_title"] = selector
        if item.get("qsAction"):
            interaction["assert_qs_action"] = selector
        elements.append({"name": qid.replace(":", "-"), "interactions": [interaction]})

    return {
        "version": 1,
        "app": (snapshots[0].get("title") if snapshots else "") or url,
        "base_url": url.rsplit("/", 1)[0] if "/" in url else url,
        "discovery": {
            "generated_at": utc_now(),
            "states": len(snapshots),
            "qid_only_executable_selectors": True,
        },
        "surfaces": [{
            "name": "discovered-main",
            "path": "/" + url.rsplit("/", 1)[-1] if "/" in url else "/",
            "qid_compliance": False,
            "elements": elements or [{"name": "full-page", "interactions": [{"action": "screenshot", "description": f"Full page of {url}"}]}],
        }],
    }


def discover_live_dom(
    cdp: CDPClient,
    *,
    url: str,
    existing_manifest: dict[str, Any] | None = None,
    max_depth: int = 2,
    max_states: int = 12,
    max_actions: int = 40,
) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("test-interactions-discovery-%Y%m%dT%H%M%S%fZ")
    cdp.enable_observers()
    cdp.navigate(url, wait_ms=1200)
    cdp.drain_events()

    snapshots: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    state_graph: list[dict[str, Any]] = []
    covered = _manifest_coverage(existing_manifest)

    queue: list[tuple[int, str | None, dict[str, Any] | None]] = [(0, None, None)]
    visited: set[str] = set()
    actions_run = 0

    while queue and len(snapshots) < max_states and actions_run < max_actions:
        depth, from_state, via_element = queue.pop(0)
        snap = _snapshot(cdp)
        state = snap["state_fingerprint"]
        if state in visited and depth > 0:
            continue
        visited.add(state)
        snapshots.append(snap)
        if from_state and via_element:
            state_graph.append({"from": from_state, "to": state, "via_qid": via_element.get("qid"), "depth": depth})

        qid_counts: dict[str, int] = {}
        for item in snap.get("interactives") or []:
            qid = item.get("qid") or ""
            if qid:
                qid_counts[qid] = qid_counts.get(qid, 0) + 1
            else:
                findings.append(_finding(
                    run_id,
                    "missing_qid",
                    "Interactive element is missing data-qid and cannot be used in an executable manifest",
                    element=item,
                    state=state,
                    evidence={"cssPath": item.get("cssPath"), "text": item.get("text")},
                ))
                findings.append(_finding(
                    run_id,
                    "manifest_uncovered_interactive",
                    "Interactive element has no data-qid, so generated manifests cannot safely represent it",
                    element=item,
                    state=state,
                    evidence={"cssPath": item.get("cssPath"), "text": item.get("text"), "reason": "missing_qid"},
                ))
            if qid and not item.get("qsAction"):
                findings.append(_finding(run_id, "qs_action_missing", "QID interactive is missing data-qs-action", element=item, state=state))
            if qid and not item.get("title"):
                findings.append(_finding(run_id, "title_missing", "QID interactive is missing title", element=item, state=state))
            if item.get("expectedKeyboard") and qid and item.get("selector") and not _keyboard_focusable(cdp, item["selector"]):
                findings.append(_finding(run_id, "keyboard_unreachable", "Element could not receive programmatic keyboard focus", element=item, state=state))
            if existing_manifest is not None and qid and item.get("selector") not in covered:
                findings.append(_finding(run_id, "manifest_uncovered_interactive", "Interactive element is not represented in the supplied manifest", element=item, state=state))

        for qid, count in qid_counts.items():
            if count > 1:
                findings.append(_finding(
                    run_id,
                    "duplicate_qid",
                    f"Live DOM contains duplicate data-qid {qid!r}",
                    element={"qid": qid, "selector": f"[data-qid='{qid}']"},
                    state=state,
                    evidence={"count": count},
                ))

        if depth >= max_depth:
            continue
        candidates = [
            item for item in snap.get("interactives") or []
            if item.get("qid") and item.get("visible") and item.get("enabled")
        ]
        for item in candidates:
            if actions_run >= max_actions or len(snapshots) >= max_states:
                break
            selector = item["selector"]
            before_url = cdp.current_url()
            before_state = state
            before_dialog_count = len(snap.get("dialogs") or [])
            before_text = snap.get("bodyText", "")
            cdp.drain_events()
            clicked = cdp.click_selector(selector)
            actions_run += 1
            time.sleep(0.25)
            events = cdp.drain_events()
            after = _snapshot(cdp)
            after_state = after["state_fingerprint"]
            after_url = after.get("url") or ""
            state_graph.append({
                "from": before_state,
                "to": after_state,
                "via_qid": item.get("qid"),
                "clicked": clicked,
                "depth": depth + 1,
            })
            findings.extend(_events_to_findings(run_id, events, item, before_state))
            if after_url != before_url:
                findings.append(_finding(run_id, "unexpected_url_drift", "Interaction changed the page URL during discovery", element=item, state=before_state, evidence={"before": before_url, "after": after_url}))
            observable_effect = (
                after_state != before_state
                or after_url != before_url
                or after.get("bodyText", "") != before_text
                or bool(events)
            )
            if not observable_effect:
                findings.append(_finding(run_id, "inert_interaction", "Click produced no observable DOM, URL, console, network, focus, or text effect", element=item, state=before_state))
            after_dialog_count = len(after.get("dialogs") or [])
            if after_dialog_count > before_dialog_count:
                cdp.press_key("Escape")
                time.sleep(0.2)
                focused_qid = cdp.get_focused_qid()
                if focused_qid != item.get("qid"):
                    findings.append(_finding(
                        run_id,
                        "focus_return_defect",
                        "Overlay close did not return focus to the opener",
                        element=item,
                        state=before_state,
                        evidence={"expected_focus_qid": item.get("qid"), "actual_focus_qid": focused_qid},
                    ))
            if after_state not in visited:
                queue.append((depth + 1, before_state, item))

    manifest = _build_manifest(url, snapshots)
    return {
        "schema": "test-interactions.discovery-result.v1",
        "run_id": run_id,
        "generated_at": utc_now(),
        "url": url,
        "bounds": {"max_depth": max_depth, "max_states": max_states, "max_actions": max_actions},
        "states_seen": len(snapshots),
        "actions_run": actions_run,
        "inventory": snapshots,
        "findings": findings,
        "state_graph": state_graph,
        "manifest": manifest,
    }


def write_discovery_artifacts(result: dict[str, Any], output_dir: Path, manifest_output: Path | None = None) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "discovery-inventory.json"
    findings_path = output_dir / "discovery-findings.jsonl"
    state_graph_path = output_dir / "state-graph.json"
    manifest_path = manifest_output or output_dir / "manifest.generated.json"
    inventory_path.write_text(json.dumps({
        "schema": result["schema"],
        "run_id": result["run_id"],
        "url": result["url"],
        "bounds": result["bounds"],
        "states_seen": result["states_seen"],
        "actions_run": result["actions_run"],
        "inventory": result["inventory"],
    }, indent=2) + "\n")
    with findings_path.open("w", encoding="utf-8") as fh:
        for finding in result.get("findings") or []:
            fh.write(json.dumps(finding, sort_keys=True) + "\n")
    state_graph_path.write_text(json.dumps(result.get("state_graph") or [], indent=2) + "\n")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result["manifest"], indent=2) + "\n")
    return {
        "inventory": str(inventory_path),
        "findings": str(findings_path),
        "state_graph": str(state_graph_path),
        "manifest": str(manifest_path),
    }
