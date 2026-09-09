"""Reopen completed comparisons and retain immutable interview events.

Input hashes and decisions are checked before disk writes. Per-request files
provide idempotent saves; amendments reference the latest immutable event.
"""
import fcntl
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from loguru import logger
from compare_variants import RecordedSpeech, artifact, load_recommended, selection_record
from comparison_target import target_gaps
from eval_webgpt_audio import TAGS, digest
from review_models import CompletedBatch, Judgment, LearningProjection, PauseRealizationGate, ReviewCandidate, ReviewEvent, ReviewRow


def read_rows(batch_path: Path) -> list[ReviewRow]:
    batch = CompletedBatch.model_validate_json(batch_path.read_text())
    rows = []
    for ref in batch.rows:
        ref.recommendation.check()
        ref.packet.check()
        recommendation, packet = load_recommended(Path(ref.recommendation.path))
        scenario = packet.comparison.scenario
        if ref.scenario != scenario.id or ref.packet != recommendation.packet:
            raise ValueError('batch row identity differs from immutable recommendation')
        candidates = []
        for rendered in packet.candidates:
            candidate = rendered.candidate
            audio = rendered.response_audio
            measured = audio.check()
            gates = list(measured.failed_gates)
            if not audio.exact_pauses['matched']:
                gates.append('exact_pause_not_realized')
            assessment = next(a for a in recommendation.recommendation.assessments if a.candidate_id == candidate.id)
            native_events = [tag for tag in re.findall(r'\[[^\]]+\]', candidate.delivery_plan.render_text) if tag in TAGS]
            realization_errors = []
            try:
                PauseRealizationGate(matched=audio.exact_pauses['matched'], tolerance_frames=0, evidence_path=audio.receipt.path)
            except ValidationError as exc:
                logger.error('known retained pause mismatch: {}', audio.receipt.path)
                realization_errors = json.loads(exc.json())
            realization = 'FAIL' if realization_errors else 'NOT_ESTABLISHED' if native_events else 'PASS'
            recorded = RecordedSpeech.model_validate_json(Path(audio.receipt.path).read_text())
            candidates.append(ReviewCandidate(
                id=candidate.id, label=candidate.label,
                response=candidate.response_text or scenario.embry_response,
                expression_reason=candidate.expression_reason,
                wav=audio.wav, technical=audio.technical_audio,
                contextual=assessment.contextual_appropriateness,
                duration_sec=measured.prosody.duration_sec, silence_ratio=measured.pauses.silence_ratio,
                failed_gates=gates, plan=candidate.delivery_plan,
                recorded_render_chunks=recorded.request.render_chunks, exact_pauses=audio.exact_pauses,
                expected_native_events=native_events,
                vocal_event_realization='NOT_ESTABLISHED' if native_events else 'NOT_APPLICABLE',
                audio_realization=realization, realization_errors=realization_errors))
        rows.append(ReviewRow(
            scenario=scenario.id, scenario_sha256=digest(scenario.model_dump(by_alias=True)),
            expected_response=packet.comparison.expected_response, expected_response_gaps=target_gaps(packet.comparison),
            legacy_baseline_response=scenario.embry_response, legacy_baseline_delivery=scenario.delivery_plan,
            audio_realization_eligible_winner=next((c.id for c in candidates if c.id == recommendation.eligible_winner and c.audio_realization == 'PASS'), None),
            context=scenario.context, prior_turns=scenario.prior_turns,
            current_user_turn=scenario.current_user_turn, packet=ref.packet,
            recommendation=ref.recommendation, context_wav=packet.narration_audio.wav,
            agent_calibration_choice=recommendation.recommendation.candidate_id,
            eligible_winner=recommendation.eligible_winner,
            rationale=recommendation.recommendation.rationale,
            eligibility_reason=recommendation.eligibility_reason, candidates=candidates))
    if sum(len(row.candidates) for row in rows) != batch.candidate_responses:
        raise ValueError('incomplete declared batch')
    return rows


def history(store: Path, mode: Literal['human', 'test_only']) -> list[dict]:
    events = []
    for path in sorted(store.glob('*.jsonl')):
        event = ReviewEvent.model_validate_json(path.read_text())
        if event.mode != mode:
            raise ValueError('human/test-only history boundary mismatch')
        events.append({'artifact': artifact(path).model_dump(), 'event': event.model_dump(by_alias=True)})
    return sorted(events, key=lambda row: (row['event']['created_at'], row['event']['judgment']['request_id']))


