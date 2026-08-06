"""ChangeSet v1: typed edit proposals with human confirmation tokens (#1232).

The agent edit API is Pydantic-discriminated command objects inside an atomic
EditProposal (roundtable decided 2-1 against raw JSON-Patch: generic patches
produce schema-valid changes that bypass semantic invariants). Verbs:
simulate_proposal (dry-run every op through the real pipeline), apply_proposal
(atomic: all ops or none, CAS-pinned to base_revision), history. Governance-
relevant ops (delete, hidden, layout) require a single-use, expiring
confirmation token minted ONLY by an explicit human action and bound to
(proposal digest, base_revision) — an agent cannot commit governance ops by
convention-breaking. Layout-free cosmetic proposals auto-pass under the
declared policy. Failure modes: stale revision, replayed/expired/cross-
proposal tokens, and validation failures all refuse with nothing written.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

TOKEN_FILE = ".confirmation_tokens.json"
TOKEN_TTL_SECONDS = 600
GOVERNANCE_FIELDS = {"hidden", "layout"}
GOVERNANCE_DECK_OPS = {"delete"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetSlideField(_Strict):
    op: Literal["set_field"] = "set_field"
    slide_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: str = ""


class DeckStructureOp(_Strict):
    op: Literal["deck_op"] = "deck_op"
    deck_op: Literal["add_after", "duplicate", "delete", "move_left", "move_right", "move_to"]
    slide_id: str = Field(min_length=1)
    target_order: int | None = None


EditOp = SetSlideField | DeckStructureOp


class EditProposal(_Strict):
    schema_: Literal["pitchdeck.edit_proposal.v1"] = Field(
        default="pitchdeck.edit_proposal.v1", alias="schema"
    )
    base_revision: int
    ops: list[EditOp] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)

    def digest(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def is_governance(self) -> bool:
        for op in self.ops:
            if isinstance(op, DeckStructureOp) and op.deck_op in GOVERNANCE_DECK_OPS:
                return True
            if isinstance(op, SetSlideField) and op.field in GOVERNANCE_FIELDS:
                return True
        return False


def _token_store(bundle_dir: Path) -> dict:
    path = bundle_dir / TOKEN_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def _write_tokens(bundle_dir: Path, store: dict) -> None:
    (bundle_dir / TOKEN_FILE).write_text(json.dumps(store, indent=1), encoding="utf-8")


def mint_confirmation_token(bundle_dir: Path, proposal: EditProposal) -> str:
    """Mint a single-use token for THIS proposal at THIS revision.

    Trust anchor: this function is only reachable from the human-facing CLI /
    workbench confirm action — the MCP adapter deliberately does not expose it.
    """
    token = secrets.token_hex(16)
    store = _token_store(bundle_dir)
    store[token] = {
        "proposal_digest": proposal.digest(),
        "base_revision": proposal.base_revision,
        "minted_at": time.time(),
    }
    _write_tokens(bundle_dir, store)
    return token


def _consume_token(bundle_dir: Path, proposal: EditProposal, token: str) -> None:
    store = _token_store(bundle_dir)
    record = store.pop(token, None)
    _write_tokens(bundle_dir, store)  # single-use: consumed even on failure below
    if record is None:
        raise PermissionError("confirmation token unknown or already used")
    if time.time() - record["minted_at"] > TOKEN_TTL_SECONDS:
        raise PermissionError("confirmation token expired; re-confirm the proposal")
    if record["proposal_digest"] != proposal.digest():
        raise PermissionError("confirmation token was minted for a different proposal")
    if record["base_revision"] != proposal.base_revision:
        raise PermissionError("confirmation token was minted for a different revision")


def _run_ops(bundle_dir: Path, ui_dir: Path, proposal: EditProposal, *, pin_first: bool) -> None:
    from .slide_edit import apply_deck_op, apply_slide_edit

    for index, op in enumerate(proposal.ops):
        expected = proposal.base_revision if (pin_first and index == 0) else None
        if isinstance(op, SetSlideField):
            apply_slide_edit(
                bundle_dir, ui_dir, slide_id=op.slide_id, field=op.field, value=op.value,
                expected_revision=expected,
            )
        else:
            apply_deck_op(
                bundle_dir, ui_dir, op=op.deck_op, slide_id=op.slide_id,
                target_order=op.target_order, expected_revision=expected,
            )


def simulate_proposal(bundle_dir: Path, proposal: EditProposal) -> dict:
    """Dry-run the WHOLE proposal on a temp overlay; zero writes."""
    import shutil
    from tempfile import TemporaryDirectory

    from .revisions import HISTORY_DIR

    with TemporaryDirectory(prefix="deck-proposal-") as tmp:
        staging = Path(tmp) / "bundle"
        shutil.copytree(bundle_dir, staging, ignore=shutil.ignore_patterns(HISTORY_DIR))
        try:
            _run_ops(staging, Path(tmp) / "ui", proposal, pin_first=False)
        except Exception as exc:
            return {"would_pass": False, "error": str(exc), "governance": proposal.is_governance()}
    return {"would_pass": True, "error": None, "governance": proposal.is_governance()}


def apply_proposal(
    bundle_dir: Path, ui_dir: Path, proposal: EditProposal, *, token: str | None = None
) -> dict:
    """Atomic apply: simulate first (all ops or none), then run for real."""
    if proposal.is_governance():
        if not token:
            raise PermissionError(
                "proposal contains governance ops (delete/hidden/layout); a human "
                "confirmation token is required"
            )
        _consume_token(bundle_dir, proposal, token)
    dry = simulate_proposal(bundle_dir, proposal)
    if not dry["would_pass"]:
        raise ValueError(f"proposal failed simulation; nothing applied: {dry['error']}")
    _run_ops(bundle_dir, ui_dir, proposal, pin_first=True)
    logger.info("proposal applied: {} ops (governance={})", len(proposal.ops), proposal.is_governance())
    return {"applied": True, "ops": len(proposal.ops), "governance": proposal.is_governance()}
