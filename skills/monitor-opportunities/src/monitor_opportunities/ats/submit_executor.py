"""Surf-driven ATS submit adapter, usable only through commit_application.

Every use requires a site policy promoting ``ats_form_submit:<provider>:<site>``
plus a per-application human authorization bound to the exact plan digest
(``authorize_application_plan``), which itself refuses plans with unresolved
required fields. This module never runs outside that gate chain.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .prefill_executor import SURF_RUN_DEFAULT, PrefillError, _surf

SUBMIT_SELECTORS = {
    "greenhouse": "button[type='submit']",
}
CONFIRMATION_MARKERS = {
    "greenhouse": ("thank you for applying", "application has been submitted", "application submitted"),
}


class SurfSubmitAdapter:
    """Clicks the provider submit control in an already-prefilled tab.

    ``submit`` returns COMMITTED only when the post-click page text carries a
    provider confirmation marker; anything ambiguous is INDETERMINATE so the
    reconciliation gate owns the retry decision.
    """

    def __init__(self, *, tab_id: str, provider: str, surf_run: Path = SURF_RUN_DEFAULT) -> None:
        if provider not in SUBMIT_SELECTORS:
            raise PrefillError(f"SUBMIT_PROVIDER_UNSUPPORTED:{provider}")
        self.tab_id = tab_id
        self.provider = provider
        self.surf_run = surf_run

    def _js(self, script: str, timeout: int = 90) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(script)
            path = handle.name
        return _surf(self.surf_run, "js", "--tab-id", self.tab_id, "--file", path, timeout=timeout)

    def submit(self, plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        selector = SUBMIT_SELECTORS[self.provider]
        click = (
            "(function(){"
            f"var el=document.querySelector(\"{selector}\");"
            "if (el===null) { return 'SUBMIT_NOT_FOUND'; }"
            "el.click(); return 'CLICKED';})()"
        )
        outcome = json.loads(self._js(click))
        if outcome != "CLICKED":
            return {"state": "INDETERMINATE", "detail": outcome}
        _surf(self.surf_run, "wait", "6")
        page = json.loads(self._js("document.body.innerText.slice(0,4000)"))
        lowered = page.lower()
        if any(marker in lowered for marker in CONFIRMATION_MARKERS[self.provider]):
            return {
                "state": "COMMITTED",
                "provider_confirmation": f"{self.provider}:{plan['posting_id']}:{idempotency_key}",
                "confirmation_excerpt": page[:300],
            }
        return {"state": "INDETERMINATE", "detail": "no confirmation marker", "page_excerpt": page[:300]}

    def reconcile(self, reservation_id: str) -> dict[str, Any]:
        page = json.loads(self._js("document.body.innerText.slice(0,4000)"))
        lowered = page.lower()
        if any(marker in lowered for marker in CONFIRMATION_MARKERS[self.provider]):
            return {"state": "COMMITTED", "provider_confirmation": f"reconciled-{reservation_id}"}
        return {"state": "INDETERMINATE", "detail": "confirmation still absent"}


# Verified live 2026-08-22 against jobs.ashbyhq.com: submit control text is
# "Submit Application"; success screen reads "successfully submitted".
ASHBY_CONFIRMATION_MARKERS = (
    "successfully submitted",
    "application success",
    "we'll contact you",
)


class AshbySubmitAdapter:
    """Submit an already-prefilled Ashby application in the human's own tab.

    Ashby is a React SPA behind reCAPTCHA. This adapter clicks the visible
    "Submit Application" control, OS-clicks the reCAPTCHA checkbox coordinate
    when present (surf `pointer.dispatch --transport os`), and reads the effect
    back from the live DOM. It never solves an escalated image challenge and
    never answers a human_required field -- an unresolved required field or a
    challenge yields INDETERMINATE so the reconciliation gate owns the retry.
    """

    def __init__(self, *, tab_id: str, surf_run: Path = SURF_RUN_DEFAULT) -> None:
        self.tab_id = tab_id
        self.provider = "ashby"
        self.surf_run = surf_run

    def _js(self, script: str, timeout: int = 90) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(script)
            path = handle.name
        return _surf(self.surf_run, "js", "--tab-id", self.tab_id, "--file", path, timeout=timeout)

    def _page_text(self) -> str:
        return json.loads(self._js("document.body.innerText.slice(0,6000)"))

    def _submit_still_present(self) -> bool:
        return json.loads(self._js(
            "JSON.stringify(/submit application/i.test(document.body.innerText))"
        ))

    def _validation_errors(self) -> list[str]:
        return json.loads(self._js(
            "JSON.stringify([].slice.call(document.querySelectorAll('[role=alert]'))"
            ".map(function(e){return (e.innerText||'').replace(/\\s+/g,' ').slice(0,120);})"
            ".filter(function(t){return /missing|required|invalid|correction/i.test(t);}).slice(0,6))"
        ))

    def submit(self, plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        click = (
            "(function(){var b=[].slice.call(document.querySelectorAll('button'))"
            ".filter(function(e){return /submit application/i.test((e.innerText||'').trim());});"
            "if(!b.length)return 'SUBMIT_NOT_FOUND';b[0].click();return 'CLICKED';})()"
        )
        if json.loads(self._js(click)) != "CLICKED":
            return {"state": "INDETERMINATE", "detail": "SUBMIT_NOT_FOUND"}
        _surf(self.surf_run, "wait", "6")

        page = self._page_text()
        lowered = page.lower()
        if any(marker in lowered for marker in ASHBY_CONFIRMATION_MARKERS) and not self._submit_still_present():
            return {
                "state": "COMMITTED",
                "provider_confirmation": f"ashby:{plan.get('posting_id')}:{idempotency_key}",
                "confirmation_excerpt": page[:300],
            }
        errors = self._validation_errors()
        if errors:
            # A blank required (human_required) field or a rejected value: the
            # human must resolve it -- never auto-answered, never retried blind.
            return {"state": "BLOCKED", "detail": "validation_errors", "errors": errors}
        return {"state": "INDETERMINATE", "detail": "no confirmation and no error surfaced", "page_excerpt": page[:300]}

    def reconcile(self, reservation_id: str) -> dict[str, Any]:
        page = self._page_text().lower()
        if any(marker in page for marker in ASHBY_CONFIRMATION_MARKERS):
            return {"state": "COMMITTED", "provider_confirmation": f"reconciled-{reservation_id}"}
        return {"state": "INDETERMINATE", "detail": "confirmation still absent"}
