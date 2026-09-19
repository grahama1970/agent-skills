#!/usr/bin/env python3
"""Closed-set local diagram-template selection backed by Jev v2 receipts."""
from __future__ import annotations

import hashlib
import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RequirementsPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(min_length=1)
    view: str = Field(min_length=1)
    data: dict[str, Any]
    steps: list[str] = Field(min_length=1)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    asset_path: str = Field(min_length=1)
    views: list[str] = Field(min_length=1)
    required_data: list[str] = Field(default_factory=list)
    min_steps: int = Field(default=1, ge=1)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["diagram_template_catalog.v1"] = Field(alias="schema")
    templates: list[CatalogEntry] = Field(min_length=1)


class JevAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["choice"]
    choice: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    score: None = None
    noul: None = None
    probabilities: dict[str, float] | None = None
    legend: None = None


class JevReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["jev.decision.v2"]
    request_id: str
    status: Literal["accepted", "abstain", "error"]
    reason: str
    request_hash: str | None = None
    state_hash: str | None = None
    questions_hash: str | None = None
    policy_hash: str
    requested_model: str
    resolved_model: str | None = None
    answers: dict[str, JevAnswer] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    elapsed_ms: float = Field(ge=0)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    retry_after_ms: int | None = Field(default=None, ge=0)


class SelectionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["diagram_template_selection_receipt.v2"] = Field("diagram_template_selection_receipt.v2", alias="schema")
    mode: Literal["live", "replay"]
    requirements_hash: str
    candidate_catalog_hash: str
    eligible_template_ids: list[str]
    eligible_asset_paths: list[str]
    selected_template_id: str | None = None
    selected_asset_path: str | None = None
    jev_status: Literal["accepted", "abstain", "error"]
    jev_confidence: float | None = Field(default=None, ge=0, le=1)
    fallback: str | None = None
    jev_request_hash: str | None
    jev_state_hash: str | None
    jev_questions_hash: str | None
    jev_resolved_model: str | None


def _stable_bytes(value: Any) -> bytes:
    if value is None: return b"z"
    if isinstance(value, bool): return b"t" if value else b"f"
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or abs(value) > 9007199254740991: raise ValueError("number outside Jev hash domain")
        return b"d" + struct.pack(">d", float(value) if value else 0.0).hex().encode()
    if isinstance(value, str):
        raw = value.encode("utf-8", errors="strict"); return b"s" + str(len(raw)).encode() + b":" + raw
    if isinstance(value, list): return b"[" + b"".join(_stable_bytes(v) for v in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(k, str) or k in {"__proto__", "prototype", "constructor"} for k in value): raise ValueError("invalid Jev hash key")
        return b"{" + b"".join(_stable_bytes(k) + _stable_bytes(value[k]) for k in sorted(value, key=lambda k: k.encode())) + b"}"
    raise ValueError("non-JSON Jev hash value")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def jev_hash(value: Any) -> str:
    return hashlib.sha256(_stable_bytes(value)).hexdigest()


def load_catalog(path: Path) -> Catalog:
    return Catalog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def eligible_entries(packet: RequirementsPacket, catalog: Catalog, repo_root: Path) -> list[CatalogEntry]:
    return sorted((entry for entry in catalog.templates if packet.view in entry.views and len(packet.steps) >= entry.min_steps and all(key in packet.data for key in entry.required_data) and (repo_root / entry.asset_path).is_file()), key=lambda entry: entry.id)


def selection_state(packet: RequirementsPacket, entries: list[CatalogEntry]) -> dict[str, Any]:
    return {"schema": "diagram_template_jev_state.v1", "requirements": packet.model_dump(), "eligible_templates": [entry.model_dump() for entry in entries]}


def load_questions(path: Path, entries: list[CatalogEntry]) -> dict[str, Any]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    expected = [entry.id for entry in entries] + ["ABSTAIN"]
    choice = questions.get("template_choice") if isinstance(questions, dict) else None
    if not isinstance(choice, dict) or choice.get("type") != "choice" or list((choice.get("criteria") or {}).keys()) != expected:
        raise ValueError("questions.template_choice options must exactly equal eligible template IDs plus ABSTAIN")
    return questions


