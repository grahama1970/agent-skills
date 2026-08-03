#!/usr/bin/env bash
# Behavioral acceptance gates for ops-gmail.
# Not an import smoke test: positive control, negative control, safety boundaries,
# and artifact/schema assertions (best-practices-skills).
unset VIRTUAL_ENV
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 - <<'PY'
import sys, json
sys.path.insert(0, "scripts")
from redaction import (
    redact_thread, MiningRecord, RedactionViolation,
    classify_export_controlled, contains_secret, SEAM_KIND,
)

failures = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else ' :: ' + detail}")
    if not cond:
        failures.append(name)

print("== positive control: ordinary thread mines cleanly ==")
r = redact_thread(
    contact_key="contact:cubrc:jane-doe", display_name="Jane Doe",
    email_domain="cubrc.org", employer="CUBRC",
    thread_text="Following up on the extraction pipeline discussion. Happy to chat next week.",
    thread_count=4, they_replied=True, warmth_tier="two_way_recent",
)
check("not flagged export-controlled", r.export_controlled_thread is False)
check("seam_validation stamped PASS", r.seam_validation == {"kind": SEAM_KIND, "status": "PASS"},
      str(r.seam_validation))
doc = r.to_memory_document()
check("document has no body/subject/snippet", not ({"body","subject","snippet"} & set(doc)))
check("document carries relationship metadata", doc["they_replied"] is True and doc["thread_count"] == 4)
check("role_basis is existing_correspondence", doc["role_basis"] == "existing_correspondence")

print("== negative control: noise thread is not promoted to warm ==")
n = redact_thread(contact_key="contact:noreply:mailer", display_name="Mailer",
                  email_domain="noreply.example", thread_text="Your receipt is attached.")
check("defaults to one_way_only", n.warmth_tier == "one_way_only", n.warmth_tier)
check("they_replied defaults False", n.they_replied is False)

print("== safety boundary: export-controlled thread yields identity only ==")
e = redact_thread(
    contact_key="contact:primeco:sam-lee", display_name="Sam Lee",
    email_domain="primeco.com", employer="PrimeCo",
    thread_text="ITAR-controlled: DISTRIBUTION STATEMENT C. Interface spec for the seeker assembly.",
    thread_count=9, they_replied=True, warmth_tier="two_way_recent",
    subject="Seeker assembly interface", body="technical details here",
)
check("flagged export_controlled", e.export_controlled_thread is True)
ed = e.to_memory_document()
check("no content fields survive", not (set(ed) & {"subject","body","snippet","excerpt","attachments"}),
      str(sorted(set(ed) & {"subject","body","snippet"})))
check("identity retained", ed["display_name"] == "Sam Lee" and ed["employer"] == "PrimeCo")
check("flag persisted to document", ed["export_controlled_thread"] is True)

print("== safety boundary: client-domain marker also flags ==")
c = redact_thread(contact_key="contact:x:y", display_name="Y", email_domain="x.com",
                  thread_text="Routine note from acme-defense.com program office",
                  client_domains=("acme-defense.com",))
check("client domain triggers flag", c.export_controlled_thread is True)

print("== adversarial: credential content is refused, not stored ==")
for label, payload in [
    ("api key", {"outcome": "sk-abcdefghijklmnopqrstuvwxyz012345"}),
    ("aws key", {"outcome": "AKIAIOSFODNN7EXAMPLE"}),
    ("reset link", {"outcome": "https://example.com/reset?token=abc123"}),
    ("private key", {"outcome": "-----BEGIN RSA PRIVATE KEY-----"}),
]:
    try:
        MiningRecord(contact_key="contact:a:b", display_name="B", email_domain="b.com",
                     extra=dict(payload)).validate()
        check(f"refuses {label}", False, "validate() accepted it")
    except RedactionViolation:
        check(f"refuses {label}", True)

print("== adversarial: sensitive topics refused ==")
try:
    MiningRecord(contact_key="contact:a:b", display_name="B", email_domain="b.com",
                 extra={"outcome": "attorney-client privileged and confidential"}).validate()
    check("refuses sensitive topic", False, "accepted")
except RedactionViolation:
    check("refuses sensitive topic", True)

print("== self-heal with record: leaked content field is dropped, not passed ==")
h = MiningRecord(contact_key="contact:a:b", display_name="B", email_domain="b.com",
                 extra={"body": "leaked correspondence", "thread_count": 2}).validate()
check("body dropped", "body" not in h.extra)
check("repair recorded", any("dropped_content_field:body" in x for x in h.repairs), str(h.repairs))
check("status SELF_HEALED", h.seam_validation["status"] == "SELF_HEALED", str(h.seam_validation))
check("legit field survived", h.extra.get("thread_count") == 2)

print("== schema assertions: malformed records raise ==")
for label, kwargs in [
    ("bad contact_key", dict(contact_key="jane", display_name="J", email_domain="j.com")),
    ("empty display_name", dict(contact_key="contact:a:b", display_name="", email_domain="b.com")),
    ("bad warmth tier", dict(contact_key="contact:a:b", display_name="B", email_domain="b.com",
                             warmth_tier="super_warm")),
]:
    try:
        MiningRecord(**kwargs).validate()
        check(f"raises on {label}", False, "accepted")
    except RedactionViolation:
        check(f"raises on {label}", True)

print("== fail closed: to_memory_document before validate ==")
try:
    MiningRecord(contact_key="contact:a:b", display_name="B", email_domain="b.com").to_memory_document()
    check("refuses unvalidated emit", False, "accepted")
except RedactionViolation:
    check("refuses unvalidated emit", True)

print("== no direct ArangoDB access anywhere in this skill ==")
import pathlib
bad = []
for p in pathlib.Path(".").rglob("*.py"):
    t = p.read_text()
    if "from arango import" in t or "ArangoClient" in t or "_api/cursor" in t:
        bad.append(str(p))
check("no arango import", not bad, str(bad))

print()
if failures:
    print(f"SANITY FAIL ({len(failures)}): {failures}")
    sys.exit(1)
print("SANITY PASS — all behavioral gates green")
PY
