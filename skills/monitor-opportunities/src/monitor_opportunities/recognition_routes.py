"""Recognition routing: get a rare-expert candidate past the screening algorithm.

A cold application — however well tailored, however local — is ~1/500. For a
candidate whose value is rare and recognizable (here: a DARPA ARCOS *prime*,
agentic formal methods, defense AI), the odds are driven almost entirely by
reaching a human who RECOGNIZES that pedigree, not by clearing an ATS funnel.

So the product's primary per-opportunity output is not an apply URL — it is the
ROUTE to recognition: a founder/CTO who knows the domain, an institutional
bridge (employer <-> the candidate's own affiliations), an alumni or
defense-network warm intro, a named hiring manager, or a consulting/subcontract
angle for someone who is already a prime and does not need a W-2. Cold apply is
the ranked-last fallback, explicitly flagged as the ~1/500 long shot it is.

This module classifies the best available route from evidence signals. The
evidence itself (who the founder is, whether an alumni/partnership bridge exists,
a named hiring manager) is gathered by research (brave-search) and passed in;
classification is deterministic and testable.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

# Evidence extraction is JUDGMENT work (is this a founder-led startup? who is the
# founder? is there a real bridge?), so it runs as an agentic pass, not regex --
# regex conflates "founder" with "founded in 1951" and invents partnerships.
# search_fn(query) -> result rows; extract_fn(prompt) -> the model's JSON string.
SearchFn = Callable[[str], list[dict[str, Any]]]
ExtractFn = Callable[[str], str]

_EXTRACT_INSTRUCTION = (
    "You are extracting recruiting-route evidence about an employer for a DARPA-prime-caliber "
    "AI engineer. From ONLY the search results below, return STRICT JSON with keys: "
    "is_founder_led_startup (bool), founder_name (string or null — only a clearly named human "
    "founder/CEO of THIS company, never the company name), founder_domain_aware (bool: does the "
    "founder work in AI/data/defense/intel), is_defense_aerospace (bool), "
    "hiring_manager_name (string or null — a named eng manager/lead for this role, else null). "
    "Do not guess. If unsupported, use null/false. Return ONLY the JSON object."
)

# Route types, best-recognition first. The ordering IS the policy: a route that
# reaches someone who recognizes the candidate's caliber beats the funnel.
ROUTE_RANK = [
    "FOUNDER_DIRECT",        # reachable technical/defense founder or CTO who knows the domain
    "DEFENSE_NETWORK",       # employer in defense/aerospace; the candidate's DARPA/ARCOS network overlaps
    "INSTITUTIONAL_BRIDGE",  # active employer<->candidate-affiliation partnership (e.g. UB CoE <-> Moog)
    "ALUMNI_REFERRAL",       # a fellow alum of the candidate's schools works at the employer
    "HIRING_MANAGER_DIRECT", # a named hiring manager / eng lead is reachable
    "CONSULTING_SUBCONTRACT",# federal/commercial signal: engage as a prime/subcontractor, not an applicant
    "COLD_APPLY_LONGSHOT",   # no recognition route found; ~1/500 funnel
]
_RANK = {name: i for i, name in enumerate(ROUTE_RANK)}


def _recognition_score(route_type: str) -> float:
    """1.0 for the strongest recognition route down to a small floor for cold apply."""
    n = len(ROUTE_RANK)
    return round(1.0 - _RANK[route_type] / n, 3)


def classify_route(opp: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Best get-past-the-algorithm route for one opportunity, from its evidence.

    ``opp`` evidence keys (all optional; populated by research):
      founder            {name, reachable, domain_aware}   a technical/defense founder or CTO
      institutional_bridge {name, detail}                  employer<->candidate-affiliation partnership
      alumni             [{name, school}]                  fellow alums at the employer
      hiring_manager     {name, role}                      named hiring manager / eng lead
      is_defense         bool                              defense/aerospace employer
      lane               employment_posting|federal_notice|commercial_signal
    ``profile`` keys: schools[], networks[] (e.g. "DARPA ARCOS", "defense/aerospace").
    """
    org = opp.get("organization") or "?"
    networks = {n.lower() for n in profile.get("networks", [])}
    schools = {s.lower() for s in profile.get("schools", [])}

    founder = opp.get("founder") or {}
    if founder.get("reachable") and founder.get("domain_aware"):
        return _route("FOUNDER_DIRECT", org,
                      target=founder.get("name") or f"{org} founder/CTO",
                      rationale=f"{founder.get('name') or 'The founder/CTO'} works in the candidate's domain and "
                                "will recognize the pedigree directly — route around the ATS.",
                      action="Substantive direct message + a concrete artifact (OSS contribution / relevant work); "
                             "no cold form.")

    if opp.get("lane") in {"federal_notice", "commercial_signal"}:
        return _route("CONSULTING_SUBCONTRACT", org,
                      target=f"{org} technical/contracts lead",
                      rationale="The candidate is already a prime; engage as prime/subcontractor or advisor, "
                                "not as a W-2 applicant.",
                      action="Respond to the sources-sought / propose scoped work; lead with prime-contract track record.")

    bridge = opp.get("institutional_bridge") or {}
    if bridge.get("name"):
        return _route("INSTITUTIONAL_BRIDGE", org,
                      target=bridge.get("name"),
                      rationale=f"Active partnership ({bridge.get('detail') or bridge.get('name')}) bridges the "
                                "candidate's own affiliations into the employer's org — a warm, credible intro.",
                      action="Ask the bridge (partnership office / shared program) for an intro to the hiring org.")

    if opp.get("is_defense") and networks:
        return _route("DEFENSE_NETWORK", org,
                      target=f"{org} defense-program contacts",
                      rationale=f"Defense/aerospace employer; the candidate's network ({', '.join(sorted(networks))}) "
                                "overlaps — a warm intro from someone who briefed or worked the same programs.",
                      action="Ask a DARPA/program contact for a warm intro; reference shared programs/stakeholders.")

    alums = [a for a in (opp.get("alumni") or []) if str(a.get("school", "")).lower() in schools]
    if alums:
        a = alums[0]
        return _route("ALUMNI_REFERRAL", org,
                      target=a.get("name"),
                      rationale=f"{a.get('name')} ({a.get('school')} alum) is inside {org} — the referral path that "
                                "employers convert on far above cold applicants.",
                      action="Ask the alum for a referral (many firms pay referral bonuses); attach the tailored resume.")

    hm = opp.get("hiring_manager") or {}
    if hm.get("name"):
        return _route("HIRING_MANAGER_DIRECT", org,
                      target=hm.get("name"),
                      rationale=f"{hm.get('name')} ({hm.get('role') or 'hiring manager'}) is reachable directly — a "
                                "targeted note beats a résumé in the ATS pile.",
                      action="Direct, specific outreach to the hiring manager; no cold form first.")

    return _route("COLD_APPLY_LONGSHOT", org,
                  target=f"{org} ATS",
                  rationale="No recognition route found. A cold application is ~1/500 regardless of geography or "
                            "résumé polish — deprioritize versus opportunities with a warm route.",
                  action="Cold apply only if nothing better; keep the résumé ATS-keyword-optimized. Long shot.")


