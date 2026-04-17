"""Pydantic schemas for two-stage relationship QRA validation.

Two-stage architecture:
- Stage A (Gate): EligiblePair, GateResult — decide eligibility
- Stage B (Generate): QRAPair, QRAResult — write prose for approved pairs
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Enums ---

class TargetFramework(str, Enum):
    SPARTA = "SPARTA"
    MITRE_ATT_CK = "MITRE_ATT&CK"
    CAPEC = "CAPEC"


class PairType(str, Enum):
    relationship = "relationship"
    risk_linkage = "risk_linkage"
    control_relevance = "control_relevance"
    adversary_relevance = "adversary_relevance"
    mitigation_gap = "mitigation_gap"


class ActionableFor(str, Enum):
    threat_assessment = "threat_assessment"
    compliance_mapping = "compliance_mapping"
    audit = "audit"
    gap_analysis = "gap_analysis"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"


class BridgeStrength(str, Enum):
    strong = "strong"
    adequate = "adequate"


class BridgeType(str, Enum):
    terminal = "terminal"
    hop = "hop"


class DuplicateRisk(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class GateStatus(str, Enum):
    eligible_pairs_found = "eligible_pairs_found"
    no_eligible_pairs = "no_eligible_pairs"
    no_cwe_record = "no_cwe_record"
    no_targets = "no_targets"


class EvidenceSource(str, Enum):
    cwe = "cwe"
    target = "target"


class BridgeSource(str, Enum):
    crosswalk_chains = "crosswalk_chains"
    glossary = "glossary"
    direct_payload_match = "direct_payload_match"


# --- Stage A: Gate schemas ---

class EligiblePair(BaseModel):
    """A CWE-to-target pair that passed the evidence gate."""
    model_config = ConfigDict(extra="forbid")

    cwe_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_framework: TargetFramework
    bridge_strength: BridgeStrength
    bridge_type: BridgeType
    primary_pair_type: PairType
    alternate_pair_types: list[PairType] = Field(default_factory=list)
    grounding_rationale: str = Field(min_length=1)
    duplicate_risk: DuplicateRisk = Field(default=DuplicateRisk.none)
    cwe_quote: str = Field(min_length=1)
    target_quote: str = Field(min_length=1)
    bridge_quotes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cwe_id(self) -> "EligiblePair":
        if not self.cwe_id.upper().startswith("CWE-"):
            raise ValueError("cwe_id must start with CWE-")
        return self


class RejectedPair(BaseModel):
    """A CWE-to-target pair that was rejected by the gate."""
    model_config = ConfigDict(extra="forbid")

    cwe_id: str
    target_id: str
    rejection_reason: str = Field(min_length=1)


class GateDiagnosis(BaseModel):
    """Diagnostic summary from the evidence gate."""
    model_config = ConfigDict(extra="forbid")

    cwe_record_ok: bool
    target_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    high_duplicate_risk_count: int = Field(ge=0, default=0)
    overall_status: GateStatus


class GateResult(BaseModel):
    """Output from Stage A: evidence gate."""
    model_config = ConfigDict(extra="forbid")

    eligible_pairs: list[EligiblePair] = Field(default_factory=list)
    rejected_pairs: list[RejectedPair] = Field(default_factory=list)
    diagnosis: GateDiagnosis


# --- Stage B: QRA generation schemas ---

class EvidenceQuote(BaseModel):
    """A verbatim quote from the payload."""
    model_config = ConfigDict(extra="forbid")

    source: EvidenceSource
    id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class BridgeEvidence(BaseModel):
    """Bridge evidence connecting CWE to target."""
    model_config = ConfigDict(extra="forbid")

    source: BridgeSource
    quote: str = Field(min_length=1)


class RelationshipQRAPair(BaseModel):
    """A generated relationship QRA pair with full evidence."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    answer: str = Field(min_length=1)

    source_framework: Literal["CWE"]
    source_id: str = Field(min_length=1)
    target_framework: TargetFramework
    target_id: str = Field(min_length=1)

    evidence_quotes: list[EvidenceQuote] = Field(min_length=2)
    bridge_evidence: list[BridgeEvidence] = Field(default_factory=list)

    pair_type: PairType
    actionable_for: ActionableFor
    confidence: Confidence

    @model_validator(mode="after")
    def validate_pair(self) -> "RelationshipQRAPair":
        if not self.source_id.upper().startswith("CWE-"):
            raise ValueError("source_id must start with CWE-")

        has_cwe_quote = any(q.source == EvidenceSource.cwe for q in self.evidence_quotes)
        has_target_quote = any(q.source == EvidenceSource.target for q in self.evidence_quotes)

        if not has_cwe_quote:
            raise ValueError("evidence_quotes must include a CWE quote")
        if not has_target_quote:
            raise ValueError("evidence_quotes must include a target quote")

        # Check question contains at least one identifier
        q_upper = self.question.upper()
        has_id = any(marker in q_upper for marker in ["CWE-", "CAPEC-", "IA-", "SV-", "T1"])
        if not has_id:
            raise ValueError("question must include at least one explicit identifier")

        return self


