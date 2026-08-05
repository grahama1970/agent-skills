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
