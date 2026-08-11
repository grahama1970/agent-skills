"""Human-in-the-loop autofill: fill the standard fields, LEAVE THE TAB OPEN.

The agent fills name/contact/resume and every field that resolves truthfully
from the answer bank, then STOPS — it never clicks Submit and never closes the
tab. The human reviews, answers any queued fields, and clicks Apply themselves.
This keeps the human in the loop, stays within site ToS (a real session doing
real typing), and saves the 20-minutes-of-grunt-work without touching anti-bot
protections. React-safe value setters so controlled inputs register the change.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .autonomous_apply import resolve_application

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[3] / "surf" / "run.sh"


class PrefillAssistError(ValueError):
    """Stable prefill-assist error."""


def _surf(surf_run: Path, *args: str, timeout: int = 45) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise PrefillAssistError(f"surf {args[0]} failed: {proc.stderr[-200:]}")
    return proc.stdout.strip()


def _fill_js(selector: str, value: str) -> str:
    """React-safe: set the value via the native setter and dispatch input/change."""
    sel = json.dumps(selector)
    val = json.dumps(value)
    return (
        "(function(){var el=document.querySelector(" + sel + ");"
        "if(!el)return 'NO_EL';"
        "var proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
        "var setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
        "setter.call(el," + val + ");"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));"
        "return 'OK';})()"
    )


def prefill_and_leave_open(
    apply_url: str,
    form: dict[str, Any],
    resume_path: str | None,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Open the form, fill everything that resolves truthfully, leave the tab open.

    Returns {tab_id, filled_ok, fill_failed, remaining_for_human, message}. The
    tab is intentionally NOT closed and Submit is NOT clicked — the human reviews
    and applies.
    """
    plan = resolve_application(form, resume_path)
    # map field name -> selector from the learned form
    selectors = {f.get("name"): f.get("selector") for f in form.get("fields", []) if f.get("selector")}

    created = _surf(surf_run, "tab.new", apply_url)
    tab_id = "".join(c for c in created.split(":", 1)[0] if c.isdigit())
    if not tab_id:
        raise PrefillAssistError(f"could not parse tab id from: {created[:120]}")
    _surf(surf_run, "wait", "6")

    filled_ok: list[str] = []
    fill_failed: list[str] = []
    for name, value in plan["filled"].items():
        sel = selectors.get(name)
        if not sel or value is None:
            fill_failed.append(name)
            continue
        # Resume/file uploads go through surf's upload path, not value-set.
        f = next((x for x in form.get("fields", []) if x.get("name") == name), {})
        if f.get("field_type") == "file":
            if resume_path and Path(resume_path).exists():
                try:
                    _surf(surf_run, "upload", "--tab-id", tab_id, "--selector", sel, resume_path, timeout=60)
                    filled_ok.append(name)
                except PrefillAssistError:
                    fill_failed.append(name)
            else:
                fill_failed.append(name)
            continue
        try:
            res = _surf(surf_run, "js", "--tab-id", tab_id, _fill_js(sel, str(value)), timeout=20)
            (filled_ok if "OK" in res else fill_failed).append(name)
        except PrefillAssistError:
            fill_failed.append(name)

    return {
        "tab_id": tab_id,
        "apply_url": apply_url,
        "filled_ok": filled_ok,
        "fill_failed": fill_failed,
        "remaining_for_human": plan["queue"],
        "submit_clicked": False,
        "tab_left_open": True,
        "message": f"Filled {len(filled_ok)} fields. Tab left open — review, answer {len(plan['queue'])} remaining, and click Apply yourself.",
    }