def _route(route_type: str, org: str, *, target: str, rationale: str, action: str) -> dict[str, Any]:
    return {
        "organization": org,
        "route_type": route_type,
        "target": target,
        "rationale": rationale,
        "action": action,
        "recognition_score": _recognition_score(route_type),
        "is_cold_longshot": route_type == "COLD_APPLY_LONGSHOT",
    }


def agentic_evidence(opp: dict[str, Any], search_fn: SearchFn, extract_fn: ExtractFn) -> dict[str, Any]:
    """Gather recognition evidence for one opportunity via search + an agentic
    extraction pass. Returns evidence keys in the shape classify_route reads.
    Any failure yields empty evidence (falls through to a safe route), never a
    fabricated one."""
    org = str(opp.get("organization") or "").strip()
    title = str(opp.get("title") or "")
    rows: list[dict[str, Any]] = []
    for query in (f"{org} founder CEO funding startup", f"{org} {title} engineering manager LinkedIn"):
        try:
            rows.extend((search_fn(query) or [])[:5])
        except Exception:  # noqa: BLE001
            continue
    if not rows:
        return {}
    packed = "\n".join(f"- {r.get('title','')} :: {r.get('description','')}" for r in rows[:10])
    try:
        raw = extract_fn(f"{_EXTRACT_INSTRUCTION}\n\nEmployer: {org}\nRole: {title}\nResults:\n{packed}")
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001 - a bad extraction is empty evidence, never invented
        return {}
    ev: dict[str, Any] = {}
    if data.get("is_defense_aerospace"):
        ev["is_defense"] = True
    fn = data.get("founder_name")
    if data.get("is_founder_led_startup") and isinstance(fn, str) and fn.strip() \
            and fn.strip().lower() not in org.lower():
        ev["founder"] = {"name": fn.strip(), "reachable": True,
                         "domain_aware": bool(data.get("founder_domain_aware")),
                         "verify_before_outreach": True}
    hm = data.get("hiring_manager_name")
    if isinstance(hm, str) and hm.strip():
        ev["hiring_manager"] = {"name": hm.strip(), "role": title, "verify_before_outreach": True}
    return ev


def route_opportunity(opp: dict[str, Any], profile: dict[str, Any],
                      search_fn: SearchFn, extract_fn: ExtractFn) -> dict[str, Any]:
    """Automatic per-opportunity recognition route: agentic evidence, then classify."""
    enriched = {**opp, **agentic_evidence(opp, search_fn, extract_fn)}
    return {**enriched, "recognition_route": classify_route(enriched, profile)}


def rank_by_recognition(opps: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach the recognition route to each opportunity and sort by reachability
    of a human who recognizes the candidate's value — cold long-shots sink."""
    routed = [{**o, "recognition_route": classify_route(o, profile)} for o in opps]
    routed.sort(key=lambda o: (-o["recognition_route"]["recognition_score"],
                               o.get("organization", "")))
    return routed
