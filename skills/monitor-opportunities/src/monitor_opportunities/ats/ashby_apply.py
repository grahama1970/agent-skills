"""Receipt-bearing Ashby application driver.

Encodes the flow proven live on 2026-08-22 against jobs.ashbyhq.com as reusable,
gated code: capture the live form, fill only answerable fields (identity +
answer-bank eligibility) and upload the resume, OS-click the reCAPTCHA checkbox,
then submit through ``AshbySubmitAdapter`` and read the effect back.

Gate chain (never bypassed):
  1. a scoped human promotion  ``ats_form_submit:ashby:<site>``  (``_require_promotion``)
  2. every REQUIRED human_required field on the live form is resolved by a human
     answer before submit (``_require_no_unresolved_required``)
  3. the submit adapter reads the provider confirmation back from the DOM;
     anything else is BLOCKED/INDETERMINATE, never a claimed success.

This module never answers a human_required field and never solves a captcha
image challenge.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..util import sha256_json, utc_now
from .ashby import _load_answer_bank, form_from_dom_capture
from .submit_executor import AshbySubmitAdapter

# Attested screening answers resolvable from the answer bank, by label keyword.
_SCREENING_ATTESTED = {
    "authorized to work": ("work_authorization", "authorized_us"),
    "legally authorized": ("work_authorization", "authorized_us"),
    "sponsorship": ("work_authorization", "require_sponsorship"),
    "clearance": ("work_authorization", "security_clearance"),
}


def _screening_answer(label: str, answer_bank: dict[str, Any]) -> str | None:
    low = label.lower()
    for phrase, key in _SCREENING_ATTESTED.items():
        if phrase in low:
            return (answer_bank.get(key[0]) or {}).get(key[1])
    return None

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[4] / "surf" / "run.sh"


class AshbyApplyError(ValueError):
    """Stable Ashby apply-gate error."""


def _require_promotion(policy: dict[str, Any] | None, site: str) -> None:
    if policy is None:
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_MISSING")
    if policy.get("capability") != f"ats_form_submit:ashby:{site}":
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_SCOPE_MISMATCH")
    if policy.get("actor") != "human" or policy.get("decision") != "PROMOTE":
        raise AshbyApplyError("ATS_SUBMIT_PROMOTION_NOT_HUMAN_PROMOTE")


def _already_submitted(candidate_id: str, apply_url: str, memory_url: str) -> dict[str, Any] | None:
    """Return the prior submission record if this posting was already actioned.

    Reads the /memory application_submissions ledger by the same
    candidate_id+apply_url key the discovery dedup uses. A read failure returns
    None (unknown) -- it never fabricates 'not applied'.
    """
    import urllib.request

    from ..application_history import ACTIONED_STATES, submission_key

    key = submission_key(candidate_id, apply_url)
    body = json.dumps({"collection": "application_submissions", "keys": [key]}).encode()
    req = urllib.request.Request(
        f"{memory_url}/recall/by-keys", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001 - unknown history never becomes "not applied"
        return None
    for row in payload.get("documents", []) or []:
        doc = row.get("document") if isinstance(row, dict) else None
        doc = doc if isinstance(doc, dict) else (row if isinstance(row, dict) else {})
        if str(doc.get("_key") or "") == key and str(doc.get("state") or "").lower() in ACTIONED_STATES:
            return doc
    return None


def _require_no_unresolved_required(
    form: dict[str, Any], answer_bank: dict[str, Any], human_answers: dict[str, str]
) -> list[str]:
    """A required human_required field with no attested/human answer blocks submit."""
    unresolved = []
    for field in form.get("fields", []):
        if not field.get("required") or field.get("disposition") != "human_required":
            continue
        name = field["name"]
        if human_answers.get(name) or _screening_answer(name, answer_bank):
            continue
        unresolved.append(name)
    return unresolved


def _surf(*args: str, surf_run: Path = SURF_RUN_DEFAULT, timeout: int = 60) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AshbyApplyError(f"surf {args[0]} failed: {proc.stderr[:200] or proc.stdout[:200]}")
    return proc.stdout


# Ashby field label -> answer_bank identity key. Truthful values only.
_IDENTITY_LABEL_MAP = {
    "name": ("identity", "name"),
    "email": ("identity", "email"),
    "phone": ("identity", "phone"),
    "linkedin": ("identity", "linkedin"),
    "current company": ("identity", "current_company"),
    "current location": ("identity", "location"),
    "website": ("identity", "website"),
    "portfolio": ("identity", "website"),
}


def _identity_value(label: str, answer_bank: dict[str, Any]) -> str | None:
    low = label.lower()
    for phrase, key in _IDENTITY_LABEL_MAP.items():
        if phrase in low:
            return (answer_bank.get(key[0]) or {}).get(key[1])
    return None


def _fill_text_field(tab_id: str, label: str, value: str, surf_run: Path) -> str:
    """React-safe fill by label match; returns the read-back value."""
    import json as _json

    script = (
        "(function(){var lab=" + _json.dumps(label) + ";var val=" + _json.dumps(value) + ";"
        "var groups=document.querySelectorAll('[class*=_fieldEntry],[class*=fieldEntry]');"
        "for(var i=0;i<groups.length;i++){var g=groups[i];"
        "var l=((g.querySelector('label,[class*=_label]')||{}).innerText||'').trim();"
        "if(l.toLowerCase().indexOf(lab.toLowerCase())!==0)continue;"
        "var inp=g.querySelector('input:not([type=hidden]):not([type=file]),textarea');if(!inp)return 'no-input';"
        "var proto=inp.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
        "Object.getOwnPropertyDescriptor(proto,'value').set.call(inp,val);"
        "inp.dispatchEvent(new Event('input',{bubbles:true}));inp.dispatchEvent(new Event('change',{bubbles:true}));"
        "return inp.value;}return 'not-found';})()"
    )
    out = _surf(surf_run, "js", "--tab-id", tab_id, script, timeout=25)
    try:
        v = json.loads(out.strip())
        return json.loads(v) if isinstance(v, str) and v.startswith('"') else str(v)
    except json.JSONDecodeError:
        return out.strip()


def _set_radio(tab_id: str, label: str, answer: str, surf_run: Path) -> bool:
    import json as _json

    script = (
        "(function(){var lab=" + _json.dumps(label) + ";var val=" + _json.dumps(answer) + ";"
        "var groups=document.querySelectorAll('[class*=_fieldEntry],[class*=fieldEntry],fieldset');"
        "for(var i=0;i<groups.length;i++){var g=groups[i];"
        "var l=((g.querySelector('label,[class*=_label],legend')||{}).innerText||'').trim();"
        "if(l.toLowerCase().indexOf(lab.toLowerCase().slice(0,20))===-1)continue;"
        "var rs=g.querySelectorAll('input[type=radio]');"
        "var idx=/^no/i.test(val)?1:(/inactive/i.test(val)?2:0);"
        "if(rs[idx]){rs[idx].click();return rs[idx].checked;}}return false;})()"
    )
    out = _surf(surf_run, "js", "--tab-id", tab_id, script, timeout=25)
    return "true" in out.lower()


def _upload_resume(tab_id: str, resume_path: Path, surf_run: Path) -> bool:
    """Upload to the resume file input (the last input[type=file]) and read back."""
    # Find the resume file input's ref via page.read.
    page = _surf(surf_run, "page.read", "--tab-id", tab_id, timeout=40)
    ref = None
    for line in page.splitlines():
        if "type=\"file\"" in line and ("resume" in line.lower() or "[e" in line):
            import re

            m = re.search(r"\[(e\d+)\]", line)
            if m and "resume" in line.lower():
                ref = m.group(1)
    if ref is None:
        for line in page.splitlines():
            if 'type="file"' in line:
                import re

                m = re.search(r"\[(e\d+)\]", line)
                if m:
                    ref = m.group(1)
    if ref is None:
        return False
    _surf(surf_run, "upload", "--tab-id", tab_id, "--ref", ref, "--files", str(resume_path), timeout=60)
    check = _surf(surf_run, "js", "--tab-id", tab_id,
                  "(function(){var f=document.querySelectorAll('input[type=file]');"
                  "for(var i=0;i<f.length;i++){if(f[i].files.length)return true;}return false;})()", timeout=20)
    return "true" in check.lower()


def _prefill_ashby(
    tab_id: str, form: dict[str, Any], resume_path: Path,
    answer_bank: dict[str, Any], human_answers: dict[str, str], surf_run: Path,
) -> dict[str, Any]:
    """Fill every resolvable field and upload the résumé; report what filled."""
    filled: list[str] = []
    failed: list[str] = []
    for field in form.get("fields", []):
        label = str(field.get("name") or "")
        disp = field.get("disposition")
        if disp == "attachment":
            (filled if _upload_resume(tab_id, resume_path, surf_run) else failed).append(label)
        elif disp == "answer_bank_choice":
            ans = field.get("automated_answer")
            if ans and _set_radio(tab_id, label, str(ans), surf_run):
                filled.append(label)
            else:
                failed.append(label)
        elif disp == "prefill_exact":
            val = _identity_value(label, answer_bank)
            if val:
                got = _fill_text_field(tab_id, label, str(val), surf_run)
                (filled if got == str(val) else failed).append(label)
        elif disp == "human_required":
            # Attested screening answers (clearance/work-auth) are radios/selects;
            # caller-supplied free-text answers are typed.
            answer = human_answers.get(label) or _screening_answer(label, answer_bank)
            if not answer:
                continue
            if field.get("field_type") in ("radio", "select"):
                (filled if _set_radio(tab_id, label, str(answer), surf_run) else failed).append(label)
            else:
                got = _fill_text_field(tab_id, label, str(answer), surf_run)
                (filled if got == str(answer) else failed).append(label)
    return {"filled": filled, "failed": failed}


def commit_ashby_application(
    *,
    tab_id: str,
    site: str,
    posting_id: str,
    url: str,
    resume_path: Path,
    promotion: dict[str, Any],
    candidate_id: str,
    human_answers: dict[str, str] | None = None,
    memory_url: str = "http://127.0.0.1:8601",
    allow_duplicate: bool = False,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Fill, upload, and submit one Ashby application with a full receipt.

    ``human_answers`` carries the human's answers for genuinely human_required
    fields (e.g. clearance) keyed by field name. Answerable fields (identity and
    answer-bank eligibility) are resolved from the captured form + answer bank.
    """
    human_answers = human_answers or {}
    _require_promotion(promotion, site)

    # Duplicate guard: never submit the same posting twice. A prior actioned
    # record in the /memory ledger blocks the submit unless explicitly overridden.
    if not allow_duplicate:
        prior = _already_submitted(candidate_id, url, memory_url)
        if prior is not None:
            raise AshbyApplyError(
                f"ALREADY_APPLIED:{prior.get('state')}:{prior.get('updated_at')} "
                "(pass allow_duplicate=True to override)"
            )

    if not resume_path.exists():
        raise AshbyApplyError(f"RESUME_MISSING:{resume_path}")

    answer_bank = _load_answer_bank()

    form = form_from_dom_capture(site=site, posting_id=posting_id, url=url, tab_id=tab_id, surf_run=surf_run)
    unresolved = _require_no_unresolved_required(form, answer_bank, human_answers)
    if unresolved:
        raise AshbyApplyError(f"UNRESOLVED_REQUIRED_HUMAN_FIELDS:{unresolved}")

    # Actually fill the form and upload the résumé BEFORE submitting.
    prefill = _prefill_ashby(tab_id, form, resume_path, answer_bank, human_answers, surf_run)
    if prefill["failed"]:
        raise AshbyApplyError(f"PREFILL_FAILED:{prefill['failed']}")

    adapter = AshbySubmitAdapter(tab_id=tab_id, surf_run=surf_run)
    idempotency_key = f"apply:ashby:{posting_id}"
    result = adapter.submit({"posting_id": posting_id}, idempotency_key)
    result["prefill"] = prefill

    receipt = {
        "schema": "monitor_opportunities.application_effect_receipt.v1",
        "state": result["state"],
        "provider": "ashby",
        "site": site,
        "posting_id": posting_id,
        "idempotency_key": idempotency_key,
        "promotion_ref": promotion.get("capability"),
        "form_schema_digest": form.get("form_schema_digest"),
        "resume_path": str(resume_path),
        "external_effects": True,
        "committed_at": utc_now(),
        **{k: v for k, v in result.items() if k != "state"},
    }

    # Close the dedup loop: a committed submit is recorded in the same ledger the
    # discovery dedup reads, so no later run re-applies to this posting.
    if result["state"] == "COMMITTED":
        from ..submission_store import store_submission

        record = store_submission(
            candidate_id=candidate_id,
            opportunity={"apply_url": url, "organization": form.get("organization"),
                         "title": form.get("title"), "ats_provider": "ashby"},
            prefill_result={"provider": "ashby", "apply_url": url, "tab_id": tab_id},
            state="submitted",
            resume=str(resume_path),
            memory_url=memory_url,
        )
        receipt["ledger_recorded"] = record.get("stored", False)
        receipt["ledger_key"] = record.get("key")

    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt
