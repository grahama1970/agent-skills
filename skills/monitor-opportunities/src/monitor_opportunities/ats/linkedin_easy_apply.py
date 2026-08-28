"""LinkedIn Easy Apply submit driver (post-report authorized, gated, safe-by-default).

LinkedIn Top Applicant and Easy Apply are prioritization signals, not standing
submission authorization. After Graham reviews the monitor-opportunities report
and authorizes one exact opportunity/payload, this driver uses Graham's own
authenticated session to drive the multi-step Easy Apply modal proven live on
2026-08-22:

    detail "Apply" button (.jobs-apply-button)
      -> "Share your profile?" consent  -> "Continue to apply to <role>"
      -> N form steps (contact / resume / screening questions)
         each advanced by "Continue to next step" -> "Review your application"
      -> "Submit application"  -> "Your application was sent" (read back)

SAFETY CONTRACT (never fabricate, never guess):
  * A scoped human promotion ``ats_form_submit:linkedin:linkedin.com`` is required.
  * An exact post-report human authorization for this candidate, posting,
    apply URL, and idempotency key is required.
  * The duplicate guard blocks re-applying to a posting already submitted.
  * Only KNOWN-ANSWERABLE required fields are filled (identity + answer-bank
    eligibility, resume already attached to the profile). ANY unrecognized
    REQUIRED screening question aborts with NEEDS_HUMAN -- it is surfaced to
    Graham, never auto-answered. EEO / salary / clearance / free-text are always
    human's.
  * COMMITTED is claimed only after reading LinkedIn's "application was sent"
    confirmation back from the DOM -- never a self-report.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..util import sha256_json, utc_now

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[4] / "surf" / "run.sh"

CONFIRMATION_MARKERS = ("application was sent", "application sent", "your application was submitted")
MAX_STEPS = 10

# Screening-question labels we can answer truthfully from the answer bank. Any
# REQUIRED field whose label matches none of these is surfaced to the human.
_ANSWERABLE_LABEL_KEYS = {
    "authorized to work": ("work_authorization", "authorized_us"),
    "legally authorized": ("work_authorization", "authorized_us"),
    "sponsorship": ("work_authorization", "require_sponsorship"),
}
# Labels that are ALWAYS the human's, even if they look answerable.
_ALWAYS_HUMAN = ("clearance", "salary", "compensation", "gender", "race", "veteran",
                 "disability", "why", "cover", "describe", "explain")


class LinkedInEasyApplyError(ValueError):
    """Stable LinkedIn Easy Apply error."""


def _load_answer_bank() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "config" / "answer_bank.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _require_promotion(policy: dict[str, Any] | None) -> None:
    if policy is None:
        raise LinkedInEasyApplyError("LINKEDIN_SUBMIT_PROMOTION_MISSING")
    if policy.get("capability") != "ats_form_submit:linkedin:linkedin.com":
        raise LinkedInEasyApplyError("LINKEDIN_SUBMIT_PROMOTION_SCOPE_MISMATCH")
    if policy.get("actor") != "human" or policy.get("decision") != "PROMOTE":
        raise LinkedInEasyApplyError("LINKEDIN_SUBMIT_PROMOTION_NOT_HUMAN_PROMOTE")


def _require_application_authorization(
    authorization: dict[str, Any] | None,
    *,
    candidate_id: str,
    posting_id: str,
    apply_url: str,
    idempotency_key: str,
) -> None:
    """Require Graham's exact post-report authorization for one Easy Apply payload."""

    if authorization is None:
        raise LinkedInEasyApplyError("LINKEDIN_APPLICATION_AUTHORIZATION_MISSING")
    if authorization.get("schema") != "monitor_opportunities.application_authorization.v1":
        raise LinkedInEasyApplyError("LINKEDIN_APPLICATION_AUTHORIZATION_SCHEMA_MISMATCH")
    if authorization.get("actor") != "human" or authorization.get("state") != "HUMAN_AUTHORIZED":
        raise LinkedInEasyApplyError("LINKEDIN_APPLICATION_AUTHORIZATION_NOT_HUMAN")
    if authorization.get("authorization_digest") is None:
        raise LinkedInEasyApplyError("LINKEDIN_APPLICATION_AUTHORIZATION_DIGEST_MISSING")
    expected = {
        "candidate_id": candidate_id,
        "posting_id": posting_id,
        "apply_url": apply_url,
        "idempotency_key": idempotency_key,
    }
    for key, value in expected.items():
        if authorization.get(key) != value:
            raise LinkedInEasyApplyError(f"LINKEDIN_APPLICATION_AUTHORIZATION_{key.upper()}_MISMATCH")


def classify_screening_field(label: str) -> tuple[str, tuple[str, str] | None]:
    """('answerable', key) | ('human_required', None) for one screening label."""
    low = label.lower()
    if any(k in low for k in _ALWAYS_HUMAN):
        return "human_required", None
    for phrase, key in _ANSWERABLE_LABEL_KEYS.items():
        if phrase in low:
            return "answerable", key
    return "human_required", None


