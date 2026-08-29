"""Gated Workday application commit path.

Workday is site/account driven, so this module is deliberately stricter than a
generic form submitter: the captured schema, exact approved answers, a scoped
Workday submit promotion, and the post-report human authorization must all bind
to the same candidate/posting/apply payload before any browser action is
attempted.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from ..contracts import SENSITIVE_FIELD_TYPES
from ..util import sha256_json, stable_id, utc_now, write_json
from .prefill_executor import SURF_RUN_DEFAULT

_HUMAN_FIELD_TYPES = SENSITIVE_FIELD_TYPES | {"choice", "file", "captcha", "password", "otp"}
_HANDOFF_NEEDLES = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "sign in",
    "signin",
    "log in",
    "login",
    "password",
    "two-factor",
    "two factor",
    "2fa",
    "mfa",
    "verification code",
    "one-time code",
    "one time code",
    "create account",
)
_IDENTITY_LABEL_MAP = {
    "first name": ("identity", "first_name"),
    "last name": ("identity", "last_name"),
    "full name": ("identity", "name"),
    "name": ("identity", "name"),
    "email": ("identity", "email"),
    "phone": ("identity", "phone"),
    "linkedin": ("identity", "linkedin"),
    "website": ("identity", "website"),
    "portfolio": ("identity", "website"),
    "city": ("identity", "location"),
    "location": ("identity", "location"),
}


class WorkdayCommitError(ValueError):
    """Stable Workday commit gate error."""


class WorkdayCommitAdapter(Protocol):
    """Browser adapter surface used after all Workday gates pass."""

    def prefill(
        self,
        *,
        apply_url: str,
        fields: list[dict[str, str]],
        out_dir: Path,
    ) -> dict[str, Any]:
        """Fill already-approved schema-bound fields and return readback evidence."""

    def submit(self, *, posting_id: str, idempotency_key: str, out_dir: Path) -> dict[str, Any]:
        """Submit and return a provider readback result."""


class SurfWorkdayAdapter:
    """Minimal Surf-backed Workday adapter.

    It fills only selectors supplied by the captured schema. Submit uses a
    conservative visible submit-button query and reports COMMITTED only when a
    post-click Workday page readback contains a stable confirmation marker.
    """

    def __init__(self, *, tab_id: str, surf_run: Path = SURF_RUN_DEFAULT) -> None:
        self.tab_id = tab_id
        self.surf_run = surf_run

    def _surf(self, *args: str, timeout: int = 90) -> str:
        proc = subprocess.run(
            [str(self.surf_run), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise WorkdayCommitError(f"SURF_COMMAND_FAILED:{args[0]}:{proc.stderr[-300:]}")
        return proc.stdout.strip()

    def _js(self, script: str, timeout: int = 90) -> Any:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(script)
            path = handle.name
        raw = self._surf("js", "--tab-id", self.tab_id, "--file", path, timeout=timeout)
        try:
            outer = json.loads(raw)
            if isinstance(outer, str) and outer.startswith(("{", "[", "\"")):
                return json.loads(outer)
            return outer
        except json.JSONDecodeError:
            return raw

    def prefill(
        self,
        *,
        apply_url: str,
        fields: list[dict[str, str]],
        out_dir: Path,
    ) -> dict[str, Any]:
        payload = json.dumps(fields)
        script = (
            "(function(){"
            f"var rows={payload};"
            "var out=[];"
            "var inputSetter=Object.getOwnPropertyDescriptor("
            "window.HTMLInputElement.prototype,'value').set;"
            "var areaSetter=Object.getOwnPropertyDescriptor("
            "window.HTMLTextAreaElement.prototype,'value').set;"
            "for(var i=0;i<rows.length;i++){"
            " var r=rows[i], el=document.querySelector(r.selector);"
            " if(!el){out.push({name:r.name,state:'SELECTOR_NOT_FOUND'});continue;}"
            " if(el.type==='file'){out.push({name:r.name,state:'FILE_FIELD_SKIPPED'});continue;}"
            " var setter=el.tagName==='TEXTAREA'?areaSetter:inputSetter;"
            " setter.call(el,r.value);"
            " el.dispatchEvent(new Event('input',{bubbles:true}));"
            " el.dispatchEvent(new Event('change',{bubbles:true}));"
            " out.push({name:r.name,state:el.value===r.value?"
            "'FILLED_VERIFIED':'FILL_MISMATCH',value:el.value});"
            "}"
            "return JSON.stringify(out);"
            "})()"
        )
        rows = self._js(script)
        if isinstance(rows, str):
            rows = json.loads(rows)
        screenshot = out_dir / "workday-prefill-evidence.png"
        try:
            self._surf("snap", "--output", str(screenshot), timeout=120)
            evidence = [str(screenshot)]
        except WorkdayCommitError:
            evidence = []
        return {"apply_url": apply_url, "field_results": rows, "browser_evidence_paths": evidence}

    def submit(self, *, posting_id: str, idempotency_key: str, out_dir: Path) -> dict[str, Any]:
        click = self._js(
            "(function(){var b=[].slice.call("
            "document.querySelectorAll('button,input[type=submit]'))"
            ".filter(function(e){return /submit|send application/i.test("
            "e.innerText||e.value||e.getAttribute('aria-label')||'');})[0];"
            "if(!b)return 'SUBMIT_NOT_FOUND';b.click();return 'CLICKED';})()"
        )
        if click != "CLICKED":
            return {
                "state": "BLOCKED",
                "blocked_reason": "WORKDAY_SUBMIT_CONTROL_NOT_FOUND",
                "submitted": False,
            }
        self._surf("wait", "6")
        text = self._js("document.body.innerText.slice(0,6000)")
        lowered = str(text).lower()
        confirmation_markers = (
            "application submitted",
            "successfully submitted",
            "thank you for applying",
        )
        if any(marker in lowered for marker in confirmation_markers):
            screenshot = out_dir / "workday-submit-confirmation.png"
            evidence: list[str] = []
            try:
                self._surf("snap", "--output", str(screenshot), timeout=120)
                evidence.append(str(screenshot))
            except WorkdayCommitError:
                pass
            return {
                "state": "COMMITTED",
                "provider_confirmation": f"workday:{posting_id}:{idempotency_key}",
                "submitted": True,
                "browser_evidence_paths": evidence,
            }
        return {
            "state": "INDETERMINATE",
            "blocked_reason": "WORKDAY_SUBMIT_CLICKED_NO_CONFIRMATION",
            "submitted": False,
            "page_excerpt": str(text)[:300],
        }


def _authorized_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set)):
        return {str(row) for row in value}
    return {str(value)}


def _scope_values(receipt: dict[str, Any], *keys: str) -> set[str]:
    values: set[str] = set()
    scope = receipt.get("scope") if isinstance(receipt.get("scope"), dict) else {}
    for key in keys:
        values.update(_authorized_values(receipt.get(key)))
        values.update(_authorized_values(scope.get(key)))
    return values


def require_workday_promotion(
    promotion: dict[str, Any] | None,
    *,
    site: str,
    candidate_id: str,
    apply_url: str,
) -> None:
    if promotion is None:
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_MISSING")
    if promotion.get("capability") != f"ats_form_submit:workday:{site}":
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_SCOPE_MISMATCH")
    if promotion.get("actor") != "human" or promotion.get("decision") != "PROMOTE":
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_NOT_HUMAN_PROMOTE")
    if candidate_id not in _scope_values(promotion, "candidate_id", "candidate_ids", "candidates"):
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_CANDIDATE_MISMATCH")
    sites = _scope_values(promotion, "site", "sites")
    if site not in sites:
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_SITE_MISMATCH")
    apply_urls = _scope_values(promotion, "apply_url", "apply_urls")
    if apply_urls and apply_url not in apply_urls:
        raise WorkdayCommitError("WORKDAY_SUBMIT_PROMOTION_APPLY_URL_MISMATCH")


def require_workday_authorization(
    authorization: dict[str, Any] | None,
    *,
    candidate_id: str,
    posting_url: str,
    apply_url: str,
    payload_digest: str,
) -> None:
    if authorization is None:
        raise WorkdayCommitError("WORKDAY_APPLICATION_AUTHORIZATION_MISSING")
    if authorization.get("schema") != "monitor_opportunities.application_authorization.v1":
        raise WorkdayCommitError("WORKDAY_APPLICATION_AUTHORIZATION_SCHEMA_MISMATCH")
    if authorization.get("actor") != "human" or authorization.get("state") != "HUMAN_AUTHORIZED":
        raise WorkdayCommitError("WORKDAY_APPLICATION_AUTHORIZATION_NOT_HUMAN")
    if not authorization.get("authorization_digest"):
        raise WorkdayCommitError("WORKDAY_APPLICATION_AUTHORIZATION_DIGEST_MISSING")
    expected = {
        "candidate_id": candidate_id,
        "posting_url": posting_url,
        "apply_url": apply_url,
        "payload_digest": payload_digest,
    }
    for key, value in expected.items():
        if authorization.get(key) != value:
            raise WorkdayCommitError(f"WORKDAY_APPLICATION_AUTHORIZATION_{key.upper()}_MISMATCH")


def _field_answer(field: dict[str, Any], approved_answers: dict[str, Any]) -> str | None:
    answers = (
        approved_answers.get("answers")
        if isinstance(approved_answers.get("answers"), dict)
        else {}
    )
    name = str(field.get("name") or "")
    if name in answers and answers[name] is not None:
        return str(answers[name])
    low = name.lower()
    for phrase, key in _IDENTITY_LABEL_MAP.items():
        if phrase in low:
            section = approved_answers.get(key[0])
            if isinstance(section, dict) and section.get(key[1]) is not None:
                return str(section[key[1]])
    return None


def plan_workday_fields(
    *,
    form_schema: dict[str, Any],
    approved_answers: dict[str, Any],
) -> dict[str, Any]:
    if form_schema.get("provider") != "workday":
        raise WorkdayCommitError("WORKDAY_FORM_PROVIDER_MISMATCH")
    fields = form_schema.get("fields")
    if not isinstance(fields, list):
        raise WorkdayCommitError("WORKDAY_FORM_FIELDS_MISSING")
    known_field_names = {str(field.get("name") or "") for field in fields}
    explicit_answers = (
        approved_answers.get("answers")
        if isinstance(approved_answers.get("answers"), dict)
        else {}
    )
    unbound = sorted(name for name in explicit_answers if str(name) not in known_field_names)
    if unbound:
        raise WorkdayCommitError(f"WORKDAY_APPROVED_ANSWER_NOT_SCHEMA_BOUND:{unbound}")

    fillable: list[dict[str, str]] = []
    unresolved_required: list[str] = []
    human_required: list[str] = []
    for field in fields:
        name = str(field.get("name") or "")
        field_type = str(field.get("field_type") or "text")
        selector = field.get("selector")
        answer = _field_answer(field, approved_answers)
        if field_type in _HUMAN_FIELD_TYPES or field.get("ambiguous"):
            human_required.append(name)
            if field.get("required"):
                unresolved_required.append(name)
            continue
        if answer is None:
            if field.get("required"):
                unresolved_required.append(name)
            continue
        if not selector:
            if field.get("required"):
                unresolved_required.append(name)
            continue
        fillable.append(
            {
                "name": name,
                "selector": str(selector),
                "value": answer,
                "field_type": field_type,
            }
        )
    return {
        "fillable_fields": fillable,
        "fillable_field_names": [row["name"] for row in fillable],
        "human_required_fields": human_required,
        "unresolved_required_fields": unresolved_required,
    }


def workday_handoff_reasons(form_schema: dict[str, Any]) -> list[str]:
    haystack: list[str] = []
    for key in ("status", "error", "page_text", "capture_method"):
        if form_schema.get(key):
            haystack.append(str(form_schema[key]))
    for row in form_schema.get("policy_observations", []) or []:
        haystack.append(str(row))
    reasons: list[str] = []
    combined = "\n".join(haystack).lower()
    for needle in _HANDOFF_NEEDLES:
        if needle in combined:
            normalized = needle.upper().replace(" ", "_").replace("-", "_")
            reasons.append(f"WORKDAY_HUMAN_HANDOFF_{normalized}")
    for field in form_schema.get("fields", []) or []:
        field_text = f"{field.get('name', '')} {field.get('field_type', '')}".lower()
        for needle in _HANDOFF_NEEDLES:
            if needle in field_text:
                normalized = needle.upper().replace(" ", "_").replace("-", "_")
                reasons.append(f"WORKDAY_HUMAN_HANDOFF_{normalized}")
    return sorted(set(reasons))


def _base_receipt(
    *,
    candidate_id: str,
    posting_url: str,
    apply_url: str,
    payload_digest: str,
    form_schema: dict[str, Any],
    out_dir: Path,
    mocked: bool,
    live: bool,
) -> dict[str, Any]:
    site = str(form_schema.get("site") or "")
    posting_id = str(form_schema.get("posting_id") or "")
    return {
        "schema": "monitor_opportunities.workday_commit_receipt.v1",
        "provider": "workday",
        "site": site,
        "posting_id": posting_id,
        "candidate_id": candidate_id,
        "posting_url": posting_url,
        "apply_url": apply_url,
        "payload_digest": payload_digest,
        "form_schema_digest": sha256_json(form_schema),
        "idempotency_key": f"apply:workday:{site}:{posting_id}:{candidate_id}",
        "mocked": mocked,
        "live": live,
        "external_effects": False,
        "submitted": False,
        "browser_evidence_paths": [],
        "created_at": utc_now(),
        "out_dir": str(out_dir),
    }


def _finish_receipt(receipt: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    receipt["receipt_digest"] = sha256_json(receipt)
    safe_candidate = "".join(ch if ch.isalnum() else "-" for ch in receipt["candidate_id"])[:80]
    path = out_dir / f"workday-commit-receipt-{safe_candidate}.json"
    write_json(path, receipt)
    receipt["receipt_path"] = str(path)
    write_json(path, receipt)
    return receipt


def _blocked(
    receipt: dict[str, Any],
    reason: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt.update(
        {
            "state": "BLOCKED",
            "blocked_reason": reason,
            "external_effects": False,
            "submitted": False,
        }
    )
    if details:
        receipt.update(details)
    return receipt


def commit_workday_application(
    *,
    candidate_id: str,
    posting_url: str,
    apply_url: str,
    payload_digest: str,
    form_schema: dict[str, Any],
    approved_answers: dict[str, Any],
    promotion: dict[str, Any],
    authorization: dict[str, Any],
    out_dir: Path,
    submit: bool = False,
    adapter: WorkdayCommitAdapter | None = None,
    allow_duplicate: bool = False,
    memory_url: str = "http://127.0.0.1:8601",
    mocked: bool = False,
    live: bool = True,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = _base_receipt(
        candidate_id=candidate_id,
        posting_url=posting_url,
        apply_url=apply_url,
        payload_digest=payload_digest,
        form_schema=form_schema,
        out_dir=out_dir,
        mocked=mocked,
        live=live,
    )
    try:
        if form_schema.get("provider") != "workday":
            raise WorkdayCommitError("WORKDAY_FORM_PROVIDER_MISMATCH")
        form_url = str(form_schema.get("url") or form_schema.get("apply_url") or "")
        if form_url and form_url != apply_url:
            raise WorkdayCommitError("WORKDAY_FORM_APPLY_URL_MISMATCH")
        plan = plan_workday_fields(form_schema=form_schema, approved_answers=approved_answers)
        receipt.update(plan)
        require_workday_promotion(
            promotion,
            site=str(form_schema.get("site") or ""),
            candidate_id=candidate_id,
            apply_url=apply_url,
        )
        require_workday_authorization(
            authorization,
            candidate_id=candidate_id,
            posting_url=posting_url,
            apply_url=apply_url,
            payload_digest=payload_digest,
        )
        receipt["authorization_digest"] = authorization["authorization_digest"]
        receipt["promotion_ref"] = promotion.get("capability")
        if not allow_duplicate:
            from .ashby_apply import _already_submitted

            prior = _already_submitted(candidate_id, apply_url, memory_url)
            if prior is not None:
                return _finish_receipt(
                    _blocked(
                        receipt,
                        "WORKDAY_ALREADY_APPLIED",
                        details={"prior_submission": prior},
                    ),
                    out_dir,
                )
        handoff = workday_handoff_reasons(form_schema)
        if handoff:
            return _finish_receipt(
                _blocked(
                    receipt,
                    "WORKDAY_HUMAN_HANDOFF_REQUIRED",
                    details={"handoff_reasons": handoff},
                ),
                out_dir,
            )
        if plan["unresolved_required_fields"]:
            return _finish_receipt(_blocked(receipt, "WORKDAY_UNRESOLVED_REQUIRED_FIELDS"), out_dir)
        if not submit:
            return _finish_receipt(_blocked(receipt, "WORKDAY_SUBMIT_NOT_REQUESTED"), out_dir)
        if not form_schema.get("fields"):
            return _finish_receipt(
                _blocked(receipt, "WORKDAY_CAPTURED_SCHEMA_FIELDS_REQUIRED"),
                out_dir,
            )
        if not plan["fillable_fields"]:
            return _finish_receipt(
                _blocked(receipt, "WORKDAY_NO_SCHEMA_BOUND_APPROVED_FIELDS"),
                out_dir,
            )
        if adapter is None:
            return _finish_receipt(_blocked(receipt, "WORKDAY_BROWSER_TAB_REQUIRED"), out_dir)

        prefill = adapter.prefill(
            apply_url=apply_url,
            fields=plan["fillable_fields"],
            out_dir=out_dir,
        )
        receipt["prefill"] = prefill
        receipt["browser_evidence_paths"] = list(prefill.get("browser_evidence_paths", []))
        failed = [
            row
            for row in prefill.get("field_results", [])
            if row.get("state") not in {"FILLED_VERIFIED", "FILE_FIELD_SKIPPED"}
        ]
        if failed:
            return _finish_receipt(
                _blocked(
                    receipt,
                    "WORKDAY_PREFILL_FAILED",
                    details={"prefill_failed": failed},
                ),
                out_dir,
            )

        result = adapter.submit(
            posting_id=str(form_schema.get("posting_id") or ""),
            idempotency_key=receipt["idempotency_key"],
            out_dir=out_dir,
        )
        prefill_paths = list(receipt.get("browser_evidence_paths", []))
        receipt.update({k: v for k, v in result.items() if k != "state"})
        receipt["state"] = str(result.get("state") or "BLOCKED")
        receipt["submitted"] = result.get("submitted") is True and receipt["state"] == "COMMITTED"
        receipt["external_effects"] = receipt["state"] in {"COMMITTED", "INDETERMINATE"}
        receipt["browser_evidence_paths"] = sorted(
            set(prefill_paths + list(result.get("browser_evidence_paths", [])))
        )
        if receipt["state"] != "COMMITTED" and not receipt.get("blocked_reason"):
            receipt["blocked_reason"] = "WORKDAY_PROVIDER_DID_NOT_CONFIRM_SUBMIT"
        if receipt["state"] == "COMMITTED":
            from ..submission_store import store_submission

            ledger = store_submission(
                candidate_id=candidate_id,
                opportunity={
                    "apply_url": apply_url,
                    "posting_url": posting_url,
                    "organization": form_schema.get("organization"),
                    "title": form_schema.get("title"),
                    "ats_provider": "workday",
                },
                prefill_result={"provider": "workday", "apply_url": apply_url},
                state="submitted",
                memory_url=memory_url,
            )
            receipt["ledger_recorded"] = ledger.get("stored", False)
            receipt["ledger_key"] = ledger.get("key")
        return _finish_receipt(receipt, out_dir)
    except WorkdayCommitError as exc:
        return _finish_receipt(_blocked(receipt, str(exc)), out_dir)


def build_fixture_authorization(
    *,
    candidate_id: str,
    posting_url: str,
    apply_url: str,
    payload_digest: str,
) -> dict[str, Any]:
    payload = {
        "schema": "monitor_opportunities.application_authorization.v1",
        "actor": "human",
        "state": "HUMAN_AUTHORIZED",
        "candidate_id": candidate_id,
        "posting_url": posting_url,
        "apply_url": apply_url,
        "payload_digest": payload_digest,
        "authorization_id": stable_id(
            "workday-authorization",
            {
                "candidate_id": candidate_id,
                "posting_url": posting_url,
                "apply_url": apply_url,
                "payload_digest": payload_digest,
            },
        ),
        "created_at": utc_now(),
        "external_effects": False,
    }
    return {**payload, "authorization_digest": sha256_json(payload)}
