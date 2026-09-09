# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "pydantic", "loguru", "httpx", "python-dotenv", "Pillow", "textual"]
# ///
"""Retained terminal interview evaluation: real TUI, existing WAV playback and JSONL readback.

Positive preference simulation is explicitly test-only and never calls human
storage or Memory. Fault controls use copied inputs, not historical evidence.
"""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from loguru import logger
from pydantic import AfterValidator, TypeAdapter, ValidationError
from textual.widgets import Input, Static, TabbedContent

from compare_variants import Comparison, load_input
from comparison_target import ExpectedResponse, compile_plan, context_hash, require_predeclared_response
from review_models import ReviewCandidate, ReviewEvent
from eval_review_process import tty_cancel, reject_missing_target_render
from review_store import history, read_rows, replay_audio, save_judgment
from review_terminal import ComparisonInterview, ComparisonPane, BATCH, OUTPUT, context_text, judgment_from_values

ROOT = Path(__file__).resolve().parents[1]
app = typer.Typer(add_completion=False)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def receipt(output: Path, run: Path, data: dict):
    data = {'passed': True, **data, 'run': str(run)}
    (run / 'result.json').write_text(json.dumps(data, indent=2))
    output.write_text(json.dumps(data, indent=2))
    check(json.loads(output.read_text()) == data, 'eval receipt readback mismatch')
    print(json.dumps(data))


def run_dir():
    run = OUTPUT / 'terminal-evals' / uuid4().hex
    run.mkdir(parents=True)
    return run




async def exercise_tui(row, run):
    application = ComparisonInterview(row)
    async with application.run_test(size=(160, 70)) as pilot:
        await pilot.pause()
        check(len(application.session.questions) == 1, 'more than one scenario question')
        pane = application.query_one(ComparisonPane)
        check(not pane.selected_indices, 'default human selection manufactured')
        application.save_screenshot(filename='terminal-context.svg', path=str(run))
        context_capture = (run / 'terminal-context.svg').read_text()
        check(context_capture.count('[gasp]') >= 3, 'candidate native tag text hidden by terminal markup')
        # Replay without selecting or advancing through the real pw-play worker.
        await pilot.press('ctrl+p')
        deadline = time.monotonic() + 20
        await pilot.pause(.2)
        while pane.playing and time.monotonic() < deadline:
            await pilot.pause(.2)
        check(not pane.playing, 'replay did not finish')
        (run / 'playback-state.txt').write_text(str(pane.query_one('#review-status', Static).render()))
        check('Replayed C01' in str(pane.query_one('#review-status', Static).render()), 'real replay receipt absent')
        check(not pane.selected_indices and application.query_one('#tabs', TabbedContent).active == 'pane_comparison', 'replay selected or advanced question')
        await pilot.press('1', '2'); await pilot.pause()
        check(pane.selected_indices == {2}, 'numbered candidate change failed')
        check(application.query_one('#tabs', TabbedContent).active == 'pane_comparison', 'selection auto-advanced')
        # Explicit submit without required fields must stay open, with no record.
        await pilot.press('ctrl+s'); await pilot.pause()
        check(application.query_one('#tabs', TabbedContent).active == 'pane_comparison', 'invalid submit bypassed required rationale')
        await pilot.press('ctrl+n'); await pilot.pause()
        check(application.focused is pane.query_one('#reviewer', Input), 'identity keyboard shortcut failed')
        await pilot.press(*list('TEST_ONLY evaluator'))
        await pilot.press('ctrl+r'); await pilot.pause()
        check(application.focused is pane.query_one('#rationale', Input), 'rationale keyboard shortcut failed')
        await pilot.pause(.4)
        field = pane.query_one('#rationale', Input)
        check(field.region.y >= pane.region.y and field.region.bottom < application.size.height - 1, 'focused rationale clipped outside terminal viewport')
        await pilot.press('space', 'space')
        await pilot.press('ctrl+s'); await pilot.pause()
        check(application.query_one('#tabs', TabbedContent).active == 'pane_comparison', 'whitespace rationale accepted')
        pane.query_one('#rationale', Input).value = ''
        await pilot.press('ctrl+r')
        await pilot.press(*list('TEST ONLY: compare intended celebration to heard result; record mismatch and proposed adjustment without claiming human preference.'))
        await pilot.pause()
        application.save_screenshot(filename='terminal-test-only.svg', path=str(run))
        await pilot.press('ctrl+s'); await pilot.pause()
    check(application.return_value is not None, 'explicit terminal submit did not return a judgment')
    return application.return_value


