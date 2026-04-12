#!/usr/bin/env python3
"""
/match-requirement orchestrator

Compares datalake requirements to SPARTA controls (NIST, ISO, SPARTA) via:
1. /extract-controls → find candidate controls
2. /create-evidence-case → validate requirement AND each control
3. /lean4-prove → determine relationship type for comparable pairs

This is a thin orchestrator — all logic lives in the composed skills.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

# Skill paths
SKILLS_ROOT = Path("/home/graham/.claude/skills")
EXTRACT_CONTROLS = SKILLS_ROOT / "extract-controls"
CREATE_EVIDENCE_CASE = SKILLS_ROOT / "create-evidence-case"
LEAN4_PROVE = SKILLS_ROOT / "lean4-prove"
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"

# Applicable frameworks (modal obligation structure only)
APPLICABLE_FRAMEWORKS = {"NIST", "SPARTA", "ISO"}

# Obligation frame extraction prompt (designed via /prompt-lab principles)
OBLIGATION_FRAME_PROMPT = """Extract the obligation frame from this {source_type} text. Return a JSON object with these fields:

- actor: who must perform the action (e.g., "the system", "the organization", "the operator")
- action: the verb describing what must be done (e.g., "implement", "verify", "protect")
- object: what the action applies to - be specific, include the full scope
- modality: the obligation strength - one of: "shall" (mandatory), "must" (mandatory), "should" (recommended), "may" (optional), "prohibited" (forbidden)
- conditions: array of preconditions or contexts when this applies (e.g., ["when processing CUI", "during flight operations"])
- parameters: key parameters with thresholds (e.g., {{"timeout_seconds": 30, "key_length_bits": 256}})
- verification_method: how compliance can be verified (e.g., "audit log review", "automated testing", "manual inspection")

TEXT:
{text}

Return ONLY valid JSON, no markdown fences."""


@dataclass
class MatchResult:
    """Result of matching a requirement to controls."""
    chunk_key: str
    requirement_text: str
    requirement_valid: bool
    requirement_case_id: Optional[str] = None
    candidate_controls: list[str] = field(default_factory=list)
    comparable_controls: list[str] = field(default_factory=list)
    excluded_controls: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    technique_family: Optional[str] = None
    matched_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chunk_key": self.chunk_key,
            "requirement_text": self.requirement_text[:200] + "..." if len(self.requirement_text) > 200 else self.requirement_text,
            "requirement_valid": self.requirement_valid,
            "requirement_case_id": self.requirement_case_id,
            "candidate_controls": self.candidate_controls,
            "comparable_controls": self.comparable_controls,
            "excluded_controls": self.excluded_controls,
            "relationships": self.relationships,
            "technique_family": self.technique_family,
            "matched_at": self.matched_at,
            "error": self.error,
        }


def memory_request(endpoint: str, payload: dict, timeout: int = 30) -> dict:
    """Make request to memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        resp = client.post(endpoint, json=payload)
        resp.raise_for_status()
        return resp.json()


def load_chunk(chunk_key: str) -> dict:
    """Load requirement chunk from ArangoDB."""
    # Extract just the key part if full path given
    key = chunk_key.split("/")[-1] if "/" in chunk_key else chunk_key

    result = memory_request("/recall/by-keys", {
        "collection": "datalake_chunks",
        "keys": [key],
    })

    documents = result.get("documents", [])
    if not documents:
        raise ValueError(f"Chunk not found: {chunk_key}")

    return documents[0]


