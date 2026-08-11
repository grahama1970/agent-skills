"""Resolve a learned ATS form against Graham's answer bank for autonomous apply.

For each form field, return a TRUTHFUL value from the answer bank / approved
profile, or queue it for one human answer. A field is auto-filled only from a
concrete standing answer — PLACEHOLDER/GENERATED entries and unmatched fields are
queued, never guessed. A questionnaire whose REQUIRED fields all resolve is
auto-submittable; otherwise it queues (and the human's answer grows the bank so
it auto-fills next time).

No network, no submit here — this is the decision layer the apply executor and
application_plan gate consume.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ANSWER_BANK = Path(__file__).resolve().parents[2] / "config" / "answer_bank.json"

# Field-name keyword -> answer-bank dotted path. First match wins.
_FIELD_MAP: tuple[tuple[str, str], ...] = (
    (r"preferred first", "identity.first_name"),
    (r"first name", "identity.first_name"),
    (r"last name|surname", "identity.last_name"),
    (r"full name|^name$|your name", "identity.name"),
    (r"email", "identity.email"),
    (r"phone|mobile", "identity.phone"),
    (r"linkedin", "identity.linkedin"),
    (r"website|portfolio|personal site", "identity.website"),
    (r"current.*(company|employer)|most recent company", "identity.current_company"),
    (r"(current|recent).*title|job title|your title", "identity.current_job_title"),
    (r"location|city|where are you", "identity.location"),
    (r"authoriz.*work|legally authorized|eligible to work", "work_authorization.authorized_us"),
    (r"sponsor", "work_authorization.require_sponsorship"),
    (r"citizen", "work_authorization.citizenship"),
    (r"gender", "eeo.gender"),
    (r"race|ethnic", "eeo.race_ethnicity"),
    (r"veteran|protected veteran", "eeo.veteran_status"),
    (r"disab", "eeo.disability_status"),
    (r"salary|compensation|pay expectation", "screening.salary_expectation"),
    (r"how did you hear|referral source", "screening.how_did_you_hear"),
    (r"years.*experience", "screening.years_experience"),
    (r"ai tools|tools.*(use|using)", "screening.what_ai_tools_do_you_use"),
    (r"why.*(company|here|interested)", "screening.why_this_company"),
    (r"notice period|when can you start", "screening.notice_period"),
    (r"relocat", "screening.willing_to_relocate"),
)
_UNRESOLVED_MARKERS = ("PLACEHOLDER", "GENERATED")


def _load_bank(path: Path = ANSWER_BANK) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dotted(bank: dict[str, Any], path: str) -> Any:
    cur: Any = bank
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def resolve_field(field: dict[str, Any], bank: dict[str, Any], resume_path: str | None) -> dict[str, Any]:
    """Return {name, disposition: auto_fill|queue, value, source, required}."""
    name = str(field.get("name") or "")
    low = name.lower()
    required = bool(field.get("required"))
    ftype = str(field.get("field_type") or "")
    if ftype == "file" or "resume" in low or low == "cv":
        return {"name": name, "disposition": "auto_fill" if resume_path else "queue",
                "value": resume_path, "source": "tailored_resume", "required": required}
    for pattern, dotted in _FIELD_MAP:
        if re.search(pattern, low):
            val = _dotted(bank, dotted)
            if isinstance(val, str) and val and not any(m in val for m in _UNRESOLVED_MARKERS):
                return {"name": name, "disposition": "auto_fill", "value": val, "source": dotted, "required": required}
            return {"name": name, "disposition": "queue", "value": None, "source": dotted, "required": required}
    return {"name": name, "disposition": "queue", "value": None, "source": "unmatched", "required": required}


def resolve_application(form: dict[str, Any], resume_path: str | None, bank: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve every field; report auto-fill coverage and whether it can auto-submit."""
    bank = bank if bank is not None else _load_bank()
    resolved = [resolve_field(f, bank, resume_path) for f in form.get("fields", [])]
    auto = [r for r in resolved if r["disposition"] == "auto_fill"]
    queued = [r for r in resolved if r["disposition"] == "queue"]
    required_queued = [r for r in queued if r["required"]]
    total = len(resolved) or 1
    return {
        "provider": form.get("provider"),
        "site": form.get("site"),
        "auto_fillable": len(auto),
        "queued": len(queued),
        "required_queued": [r["name"] for r in required_queued],
        "coverage": round(len(auto) / total, 2),
        "auto_submittable": len(required_queued) == 0,
        "filled": {r["name"]: r["value"] for r in auto},
        "queue": [r["name"] for r in queued],
    }
