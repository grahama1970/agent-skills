"""Optional complete expected-response baseline inside the existing comparison JSONL.

Legacy inputs keep their original plan/evaluation scope. New renders require a
context-bound target before any audio work; no target is inferred from winners.
"""
import subprocess

from typing import Literal

from pydantic import Field
from pydantic_core import PydanticCustomError

from eval_webgpt_audio import ROOT, Delivery, Evidence, Scenario, Strict, Text, digest
from speak import RenderPlan


class ExpectedResponse(Strict):
    context_sha256: Text = Field(pattern=r'^[a-f0-9]{64}$')
    response_text: Text
    response_meaning: Text
    emotional_intent: Text
    delivery_plan: Delivery
    rationale: Text
    context_evidence: list[Evidence] = Field(min_length=1)
    render_plan: RenderPlan
    pause_tolerance_frames: Literal[0]

    def check(self, scenario: Scenario):
        if self.context_sha256 != context_hash(scenario):
            raise PydanticCustomError('stale_expected_context', 'Expected-response context changed',
                                      {'expected': context_hash(scenario), 'observed': self.context_sha256, 'evidence_path': 'scenario.context/prior_turns/current_user_turn'})
        data = scenario.model_dump(by_alias=True)
        data.update(embry_response=self.response_text, delivery_plan=self.delivery_plan.model_dump())
        Scenario.model_validate(data)  # Existing tag grammar, wording, intensity/backend compatibility.
        turns = {t.id: t.text for t in scenario.prior_turns if t.id in scenario.context.relevant_turn_ids}
        turns[scenario.current_user_turn.id] = scenario.current_user_turn.text
        if any(e.turn_id not in turns or e.quote not in turns[e.turn_id] for e in self.context_evidence):
            raise PydanticCustomError('ungrounded_expected_rationale', 'Expected-response quote is not in relevant turns',
                                      {'expected': turns, 'observed': [e.model_dump() for e in self.context_evidence], 'evidence_path': 'expected_response.context_evidence'})
        compiled = compile_plan(self.delivery_plan)
        if compiled != self.render_plan:
            raise PydanticCustomError('stale_expected_pause_plan', 'Compiled expected pause plan differs',
                                      {'expected': self.render_plan.model_dump(by_alias=True), 'observed': compiled.model_dump(by_alias=True), 'evidence_path': 'expected_response.render_plan'})


def context_hash(scenario: Scenario) -> str:
    return digest({'context': scenario.context.model_dump(),
                   'prior_turns': [t.model_dump() for t in scenario.prior_turns],
                   'current_user_turn': scenario.current_user_turn.model_dump()})


def compile_plan(delivery: Delivery) -> RenderPlan:
    command = [str(ROOT.parent / 'best-practices-chatterbox/run.sh'), 'plan-silence',
               '--text', delivery.render_text, '--tone', delivery.tone]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    return RenderPlan.model_validate_json(result.stdout)


def require_predeclared_response(comparison, info=None):
    if comparison.expected_response is None:
        raise PydanticCustomError('missing_expected_response', 'Predeclared expected response/delivery is required before rendering',
                                  {'expected': 'expected_response with meaning, intent, grounded quotes, context hash, compiled render_plan and zero-frame pause tolerance',
                                   'observed': None, 'evidence_path': (info.context or {}).get('input_path', 'comparison.expected_response') if info else 'comparison.expected_response'})
    comparison.expected_response.check(comparison.scenario)
    return comparison


def target_gaps(comparison) -> list[str]:
    if comparison.expected_response is not None:
        comparison.expected_response.check(comparison.scenario)
        return []
    gaps = ['No explicit expected-response meaning/emotional-intent statement with target-specific grounded rationale and quote linkage.',
            'No expected-baseline compiled render_chunks frozen in the input; candidate receipts retain their actual render plans and PCM checks.']
    if comparison.scenario.expected_appropriateness == 'FAIL':
        gaps.append('The retained scenario baseline is an intentional negative control, not an expected correct response.')
    return gaps
