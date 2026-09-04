#!/usr/bin/env python3
"""Adversarial replay of a retained live approval through production state methods.

No providers are invoked. Session identity is restored as test setup; artifacts
are copied before mutation. This proves guards, not a fresh live conversation.
"""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from live_evidence.config import AppSettings, InterviewProfile
from live_evidence.models import EvidenceCard
from live_evidence.state import RuntimeState


async def main():
    source = Path('/tmp/live-evidence-reviewed-publication.json')
    original = EvidenceCard.model_validate(json.loads(source.read_text())['cards'][0])
    checks = {}
    with tempfile.TemporaryDirectory(prefix='le-review-binding-') as name:
        temp = Path(name)
        old = Path(original.answer_review['run_dir'])
        run = temp / 'run'
        run.mkdir()
        shutil.copy2(old / 'dag.json', run / 'dag.json')
        for node in (original.answer_review['creator_node'], original.answer_review['reviewer_node']):
            src = old / 'node-artifacts' / node
            dst = run / 'node-artifacts' / node
            dst.mkdir(parents=True)
            receipt = json.loads((src / 'node-receipt.json').read_text())
            for key, filename in [('response_path', 'response.md'), ('prompt_path', 'prompt.md')]:
                shutil.copy2(Path(receipt[key]), dst / filename)
                receipt[key] = str(dst / filename)
            (dst / 'node-receipt.json').write_text(json.dumps(receipt))
        card = original.model_copy(deep=True)
        card.answer_review['run_dir'] = str(run)
        binding = card.answer_review['binding']
        settings = AppSettings(skill_root=Path(__file__).resolve().parents[1], data_dir=temp,
                               profile_path=temp / 'profile.yaml')
        def state():
            value = RuntimeState(settings, InterviewProfile(name='approval-replay'))
            # Fixture restoration only; the tested publication/update calls below
            # are the production methods and receive the original approved card.
            value._session.session_id = binding['session_id']
            value._session.policy_digest = binding['policy_digest']
            value._active_question_id = card.question_id
            value._active_question_revision = card.question_revision
            value._question_last_revision[card.question_id] = card.question_revision
            return value
        valid = state()
        checks['valid_approval_published'] = await valid.publish_card_fenced(card) is not None
        mutations = {
            'changed_answer': {'answer': card.answer + '\n- Unreviewed claim'},
            'wrong_revision': {'question_revision': card.question_revision + 1},
            'missing_approval': {'answer_review': None},
        }
        for label, fields in mutations.items():
            value = state()
            changed = card.model_copy(update=fields)
            checks[label] = (await value.publish_card_fenced(changed) is None
                             and not (await value.snapshot()).cards)
        value = state()
        value._session.session_id = 'another-session'
        checks['wrong_session'] = (await value.publish_card_fenced(card) is None
                                   and not (await value.snapshot()).cards)
        checks['update_answer_rejected'] = not await valid.update_card_fields(card.card_id, answer='unreviewed replacement')
        checks['update_amendment_rejected'] = not await valid.update_card_fields(card.card_id, amendment_text='unreviewed replacement', amendment_complete=True)
        bypass = state()
        await bypass.add_card(card.model_copy(update={'answer_review': None}))
        checks['add_card_cannot_bypass'] = not (await bypass.snapshot()).cards
        missing = run / 'node-artifacts' / card.answer_review['reviewer_node'] / 'node-receipt.json'
        missing.unlink()
        value = state()
        checks['missing_reviewer_artifact'] = await value.publish_card_fenced(card) is None
    receipt = {'schema': 'live_evidence.review_binding_eval.v1',
               'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
               'provider_calls': 0, 'fixture_backed': True,
               'source_receipt': str(source),
               'proof_scope': 'Production state methods with restored session and copied prior live artifacts; no new provider, HTTP, UI or audio proof'}
    path = Path('/tmp/live-evidence-review-binding-eval.json')
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