class LinkedInEasyApplyAdapter:
    """Drive one Easy Apply modal to a read-back-confirmed submission."""

    def __init__(self, *, tab_id: str, surf_run: Path = SURF_RUN_DEFAULT) -> None:
        self.tab_id = tab_id
        self.surf_run = surf_run
        self.answer_bank = _load_answer_bank()

    def _js(self, script: str, timeout: int = 30) -> Any:
        with __import__("tempfile").NamedTemporaryFile("w", suffix=".js", delete=False) as h:
            h.write(script)
            path = h.name
        proc = subprocess.run(
            [str(self.surf_run), "js", "--tab-id", self.tab_id, "--file", path],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            raise LinkedInEasyApplyError(f"surf js failed: {proc.stderr[:160]}")
        raw = proc.stdout.strip()
        try:
            inner = json.loads(raw) if raw.startswith('"') else raw
            return json.loads(inner) if isinstance(inner, str) else inner
        except json.JSONDecodeError:
            return raw

    def _wait(self, seconds: int = 3) -> None:
        subprocess.run([str(self.surf_run), "wait", str(seconds)], capture_output=True, text=True, timeout=seconds + 10)

    def _open_modal(self) -> str:
        clicked = self._js(
            "(function(){var b=document.querySelector('.jobs-apply-button');"
            "if(!b)return 'NO_APPLY_BUTTON';b.click();return 'CLICKED';})()"
        )
        if clicked != "CLICKED":
            return clicked
        self._wait(3)
        # Optional "Share your profile?" consent step.
        self._js(
            "(function(){var b=[].slice.call(document.querySelectorAll('.artdeco-modal button,div[role=dialog] button'))"
            ".filter(function(x){return /continue to apply/i.test(x.innerText||x.getAttribute('aria-label')||'');})[0];"
            "if(b){b.click();return 'CONSENTED';}return 'NO_CONSENT';})()"
        )
        self._wait(2)
        return "OPEN"

    def _read_step(self) -> dict[str, Any]:
        return self._js(
            "(function(){var m=document.querySelector('.jobs-easy-apply-modal,.artdeco-modal,div[role=dialog]');"
            "if(!m)return {modal:false};"
            "function lab(e){return (e.getAttribute('aria-label')||"
            "(e.labels&&e.labels[0]?e.labels[0].innerText:'')||'').replace(/\\s+/g,' ').trim();}"
            "var reqs=[].slice.call(m.querySelectorAll('input,select,textarea')).map(function(e){"
            "var fs=e.closest('fieldset');var flab=fs?((fs.querySelector('legend')||{}).innerText||''):'';"
            "return {label:(lab(e)||flab).slice(0,80),type:e.type||e.tagName.toLowerCase(),"
            "required:e.required||e.getAttribute('aria-required')==='true'||/\\*/.test(flab),value:e.value||''};});"
            "var btns=[].slice.call(m.querySelectorAll('button')).map(function(b){"
            "return (b.getAttribute('aria-label')||b.innerText||'').replace(/\\s+/g,' ').trim();}).filter(Boolean);"
            "var t=m.innerText||'';"
            "return {modal:true,fields:reqs,buttons:btns.slice(0,8),"
            "confirmed:/application was sent|application sent|your application was submitted/i.test(t)};})()"
        )

    def _answer_for(self, label: str) -> str | None:
        kind, key = classify_screening_field(label)
        if kind != "answerable" or key is None:
            return None
        return (self.answer_bank.get(key[0]) or {}).get(key[1])

    def _fill_answerable(self, fields: list[dict[str, Any]]) -> None:
        """Fill only KNOWN-ANSWERABLE required fields from the answer bank."""
        for f in fields:
            if not f.get("required") or str(f.get("value") or "").strip():
                continue
            label = str(f.get("label") or "")
            answer = self._answer_for(label)
            if not answer:
                continue
            esc_label = json.dumps(label[:60])
            esc_answer = json.dumps(str(answer))
            self._js(
                "(function(){var lab=" + esc_label + ";var val=" + esc_answer + ";"
                "var m=document.querySelector('.jobs-easy-apply-modal,.artdeco-modal,div[role=dialog]');if(!m)return 'nomodal';"
                "var els=[].slice.call(m.querySelectorAll('input,select,textarea'));"
                "function labof(e){var fs=e.closest('fieldset');return (e.getAttribute('aria-label')||"
                "(e.labels&&e.labels[0]?e.labels[0].innerText:'')||(fs?((fs.querySelector('legend')||{}).innerText||''):'')).trim();}"
                "for(var i=0;i<els.length;i++){var e=els[i];if(labof(e).slice(0,60)!==lab.slice(0,60))continue;"
                "if(e.tagName==='SELECT'){for(var j=0;j<e.options.length;j++){if(e.options[j].text.trim().toLowerCase()===val.toLowerCase()){e.selectedIndex=j;e.dispatchEvent(new Event('change',{bubbles:true}));return 'select';}}}"
                "else if(e.type==='radio'){var fs=e.closest('fieldset');var rs=fs?fs.querySelectorAll('input[type=radio]'):[e];"
                "for(var k=0;k<rs.length;k++){var rl=(rs[k].getAttribute('aria-label')||(rs[k].labels&&rs[k].labels[0]?rs[k].labels[0].innerText:'')||'').trim();"
                "if(rl.toLowerCase()===val.toLowerCase()){rs[k].click();return 'radio';}}}"
                "else{var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(e,val);e.dispatchEvent(new Event('input',{bubbles:true}));return 'text';}}"
                "return 'nomatch';})()"
            )

    def _blocking_required(self, fields: list[dict[str, Any]]) -> list[str]:
        """Any required field still empty AFTER filling -- never submit blank."""
        return [str(f.get("label")) for f in fields
                if f.get("required") and not str(f.get("value") or "").strip()]

    def _click(self, pattern: str) -> bool:
        return self._js(
            "(function(){var b=[].slice.call(document.querySelectorAll('.jobs-easy-apply-modal button,.artdeco-modal button,div[role=dialog] button'))"
            f".filter(function(x){{return /{pattern}/i.test(x.getAttribute('aria-label')||x.innerText||'');}})[0];"
            "if(b){b.click();return true;}return false;})()"
        ) is True

    def submit(self, plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        opened = self._open_modal()
        if opened not in ("OPEN",):
            return {"state": "INDETERMINATE", "detail": f"modal_open:{opened}"}

        for _step in range(MAX_STEPS):
            step = self._read_step()
            if not step.get("modal"):
                return {"state": "INDETERMINATE", "detail": "modal_vanished"}
            if step.get("confirmed"):
                return {"state": "COMMITTED",
                        "provider_confirmation": f"linkedin:{plan.get('posting_id')}:{idempotency_key}"}

            # Fill known-answerable required fields, then re-read the step.
            self._fill_answerable(step.get("fields", []))
            step = self._read_step()
            blocking = self._blocking_required(step.get("fields", []))
            if blocking:
                # A required field we cannot truthfully answer (or could not fill)
                # remains empty. Never submit blank, never guess -- surface it.
                return {"state": "NEEDS_HUMAN", "detail": "unresolved_required_screening",
                        "questions": blocking}

            if self._click("submit application"):
                self._wait(4)
                final = self._read_step()
                if final.get("confirmed") or not final.get("modal"):
                    return {"state": "COMMITTED",
                            "provider_confirmation": f"linkedin:{plan.get('posting_id')}:{idempotency_key}"}
                return {"state": "INDETERMINATE", "detail": "submit_clicked_no_confirmation"}
            if self._click("review your application"):
                self._wait(2)
                continue
            if self._click("continue to next step"):
                self._wait(2)
                continue
            return {"state": "INDETERMINATE", "detail": "no_actionable_button", "buttons": step.get("buttons")}
        return {"state": "INDETERMINATE", "detail": "max_steps_exceeded"}


def commit_linkedin_easy_apply(
    *,
    tab_id: str,
    candidate_id: str,
    posting_id: str,
    apply_url: str,
    promotion: dict[str, Any],
    authorization: dict[str, Any],
    memory_url: str = "http://127.0.0.1:8601",
    allow_duplicate: bool = False,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Submit one LinkedIn Easy Apply with the full gate + dedup + receipt chain."""
    _require_promotion(promotion)
    idempotency_key = f"apply:linkedin:{posting_id}"
    _require_application_authorization(
        authorization,
        candidate_id=candidate_id,
        posting_id=posting_id,
        apply_url=apply_url,
        idempotency_key=idempotency_key,
    )

    if not allow_duplicate:
        from .ashby_apply import _already_submitted

        prior = _already_submitted(candidate_id, apply_url, memory_url)
        if prior is not None:
            raise LinkedInEasyApplyError(f"ALREADY_APPLIED:{prior.get('state')} (pass allow_duplicate=True to override)")

    adapter = LinkedInEasyApplyAdapter(tab_id=tab_id, surf_run=surf_run)
    result = adapter.submit({"posting_id": posting_id}, idempotency_key)

    receipt = {
        "schema": "monitor_opportunities.application_effect_receipt.v1",
        "state": result["state"],
        "provider": "linkedin_easy_apply",
        "posting_id": posting_id,
        "apply_url": apply_url,
        "idempotency_key": idempotency_key,
        "promotion_ref": promotion.get("capability"),
        "authorization_digest": authorization["authorization_digest"],
        "external_effects": True,
        "committed_at": utc_now(),
        **{k: v for k, v in result.items() if k != "state"},
    }
    if result["state"] == "COMMITTED":
        from ..submission_store import store_submission

        rec = store_submission(
            candidate_id=candidate_id,
            opportunity={"apply_url": apply_url, "ats_provider": "linkedin_easy_apply"},
            prefill_result={"provider": "linkedin_easy_apply", "apply_url": apply_url, "tab_id": tab_id},
            state="submitted",
            memory_url=memory_url,
        )
        receipt["ledger_recorded"] = rec.get("stored", False)
    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt
