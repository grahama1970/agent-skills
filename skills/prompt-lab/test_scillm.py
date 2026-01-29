#!/usr/bin/env python3
"""Debug scillm call."""
import os
import asyncio
import json
from pathlib import Path

# Load env
env_file = Path('/home/graham/workspace/experiments/sparta/.env')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"\'')

print('Env check:')
print('  CHUTES_API_BASE:', os.environ.get('CHUTES_API_BASE', 'NOT SET'))
print('  CHUTES_TEXT_MODEL:', os.environ.get('CHUTES_TEXT_MODEL', 'NOT SET'))

from scillm import parallel_acompletions

async def test():
    req = {
        'model': os.environ['CHUTES_TEXT_MODEL'],
        'messages': [
            {'role': 'system', 'content': '''You are a taxonomy classifier. Return ONLY valid JSON in this format: {"conceptual": ["tag"], "tactical": ["tag"], "confidence": 0.9}'''},
            {'role': 'user', 'content': 'Control: Registry Run Keys\nDescription: Adversaries achieve persistence by adding a program to startup.'},
        ],
        'response_format': {'type': 'json_object'},
        'max_tokens': 256,
        'temperature': 0,
    }
    print('Request model:', req['model'])

    results = await parallel_acompletions(
        [req],
        api_base=os.environ['CHUTES_API_BASE'],
        api_key=os.environ['CHUTES_API_KEY'],
        custom_llm_provider='openai_like',
        concurrency=1,
        timeout=30,
        wall_time_s=60,
        tenacious=False,
    )
    print('Results:')
    for r in results:
        print('  error:', r.get('error'))
        print('  status:', r.get('status'))
        print('  content:', r.get('content'))

if __name__ == '__main__':
    asyncio.run(test())
