# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "pydantic", "typer", "loguru"]
# ///
"""Scoped provisional comparison lessons via Memory, with independent recall readback.

Canonical Memory text is clean reasoning, never renderer-tagged utterances.
Human-confirmed status requires an actual retained caller-attested preference.
"""
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from compare_variants import Artifact, Selection, artifact, load_recommended
from eval_webgpt_audio import digest, file_hash

app = typer.Typer(add_completion=False)
URL = 'http://127.0.0.1:8601'
SCOPE = 'chatterbox-speak-contextual-comparison'
TAGS = ['skill:chatterbox-speak', 'contextual-audio-comparison', 'provisional-learning', 'Precision', 'Fragility']


class Lesson(BaseModel):
    model_config = ConfigDict(extra='ignore', populate_by_name=True)
    key: str = Field(alias='_key', min_length=1)
    problem: str = ''
    solution: str = ''
    status: Literal['provisional_agent_recommendation', 'human_confirmed_preference'] | None = None
    tags: list[str] = Field(default_factory=list)


class StoredLesson(Lesson):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    scope: str
    status: Literal['provisional_agent_recommendation', 'human_confirmed_preference']
    scenario_id: str
    scenario_sha256: str
    context_sha256: str
    context_origin: str
    recommendation_rationale: str
    recommendation_candidate_id: str
    eligible_winner: str | None
    influenced_by: list[str]
    provenance: dict[str, Artifact | None]
    updated_at: str


class UpsertResult(BaseModel):
    collection: Literal['lessons_v2']
    inserted: int
    updated: int
    errors: list
    total: int


class ReadbackLesson(StoredLesson):
    # Memory-owned bookkeeping fields remain outside the lesson projection.
    model_config = ConfigDict(extra='ignore', populate_by_name=True)


class Listed(BaseModel):
    documents: list[ReadbackLesson]


class Recall(BaseModel):
    model_config = ConfigDict(extra='allow')
    found: bool
    should_scan: bool
    confidence: float
    items: list[Lesson]


def post(endpoint: str, payload: dict):
    r = httpx.post(URL + endpoint, json=payload, headers={'X-Caller-Skill': 'chatterbox-speak'},
                   timeout=httpx.Timeout(30, connect=2))
    if r.is_error:
        raise ValueError(f'Memory {endpoint} rejected request ({r.status_code}): {r.text}')
    return r.json()


def recall_data(query: str) -> Recall:
    return Recall.model_validate(post('/recall', {'q': query, 'scope': SCOPE,
                                                'tags': TAGS[:2], 'k': 10}))


@app.command()
def recall(situation: str, output: Path):
    """Recall scoped lessons before a later recommendation; preserve the actual result."""
    result = recall_data(f'Which provisional contextual audio comparison lessons apply to {situation}?')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(by_alias=True, indent=2))
    print(result.model_dump_json(by_alias=True))


@app.command()
def store(recommendation: Path, output: Path, selection: Path | None = None):
    """Store a stable scoped lesson, then prove its key is independently recalled."""
    r, p = load_recommended(recommendation)
    status = 'provisional_agent_recommendation'
    preference = None
    if selection:
        preference = Selection.model_validate_json(selection.read_text())
        preference.recommendation.check()
        preference.packet.check()
        if (preference.recommendation.sha256 != file_hash(recommendation)
                or preference.packet.sha256 != r.packet.sha256
                or preference.candidate_id not in [c.candidate.id for c in p.candidates]
                or preference.agent_candidate_id != r.recommendation.candidate_id
                or preference.concurs != (preference.candidate_id == r.recommendation.candidate_id)):
            raise ValueError('human preference does not match recommendation, packet or candidate')
        status = 'human_confirmed_preference'
    context = p.comparison.scenario.context.model_dump()
    key = 'chatterbox-comparison-' + file_hash(selection or recommendation)[:32]
    rationale = preference.reason if preference else r.recommendation.rationale
    # Explicit renderer markup grammar is excluded from canonical Memory prose.
    clean = re.sub(r'\[[^\]]+\]', '', rationale)
    doc = {'_key': key, 'scope': SCOPE, 'status': status, 'tags': TAGS + [f'status:{status}'],
           'problem': re.sub(r'\[[^\]]+\]', '', f'What did contextual audio comparison {p.comparison.scenario.id} show? {context["situation"]}'),
           'solution': f'{status}: {clean} {r.eligibility_reason} Not a production default or universal threshold rule.',
           'scenario_id': p.comparison.scenario.id, 'scenario_sha256': p.input_sha256,
           'context_sha256': digest(context), 'context_origin': context['origin'],
           'recommendation_rationale': clean, 'recommendation_candidate_id': r.recommendation.candidate_id,
           'eligible_winner': r.eligible_winner, 'influenced_by': r.recommendation.provisional_guidance_used,
           'provenance': {'recommendation': artifact(recommendation).model_dump(), 'packet': r.packet.model_dump(),
                          'ask_node': r.node.model_dump(), 'selection': artifact(selection).model_dump() if selection else None},
           'updated_at': datetime.now(UTC).isoformat()}
    doc = StoredLesson.model_validate(doc).model_dump(by_alias=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    request_path = output.with_suffix('.request.json')
    request_path.write_text(json.dumps(doc, indent=2))
    # Memory /store's lessons compatibility path projects metadata away; the owning
    # /upsert endpoint preserves the full lesson in its live lessons_v2 collection.
    response = UpsertResult.model_validate(post('/upsert', {'collection': 'lessons_v2', 'documents': [doc]}))
    output.with_suffix('.store-response.json').write_text(response.model_dump_json(indent=2))
    if response.errors or response.inserted + response.updated != 1:
        raise ValueError('Memory upsert did not accept exactly one scoped lesson')
    listed = Listed.model_validate(post('/list', {'collection': 'lessons_v2', 'filters': {'_key': key}, 'limit': 1}))
    output.with_suffix('.list-readback.json').write_text(listed.model_dump_json(indent=2))
    if len(listed.documents) != 1 or listed.documents[0].model_dump(by_alias=True) != doc:
        raise ValueError('Memory full lesson metadata readback mismatch')
    # The live full-document readback can precede search-index visibility. Poll the
    # independent recall effect, never repeat the write hoping for a different result.
    for attempt in range(10):
        readback = recall_data(f'{key} {doc["problem"]}')
        output.with_suffix(f'.recall-attempt-{attempt+1}.json').write_text(readback.model_dump_json(by_alias=True, indent=2))
        matches = [i for i in readback.items if i.key == key and i.solution == doc['solution']]
        if matches:
            break
        time.sleep(2)
    output.with_suffix('.recall.json').write_text(readback.model_dump_json(by_alias=True, indent=2))
    if not matches:
        raise ValueError('Memory persistence not independently confirmed by exact key and clean solution recall')
    receipt = {'schema': 'chatterbox_speak.memory_learning.v1', 'stored_key': key, 'status': status,
               'independent_recall_verified': True, 'document': str(request_path),
               'readback': str(output.with_suffix('.recall.json')), 'recommendation_sha256': file_hash(recommendation)}
    output.write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    try:
        app()
    except (ValueError, OSError, httpx.HTTPError) as exc:
        logger.error('{}', exc)
        raise SystemExit(1)
