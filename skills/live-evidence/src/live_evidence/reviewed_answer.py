"""Read a creator answer only after its Tau reviewer has admitted that exact text.

Local Ask artifacts are trusted runtime outputs, not remote user-supplied URLs.
A provider dispatch or a PASS string in an answer is never sufficient.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .solver import answer_is_scannable


def binding_text(binding: dict) -> str:
    return 'LIVE_EVIDENCE_BINDING=' + json.dumps(binding, sort_keys=True, separators=(',', ':'))


def read_reviewed_answer(run_dir: Path, binding: dict) -> tuple[str, dict]:
    """Fail closed on missing, substituted, truncated, or unreviewed artifacts."""
    root = run_dir.resolve(strict=True)
    dag = json.loads((root / 'dag.json').read_text())
    context = dag['context']
    if context.get('dag_template') != 'creator-reviewer':
        raise ValueError('creator_reviewer_dag_required')
    if binding_text(binding) not in context.get('request', ''):
        raise ValueError('review_binding_mismatch')
    first = dag['entry_node']
    successors = [e['to'] for e in dag['edges'] if e['from'] == first]
    if len(successors) != 1 or successors[0] in {'join', 'human'}:
        raise ValueError('reviewer_dependency_missing')
    second = successors[0]
    receipts = []
    responses = []
    for node in (first, second):
        node_dir = (root / 'node-artifacts' / node).resolve(strict=True)
        if not node_dir.is_relative_to(root / 'node-artifacts'):
            raise ValueError('node_path_outside_run')
        receipt_path = node_dir / 'node-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('schema') != 'ask.tau_dag_handler_receipt.v1'
                or receipt.get('node_id') != node or receipt.get('ok') is not True
                or receipt.get('status') != 'PASS' or receipt.get('live') is not True
                or receipt.get('mocked') is not False):
            raise ValueError('review_node_not_admitted')
        response_path = Path(receipt['response_path']).resolve(strict=True)
        if response_path != node_dir / 'response.md':
            raise ValueError('unexpected_response_path')
        responses.append(response_path.read_text().strip())
        receipts.append(receipt)
    creator, reviewer = receipts
    answer = responses[0]
    if not answer or len(answer) > 2400:
        raise ValueError('reviewed_answer_outside_card_budget')
    scannable, violations = answer_is_scannable(answer)
    if not scannable:
        raise ValueError(f'reviewed_answer_not_scannable:{violations}')
    if reviewer.get('verdict') != 'PASS' or not reviewer.get('requires_verdict'):
        raise ValueError('reviewer_approval_missing')
    if first not in reviewer.get('prior_nodes', []):
        raise ValueError('reviewer_did_not_receive_creator')
    prompt_path = Path(reviewer['prompt_path']).resolve(strict=True)
    if not prompt_path.is_relative_to(root):
        raise ValueError('review_prompt_outside_run')
    prompt = prompt_path.read_text()
    if answer not in prompt or binding_text(binding) not in prompt:
        raise ValueError('reviewer_did_not_receive_exact_answer')
    approval = {
        'run_dir': str(root), 'binding': binding,
        'answer_sha256': hashlib.sha256(answer.encode()).hexdigest(),
        'creator_node': first, 'reviewer_node': second,
        'reviewer_response_sha256': hashlib.sha256(responses[1].encode()).hexdigest(),
    }
    return answer, approval


def card_has_bound_review(card) -> bool:
    """Re-read approval artifacts; copied verdict labels cannot authorize display."""
    approval = card.answer_review
    if not isinstance(approval, dict):
        return False
    binding = approval.get('binding', {})
    if (binding.get('question_id') != card.question_id
            or binding.get('question_revision') != card.question_revision
            or binding.get('policy_digest') != card.policy_digest
            or binding.get('query') != card.query):
        return False
    try:
        answer, current = read_reviewed_answer(Path(approval['run_dir']), binding)
        return answer == card.answer and current == approval
    except (OSError, ValueError, KeyError, TypeError):
        return False