@app.command()
def live(output: Path):
    run = run_dir()
    human = OUTPUT / 'human-reviews'
    before = history(human, 'human')
    rows = read_rows(BATCH)
    check(len(rows) == 6 and sum(len(r.candidates) for r in rows) == 30, 'completed batch incomplete')
    row = next(r for r in rows if r.scenario == 'celebration')
    check(row.eligible_winner is None, 'no-winner state lost')
    check(row.expected_response is None and row.expected_response_gaps, 'legacy evidence retroactively promoted')
    check(any(c.audio_realization == 'FAIL' for c in row.candidates), 'pause mismatch no longer red flagged')
    check(all(c.audio_realization != 'PASS' for c in row.candidates if c.expected_native_events), 'unobserved vocal event passed')
    terminal = tty_cancel(run)
    # Separately labeled scripted terminal interaction, NEVER a real human selection.
    judgment = asyncio.run(exercise_tui(row, run))
    store = OUTPUT / 'review-test-only' / run.name
    saved = save_judgment(BATCH, store, 'test_only', judgment)
    event = ReviewEvent.model_validate_json(Path(saved['artifact']['path']).read_text())
    check(event.mode == 'test_only' and event.selection is None, 'simulation leaked human preference')
    check(event.learning_projection.status == 'test_only_not_learning', 'simulation leaked learning')
    check(event.judgment.candidate == 'C02' and event.judgment.outcome == 'alternative', 'wrong candidate saved')
    duplicate = save_judgment(BATCH, store, 'test_only', judgment)
    check(duplicate['duplicate'] and duplicate['artifact'] == saved['artifact'], 'same request duplicated')
    prior_bytes = Path(saved['artifact']['path']).read_bytes()
    latest = saved['artifact']
    for choice in ['Reject all', 'Defer']:
        amendment = judgment_from_values(row, choice, 'TEST_ONLY evaluator', f'TEST ONLY {choice}: no actual human judgment.', latest)
        latest = save_judgment(BATCH, store, 'test_only', amendment)['artifact']
    check(Path(saved['artifact']['path']).read_bytes() == prior_bytes, 'amend overwrote history')
    check(len(history(store, 'test_only')) == 3, 'reject/defer not retained separately')
    wav = row.candidates[0].wav
    check(hashlib.sha256(Path(wav.path).read_bytes()).hexdigest() == wav.sha256, 'replayed WAV changed')
    check(history(human, 'human') == before, 'test mutated actual human review history')
    receipt(output, run, {'evidence': 'actual_PTY_and_live_pw_play_plus_test_only_Textual_interactions',
                         'terminal': terminal, 'simulation': 'test_only_not_human_preference',
                         'saved': saved['artifact'], 'one_question': True, 'no_default_selection': True,
                         'replay_no_advance_or_submit': True, 'rationale_gate': True, 'immutable_readback': True,
                         'visible_rationale_and_native_tag_text': True,
                         'all_six_original_packets_valid': True, 'human_history_unchanged': True,
                         'target_first_audio_quality': 'NOT_ESTABLISHED', 'native_event_realization': 'NOT_ESTABLISHED'})


async def exercise_compact(row, run):
    application = ComparisonInterview(row)
    async with application.run_test(size=(113, 7)) as pilot:
        await pilot.pause(.3)
        pane = application.query_one(ComparisonPane)
        check(pane.region.y == 0 and pane.region.height >= 5, 'compact chrome consumes the viewport')
        application.save_screenshot(filename='compact-context.svg', path=str(run))
        check('CONTEXT' in (run / 'compact-context.svg').read_text(), 'compact context not rendered')
        await pilot.press('2'); await pilot.pause(.3)
        choice = pane.query_one('#opt_comparison_2')
        check(0 <= choice.region.y < 6 and pane.selected_indices == {2}, 'compact current choice not visible')
        application.save_screenshot(filename='compact-choice.svg', path=str(run))
        await pilot.press('ctrl+n'); await pilot.pause(.3)
        field = pane.query_one('#reviewer', Input)
        check(application.focused is field and 0 <= field.region.y and field.region.bottom <= 6, 'compact reviewer unreachable')
        await pilot.press(*list('TEST ONLY'))
        await pilot.press('ctrl+r'); await pilot.pause(.3)
        field = pane.query_one('#rationale', Input)
        check(application.focused is field and 0 <= field.region.y and field.region.bottom <= 6, 'compact rationale unreachable')
        await pilot.press(*list('TEST ONLY compact keyboard submit; no human preference saved.'))
        application.save_screenshot(filename='compact-rationale.svg', path=str(run))
        await pilot.press('ctrl+s'); await pilot.pause()
    check(application.return_value is not None and application.return_value.candidate == 'C02', 'compact explicit submit failed')
    return {'context_visible': True, 'choice_visible': True, 'rationale_visible': True, 'explicit_submit': True}


