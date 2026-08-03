#!/usr/bin/env python3
"""Enforced redaction contract for ops-gmail.

Producer-side seam validation: nothing crosses into /memory without passing
through here. Outcomes are exactly pass, self-heal-with-record, or raise —
never warn-and-continue (best-practices-skills, Typed Seam Contracts).

Copy-safe: stdlib only, @dataclass + validate(), no pydantic import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SEAM_KIND = "ops_gmail.mining_record.v1"

# A thread matching any of these is export-controlled: identity + org only.
EXPORT_CONTROL_MARKERS = (
    "itar",
    "export-controlled",
    "export controlled",
    "ear99",
    "ear 99",
    "controlled unclassified",
    "cui//",
    "distribution statement",
    "noforn",
    "proprietary — do not distribute",
)

# Never recorded, regardless of thread classification.
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[abps])[-_][A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b\d{6}\b(?=[^\n]{0,40}(?:code|otp|verification|2fa))", re.I),
    re.compile(r"https?://\S*(?:reset|recover|verify|magic|token)\S*", re.I),
    re.compile(r"\b(?:password|passwd|api[_ -]?key|bearer)\s*[:=]\s*\S+", re.I),
)

SENSITIVE_TOPIC_MARKERS = (
    "medical", "diagnosis", "prescription", "attorney-client", "privileged and confidential",
    "invoice attached", "wire transfer", "routing number", "ssn", "social security",
)

# Fields that may be recorded for ANY thread, including export-controlled ones.
IDENTITY_FIELDS = frozenset({
    "contact_key", "display_name", "email_domain", "employer", "org_key",
    "thread_count", "last_contact_at", "they_replied", "reply_latency_days",
    "warmth_tier", "role_basis", "export_controlled_thread", "seam_validation",
    "deadline_at", "outcome",
})

# Fields that carry correspondence and must be dropped when flagged.
CONTENT_FIELDS = frozenset({"subject", "snippet", "body", "excerpt", "attachments", "quoted_text"})


class RedactionViolation(Exception):
    """Raised when a record cannot be made safe. Fail closed."""


def classify_export_controlled(text: str, client_domains: tuple[str, ...] = ()) -> bool:
    """True when the thread must be treated as export-controlled."""
    low = (text or "").lower()
    if any(m in low for m in EXPORT_CONTROL_MARKERS):
        return True
    return any(d and d.lower() in low for d in client_domains)


def contains_secret(text: str) -> bool:
    return any(p.search(text or "") for p in SECRET_PATTERNS)


def contains_sensitive_topic(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in SENSITIVE_TOPIC_MARKERS)


@dataclass
class MiningRecord:
    """One contact-relationship record extracted from the mailbox."""

    contact_key: str
    display_name: str
    email_domain: str
    employer: str = ""
    thread_count: int = 0
    they_replied: bool = False
    warmth_tier: str = "one_way_only"
    role_basis: str = "existing_correspondence"
    export_controlled_thread: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    repairs: list[str] = field(default_factory=list)
    seam_validation: dict[str, str] = field(default_factory=dict)

    VALID_TIERS = ("two_way_recent", "two_way_dormant", "one_way_only", "inbound_only")

    def validate(self) -> "MiningRecord":
        """Pass, self-heal with a recorded repair, or raise. Never warn."""
        if not self.contact_key or not self.contact_key.startswith("contact:"):
            raise RedactionViolation(f"contact_key must start with 'contact:', got {self.contact_key!r}")
        if not self.display_name:
            raise RedactionViolation("display_name is required")
        if self.warmth_tier not in self.VALID_TIERS:
            raise RedactionViolation(f"warmth_tier {self.warmth_tier!r} not in {self.VALID_TIERS}")

        # Self-heal: strip any content field that leaked into extra.
        leaked = sorted(set(self.extra) & CONTENT_FIELDS)
        for key in leaked:
            self.extra.pop(key, None)
            self.repairs.append(f"dropped_content_field:{key}")

        # Self-heal: strip unknown fields not on the identity allowlist.
        unknown = sorted(k for k in self.extra if k not in IDENTITY_FIELDS)
        for key in unknown:
            self.extra.pop(key, None)
            self.repairs.append(f"dropped_unallowlisted_field:{key}")

        # Fail closed: secrets or sensitive topics must never have reached here.
        blob = " ".join(str(v) for v in self.extra.values())
        if contains_secret(blob):
            raise RedactionViolation("record carries credential-like content; refusing to emit")
        if contains_sensitive_topic(blob):
            raise RedactionViolation("record carries sensitive-topic content; refusing to emit")

        # An export-controlled thread may only ever carry identity + org.
        if self.export_controlled_thread:
            residual = sorted(set(self.extra) - IDENTITY_FIELDS)
            if residual:
                raise RedactionViolation(
                    f"export-controlled record retained non-identity fields: {residual}"
                )

        self.seam_validation = {
            "kind": SEAM_KIND,
            "status": "SELF_HEALED" if self.repairs else "PASS",
        }
        return self

    def to_memory_document(self) -> dict[str, Any]:
        """Shape written through /memory. Never contains correspondence."""
        doc = {
            "_key": self.contact_key,
            "kind": "contact",
            "scope": "career-outreach",
            "display_name": self.display_name,
            "email_domain": self.email_domain,
            "employer": self.employer,
            "thread_count": self.thread_count,
            "they_replied": self.they_replied,
            "warmth_tier": self.warmth_tier,
            "role_basis": self.role_basis,
            "export_controlled_thread": self.export_controlled_thread,
            "source": "ops-gmail:mine",
            "seam_validation": self.seam_validation,
        }
        doc.update({k: v for k, v in self.extra.items() if k in IDENTITY_FIELDS})
        if not self.seam_validation:
            raise RedactionViolation("to_memory_document() called before validate()")
        return doc


def redact_thread(
    *,
    contact_key: str,
    display_name: str,
    email_domain: str,
    thread_text: str,
    employer: str = "",
    client_domains: tuple[str, ...] = (),
    **extra: Any,
) -> MiningRecord:
    """Build a validated MiningRecord from a raw thread. The only entry point."""
    flagged = classify_export_controlled(thread_text, client_domains)
    if flagged:
        extra = {k: v for k, v in extra.items() if k in IDENTITY_FIELDS}
    rec = MiningRecord(
        contact_key=contact_key,
        display_name=display_name,
        email_domain=email_domain,
        employer=employer,
        export_controlled_thread=flagged,
        extra=dict(extra),
    )
    return rec.validate()