def receipt_from_jev(packet: RequirementsPacket, catalog: Catalog, questions: dict[str, Any], raw: dict[str, Any], repo_root: Path, mode: Literal["live", "replay"]) -> SelectionReceipt:
    entries = eligible_entries(packet, catalog, repo_root)
    state = selection_state(packet, entries)
    receipt = JevReceipt.model_validate(raw)
    if receipt.state_hash != jev_hash(state) or receipt.questions_hash != jev_hash(questions):
        raise ValueError("Jev receipt does not bind the deterministic state/questions")
    request = {"state": state, "model": "jev-latest", "questions": questions}
    if receipt.request_hash != jev_hash(request):
        raise ValueError("Jev receipt does not bind the deterministic request")
    selected: CatalogEntry | None = None
    confidence: float | None = None
    if receipt.status == "accepted":
        answer = receipt.answers.get("template_choice")
        if answer is None or answer.choice == "ABSTAIN" or answer.choice not in {entry.id for entry in entries}:
            raise ValueError("accepted Jev receipt must choose one eligible template ID")
        selected = next(entry for entry in entries if entry.id == answer.choice)
        confidence = answer.confidence
    elif receipt.status not in {"abstain", "error"}:
        raise ValueError("unsupported Jev receipt status")
    return SelectionReceipt(
        mode=mode, requirements_hash=canonical_hash(packet.model_dump()), candidate_catalog_hash=canonical_hash(catalog.model_dump(by_alias=True)),
        eligible_template_ids=[entry.id for entry in entries], eligible_asset_paths=[entry.asset_path for entry in entries],
        selected_template_id=selected.id if selected else None, selected_asset_path=selected.asset_path if selected else None,
        jev_status=receipt.status, jev_confidence=confidence, fallback=receipt.reason if selected is None else None,
        jev_request_hash=receipt.request_hash, jev_state_hash=receipt.state_hash, jev_questions_hash=receipt.questions_hash, jev_resolved_model=receipt.resolved_model,
    )


def invoke_jev(packet: RequirementsPacket, catalog: Catalog, questions_path: Path, repo_root: Path) -> SelectionReceipt:
    entries = eligible_entries(packet, catalog, repo_root)
    questions = load_questions(questions_path, entries)
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp); state_path = temp / "state.json"; raw_path = temp / "jev.json"
        state_path.write_text(json.dumps(selection_state(packet, entries)), encoding="utf-8")
        result = subprocess.run([str(repo_root / "skills/jev/run.sh"), "ask", "--state", f"@{state_path}", "--questions", f"@{questions_path}", "--allow-egress", "--data-class", "public", "--out", raw_path], capture_output=True, text=True, timeout=120)
        if not raw_path.exists(): raise ValueError(result.stderr[-2000:] or "Jev produced no receipt")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    return receipt_from_jev(packet, catalog, questions, raw, repo_root, "live")


def validate_receipt(receipt_path: Path, packet_path: Path, catalog_path: Path, repo_root: Path) -> SelectionReceipt:
    receipt = SelectionReceipt.model_validate(json.loads(receipt_path.read_text(encoding="utf-8")))
    packet = RequirementsPacket.model_validate(json.loads(packet_path.read_text(encoding="utf-8"))); catalog = load_catalog(catalog_path)
    entries = eligible_entries(packet, catalog, repo_root)
    if receipt.requirements_hash != canonical_hash(packet.model_dump()) or receipt.candidate_catalog_hash != canonical_hash(catalog.model_dump(by_alias=True)):
        raise ValueError("receipt does not bind requirements/catalog")
    if receipt.eligible_template_ids != [entry.id for entry in entries] or receipt.eligible_asset_paths != [entry.asset_path for entry in entries]:
        raise ValueError("receipt eligible candidates do not match deterministic eligibility")
    if receipt.jev_status != "accepted" or receipt.selected_template_id is None or receipt.selected_asset_path is None:
        raise ValueError("governed render/push requires an accepted Jev selection")
    if receipt.selected_template_id not in receipt.eligible_template_ids or receipt.selected_asset_path not in receipt.eligible_asset_paths:
        raise ValueError("receipt selection is ineligible")
    if not (repo_root / receipt.selected_asset_path).is_file(): raise ValueError("receipt selected asset does not exist locally")
    return receipt