class EmptyDiagnosis(BaseModel):
    """Diagnosis when no QRAs could be generated."""
    model_config = ConfigDict(extra="forbid")

    missing_evidence: list[str] = Field(default_factory=list)
    suggestion: str = Field(min_length=1)
    deflection: str = Field(default="")


class RelationshipQRAResult(BaseModel):
    """Output from Stage B: QRA generation (success case)."""
    model_config = ConfigDict(extra="forbid")

    pairs: list[RelationshipQRAPair] = Field(min_length=1)


class EmptyRelationshipQRAResult(BaseModel):
    """Output from Stage B: QRA generation (empty case)."""
    model_config = ConfigDict(extra="forbid")

    pairs: list[RelationshipQRAPair] = Field(default_factory=list, max_length=0)
    reason: str = Field(min_length=1)
    diagnosis: EmptyDiagnosis


# --- Validation helpers ---

def validate_gate_response(data: dict) -> GateResult:
    """Validate Stage A gate response."""
    return GateResult.model_validate(data)


def validate_qra_response(data: dict) -> RelationshipQRAResult | EmptyRelationshipQRAResult:
    """Validate Stage B QRA response."""
    if data.get("pairs"):
        return RelationshipQRAResult.model_validate(data)
    else:
        return EmptyRelationshipQRAResult.model_validate(data)


def validate_evidence_payload(payload: dict) -> list[str]:
    """Validate evidence case payload structure. Returns list of errors."""
    errors = []

    # Check cwe_record
    cwe = payload.get("cwe_record") or payload.get("capec_record")
    if not cwe:
        errors.append("missing cwe_record or capec_record")
    elif not cwe.get("description"):
        errors.append("cwe_record missing description")

    # Check target_records
    targets = payload.get("target_records", [])
    if not targets:
        errors.append("missing or empty target_records")
    else:
        for i, t in enumerate(targets):
            if not t.get("control_id"):
                errors.append(f"target_records[{i}] missing control_id")
            if not t.get("framework"):
                errors.append(f"target_records[{i}] missing framework")
            if not t.get("description"):
                errors.append(f"target_records[{i}] missing description")

    return errors


def normalize_quote(text: str) -> str:
    """Light normalization for exact-span checks."""
    import re
    text = text.strip().lower()
    text = text.replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def validate_grounding_against_payload(
    qra: RelationshipQRAPair,
    payload: dict,
) -> list[str]:
    """Verify that QRA quotes actually appear in the payload. Returns list of errors."""
    errors = []

    # Build searchable text from payload
    cwe = payload.get("cwe_record") or payload.get("capec_record") or {}
    cwe_text = normalize_quote(" ".join([
        cwe.get("description", ""),
        cwe.get("extended_description", ""),
    ]))

    target_texts = {}
    for t in payload.get("target_records", []):
        tid = t.get("control_id", "")
        target_texts[tid] = normalize_quote(t.get("description", ""))

    glossary_text = normalize_quote(" ".join([
        g.get("description", "") for g in payload.get("glossary", [])
    ]))

    crosswalk_text = normalize_quote(" ".join([
        h.get("description", "")
        for c in payload.get("crosswalk_chains", [])
        for h in c.get("hops", [])
    ]))

    all_text = cwe_text + " " + glossary_text + " " + crosswalk_text

    # Check evidence quotes
    for eq in qra.evidence_quotes:
        quote_norm = normalize_quote(eq.quote)
        if eq.source == EvidenceSource.cwe:
            if quote_norm not in cwe_text and quote_norm not in glossary_text:
                errors.append(f"CWE quote not found in payload: {eq.quote[:50]}...")
        elif eq.source == EvidenceSource.target:
            target_text = target_texts.get(eq.id, "")
            if quote_norm not in target_text and quote_norm not in glossary_text:
                errors.append(f"Target quote not found in payload: {eq.quote[:50]}...")

    # Check bridge evidence
    for be in qra.bridge_evidence:
        if normalize_quote(be.quote) not in all_text:
            errors.append(f"Bridge quote not found in payload: {be.quote[:50]}...")

    return errors