def save_judgment(batch_path: Path, store: Path, mode: Literal['human', 'test_only'], judgment: Judgment) -> dict:
    # ponytail: one local file lock serializes saves; per-scenario locks only if throughput matters.
    store.mkdir(parents=True, exist_ok=True)
    with (store / 'save.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_rows(batch_path)
        row = next((r for r in rows if r.scenario == judgment.scenario), None)
        if row is None or row.recommendation.sha256 != judgment.recommendation_sha256:
            raise ValueError('unknown scenario or stale recommendation; reload batch')
        if judgment.candidate is not None:
            if judgment.candidate not in {c.id for c in row.candidates}:
                raise ValueError('unknown candidate')
            concurs = judgment.candidate == row.agent_calibration_choice
            if concurs != (judgment.outcome == 'agree'):
                raise ValueError('outcome differs from agent concurrence')
        path = store / f'{judgment.request_id}.jsonl'
        if path.exists():
            prior = ReviewEvent.model_validate_json(path.read_text())
            if prior.judgment != judgment or prior.mode != mode:
                raise ValueError('request id reused with different judgment')
            return {'artifact': artifact(path).model_dump(), 'event': prior.model_dump(by_alias=True), 'duplicate': True}
        previous = [h for h in history(store, mode) if h['event']['judgment']['scenario'] == row.scenario]
        expected = previous[-1]['artifact'] if previous else None
        supplied = judgment.supersedes.model_dump() if judgment.supersedes else None
        if supplied != expected:
            raise ValueError('history changed; reload and explicitly amend the latest judgment')
        if judgment.supersedes:
            judgment.supersedes.check()
        selection = None
        if mode == 'human' and judgment.candidate is not None:
            # The existing comparison owner supplies human preference semantics.
            selection = selection_record(Path(row.recommendation.path), judgment.candidate,
                                         judgment.reason, judgment.evaluator_identity,
                                         f'{judgment.outcome}: {judgment.candidate}\n{judgment.reason}')
        event = ReviewEvent(
            created_at=datetime.now(UTC).isoformat(), mode=mode, judgment=judgment,
            scenario_sha256=row.scenario_sha256, recommendation=row.recommendation, packet=row.packet,
            wav_hashes={'context': row.context_wav.sha256, **{c.id: c.wav.sha256 for c in row.candidates}},
            selection=selection,
            learning_projection=LearningProjection(
                status='test_only_not_learning' if mode == 'test_only' else 'human_confirmed_preference' if selection else 'human_review_no_preference',
                context_sha256=digest(row.context.model_dump()),
                predeclared_requested_outcome=row.current_user_turn.text,
                candidate_targets={c.id: c.expression_reason for c in row.candidates},
                candidate_controls={c.id: c.plan for c in row.candidates},
                candidate_wording={c.id: c.response for c in row.candidates},
                observed_technical={c.id: c.technical for c in row.candidates},
                measured_silence_ratios={c.id: c.silence_ratio for c in row.candidates},
                observed_audio_realization={c.id: c.audio_realization for c in row.candidates},
                expected_response_gaps=row.expected_response_gaps,
                perceived_delivery='HUMAN_REPORTED_NOT_INDEPENDENTLY_VERIFIED' if mode == 'human' and judgment.perceived_result else 'NOT_ESTABLISHED',
                human_rationale=judgment.reason,
                human_perceived_result=judgment.perceived_result if mode == 'human' else None,
                proposed_adjustment=judgment.proposed_adjustment))
        # Write complete bytes atomically, with no replacement even across processes.
        temporary = store / f'.{judgment.request_id}.pending'
        with temporary.open('x') as output:
            output.write(event.model_dump_json(by_alias=True) + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory = os.open(store, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        readback = ReviewEvent.model_validate_json(path.read_text())
        if readback != event:
            raise ValueError('saved event differs from independent readback')
        return {'artifact': artifact(path).model_dump(), 'event': readback.model_dump(by_alias=True), 'duplicate': False}


def replay_audio(row: ReviewRow, candidate: str, receipt: Path) -> dict:
    wav = row.context_wav if candidate == 'context' else next((c.wav for c in row.candidates if c.id == candidate), None)
    if wav is None:
        raise ValueError('unknown replay candidate')
    wav.check()
    lock_path = Path('/mnt/storage12tb/skills/chatterbox-speak/outputs/contextual/playback.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        played = subprocess.run(['pw-play', wav.path], capture_output=True, text=True, timeout=180)
    wav.check()
    result = {'schema': 'chatterbox_speak.terminal_replay.v1', 'scenario': row.scenario,
              'candidate': candidate, 'wav': wav.model_dump(), 'returncode': played.returncode,
              'stderr': played.stderr, 'human_hearing': 'NOT_ESTABLISHED', 'rerendered': False}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(result, indent=2))
    if json.loads(receipt.read_text()) != result:
        raise ValueError('replay receipt readback mismatch')
    if played.returncode != 0:
        raise ValueError(f'pw-play failed: {played.stderr}')
    return result

