#!/usr/bin/env python3
"""Analyze disagreements between keyword scorer and LLM predictions."""

import json
import asyncio
import os
from pathlib import Path

SKILL_DIR = Path(__file__).parent

# Load ground truth
gt = json.loads((SKILL_DIR / 'ground_truth/taxonomy_large.json').read_text())

# Load prompt
prompt_file = SKILL_DIR / 'prompts/taxonomy_v2.txt'
content = prompt_file.read_text()
parts = content.split('[USER]')
system = parts[0].replace('[SYSTEM]', '').strip()
user_template = parts[1].strip()

# Load model config
models = json.loads((SKILL_DIR / 'models.json').read_text())
model_config = models['deepseek-v3.2']

# Import scillm
from scillm.batch import parallel_acompletions

api_base = os.environ.get('CHUTES_API_BASE', '').strip('"\'')
api_key = os.environ.get('CHUTES_API_KEY', '').strip('"\'')
model_id = model_config.get('model')

# Test first 15 cases and show disagreements
cases = gt['cases'][:15]

async def run():
    disagreements = []

    for c in cases:
        name = c['input']['name']
        desc = c['input']['description'][:300]
        expected_c = c['expected']['conceptual']
        expected_t = c['expected']['tactical']
        collection = c['metadata']['collection']

        user_msg = f"Control: {name}\n\nDescription: {desc}"

        req = {
            'model': model_id,
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user_msg},
            ],
            'response_format': {'type': 'json_object'},
            'max_tokens': 256,
            'temperature': 0,
        }

        try:
            resp = await parallel_acompletions(
                [req], api_base=api_base, api_key=api_key,
                custom_llm_provider='openai_like', concurrency=1,
                timeout=30, wall_time_s=60, tenacious=False,
            )

            if resp and not resp[0].get('error'):
                result = resp[0].get('content', {})
                if isinstance(result, str):
                    result = json.loads(result)
                pred_c = result.get('conceptual', [])
                pred_t = result.get('tactical', [])

                # Check for disagreement
                c_match = set(pred_c) == set(expected_c)
                t_match = set(pred_t) == set(expected_t)

                if not c_match or not t_match:
                    disagreements.append({
                        'id': c['id'],
                        'collection': collection,
                        'name': name,
                        'desc_snippet': desc[:100],
                        'keyword_scorer': {'c': expected_c, 't': expected_t},
                        'llm_pred': {'c': pred_c, 't': pred_t},
                    })
        except Exception as e:
            print(f"Error on {c['id']}: {e}")

    print(f"\n{'='*60}")
    print(f"Analyzed {len(cases)} cases, found {len(disagreements)} disagreements")
    print(f"{'='*60}\n")

    for d in disagreements:
        print(f"\n=== {d['id']} ({d['collection']}) ===")
        print(f"Name: {d['name']}")
        print(f"Desc: {d['desc_snippet']}...")
        print(f"Keyword Scorer: C={d['keyword_scorer']['c']} T={d['keyword_scorer']['t']}")
        print(f"LLM Prediction: C={d['llm_pred']['c']} T={d['llm_pred']['t']}")

if __name__ == '__main__':
    asyncio.run(run())