@app.command()
def compact(output: Path):
    """Exercise the observed seven-row overlay dimensions, without preference writes."""
    run = run_dir(); before = history(OUTPUT / 'human-reviews', 'human')
    row = read_rows(BATCH)[0]
    terminal = tty_cancel(run, rows=7, columns=113)
    checks = asyncio.run(exercise_compact(row, run))
    check(history(OUTPUT / 'human-reviews', 'human') == before, 'compact test wrote a human preference')
    receipt(output, run, {'viewport': {'rows': 7, 'columns': 113}, 'actual_pty': terminal,
                         'simulation': 'test_only_keyboard_no_persistence', 'human_history_unchanged': True, **checks})


@app.command()
def negative(output: Path):
    run = run_dir(); rows = read_rows(BATCH); row = rows[0]; rejected = []
    for identity, reason in [('TEST_ONLY', ''), ('TEST_ONLY', '   '), ('', 'TEST ONLY')]:
        try: judgment_from_values(row, 'C01', identity, reason, None)
        except ValidationError as exc:
            logger.error('expected boundary rejection: {}', exc)
            rejected.append(json.loads(exc.json()))
        else: raise ValueError('invalid judgment accepted')
    unobserved = row.candidates[0].model_dump()
    unobserved['audio_realization'] = 'PASS'
    try: ReviewCandidate.model_validate(unobserved)
    except ValidationError as exc:
        logger.error('expected unobserved-event rejection: {}', exc); rejected.append(json.loads(exc.json()))
    else: raise ValueError('unobserved event accepted as PASS')
    original = json.loads(BATCH.read_text())
    for kind in ['missing', 'stale']:
        data = json.loads(json.dumps(original))
        if kind == 'missing': data['rows'][0]['recommendation']['path'] = str(run / 'missing.jsonl')
        else: data['rows'][0]['recommendation']['sha256'] = '0' * 64
        path = run / f'{kind}.json';path.write_text(json.dumps(data))
        try: read_rows(path)
        except (ValueError, OSError) as exc:
            logger.error('expected artifact rejection: {}', exc); rejected.append({'kind': kind, 'error': str(exc)})
        else: raise ValueError('bad artifact accepted')
    receipt(output, run, {'rejections': rejected, 'source_artifacts_unchanged': True})


@app.command()
def targets(output: Path):
    run = run_dir()
    comparison = load_input(ROOT / 'fixtures/reply_variants.jsonl', 'celebration', 5)
    gate = TypeAdapter(Annotated[Comparison, AfterValidator(require_predeclared_response)])
    errors = []
    try: gate.validate_python(comparison)
    except ValidationError as exc:
        logger.error('expected missing target rejection: {}', exc);errors += json.loads(exc.json())
    else: raise ValueError('missing expected response accepted')
    scenario = comparison.scenario
    # Test-only target validation. Never attached to historical audio or treated as prior evidence.
    target = ExpectedResponse(context_sha256=context_hash(scenario), response_text=scenario.embry_response,
                              response_meaning='TEST ONLY: acknowledge the stated achievement.', emotional_intent='TEST ONLY: welcomed celebration',
                              delivery_plan=scenario.delivery_plan, rationale='TEST ONLY: the listener explicitly welcomes celebration.',
                              context_evidence=[{'turn_id': 'u1', 'quote': scenario.prior_turns[0].text, 'relevance': 'TEST ONLY direct requested reaction'}],
                              render_plan=compile_plan(scenario.delivery_plan), pause_tolerance_frames=0)
    data = comparison.model_dump(by_alias=True);data['expected_response'] = target.model_dump(by_alias=True)
    gate.validate_python(Comparison.model_validate(data))
    for fault in ['context', 'pause', 'wording', 'tag-backend']:
        changed = json.loads(json.dumps(data))
        if fault == 'context': changed['scenario']['context']['situation'] += ' changed'
        elif fault == 'pause': changed['expected_response']['render_plan']['render_chunks'][0]['pause_after_ms'] += 1
        elif fault == 'wording': changed['expected_response']['response_text'] = ''
        else: changed['expected_response']['delivery_plan']['realization'] = 'intensity'
        try: gate.validate_python(Comparison.model_validate(changed))
        except ValidationError as exc:
            logger.error('expected target fault rejection: {}', exc); errors += json.loads(exc.json())
        else: raise ValueError(f'stale/invalid target accepted: {fault}')
    # Public render command must stop before narration, rendering, or output creation.
    reject_missing_target_render(run)
    receipt(output, run, {'errors': errors, 'legacy_audio_rebound': False, 'public_render_blocked_before_audio': True,
                         'positive_target': 'test_only_validation_not_historical_evidence'})


if __name__ == '__main__':
    app()
