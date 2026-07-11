# s03 Story

Builds a story contract from memory residue and the idea.

## Input

- `residue_links.json` (from s02)
- `idea_contract.json` (from s01)

## Output

`story_contract.json` → consumed by s04 Voice and s05 Panels

## Contract schema

`schemas/story_contract.schema.json`

## Usage

```bash
python story.py \
  --idea ../s01_idea/idea_contract.json \
  --residue ../s02_memories/residue_links.json \
  --out . \
  --persona-ids horus_lupercal \
  --model gpt-5.5
```

The story is synthesized by scillm (configurable via `SCILLM_URL` and
`SCILLM_KEY` env vars, defaults to `http://127.0.0.1:4001` and
`sk-dev-proxy-123`).  A trailing JSON block on the last line of the
generated story is parsed for `speaking_characters` and
`target_duration_s` metadata.
