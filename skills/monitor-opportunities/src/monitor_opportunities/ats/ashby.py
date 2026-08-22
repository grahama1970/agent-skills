"""Ashby (jobs.ashbyhq.com) form adapter.

Ashby is a React SPA: every field lives in a container with a visible label,
the inputs carry only generic "Type here..." placeholders, and the submit is
protected by reCAPTCHA. That last fact is not worked around - a live reCAPTCHA
is a human handoff (surf/captcha boundary), which fits the per-application
permission model exactly: the human is present to authorize the exact payload
AND to clear the captcha in their own tab. Nothing here submits autonomously.

form_from_dom_capture reads the real rendered form into the same
`monitor_opportunities.ats_form.v1` shape the Greenhouse adapter produces, so
the existing inspect -> plan -> prefill -> authorize -> submit chain drives
Ashby unchanged.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..util import sha256_json, utc_now

SURF_RUN_DEFAULT = Path(__file__).resolve().parents[4] / "surf" / "run.sh"

# Read every field group's label, input kind, and required flag from the live DOM.
_ASHBY_FIELD_JS = (
    "(function(){"
    "var o=[];"
    "var groups=document.querySelectorAll('[class*=_fieldEntry],[class*=fieldEntry],fieldset');"
    "for(var i=0;i<groups.length;i++){var g=groups[i];"
    "var labEl=g.querySelector('label,[class*=_label],legend')||{};"
    "var lab=((labEl.innerText||'').replace(/\\s+/g,' ').trim());"
    "var inp=g.querySelector('input:not([type=hidden]),textarea,select');"
    "if(!inp||!lab)continue;"
    # Ashby marks required fields with a CSS class on the label/heading (e.g.
    # _required_f7cvd_91), not always an asterisk or the input's required attr.
    "var reqClass=/_required/.test(labEl.className||'')||!!g.querySelector('[class*=_required]');"
    "var req=inp.required||/required|\\*/i.test(lab)||g.getAttribute('aria-required')==='true'||reqClass;"
    "var opts=[];"
    "if(inp.type==='radio'||inp.tagName==='SELECT'){"
    "var rs=g.querySelectorAll(inp.tagName==='SELECT'?'option':'input[type=radio]');"
    "for(var j=0;j<rs.length;j++){var rl=rs[j].getAttribute('aria-label')||((rs[j].parentElement||{}).innerText||'').trim()||rs[j].value;if(rl)opts.push(rl.slice(0,40));}}"
    "o.push({label:lab.slice(0,120),tag:inp.tagName,type:inp.type||inp.tagName.toLowerCase(),required:!!req,options:opts.slice(0,8)});"
    "}"
    "var captcha=!!document.querySelector('[name=g-recaptcha-response],.g-recaptcha,iframe[src*=recaptcha]');"
    "return JSON.stringify({fields:o,captcha:captcha,file_inputs:document.querySelectorAll('input[type=file]').length});"
    "})()"
)

# Requirement labels map to the answer-bank keys / claim-bound resume, not to raw text.
_FIELD_KIND = {
    "file": "attachment",
    "email": "prefill_exact",
    "tel": "prefill_exact",
    "text": "prefill_exact",
    "textarea": "human_required",   # free text is always the human's
    "radio": "human_required",       # eligibility/EEO selects are the human's
    "select": "human_required",
}


class AshbyFormError(ValueError):
    """Stable Ashby capture error."""


def _load_answer_bank() -> dict[str, Any]:
    """The candidate's standing truthful answers (identity, work authorization)."""
    import json

    path = Path(__file__).resolve().parents[3] / "config" / "answer_bank.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _surf(surf_run: Path, *args: str, timeout: int = 60) -> str:
    proc = subprocess.run([str(surf_run), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise AshbyFormError(f"surf {args[0]} failed: {proc.stderr[:200] or proc.stdout[:200]}")
    return proc.stdout


# Eligibility questions whose truthful answer is a human-attested fact already in
# the answer bank (derived from citizenship). These are answerable, NOT
# human_required -- re-asking them was a logic flaw (2026-08-22). Clearance is
# deliberately excluded: it is variable and stays human_required.
_ELIGIBILITY_ANSWERABLE = {
    "authorized to work": ("work_authorization", "authorized_us"),
    "legally authorized": ("work_authorization", "authorized_us"),
    "sponsorship": ("work_authorization", "require_sponsorship"),
}


def _eligibility_answer_key(label: str) -> tuple[str, str] | None:
    low = label.lower()
    for phrase, key in _ELIGIBILITY_ANSWERABLE.items():
        if phrase in low:
            return key
    return None


def _field_kind(label: str, input_type: str) -> str:
    low = label.lower()
    # Citizenship-derived eligibility answers come from the answer bank, not the
    # human, every time -- so they are answerable, not human_required.
    if _eligibility_answer_key(label) is not None:
        return "answer_bank_choice"
    # Sensitive / genuinely variable content is human_required regardless of type.
    if any(k in low for k in ("clearance", "gender", "race",
                              "veteran", "disability", "why", "cover", "salary")):
        return "human_required"
    return _FIELD_KIND.get(input_type, "human_required")


def form_from_dom_capture(
    *,
    site: str,
    posting_id: str,
    url: str,
    tab_id: str,
    surf_run: Path = SURF_RUN_DEFAULT,
) -> dict[str, Any]:
    """Read the live Ashby application form into the canonical ats_form shape."""

    import json

    raw = _surf(surf_run, "js", "--tab-id", tab_id, "--no-activate", _ASHBY_FIELD_JS).strip()
    # surf prints the JS return value as a JSON string literal; decode once to the
    # string, then parse that string as the payload JSON.
    try:
        inner = json.loads(raw) if raw.startswith('"') else raw
        payload = json.loads(inner) if isinstance(inner, str) else inner
    except json.JSONDecodeError as exc:
        raise AshbyFormError(f"unparseable Ashby DOM payload: {raw[:120]}") from exc
    if not isinstance(payload, dict):
        raise AshbyFormError("Ashby DOM payload was not an object")
    answer_bank = _load_answer_bank()
    fields = []
    for f in payload.get("fields", []):
        label = str(f.get("label") or "").rstrip("* ").strip()
        if not label:
            continue
        disposition = _field_kind(label, str(f.get("type") or ""))
        field = {
            "name": label,
            "label": label,
            "field_type": f.get("type") or "text",
            "required": bool(f.get("required")),
            "disposition": disposition,
            "options": f.get("options") or [],
        }
        if disposition == "answer_bank_choice":
            key = _eligibility_answer_key(label)
            answer = None
            if key is not None:
                answer = (answer_bank.get(key[0]) or {}).get(key[1])
            # No truthful answer on file -> fall back to human_required, never guess.
            if answer:
                field["automated_answer"] = answer
                field["answer_bank_key"] = list(key)
            else:
                field["disposition"] = "human_required"
        fields.append(field)
    form = {
        "schema": "monitor_opportunities.ats_form.v1",
        "provider": "ashby",
        "site": site,
        "posting_id": posting_id,
        "url": url,
        "fields": fields,
        "accepted_attachments": ["resume"],
        "policy_observations": (
            ["Live reCAPTCHA present: submit requires human handoff to clear the challenge."]
            if payload.get("captcha") else []
        ),
        "captcha_present": bool(payload.get("captcha")),
        "captured_at": utc_now(),
    }
    form["form_schema_digest"] = sha256_json(form)
    return form
