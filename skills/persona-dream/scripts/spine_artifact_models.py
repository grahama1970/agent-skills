"""Typed admission models for the cognition spine's existing artifact formats.

These validate structure, declared success and internal consistency, not model
truth or perceptual quality. Extra diagnostic fields remain forward-compatible;
the filename/schema binding is closed. Journal and ToM models reuse the existing
schema-generated contracts. Cross-file hashes and generation bindings are checked
by the step gate, not inferred from PASS strings.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from generated_models.persona_journal_v1_schema import PersonaDreamPersonaJournalV1
from generated_models.tom_candidate_v1_schema import PersonaDreamTomCandidateV1

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class Panel(Record):
    panel_id: Text
    action: Text
    mood: Text


class StoryboardPlan(Record):
    schema_name: Literal["persona_dream.cycle_storyboard_plan.v1"] = Field(alias="schema")
    dream_synopsis: Text
    panels: list[Panel] = Field(min_length=1)


class SelectedResidue(Record):
    cluster_id: Text
    seed_memory: Text
    selected: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def seed_is_selected(self) -> "SelectedResidue":
        if self.seed_memory not in self.selected:
            raise ValueError("seed_memory must be among selected source ids")
        return self


class SelectionReceipt(Record):
    schema_name: Literal["persona_dream.cycle_selection_receipt.v2"] = Field(alias="schema")
    persona_id: Text
    chosen: SelectedResidue
    selection_mode: Text
    seed: Text


class ResidueItem(Record):
    source_id: Text
    text: Text


class ResidueLinks(Record):
    schema_name: Literal["persona_dream.residue_links.v1"] = Field(alias="schema")
    idea_id: Text
    items: list[ResidueItem] = Field(min_length=1)


class TomReceipt(Record):
    schema_name: Literal["persona_dream.tom_validation_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS_TOM_VALIDATION_LIVE", "PASS_TOM_VALIDATION_DETERMINISTIC_PROJECTION"]
    run_id: Text
    revision_id: Text
    dream_id: Text
    interpretation_sha256: Digest
    canonical_memory_write_allowed: Literal[False]
    accepted_tom_candidates: list[PersonaDreamTomCandidateV1]
    accepted_count: int = Field(ge=0, strict=True)
    rejected_count: int = Field(ge=0, strict=True)
    proposed_candidate_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def counts_match(self) -> "TomReceipt":
        if self.accepted_count != len(self.accepted_tom_candidates):
            raise ValueError("accepted_count does not match candidates")
        if self.accepted_count + self.rejected_count != self.proposed_candidate_count:
            raise ValueError("candidate counts do not reconcile")
        return self


class ObservationFrame(Record):
    panel_id: Text
    observed_entities: list[Text] = Field(min_length=1)


class ObservationPacket(Record):
    schema_name: Literal["persona_dream.cycle_storyboard_observation_packet.v1"] = Field(alias="schema")
    status: Literal["ACCEPTED_STORYBOARD_OBSERVATION"]
    evidence_origin: Literal["storyboard_frames"]
    evidence_class: Literal["synthetic_dream"]
    source_revision_id: Text
    source_video_sha256: Digest
    frame_evidence: list[ObservationFrame] = Field(min_length=1)
    coverage_gaps: list[str]


class PersonaJournal(PersonaDreamPersonaJournalV1):
    @model_validator(mode="after")
    def cycles_match(self) -> "PersonaJournal":
        if self.cycle != self.session_mood.source_cycle or self.cycle != self.dream_provenance.cycle:
            raise ValueError("journal, mood and provenance must bind the same cycle")
        return self


class SpokenTextReceipt(Record):
    schema_name: Literal["persona_dream.cycle_journal_spoken_text_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS_CYCLE_JOURNAL_SPOKEN_TEXT"]
    source: Text
    journal_spoken: Text
    spoken_text_sha256: Digest


class JournalAudioReceipt(Record):
    schema_name: Literal["persona_dream.journal_audio_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS_JOURNAL_SPOKEN"]
    run_dir: Text
    audio: Text
    audio_bytes: int = Field(gt=0, strict=True)
    audio_sha256: Digest
    spoken_text_sha256: Digest
    asr_ok: Literal[True]
    readback_proves_audio: Literal[True]
    failed_gates: list[str] = Field(max_length=0)


class VoicedTurn(Record):
    audio: Text
    audio_sha256: Digest
    audio_bytes: int = Field(gt=0, strict=True)
    append_read_back: Literal[True]


class ConversationPair(Record):
    pair: int = Field(gt=0, strict=True)
    horus: VoicedTurn
    embry: VoicedTurn


class ConversationReceipt(Record):
    schema_name: Literal["persona_dream.dynamic_conversation_receipt.v1"] = Field(alias="schema")
    status: Literal["PASS_DYNAMIC_CONVERSATION"]
    run_dir: Text
    turn_count: int = Field(gt=0, strict=True)
    turn_pairs: list[ConversationPair] = Field(min_length=1)

    @model_validator(mode="after")
    def turn_counts_match(self) -> "ConversationReceipt":
        if self.turn_count != 2 * len(self.turn_pairs):
            raise ValueError("turn_count must match the voiced pairs")
        return self


class ConversationTurn(Record):
    schema_name: Literal["persona_dream.conversation_turn.v1"] = Field(alias="schema")
    role: Text
    text: Text
    journal_spoken_sha256: Digest
    created_at: Text
    audio: Text | None = None
    audio_sha256: Digest | None = None

    @model_validator(mode="after")
    def audio_reference_is_complete(self) -> "ConversationTurn":
        if bool(self.audio) != bool(self.audio_sha256):
            raise ValueError("audio path and hash must be supplied together")
        return self


SPINE_ARTIFACT_MODELS: dict[str, type[BaseModel]] = {
    "storyboard_plan.json": StoryboardPlan,
    "selection_receipt.v1.json": SelectionReceipt,
    "residue_links.json": ResidueLinks,
    "phase14_tom.json": TomReceipt,
    "observation_packet.json": ObservationPacket,
    "dream_journal.v1.json": PersonaJournal,
    "JOURNAL_SPOKEN_TEXT_RECEIPT.json": SpokenTextReceipt,
    "JOURNAL_AUDIO_RECEIPT.json": JournalAudioReceipt,
    "dynamic_conversation_receipt.v1.json": ConversationReceipt,
    "conversation.jsonl": ConversationTurn,
}