def run_extract_controls(text: str) -> list[dict]:
    """Run /extract-controls on text to find candidate controls."""
    cmd = [
        str(EXTRACT_CONTROLS / "run.sh"),
        "extract",
        "--text", text,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        logger.error(f"extract-controls failed: {result.stderr}")
        return []

    try:
        output = json.loads(result.stdout)
        return output.get("controls", [])
    except json.JSONDecodeError:
        logger.error(f"Failed to parse extract-controls output: {result.stdout[:500]}")
        return []


def run_evidence_case(question: str, context: dict) -> dict:
    """Run /create-evidence-case to validate a claim."""
    # Use the runner.py programmatic interface
    cmd = [
        "uv", "run", "--project", str(CREATE_EVIDENCE_CASE),
        "python", str(CREATE_EVIDENCE_CASE / "runner.py"),
        "validate",
        "--question", question,
        "--context", json.dumps(context),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.warning(f"create-evidence-case returned non-zero: {result.stderr[:500]}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Fallback: try to extract verdict from output
        if "SATISFIED" in result.stdout:
            return {"verdict": "SATISFIED"}
        elif "INCONCLUSIVE" in result.stdout:
            return {"verdict": "INCONCLUSIVE"}
        else:
            return {"verdict": "NOT_SATISFIED", "error": result.stderr[:500]}


def run_lean4_prove(requirement_frame: dict, control_frame: dict) -> dict:
    """Run /lean4-prove to determine relationship between frames."""
    # Format the comparison theorem
    theorem = f"""
    Given requirement obligation:
      actor: {requirement_frame.get('actor', 'the system')}
      action: {requirement_frame.get('action', 'implement')}
      object: {requirement_frame.get('object', '')}
      modality: {requirement_frame.get('modality', 'shall')}
      conditions: {requirement_frame.get('conditions', [])}

    Given control obligation:
      actor: {control_frame.get('actor', 'the organization')}
      action: {control_frame.get('action', 'implement')}
      object: {control_frame.get('object', '')}
      modality: {control_frame.get('modality', 'shall')}
      conditions: {control_frame.get('conditions', [])}

    Prove the relationship type between these obligations.
    """

    cmd = [
        str(LEAN4_PROVE / "run.sh"),
        "--requirement", theorem,
        "--tactics", "simp,decide,cases",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    try:
        output = json.loads(result.stdout)
        return {
            "success": output.get("success", False),
            "relationship_type": classify_relationship(output),
            "proof_code": output.get("code"),
            "attempts": output.get("attempts", 0),
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "relationship_type": "unknown",
            "error": result.stderr[:500] if result.stderr else "Parse error",
        }


def classify_relationship(lean4_result: dict) -> str:
    """Classify the relationship type from Lean4 proof result."""
    if not lean4_result.get("success"):
        return "unknown"

    code = lean4_result.get("code", "").lower()

    # Simple heuristics based on proof structure
    # In practice, the Lean4 proof should explicitly state the relationship
    if "equivalent" in code or "≃" in code:
        return "equivalent"
    elif "refines" in code or "stronger" in code or ">=" in code:
        return "refines"
    elif "partial" in code or "subset" in code or "<" in code:
        return "partial_coverage"
    elif "conflict" in code or "¬" in code or "not compatible" in code:
        return "conflicts"
    else:
        return "refines"  # Default to refines if proof succeeds


def compute_confidence(
    lean4_result: dict,
    req_frame: dict,
    ctrl_frame: dict,
    extraction_method: str = "scillm",
) -> float:
    """Compute nuanced confidence score from multiple signals.

    Returns float 0.0-1.0 based on:
    - Lean4 proof success/failure (base)
    - Proof complexity (fewer tactics = higher confidence)
    - Frame extraction method (scillm > heuristic)
    - Frame completeness (more fields = higher confidence)
    """
    # Base confidence from proof result
    if not lean4_result.get("success"):
        base = 0.3  # Failed proof starts low
    else:
        base = 0.8  # Successful proof starts high

    # Adjust for proof complexity (more attempts = less confident)
    attempts = lean4_result.get("attempts", 1)
    if attempts <= 1:
        complexity_adj = 0.1
    elif attempts <= 3:
        complexity_adj = 0.05
    else:
        complexity_adj = -0.1  # Many attempts = less confident

    # Adjust for extraction method
    if extraction_method == "scillm":
        extraction_adj = 0.05
    else:
        extraction_adj = -0.1  # Heuristic is less reliable

    # Frame completeness score
    frame_fields = ["actor", "action", "object", "modality", "conditions", "parameters"]
    req_completeness = sum(1 for f in frame_fields if req_frame.get(f)) / len(frame_fields)
    ctrl_completeness = sum(1 for f in frame_fields if ctrl_frame.get(f)) / len(frame_fields)
    completeness_adj = ((req_completeness + ctrl_completeness) / 2 - 0.5) * 0.2

    # Compute final confidence, clamped to [0, 1]
    confidence = base + complexity_adj + extraction_adj + completeness_adj
    return max(0.0, min(1.0, confidence))


def extract_obligation_frame(text: str, source_type: str) -> dict:
    """Extract obligation frame from requirement or control text via /scillm.

    Uses structured JSON extraction for accurate obligation parsing.
    Falls back to heuristic extraction if /scillm unavailable.
    """
    # Try /scillm structured extraction first
    try:
        prompt = OBLIGATION_FRAME_PROMPT.format(source_type=source_type, text=text[:2000])

        resp = httpx.post(
            SCILLM_URL,
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]
        frame = json.loads(content)

        # Validate required fields
        frame.setdefault("actor", "the system")
        frame.setdefault("action", "implement")
        frame.setdefault("object", text[:500])
        frame.setdefault("modality", "shall")
        frame.setdefault("conditions", [])
        frame.setdefault("parameters", {})
        frame.setdefault("verification_method", "")
        frame["source_type"] = source_type
        frame["extraction_method"] = "scillm"

        logger.debug(f"Extracted frame via /scillm: actor={frame['actor']}, action={frame['action']}")
        return frame

    except Exception as e:
        logger.warning(f"scillm extraction failed, using heuristic fallback: {e}")
        return _extract_obligation_frame_heuristic(text, source_type)


def _extract_obligation_frame_heuristic(text: str, source_type: str) -> dict:
    """Heuristic fallback for obligation frame extraction.

    Used when /scillm is unavailable. Less accurate but always works.
    """
    text_lower = text.lower()

    # Detect modality - find earliest occurrence
    modality = "shall"
    modality_patterns = [
        ("shall not", "prohibited"),
        ("must not", "prohibited"),
        ("prohibited", "prohibited"),
        ("must", "must"),
        ("should not", "should_not"),
        ("should", "should"),
        ("shall", "shall"),
        ("may", "may"),
    ]
    modal_positions = []
    for pattern, modal in modality_patterns:
        pos = text_lower.find(pattern)
        if pos != -1:
            modal_positions.append((pos, modal))
    if modal_positions:
        modal_positions.sort(key=lambda x: x[0])
        modality = modal_positions[0][1]

    # Extract actor with broader patterns
    actor = "the system"
    actor_patterns = [
        ("organization", "the organization"),
        ("operator", "the operator"),
        ("administrator", "the administrator"),
        ("information system", "the information system"),
        ("spacecraft", "the spacecraft"),
        ("ground system", "the ground system"),
        ("mission", "the mission"),
    ]
    for pattern, actor_name in actor_patterns:
        if pattern in text_lower:
            actor = actor_name
            break

    # Extract action - find first verb after modal keyword
    action = "implement"
    action_verbs = [
        "authenticate", "authorize", "encrypt", "implement", "ensure",
        "verify", "audit", "review", "establish", "maintain", "protect",
        "enforce", "configure", "monitor", "log", "validate", "restrict",
        "document", "test", "deploy", "disable", "enable", "require",
    ]
    # Find position of each verb and pick the earliest one
    verb_positions = []
    for verb in action_verbs:
        pos = text_lower.find(verb)
        if pos != -1:
            verb_positions.append((pos, verb))
    if verb_positions:
        verb_positions.sort(key=lambda x: x[0])
        action = verb_positions[0][1]

    # Extract object - use first sentence or clause up to 500 chars
    obj = text[:500]
    if ". " in obj:
        obj = obj.split(". ")[0]

    return {
        "actor": actor,
        "action": action,
        "object": obj,
        "modality": modality,
        "conditions": [],
        "parameters": {},
        "verification_method": "",
        "source_type": source_type,
        "extraction_method": "heuristic",
    }


def shares_technique(req_entities: list, ctrl_entities: list, control_id: str = "") -> tuple[bool, Optional[str]]:
    """Check if requirement and control share a SPARTA technique family.

    Falls back to control family matching if technique_family is not available.
    """
    req_techniques = {e.get("technique_family") for e in req_entities if e.get("technique_family")}
    ctrl_techniques = {e.get("technique_family") for e in ctrl_entities if e.get("technique_family")}

    # Primary: technique_family match
    shared = req_techniques & ctrl_techniques
    if shared:
        return True, list(shared)[0]

    # Fallback 1: Check if control ID maps to a known family
    # SPARTA controls: SV-AC (Access Control), SV-CF (Config), SV-IT (Integrity), etc.
    # NIST controls: AC- (Access Control), SC- (System/Comm), AU- (Audit), etc.
    control_families = {
        "SV-AC": "access_control", "AC-": "access_control",
        "SV-CF": "configuration", "CM-": "configuration",
        "SV-IT": "integrity", "SI-": "integrity",
        "SV-MA": "maintenance", "MA-": "maintenance",
        "SV-AU": "audit", "AU-": "audit",
        "SV-SP": "supply_chain", "SR-": "supply_chain",
        "SC-": "system_comm",
        "IA-": "identification_auth",
        "PE-": "physical",
        "PS-": "personnel",
        "PL-": "planning",
        "RA-": "risk_assessment",
        "CA-": "assessment",
        "SA-": "acquisition",
    }

    ctrl_family = None
    for prefix, family in control_families.items():
        if control_id.upper().startswith(prefix):
            ctrl_family = family
            break

    if ctrl_family:
        # Check if any requirement entity mentions this family domain
        req_text_lower = " ".join(str(e) for e in req_entities).lower()
        family_keywords = {
            "access_control": ["access", "permission", "authorize", "authenticate", "credential"],
            "configuration": ["config", "setting", "parameter", "baseline"],
            "integrity": ["integrity", "tamper", "verify", "hash", "checksum"],
            "maintenance": ["maintenance", "patch", "update", "repair"],
            "audit": ["audit", "log", "monitor", "record", "trail"],
            "supply_chain": ["supply", "vendor", "component", "third-party"],
            "system_comm": ["encrypt", "communication", "boundary", "interface"],
            "identification_auth": ["identity", "authenticate", "credential", "password"],
        }

        if ctrl_family in family_keywords:
            for kw in family_keywords[ctrl_family]:
                if kw in req_text_lower:
                    return True, f"{ctrl_family}_keyword_match"

    # Fallback 2: If both sets empty but entities exist, allow comparison (low confidence)
    if req_entities and ctrl_entities:
        logger.debug(f"No technique/family match, but entities exist - allowing with low confidence")
        return True, "no_technique_fallback"

    return False, None


def persist_edge(
    chunk_key: str,
    control_id: str,
    relationship: dict,
    req_case_id: str,
    ctrl_case_id: str,
    confidence_threshold: float = 0.7,
    extraction_method: str = "heuristic",
    technique_match_type: Optional[str] = None,
) -> tuple[str, str]:
    """Persist result to appropriate collection based on relationship type and confidence.

    Returns (edge_key, collection) tuple.
    """
    edge_key = hashlib.md5(f"{chunk_key}:{control_id}".encode()).hexdigest()[:16]
    rel_type = relationship.get("relationship_type", "unknown")
    confidence = relationship.get("confidence", 1.0 if relationship.get("success") else 0.0)

    base_doc = {
        "_key": edge_key,
        "chunk_key": chunk_key,
        "control_id": control_id,
        "relationship_type": rel_type,
        "confidence": confidence,
        "lean4_status": "proved" if relationship.get("success") else "failed",
        "proof_code": relationship.get("proof_code"),
        "requirement_case_id": req_case_id,
        "control_case_id": ctrl_case_id,
        "matched_at": datetime.now(timezone.utc).isoformat(),
        # Quality indicators for Brandon's review
        "extraction_method": extraction_method,  # scillm or heuristic
        "technique_match_type": technique_match_type,  # technique_family, keyword_match, or fallback
    }

    # Route based on relationship type and confidence
    if rel_type == "conflicts":
        # Conflicts always go to match_conflicts for urgent review
        memory_request("/upsert", {
            "collection": "match_conflicts",
            "documents": [base_doc],
        })
        logger.warning(f"CONFLICT detected: {chunk_key} vs {control_id}")
        return edge_key, "match_conflicts"

    elif rel_type in ("unknown", "partial_coverage") or confidence < confidence_threshold:
        # Low confidence or uncertain → pending review
        base_doc["review_reason"] = (
            f"low_confidence ({confidence:.2f})" if confidence < confidence_threshold
            else f"relationship_{rel_type}"
        )
        memory_request("/upsert", {
            "collection": "pending_review",
            "documents": [base_doc],
        })
        return edge_key, "pending_review"

    else:
        # High confidence match → requirement_control_edges
        edge_doc = {
            **base_doc,
            "_from": f"datalake_chunks/{chunk_key.split('/')[-1]}",
            "_to": f"sparta_controls/{control_id}",
        }
        memory_request("/upsert", {
            "collection": "requirement_control_edges",
            "documents": [edge_doc],
        })
        return edge_key, "requirement_control_edges"


def match_requirement(chunk_key: str, dry_run: bool = False, confidence_threshold: float = 0.7) -> MatchResult:
    """Main orchestration: match a requirement to all applicable controls."""
    result = MatchResult(
        chunk_key=chunk_key,
        requirement_text="",
        requirement_valid=False,
        matched_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        # Step 1: Load requirement
        logger.info(f"Loading chunk: {chunk_key}")
        chunk = load_chunk(chunk_key)
        result.requirement_text = chunk.get("text", chunk.get("content", ""))

        if not result.requirement_text:
            result.error = "Empty requirement text"
            return result

        # Step 2: Find candidate controls
        logger.info("Finding candidate controls via /extract-controls")
        candidates = run_extract_controls(result.requirement_text)
        result.candidate_controls = [c.get("control_id") for c in candidates if c.get("control_id")]

        # Filter to applicable frameworks
        result.candidate_controls = [
            cid for cid in result.candidate_controls
            if any(fw in cid.upper() for fw in APPLICABLE_FRAMEWORKS) or
               cid.startswith("AC-") or cid.startswith("SC-") or  # NIST patterns
               cid.startswith("SV-") or  # SPARTA patterns
               cid.startswith("A.")  # ISO patterns
        ]

        if not result.candidate_controls:
            result.error = "No applicable controls found"
            return result

        logger.info(f"Found {len(result.candidate_controls)} candidate controls")

        # Step 3: Validate requirement via /create-evidence-case
        logger.info("Validating requirement via /create-evidence-case")
        req_case = run_evidence_case(
            question=f"Is this a valid, grounded requirement with clear obligation structure? '{result.requirement_text[:200]}'",
            context={"source": "datalake_chunks", "chunk_key": chunk_key}
        )

        if req_case.get("verdict") != "SATISFIED":
            result.requirement_valid = False
            result.error = f"Requirement failed validation: {req_case.get('verdict')}"
            return result

        result.requirement_valid = True
        result.requirement_case_id = req_case.get("case_id")
        req_entities = req_case.get("entities", [])

        # Step 4: Validate each control (parallel execution)
        logger.info(f"Validating {len(result.candidate_controls)} candidate controls in parallel")
        control_cases = {}

        def validate_control(control_id: str) -> tuple[str, dict]:
            case = run_evidence_case(
                question=f"Is {control_id} a valid, coherent control with clear obligation structure?",
                context={"source": "sparta_controls", "control_id": control_id}
            )
            return control_id, case

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(validate_control, cid): cid for cid in result.candidate_controls}
            for future in as_completed(futures):
                try:
                    control_id, ctrl_case = future.result(timeout=120)
                    control_cases[control_id] = ctrl_case
                except Exception as e:
                    control_id = futures[future]
                    logger.warning(f"Control validation failed for {control_id}: {e}")
                    control_cases[control_id] = {"verdict": "ERROR", "error": str(e)}

        # Step 5: Filter to comparable pairs
        for control_id, ctrl_case in control_cases.items():
            if ctrl_case.get("verdict") != "SATISFIED":
                result.excluded_controls.append({
                    "control_id": control_id,
                    "reason": f"validation_failed: {ctrl_case.get('verdict')}"
                })
                continue

            ctrl_entities = ctrl_case.get("entities", [])
            shares, technique = shares_technique(req_entities, ctrl_entities, control_id)

            if not shares:
                result.excluded_controls.append({
                    "control_id": control_id,
                    "reason": "different_technique"
                })
                continue

            result.comparable_controls.append(control_id)
            if not result.technique_family:
                result.technique_family = technique

        if not result.comparable_controls:
            result.error = "No controls share technique with requirement"
            return result

        logger.info(f"{len(result.comparable_controls)} controls are comparable")

        # Step 6: Lean4 comparison for each comparable control
        logger.info("Running /lean4-prove for relationship classification")
        req_frame = extract_obligation_frame(result.requirement_text, "requirement")
        req_extraction_method = req_frame.get("extraction_method", "heuristic")

        for control_id in result.comparable_controls:
            ctrl_case = control_cases[control_id]
            ctrl_text = ctrl_case.get("control_text", control_id)
            ctrl_frame = extract_obligation_frame(ctrl_text, "control")

            relationship = run_lean4_prove(req_frame, ctrl_frame)

            # Compute nuanced confidence
            confidence = compute_confidence(
                lean4_result=relationship,
                req_frame=req_frame,
                ctrl_frame=ctrl_frame,
                extraction_method=req_extraction_method,
            )
            relationship["confidence"] = confidence

            rel_record = {
                "control_id": control_id,
                "relationship_type": relationship.get("relationship_type", "unknown"),
                "lean4_status": "proved" if relationship.get("success") else "failed",
                "confidence": confidence,
                "extraction_method": req_extraction_method,
            }

            # Step 7: Persist to appropriate collection based on type/confidence
            if not dry_run:
                proof_key, collection = persist_edge(
                    chunk_key=chunk_key,
                    control_id=control_id,
                    relationship=relationship,
                    req_case_id=result.requirement_case_id or "",
                    ctrl_case_id=ctrl_case.get("case_id", ""),
                    confidence_threshold=confidence_threshold,
                    extraction_method=req_extraction_method,
                    technique_match_type=result.technique_family,
                )
                rel_record["proof_key"] = f"{collection}/{proof_key}"
                rel_record["routed_to"] = collection

            result.relationships.append(rel_record)

        logger.info(f"Matched {len(result.relationships)} relationships")

    except Exception as e:
        logger.exception("Match failed")
        result.error = str(e)

    return result


def cmd_match(args):
    """Handle match command."""
    if not args.chunk_key:
        print("Error: --chunk-key required", file=sys.stderr)
        sys.exit(1)

    result = match_requirement(
        args.chunk_key,
        dry_run=args.dry_run,
        confidence_threshold=args.confidence_threshold,
    )
    print(json.dumps(result.to_dict(), indent=2))

    if result.error:
        sys.exit(1)


def cmd_batch(args):
    """Handle batch command."""
    # Query proof_jobs for pending jobs
    try:
        result = memory_request("/list", {
            "collection": "proof_jobs",
            "filters": {"status": "pending"},
            "limit": args.limit,
        })

        jobs = result.get("items", [])
        logger.info(f"Found {len(jobs)} pending jobs")

        for job in jobs:
            chunk_key = job.get("requirement_chunk")
            if not chunk_key:
                continue

            logger.info(f"Processing: {chunk_key}")
            match_result = match_requirement(
                chunk_key,
                dry_run=args.dry_run,
                confidence_threshold=args.confidence_threshold,
            )

            # Update job status
            if not args.dry_run:
                status = "completed" if not match_result.error else "failed"
                memory_request("/upsert", {
                    "collection": "proof_jobs",
                    "documents": [{
                        "_key": job.get("_key"),
                        "status": status,
                        "result": match_result.to_dict(),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }],
                })

            print(json.dumps(match_result.to_dict()))

    except Exception as e:
        logger.exception("Batch processing failed")
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_coverage(args):
    """Handle coverage command."""
    try:
        # Count edges by relationship type
        result = memory_request("/query", {
            "aql": """
                FOR e IN requirement_control_edges
                COLLECT rel = e.relationship_type WITH COUNT INTO cnt
                SORT cnt DESC
                RETURN {relationship_type: rel, count: cnt}
            """,
            "bind_vars": {},
        })

        print("Relationship Coverage:")
        print("-" * 40)
        for row in result.get("results", []):
            print(f"  {row['relationship_type']}: {row['count']}")

        # Count by framework if specified
        if args.framework:
            result = memory_request("/query", {
                "aql": """
                    FOR e IN requirement_control_edges
                    FILTER CONTAINS(UPPER(e._to), @framework)
                    COLLECT rel = e.relationship_type WITH COUNT INTO cnt
                    RETURN {relationship_type: rel, count: cnt}
                """,
                "bind_vars": {"framework": args.framework.upper()},
            })

            print(f"\n{args.framework} Framework:")
            print("-" * 40)
            for row in result.get("results", []):
                print(f"  {row['relationship_type']}: {row['count']}")

    except Exception as e:
        logger.exception("Coverage query failed")
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_review_queue(args):
    """Handle review-queue command."""
    try:
        # Query pending_review and match_conflicts
        pending = memory_request("/query", {
            "aql": f"""
                FOR d IN pending_review
                FILTER d._key != "_init"
                SORT d.matched_at DESC
                LIMIT {args.limit}
                RETURN d
            """,
            "bind_vars": {},
        })

        conflicts = memory_request("/query", {
            "aql": """
                FOR d IN match_conflicts
                FILTER d._key != "_init"
                SORT d.matched_at DESC
                LIMIT 20
                RETURN d
            """,
            "bind_vars": {},
        })

        pending_items = pending.get("results", []) if isinstance(pending, dict) else pending
        conflict_items = conflicts.get("results", []) if isinstance(conflicts, dict) else conflicts

        if args.export:
            # Export to CSV with quality indicators
            import csv
            with open(args.export, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "type", "chunk_key", "control_id", "relationship_type",
                    "confidence", "extraction_method", "technique_match_type",
                    "review_reason", "matched_at"
                ])
                for item in conflict_items:
                    writer.writerow([
                        "CONFLICT",
                        item.get("chunk_key", ""),
                        item.get("control_id", ""),
                        item.get("relationship_type", ""),
                        item.get("confidence", ""),
                        item.get("extraction_method", "unknown"),
                        item.get("technique_match_type", ""),
                        "",
                        item.get("matched_at", ""),
                    ])
                for item in pending_items:
                    writer.writerow([
                        "PENDING",
                        item.get("chunk_key", ""),
                        item.get("control_id", ""),
                        item.get("relationship_type", ""),
                        item.get("confidence", ""),
                        item.get("extraction_method", "unknown"),
                        item.get("technique_match_type", ""),
                        item.get("review_reason", ""),
                        item.get("matched_at", ""),
                    ])
            print(f"Exported {len(conflict_items)} conflicts + {len(pending_items)} pending to {args.export}")
        else:
            # Print to console
            if conflict_items:
                print(f"\n{'='*60}")
                print(f"CONFLICTS ({len(conflict_items)}) - Require immediate attention")
                print(f"{'='*60}")
                for item in conflict_items:
                    print(f"  {item.get('chunk_key', '?')[:30]} <-> {item.get('control_id', '?')}")

            print(f"\n{'='*60}")
            print(f"PENDING REVIEW ({len(pending_items)})")
            print(f"{'='*60}")
            if not pending_items:
                print("  No items pending review.")
            else:
                for item in pending_items:
                    reason = item.get("review_reason", "unknown")
                    print(f"  {item.get('chunk_key', '?')[:30]} <-> {item.get('control_id', '?')} ({reason})")

            print(f"\nTotal: {len(conflict_items)} conflicts, {len(pending_items)} pending")

    except Exception as e:
        logger.exception("Review queue query failed")
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="/match-requirement orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # match command
    match_parser = subparsers.add_parser("match", help="Match a single requirement")
    match_parser.add_argument("--chunk-key", required=True, help="datalake_chunks key")
    match_parser.add_argument("--dry-run", action="store_true", help="Don't persist results")
    match_parser.add_argument("--confidence-threshold", type=float, default=0.7,
                              help="Confidence threshold for auto-accept (default: 0.7)")
    match_parser.set_defaults(func=cmd_match)

    # batch command
    batch_parser = subparsers.add_parser("batch", help="Process batch from queue")
    batch_parser.add_argument("--limit", type=int, default=10, help="Max jobs to process")
    batch_parser.add_argument("--priority", type=int, help="Filter by priority")
    batch_parser.add_argument("--dry-run", action="store_true", help="Don't persist results")
    batch_parser.add_argument("--confidence-threshold", type=float, default=0.7,
                              help="Confidence threshold for auto-accept (default: 0.7)")
    batch_parser.set_defaults(func=cmd_batch)

    # coverage command
    coverage_parser = subparsers.add_parser("coverage", help="Show matching statistics")
    coverage_parser.add_argument("--framework", help="Filter by framework (NIST, SPARTA, ISO)")
    coverage_parser.set_defaults(func=cmd_coverage)

    # review-queue command
    review_parser = subparsers.add_parser("review-queue", help="List pending reviews")
    review_parser.add_argument("--limit", type=int, default=50, help="Max items to show")
    review_parser.add_argument("--export", type=str, help="Export to CSV file")
    review_parser.set_defaults(func=cmd_review_queue)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
