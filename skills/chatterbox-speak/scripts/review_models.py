"""Typed contextual interview transport and append-only judgment records.

Consumes immutable comparison artifacts. Rejects malformed judgments and keeps
explicit test-only simulation separate from caller-attested human preferences.
"""
from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from compare_variants import Artifact, Selection
from comparison_target import ExpectedResponse
from speak import RenderChunk
from eval_webgpt_audio import Context, Delivery, Projection, Strict, Text, Turn, Verdict


class BatchRowReference(Projection):
    scenario: Text
    recommendation: Artifact
    packet: Artifact


class CompletedBatch(Projection):
    scenarios: Literal[6]
    candidate_responses: Literal[30]
    underlying_context_families: Literal[3]
    human_selection_status: Literal['NOT_PROVIDED']
    rows: list[BatchRowReference] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def unique(self):
        if len({r.scenario for r in self.rows}) != len(self.rows):
            raise ValueError('duplicate scenario identity')
        return self


class PauseRealizationGate(Strict):
    matched: bool
    tolerance_frames: Literal[0]
    evidence_path: Text

    @model_validator(mode='after')
    def exact_pause_required(self):
        if not self.matched:
            raise PydanticCustomError('expected_pause_not_realized', 'Expected PCM pause is missing or misplaced',
                                      {'expected': 'zero PCM at each planned boundary', 'observed': 'boundary mismatch',
                                       'tolerance_frames': self.tolerance_frames, 'evidence_path': self.evidence_path})
        return self


class ReviewCandidate(Strict):
    id: Text
    label: Text
    response: Text
    expression_reason: Text
    wav: Artifact
    technical: Literal['PASS', 'FAIL']
    contextual: Verdict
    duration_sec: float
    silence_ratio: float
    failed_gates: list[str]
    plan: Delivery
    recorded_render_chunks: list[RenderChunk]
    exact_pauses: dict
    expected_native_events: list[str]
    vocal_event_realization: Literal['NOT_ESTABLISHED', 'NOT_APPLICABLE']
    audio_realization: Verdict
    realization_errors: list[dict]

    @model_validator(mode='after')
    def no_unobserved_event_pass(self):
        if self.expected_native_events and self.vocal_event_realization == 'NOT_ESTABLISHED' and self.audio_realization == 'PASS':
            raise PydanticCustomError('missing_vocal_event_observation', 'Native event realization cannot pass without audible evidence',
                                      {'expected': self.expected_native_events, 'observed': None, 'evidence_path': self.wav.path})
        if self.exact_pauses.get('matched') is not True and self.audio_realization != 'FAIL':
            raise PydanticCustomError('expected_pause_not_realized', 'Pause mismatch must be audio-realization FAIL',
                                      {'expected': True, 'observed': self.exact_pauses.get('matched'), 'evidence_path': self.wav.path})
        return self


class ReviewRow(Strict):
    scenario: Text
    scenario_sha256: Text
    expected_response: ExpectedResponse | None
    expected_response_gaps: list[str]
    legacy_baseline_response: Text
    legacy_baseline_delivery: Delivery
    audio_realization_eligible_winner: str | None
    context: Context
    prior_turns: list[Turn]
    current_user_turn: Turn
    packet: Artifact
    recommendation: Artifact
    context_wav: Artifact
    agent_calibration_choice: Text
    eligible_winner: str | None
    rationale: Text
    eligibility_reason: Text
    candidates: list[ReviewCandidate]


class Judgment(Strict):
    request_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    scenario: Text
    recommendation_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    outcome: Literal['agree', 'alternative', 'reject_all', 'defer']
    candidate: str | None
    reason: Text = Field(max_length=4000)
    evaluator_identity: Text = Field(max_length=160)
    supersedes: Artifact | None = None
    perceived_result: Text | None = Field(default=None, max_length=4000)
    proposed_adjustment: Text | None = Field(default=None, max_length=4000)

    @model_validator(mode='after')
    def candidate_required_only_for_choice(self):
        if (self.outcome in {'agree', 'alternative'}) != (self.candidate is not None):
            raise ValueError('candidate required only for agreement or alternative')
        return self


class LearningProjection(Strict):
    status: Literal['test_only_not_learning', 'human_confirmed_preference', 'human_review_no_preference']
    context_sha256: Text
    predeclared_requested_outcome: Text
    candidate_targets: dict[str, str]
    candidate_controls: dict[str, Delivery]
    candidate_wording: dict[str, str]
    observed_technical: dict[str, Literal['PASS', 'FAIL']]
    measured_silence_ratios: dict[str, float]
    observed_audio_realization: dict[str, Verdict]
    expected_response_gaps: list[str]
    perceived_delivery: Literal['NOT_ESTABLISHED', 'HUMAN_REPORTED_NOT_INDEPENDENTLY_VERIFIED']
    human_rationale: Text
    human_perceived_result: Text | None
    proposed_adjustment: Text | None
    application_status: Literal['PROPOSED_NOT_APPLIED'] = 'PROPOSED_NOT_APPLIED'


class ReviewEvent(Strict):
    schema_id: Literal['chatterbox_speak.review_event.v1'] = Field(default='chatterbox_speak.review_event.v1', alias='schema')
    created_at: Text
    mode: Literal['human', 'test_only']
    judgment: Judgment
    scenario_sha256: Text
    recommendation: Artifact
    packet: Artifact
    wav_hashes: dict[str, str]
    selection: Selection | None
    learning_projection: LearningProjection

    @model_validator(mode='after')
    def test_inputs_are_not_human_preferences(self):
        if self.mode == 'test_only' and self.selection is not None:
            raise ValueError('test-only events cannot contain a human preference')
        if self.mode == 'human' and (self.judgment.candidate is not None) != (self.selection is not None):
            raise ValueError('human candidate judgment requires the owning selection record')
        return self

