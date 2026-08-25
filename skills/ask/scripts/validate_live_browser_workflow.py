#!/usr/bin/env python3
"""Validate a live Ask browser roundtable or competition receipt directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--workflow-mode", choices=["roundtable", "compete"], required=True)
    parser.add_argument("--handler", action="append", required=True)
    parser.add_argument("--expect-text", action="append", default=[])
    parser.add_argument("--min-concurrency", type=int, default=1)
    parser.add_argument("--require-cleanup", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate(
        args.run_dir,
        workflow_mode=args.workflow_mode,
        handlers=args.handler,
        expect_text=args.expect_text,
        min_concurrency=args.min_concurrency,
        require_cleanup=args.require_cleanup,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{report['status']}: {args.workflow_mode} {args.run_dir}")
        for item in report["checks"]:
            print(f"- {item['status']}: {item['name']} {item.get('detail', '')}".rstrip())
    return 0 if report["ok"] else 1


def validate(
    run_dir: Path,
    *,
    workflow_mode: str,
    handlers: list[str],
    expect_text: list[str],
    min_concurrency: int,
    require_cleanup: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    run_dir = run_dir.expanduser().resolve()

    lifecycle = _load_lifecycle(run_dir)
    receipt = _load_json(run_dir / "tau-receipts" / "dag-receipt.json")
    lifecycle_mode = str(lifecycle.get("workflow_mode") or lifecycle.get("mode") or "")
    reuse_bound = lifecycle_mode == "reuse-bound"
    handler_tabs = _handler_tabs(lifecycle)
    checks.append(_check(_lifecycle_ok(lifecycle, reuse_bound=reuse_bound), "browser_lifecycle_ok", lifecycle.get("status")))
    checks.append(_check(lifecycle.get("mocked") is not True, "browser_lifecycle_not_mocked"))
    checks.append(
        _check(
            bool(lifecycle.get("live") is True or lifecycle.get("created_tabs") or reuse_bound),
            "browser_lifecycle_live",
        )
    )
    checks.append(_check(_workflow_matches(lifecycle, workflow_mode), "workflow_mode", lifecycle.get("workflow_mode") or lifecycle.get("mode")))
    checks.append(_check(reuse_bound or bool(lifecycle.get("window_id")), "fresh_window_id", lifecycle.get("window_id")))
    checks.append(_check(receipt.get("ok") is True, "tau_receipt_ok", receipt.get("status")))
    checks.append(_check(receipt.get("mocked") is False, "tau_receipt_not_mocked"))
    checks.append(_check(receipt.get("live") is True, "tau_receipt_live"))
    checks.append(
        _check(
            int(receipt.get("max_observed_concurrency") or 0) >= min_concurrency,
            "tau_observed_concurrency",
            receipt.get("max_observed_concurrency"),
        )
    )

    seen_tabs: set[str] = set()
    seat_status: dict[str, dict[str, Any]] = {}
    status_counts = {"usable": 0, "failed": 0, "missing": 0}
    failure_codes: dict[str, int] = {}
    for handler in handlers:
        tab = handler_tabs.get(handler) or {}
        tab_id = str(tab.get("tab_id") or "")
        project = str(tab.get("project") or "")
        node_dir = run_dir / "node-artifacts" / f"handler-{handler}"
        node_receipt = _load_json(node_dir / "node-receipt.json")
        meta = _load_json(node_dir / "response.meta.json")
        response_path = node_dir / "response.md"
        raw_path = node_dir / "response.raw.md"
        response_text = response_path.read_text(encoding="utf-8", errors="replace") if response_path.is_file() else ""
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.is_file() else ""
        requested = str(meta.get("requested_tab_id") or "")
        controlled = str(meta.get("controlled_tab_id") or "")
        if handler == "webgpt" and not controlled and meta.get("controlled_tab_id_inferred_from_requested") is True:
            controlled = requested
        if reuse_bound and not tab_id:
            tab_id = controlled or requested
            if tab_id:
                tab = {"handler": handler, "tab_id": tab_id, "project": project}
                handler_tabs[handler] = tab

        checks.append(_check(bool(tab_id), f"{handler}_tab_id", tab_id))
        checks.append(_check(tab_id not in seen_tabs, f"{handler}_tab_unique", tab_id))
        seen_tabs.add(tab_id)
        checks.append(
            _check(
                reuse_bound or project.startswith(f"{run_dir.name}-{handler}"),
                f"{handler}_run_scoped_project",
                project,
            )
        )
        checks.append(_check(node_receipt.get("ok") is True, f"{handler}_node_receipt_ok", node_receipt.get("status")))
        checks.append(_check(node_receipt.get("mocked") is False, f"{handler}_not_mocked"))
        checks.append(_check(node_receipt.get("live") is True, f"{handler}_live"))
        checks.append(_check(node_receipt.get("provider_live") is True, f"{handler}_provider_live"))
        checks.append(_check(response_path.is_file() and bool(response_text.strip()), f"{handler}_response_present"))
        for text in expect_text:
            checks.append(_check(text in response_text, f"{handler}_response_contains_{_slug(text)}"))
        sentinel = str(meta.get("sentinel") or "")
        checks.append(_check(_has_sentinel(raw_text, sentinel), f"{handler}_raw_contains_sentinel"))
        checks.append(_check(not _has_sentinel(response_text, sentinel), f"{handler}_clean_response_strips_sentinel"))
        checks.append(
            _check(
                not meta.get("clean_contamination_markers") and not _clean_response_contamination_markers(response_text),
                f"{handler}_clean_response_uncontaminated",
                meta.get("clean_contamination_markers") or _clean_response_contamination_markers(response_text),
            )
        )
        checks.append(_check(not requested or requested == tab_id, f"{handler}_requested_tab_matches_workspace", requested))
        checks.append(_check(not controlled or controlled == tab_id, f"{handler}_controlled_tab_matches_workspace", controlled))
        failure_code = str(node_receipt.get("failure_code") or meta.get("failure_code") or meta.get("failure") or "")
        if node_receipt.get("__missing_path__"):
            seat_state = "missing"
        elif node_receipt.get("ok") is True and response_path.is_file() and bool(response_text.strip()):
            seat_state = "usable"
        else:
            seat_state = "failed"
        status_counts[seat_state] += 1
        if failure_code:
            failure_codes[failure_code] = failure_codes.get(failure_code, 0) + 1
        seat_status[handler] = {
            "state": seat_state,
            "status": node_receipt.get("status"),
            "ok": node_receipt.get("ok"),
            "provider_live": node_receipt.get("provider_live"),
            "failure_code": failure_code or None,
            "proof_status": meta.get("proof_status"),
            "requested_tab_id": requested or None,
            "controlled_tab_id": controlled or None,
            "raw_contains_sentinel": _has_sentinel(raw_text, sentinel),
            "response_path": str(response_path),
            "recovery_packet_path": node_receipt.get("recovery_packet_path"),
        }

    join_dir = run_dir / "node-artifacts" / "join"
    join_receipt = _load_json(join_dir / "node-receipt.json")
    checks.append(_check(join_receipt.get("ok") is True, "join_receipt_ok", join_receipt.get("status")))
    if workflow_mode == "roundtable":
        checks.append(_check((join_dir / "roundtable-summary.md").is_file(), "roundtable_summary_present"))
    else:
        scorecard = _load_json(join_dir / "compete-scorecard.json")
        checks.append(_check((join_dir / "compete-scorecard.json").is_file(), "compete_scorecard_present"))
        checks.append(_check(bool(scorecard.get("winner_handler")), "compete_winner_handler", scorecard.get("winner_handler")))
        checks.append(
            _check(
                (join_dir / "winner-continuation-request.md").is_file()
                or (join_dir / "winner-revision-request.md").is_file(),
                "winner_continuation_or_legacy_revision_present",
            )
        )

    if require_cleanup:
        checks.append(_check(_cleanup_ok(lifecycle), "browser_lifecycle_cleanup_ok", lifecycle.get("cleanup_status")))
    checks.insert(6, _check(bool(handler_tabs), "handler_tabs_present", len(handler_tabs)))

    ok = all(item["ok"] for item in checks)
    return {
        "schema": "ask.live_browser_workflow_validation.v1",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "run_dir": str(run_dir),
        "workflow_mode": workflow_mode,
        "handlers": handlers,
        "seat_status": seat_status,
        "status_counts": status_counts,
        "failure_codes": failure_codes,
        "checks": checks,
        "failed_checks": [item for item in checks if not item["ok"]],
    }


def _load_lifecycle(run_dir: Path) -> dict[str, Any]:
    workspace_path = run_dir / "browser-workspace.json"
    if workspace_path.is_file():
        data = _load_json(workspace_path)
        data.setdefault("created_tabs", list((data.get("handler_tabs") or {}).values()))
        return data
    return _load_json(run_dir / "browser-tab-lifecycle.json")


def _handler_tabs(lifecycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    handler_tabs = lifecycle.get("handler_tabs")
    if isinstance(handler_tabs, dict):
        return {str(handler): dict(tab) for handler, tab in handler_tabs.items() if isinstance(tab, dict)}
    tabs: dict[str, dict[str, Any]] = {}
    created_tabs = lifecycle.get("created_tabs")
    if isinstance(created_tabs, list):
        for item in created_tabs:
            if not isinstance(item, dict):
                continue
            handler = str(item.get("handler") or "")
            if handler:
                tabs[handler] = dict(item)
    return tabs


def _workflow_matches(lifecycle: dict[str, Any], workflow_mode: str) -> bool:
    if lifecycle.get("workflow_mode"):
        return str(lifecycle.get("workflow_mode")) == workflow_mode
    return str(lifecycle.get("mode") or "") in {
        "fresh-temporary",
        "fresh-keep",
        "fresh-shared-temporary",
        "fresh-shared-keep",
        "reuse-bound",
        "auto",
    }


def _lifecycle_ok(lifecycle: dict[str, Any], *, reuse_bound: bool = False) -> bool:
    if reuse_bound and lifecycle.get("status") in {"skipped", "READY"}:
        return True
    return lifecycle.get("ok") is True or lifecycle.get("status") == "READY"


def _cleanup_ok(lifecycle: dict[str, Any]) -> bool:
    if lifecycle.get("closed") is True:
        return True
    if lifecycle.get("cleanup_status") != "attempted":
        return False
    cleanup = lifecycle.get("cleanup")
    if not isinstance(cleanup, list) or not cleanup:
        return False
    return all(isinstance(item, dict) and item.get("returncode") == 0 for item in cleanup)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"__missing_path__": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"__invalid_json__": str(path), "error": str(exc)}
    return data if isinstance(data, dict) else {"__unexpected_json_type__": type(data).__name__}


def _check(ok: bool, name: str, detail: Any = "") -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "ok": bool(ok), "status": "PASS" if ok else "FAIL"}
    if detail != "":
        item["detail"] = detail
    return item


def _has_sentinel(text: str, sentinel: str = "") -> bool:
    if sentinel:
        return sentinel in text
    return "<<<" in text and "_DONE:" in text and ">>>" in text


def _clean_response_contamination_markers(text: str) -> list[str]:
    markers = (
        "What can we tackle together?",
        "@keyframes",
        "Automation-only instruction:",
        "After your complete answer, append a final line containing only this exact marker:",
        "Do not print anything after that marker.",
    )
    return [marker for marker in markers if marker in text]


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")[:48]


if __name__ == "__main__":
    raise SystemExit(main())
