"""Nightly digest + lane-health phases (extracted from cli.nightly).

The morning digest is the human-facing product: response-ranked shortlist with
triggers, warm paths (config + mailbox + premium inbound + hiring contacts),
premium per-job insights, and researched prospects. Lane health flags DEGRADED
and THIN lanes honestly. Extracted move-only from a 434-line nightly god
function (style-max-800-lines / thin-function rule); behavior unchanged.

Raises ContractError (NIGHTLY_DIGEST_EMPTY) for the caller to fail the run.
"""

from __future__ import annotations

import json
import os as _os
from pathlib import Path
from typing import Any

from loguru import logger

from .contracts import ContractError
from .morning_digest import build_digest
from .util import read_json, utc_now  # noqa: F401  (read_json: parity with cli)


def run_digest_phase(
    out: Path,
    skill_dir: Path,
    capture_dir: Path,
    memory_url: str,
    steps: dict[str, Any],
) -> None:
    """DIGEST phase: build, enrich, persist, and receipt the morning digest."""
    import urllib.request as _digest_urlreq

    shortlist_path = out / "ranking" / "shortlist.json"
    digest: dict[str, object] = {}
    if shortlist_path.exists():
        shortlist_rows = json.loads(shortlist_path.read_text(encoding="utf-8"))
        # Trigger signal: fit-gated, receipted brave-search pass (fail-soft to {}).
        from .trigger_signals import triggers_for_shortlist

        try:
            triggers, trigger_receipt = triggers_for_shortlist(shortlist_rows)
        except Exception as exc:  # noqa: BLE001 - trigger enrichment must never fail the run
            logger.warning("trigger enrichment skipped: {}", exc)
            triggers = {}
            trigger_receipt = {
                "schema": "monitor_opportunities.trigger_receipt.v1",
                "error": str(exc), "records": [],
            }
        (out / "trigger-receipt.json").write_text(
            json.dumps(trigger_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # Warm-path config (populated by discover-contacts; empty -> 0, honest).
        warm_paths_cfg = skill_dir / "config" / "warm_paths.json"
        try:
            warm_paths = json.loads(warm_paths_cfg.read_text(encoding="utf-8")).get("by_org", {})
        except (OSError, ValueError):
            warm_paths = {}
        # Mailbox-mined warm contacts (/mailbox-mining -> /memory `contacts`):
        # people Graham actually corresponds with at shortlist orgs. Fail-soft.
        try:
            from .prospect_research import mailbox_warm_contacts

            mb_warm = mailbox_warm_contacts(
                memory_url, [str(r.get("organization") or "") for r in shortlist_rows]
            )
            for org, entry in mb_warm.items():
                warm_paths.setdefault(org, entry)
            steps["mailbox_warm"] = {"orgs_matched": len(mb_warm)}
        except Exception as exc:  # noqa: BLE001
            logger.warning("mailbox warm contacts skipped: {}", exc)
        # Premium inbound: who viewed the profile already showed interest — the
        # warmest signal for BOTH employment and consulting. Their orgs join the
        # warm-paths overlay; the viewers themselves are researched (dogpile/
        # brave) and surfaced in the digest. Best-effort.
        inbound_viewers: list[dict[str, object]] = []
        try:
            from .browser_capture import capture_linkedin_who_viewed
            from .prospect_research import research_prospects

            wv_receipt = capture_linkedin_who_viewed(capture_dir)
            steps["who_viewed"] = {"status": wv_receipt.get("status"),
                                   "viewers": wv_receipt.get("viewers_captured")}
            if wv_receipt.get("evidence_path"):
                viewers = json.loads(
                    Path(wv_receipt["evidence_path"]).read_text(encoding="utf-8")
                ).get("viewers", [])
                for v in viewers:
                    org = str(v.get("org") or "").strip()
                    if org and org.lower() not in {k.lower() for k in warm_paths}:
                        warm_paths[org] = {"warm_path": 0.7,
                                           "via": f"viewed your profile ({v.get('name')})"}
                inbound_viewers = research_prospects(viewers, limit=5)
        except Exception as exc:  # noqa: BLE001 - inbound enrichment must never fail the run
            logger.warning("who-viewed enrichment skipped: {}", exc)
        # Actively-hiring contacts in the network (param discovered live): warm
        # hiring leads for BOTH tracks, each with the mutual-connection referral
        # path. Their orgs join warm-paths; top contacts are researched.
        hiring_contacts: list[dict[str, object]] = []
        try:
            from .browser_capture import capture_linkedin_actively_hiring

            ah_receipt = capture_linkedin_actively_hiring(capture_dir)
            steps["actively_hiring"] = {"status": ah_receipt.get("status"),
                                        "contacts": ah_receipt.get("contacts_captured")}
            if ah_receipt.get("evidence_path"):
                contacts = json.loads(
                    Path(ah_receipt["evidence_path"]).read_text(encoding="utf-8")
                ).get("contacts", [])
                for c in contacts:
                    org = str(c.get("org") or "").strip()
                    if org and org.lower() not in {k.lower() for k in warm_paths}:
                        via = f"{c.get('name')} is hiring; mutuals: {c.get('mutuals') or 'n/a'}"
                        warm_paths[org] = {"warm_path": 0.8, "via": via}
                from .prospect_research import research_prospects as _rp

                hiring_contacts = _rp(contacts, limit=5)
        except Exception as exc:  # noqa: BLE001 - enrichment must never fail the run
            logger.warning("actively-hiring enrichment skipped: {}", exc)
        digest = build_digest(shortlist_rows, triggers=triggers, warm_paths=warm_paths)
        if inbound_viewers:
            digest["inbound_interest"] = inbound_viewers[:10]
        if hiring_contacts:
            digest["warm_hiring_contacts"] = hiring_contacts[:10]
        # CONTACT CHANGES -> VENDOR LEADS. A contact who switched roles/orgs, or
        # whose company just won a contract, is the strongest consulting signal
        # we have: time-boxed mandate + already-warm relationship. Diffs tonight's
        # captured contacts against the last snapshot in /memory, and runs a
        # brave-search public-signal pass (which also works on first sighting).
        try:
            from .contact_changes import detect as detect_contact_changes

            roster: list[dict[str, object]] = []
            for src, rows in (
                ("actively_hiring", hiring_contacts),
                ("profile_viewer", inbound_viewers),
            ):
                for r in rows or []:
                    roster.append({**r, "_capture_source": src})
            if roster:
                leads, cc_receipt = detect_contact_changes(
                    roster, "linkedin_capture", memory_url, utc_now()
                )
                (out / "contact-changes.json").write_text(
                    json.dumps(
                        {"schema": "monitor_opportunities.contact_changes_run.v1",
                         "receipt": cc_receipt, "vendor_leads": leads},
                        indent=2, sort_keys=True,
                    ) + "\n",
                    encoding="utf-8",
                )
                if leads:
                    digest["vendor_leads"] = leads[:10]
                steps["contact_changes"] = cc_receipt
        except Exception as exc:  # noqa: BLE001 - must never fail the run
            logger.warning("contact-change detection skipped: {}", exc)
            steps["contact_changes"] = {"error": str(exc)}

        # CONSULTING/PROSPECT QUEUE — federal buyers + commercial signals. This
        # was built and unit-tested but never wired into the nightly, so it had
        # produced nothing every run despite being "equally important to the
        # employer queue". Fail-soft, written to its own artifact and surfaced
        # in the digest.
        try:
            from .prospect_queue import build_prospect_queue

            sam_evidence = None
            sam_path = capture_dir / "sam-website-evidence.json"
            if sam_path.exists():
                sam_evidence = json.loads(sam_path.read_text(encoding="utf-8"))
            prospects = build_prospect_queue(sam_evidence, shortlist_rows)
            (out / "prospect-queue.json").write_text(
                json.dumps(
                    {
                        "schema": "monitor_opportunities.prospect_queue.v1",
                        "generated_from": {
                            "sam_evidence": str(sam_path) if sam_evidence else None,
                            "shortlist_rows": len(shortlist_rows),
                        },
                        "prospects": prospects,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            if prospects:
                digest["prospect_queue"] = prospects[:10]
            steps["prospect_queue"] = {
                "prospects": len(prospects),
                "federal": sum(1 for p in prospects if p.get("signal_type") == "federal"),
                "artifact": str(out / "prospect-queue.json"),
            }
        except Exception as exc:  # noqa: BLE001 - prospecting must never fail the run
            logger.warning("prospect queue skipped: {}", exc)
            steps["prospect_queue"] = {"error": str(exc)}
        # Premium per-job competitive insights for the digest top (bounded):
        # applicant-rank percentile ('top N%'), applicant count, salary.
        try:
            from .browser_capture import capture_linkedin_job_insights

            top_urls: list[str] = []
            by_id = {r.get("candidate_id"): r for r in shortlist_rows}
            for e in digest.get("top", []):
                row = by_id.get(e.get("candidate_id")) or {}
                url = str(row.get("posting_url") or "")
                if "linkedin.com/jobs" in url:
                    top_urls.append(url)
                    e["_posting_url"] = url
            insights = capture_linkedin_job_insights(top_urls) if top_urls else {}
            enriched_n = 0
            for e in digest.get("top", []):
                info = insights.get(e.pop("_posting_url", ""))
                if info:
                    e["premium_insights"] = info
                    enriched_n += 1
            steps["job_insights"] = {"jobs_checked": len(top_urls), "enriched": enriched_n}
        except Exception as exc:  # noqa: BLE001
            logger.warning("job insights enrichment skipped: {}", exc)
        # Fail-closed: a shortlist with rows that yields an empty digest is a real
        # defect (the headline deliverable), not something to warn past.
        if shortlist_rows and not digest.get("top"):
            raise ContractError(
                "NIGHTLY_DIGEST_EMPTY",
                f"{len(shortlist_rows)} shortlisted rows produced 0 digest entries",
            )
        # PRE-PUBLISH TRUTH CONTRACT (webgpt eval review P0 #01/#05). The digest
        # is the human-visible product, so it is validated against this run's own
        # independent evidence BEFORE it is written or mirrored anywhere. A
        # violation fails the run closed: a wrong digest is worse than none.
        from .prepublish_contract import validate as validate_prepublish

        # Source receipt ids from THIS run, so lineage-traceable can prove every
        # displayed fact walks back to source bytes this run actually fetched.
        receipts_path = out / "discovery" / "source-receipts.jsonl"
        run_source_ids: set[str] | None = None
        if receipts_path.exists():
            run_source_ids = set()
            for line in receipts_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rid = json.loads(line).get("receipt_id")
                except ValueError:
                    continue
                if rid:
                    run_source_ids.add(str(rid))
        contract_ok, contract_report = validate_prepublish(
            digest,
            shortlist_rows,
            trigger_receipt=trigger_receipt,
            source_receipt_ids=run_source_ids,
        )
        (out / "prepublish-contract.json").write_text(
            json.dumps(contract_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        steps["prepublish_contract"] = {
            "ok": contract_ok,
            "violations": len(contract_report.get("violations", [])),
            "artifact": str(out / "prepublish-contract.json"),
        }
        if not contract_ok:
            rules = sorted({v["rule"] for v in contract_report["violations"]})
            raise ContractError(
                "NIGHTLY_DIGEST_CONTRACT_VIOLATION",
                f"{len(contract_report['violations'])} pre-publish violation(s) "
                f"[{', '.join(rules)}]; digest withheld. See prepublish-contract.json",
            )
        (out / "morning-digest.json").write_text(
            json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # mirror to /memory (recallable once the morning_opportunities view is registered)
        try:
            body = json.dumps({
                "document": {"_key": f"digest-{out.name}", **digest},
                "collection": "morning_opportunities",
            }).encode()
            _digest_urlreq.urlopen(
                _digest_urlreq.Request(
                    f"{memory_url}/store", data=body,
                    headers={"Content-Type": "application/json"},
                ),
                timeout=20,
            )
        except OSError as exc:
            logger.warning("digest memory store skipped: {}", exc)
    # DIGEST is a first-class, validated phase: it must have produced a non-empty
    # top when there was a shortlist, and its artifact must exist on disk.
    digest_artifact = out / "morning-digest.json"
    digest_ok = bool(digest.get("top")) and digest_artifact.exists()
    steps["digest"] = {
        "phase": "DIGEST_COMPLETE",
        "top": len(digest.get("top", [])),
        "counts": digest.get("counts", {}),
        "signals_wired": digest.get("signals_wired", {}),
        "artifact": str(digest_artifact) if digest_artifact.exists() else None,
        "trigger_receipt": (
            str(out / "trigger-receipt.json")
            if (out / "trigger-receipt.json").exists() else None
        ),
        "seam_validation": {
            "kind": "morning_digest.v1",
            "status": "PASS" if digest_ok else "SKIPPED_NO_SHORTLIST",
        },
    }


def lane_health_phase(out: Path, steps: dict[str, Any]) -> None:
    """Flag DEGRADED/THIN lanes from source receipts + lane summaries."""
    # Lane health: the run reports each lane MATCHES even when a lane's live sources
    # all failed (last run: federal lane B = SAM.gov API 404 + DARPA landing-page-as-1).
    # Flag DEGRADED honestly so the federal/client queues can't masquerade as healthy.
    # result_status alone lies: a lane can read MATCHES while producing ~nothing
    # (DARPA parsed a landing page as 1 opp; SAM website captured 0 rows). So a
    # lane is THIN when it yields fewer than MIN_LANE_CANDIDATES real candidates,
    # even if no source hard-failed. THIN_LANE_MIN is env-overridable.
    _DEGRADED = {"FEED_DOWN", "ERROR", "NO_MATCHES"}
    try:
        thin_min = max(1, int(_os.environ.get("MONITOR_THIN_LANE_MIN", "3")))
    except ValueError:
        thin_min = 3
    observed_by_lane: dict[str, int] = {}
    summaries_path = out / "discovery" / "lane-summaries.json"
    if summaries_path.exists():
        try:
            for s in json.loads(summaries_path.read_text(encoding="utf-8")):
                observed_by_lane[str(s.get("lane"))] = int(s.get("candidates_observed") or 0)
        except (ValueError, OSError):
            observed_by_lane = {}
    lane_health: dict[str, object] = {}
    receipts_path = out / "discovery" / "source-receipts.jsonl"
    if receipts_path.exists():
        by_lane: dict[str, list[dict[str, object]]] = {}
        for line in receipts_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            by_lane.setdefault(str(rec.get("lane") or "?"), []).append(rec)
        for lane, recs in sorted(by_lane.items()):
            healthy = [r for r in recs if str(r.get("result_status")) not in _DEGRADED]
            degraded = [
                {"provider": r.get("provider"), "result_status": r.get("result_status"),
                 "response_status": r.get("response_status")}
                for r in recs if str(r.get("result_status")) in _DEGRADED
            ]
            observed = observed_by_lane.get(lane, 0)
            if not healthy:
                status = "DEGRADED" if degraded else "EMPTY"
            elif observed < thin_min:
                status = "THIN"  # sources 'ok' but near-zero real candidates
            else:
                status = "HEALTHY"
            lane_health[lane] = {"status": status, "sources": len(recs),
                                 "healthy_sources": len(healthy),
                                 "candidates_observed": observed, "degraded": degraded}
    steps["lane_health"] = lane_health

