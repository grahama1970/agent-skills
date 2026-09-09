# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "pydantic", "loguru", "httpx", "python-dotenv", "Pillow", "textual", "rich"]
# ///
"""One contextual question at a time in the existing interview TUI.

Uses its Question/Session, pane registry, numbered options and Submit pane.
Playback never submits or advances. Only explicit validated human submission
reaches the shared immutable JSONL store; no browser or server is required.
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import typer
from loguru import logger
from rich.markup import escape
from pydantic import ValidationError
from textual import on, work
from textual.binding import Binding
from textual.widgets import Button, Input, Static, TabbedContent

# Existing interview is a sibling source package; bootstrap only at this CLI seam.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from interview import Question, Session, register_tui_pane
from interview.tui import InterviewApp
from interview.tui_panes import QuestionPane, SubmitPane
from interview.tui_widgets import OptionItem

from review_models import Judgment, ReviewRow
from review_store import history, read_rows, replay_audio, save_judgment

OUTPUT = Path('/mnt/storage12tb/skills/chatterbox-speak/outputs')
BATCH = OUTPUT / 'variant-batch-summary.json'
app = typer.Typer(add_completion=False)


def context_text(row: ReviewRow) -> str:
    turns = [t for t in row.prior_turns if t.id in row.context.relevant_turn_ids] + [row.current_user_turn]
    return '\n'.join([
        f'CONTEXT ({row.context.origin}): {row.context.situation}', row.context.relationship,
        'RELEVANT TURNS:', *[f'{t.role}: {t.text}' for t in turns],
        f'REQUESTED OUTCOME BEFORE RENDER: {row.current_user_turn.text}',
        f'PROVISIONAL AGENT RECOMMENDATION: {row.agent_calibration_choice}', row.rationale,
        row.eligibility_reason,
        f'AUDIO-REALIZATION ELIGIBLE WINNER: {row.audio_realization_eligible_winner or "NONE"}; this does not establish emotional naturalness.',
        ('EXPECTED RESPONSE (input-declared): ' + row.expected_response.model_dump_json() if row.expected_response else
         'LEGACY PARTIAL TARGET EVIDENCE — original context/plan/evaluation scope preserved.\n'
         + f'Authored baseline wording: {row.legacy_baseline_response}\nLegacy baseline delivery: {row.legacy_baseline_delivery.model_dump_json()}\n'
         + '\n'.join('Missing target fact: ' + gap for gap in row.expected_response_gaps)),
        'Requested intensity/arousal is a target, NOT measured or perceived emotion.',
        'Human perception: NOT_ESTABLISHED. No thresholds or production defaults change.',
    ])


def candidate_description(candidate) -> str:
    return (f'{candidate.response}\nTarget (pre-render): {candidate.expression_reason}\n'
            f'Controls: {candidate.plan.tone}; intensity target {candidate.plan.intensity_band}; '
            f'{candidate.plan.realization}; requested arousal {candidate.plan.target_arousal}\n'
            f'Render plan: {candidate.plan.render_text}\n'
            f'Observed: technical {candidate.technical}; {candidate.duration_sec:.2f}s; '
            f'silence ratio {candidate.silence_ratio:.4f}; flags {candidate.failed_gates}\n'
            f'Recorded compiler chunks (not retroactive target proof): {[c.model_dump() for c in candidate.recorded_render_chunks]}\n'
            f'Exact PCM pause match: {candidate.exact_pauses["matched"]}; expected native events: {candidate.expected_native_events or "none"}\n'
            f'Vocal-event observation: {candidate.vocal_event_realization}; audio realization: {candidate.audio_realization}\n'
            + ('RED FLAG: expected pause missing/misplaced. ' + json.dumps(candidate.realization_errors) if candidate.audio_realization == 'FAIL' else
               'BLOCKED: audible native-event proof absent; applied_tags/request echoes cannot prove it.' if candidate.expected_native_events else
               'Realization PASS covers exact pauses only; perceived emotional delivery is not established.'))


def session_for(row: ReviewRow, prior: bool = False) -> Session:
    options = [{'label': c.id, 'description': candidate_description(c)} for c in row.candidates]
    options += [{'label': 'Reject all', 'description': 'No acceptable candidate; no candidate preference inferred.'},
                {'label': 'Defer', 'description': 'Leave this scenario unresolved; explain why.'}]
    return Session(id=uuid4().hex, title=f'Embry Reply Interview · {row.scenario}',
                   context=('AMENDMENT: final Submit appends a new record, preserving the prior judgment.' if prior else
                            'One question · no choice selected · replays stay here · Ctrl+S explicitly submits when ready · Esc cancels'),
                   questions=[Question(id='comparison', header='Comparison', type='select', text=context_text(row), options=options)], mode='tui')


def judgment_from_values(row: ReviewRow, choice: str | None, identity: str, reason: str, latest) -> Judgment:
    candidate = choice if choice in {c.id for c in row.candidates} else None
    if candidate:
        outcome = 'agree' if candidate == row.agent_calibration_choice else 'alternative'
    elif choice == 'Reject all':
        outcome = 'reject_all'
    elif choice == 'Defer':
        outcome = 'defer'
    else:
        raise ValueError('Select a numbered candidate, Reject all or Defer. Nothing saved.')
    return Judgment(request_id=str(uuid4()), scenario=row.scenario,
                    recommendation_sha256=row.recommendation.sha256, outcome=outcome, candidate=candidate,
                    evaluator_identity=identity, reason=reason, supersedes=latest)


class ComparisonPane(QuestionPane):
    """Small consuming pane: original numbered options plus replay and rationale."""
    DEFAULT_CSS = '''
    ComparisonPane { overflow-y: auto; height: 1fr; }
    ComparisonPane OptionItem .option-content { height: auto; }
    ComparisonPane Input { margin: 1 0; }
    ComparisonPane Button { margin-bottom: 1; }
    ComparisonPane .question-text { height: auto; }
    '''

    def __init__(self, question, row: ReviewRow):
        super().__init__(question)
        self.row = row
        self.playing = False

    def compose(self):
        yield Static(self.question.text, classes='question-text', markup=False)
        yield Button('Play context', id='play-context')
        yield Static('Select 1–5 directly; use Up/Down then Enter for other choices. Selection does not advance.', markup=False)
        for index, option in enumerate(self.question.options or [], 1):
            yield OptionItem(index=index, label=escape(option.label), description=escape(option.description), id=f'opt_comparison_{index}')
            if option.label in {c.id for c in self.row.candidates}:
                yield Button(f'Play {option.label}', id=f'play-{option.label.lower()}')
        yield Static('Reviewer identity (caller-attested; required)', markup=False)
        yield Input(placeholder='Your name', id='reviewer', max_length=160)
        yield Static('Rationale (required): intended outcome → heard result → mismatch → proposed adjustment. This is your report, not measured emotion.', markup=False)
        yield Input(placeholder='Explain agreement, override, rejection or deferral', id='rationale', max_length=4000)
        yield Static('No human choice yet. Ctrl+N reviewer, Ctrl+R rationale, Ctrl+S explicitly submits.', id='review-status', markup=False)

    def select_option(self, index: int):
        if self.playing or not 1 <= index <= len(self.question.options or []):
            return
        self.selected_indices = {index}
        for number in range(1, len(self.question.options or []) + 1):
            self.query_one(f'#opt_comparison_{number}', OptionItem).set_selected(number == index)
        self.query_one('#review-status', Static).update(f'Selected {self.question.options[index-1].label}; NOT submitted. Rationale and final Submit required.')

    @on(Button.Pressed)
    def replay_pressed(self, event: Button.Pressed):
        identifier = event.button.id or ''
        if not identifier.startswith('play-'):
            return
        event.stop()
        if self.playing:
            self.app.notify('Playback already in progress; wait for it to finish.')
            return
        target = 'context' if identifier == 'play-context' else identifier.removeprefix('play-').upper()
        self.playing = True
        self.play(target)

    @work
    async def play(self, target: str):
        self.query_one('#review-status', Static).update(f'Playing {target}; this does not select, advance or submit.')
        receipt = OUTPUT / 'review-replays' / f'{uuid4().hex}.json'
        try:
            await asyncio.to_thread(replay_audio, self.row, target, receipt)
            self.query_one('#review-status', Static).update(f'Replayed {target}. Human hearing unconfirmed. Receipt: {receipt}')
        except Exception as exc:
            logger.error('terminal playback failed: {}', exc)
            self.query_one('#review-status', Static).update(f'Playback failed: {exc}. No audio regenerated.')
        finally:
            self.playing = False


class ComparisonInterview(InterviewApp):
    """Reuse interview navigation/Submit; suppress its single-choice auto-advance."""
    CSS = InterviewApp.CSS + '\nTabbedContent > ContentSwitcher { height: 1fr; }'
    def __init__(self, row: ReviewRow, latest=None):
        register_tui_pane('select', lambda question, base_path=None: ComparisonPane(question, row))
        super().__init__(session_for(row, prior=latest is not None))
        self.row, self.latest = row, latest

    BINDINGS = InterviewApp.BINDINGS + [
        Binding('ctrl+n', 'reviewer', 'Reviewer', priority=True), Binding('ctrl+r', 'rationale', 'Rationale', priority=True),
        Binding('ctrl+p', 'replay_choice', 'Replay Choice', priority=True), Binding('ctrl+o', 'replay_context', 'Play Context', priority=True),
        Binding('ctrl+s', 'submit_judgment', 'Submit', priority=True),
    ]

    def action_submit_judgment(self):
        self._do_submit()

    def action_reviewer(self):
        field = self.query_one('#reviewer', Input); field.focus(); field.scroll_visible()

    def action_rationale(self):
        field = self.query_one('#rationale', Input); field.focus(); field.scroll_visible()

    def action_replay_choice(self):
        if 1 <= self.current_option_index <= len(self.row.candidates):
            self.query_one(f'#play-{self.row.candidates[self.current_option_index-1].id.lower()}', Button).press()

    def action_replay_context(self):
        self.query_one('#play-context', Button).press()

    def _get_option_count(self):
        return len(self.row.candidates) + 2

    def _highlight_current_option(self):
        pane = self._get_current_pane()
        if isinstance(pane, ComparisonPane):
            pane.query_one(f'#opt_comparison_{self.current_option_index}', OptionItem).scroll_visible()

    def _quick_select(self, num: int):
        pane = self._get_current_pane()
        if isinstance(pane, ComparisonPane):
            self.current_option_index = num
            pane.select_option(num)

    def action_select_or_submit(self):
        pane = self._get_current_pane()
        if isinstance(pane, SubmitPane):
            self._do_submit()
        elif isinstance(pane, ComparisonPane) and not isinstance(self.focused, Input):
            pane.select_option(self.current_option_index)

    def _do_submit(self):
        pane = self.query_one(ComparisonPane)
        try:
            if pane.playing:
                raise ValueError('Wait for playback to finish before submitting.')
            index = next(iter(pane.selected_indices), None)
            choice = pane.question.options[index-1].label if index is not None else None
            judgment = judgment_from_values(self.row, choice, pane.query_one('#reviewer', Input).value,
                                            pane.query_one('#rationale', Input).value, self.latest)
        except (ValueError, ValidationError) as exc:
            logger.error('terminal judgment rejected: {}', exc)
            self.query_one('#tabs', TabbedContent).active = 'pane_comparison'
            pane.query_one('#review-status', Static).update(str(exc))
            self.notify('Choice, reviewer identity and a nonblank rationale are required. Nothing saved.', severity='error')
            return
        self.exit(judgment)


@app.command()
def review(scenario: str, batch: Path = BATCH):
    """Review exactly one completed scenario in the terminal; no browser dependency."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise typer.BadParameter('Run this command in an actual terminal. Piped human answers are not accepted.')
    row = next((row for row in read_rows(batch) if row.scenario == scenario), None)
    if row is None:
        raise typer.BadParameter('unknown scenario')
    store = OUTPUT / 'human-reviews'
    events = [h for h in history(store, 'human') if h['event']['judgment']['scenario'] == scenario]
    latest = events[-1]['artifact'] if events else None
    judgment = ComparisonInterview(row, latest).run()
    if not isinstance(judgment, Judgment):
        print('Cancelled. No human judgment saved.'); return
    saved = save_judgment(batch, store, 'human', judgment)
    reopened = next(h for h in history(store, 'human') if h['artifact'] == saved['artifact'])
    print(json.dumps({'saved': reopened['artifact'], 'outcome': judgment.outcome,
                      'readback_verified': True, 'production_defaults_changed': False}, indent=2))


if __name__ == '__main__':
    app()
