# s01 Idea

Generates a persona dream idea contract.

## Behavior

- **Seed mode** (`--seed`): records a human/project-agent supplied idea.
- **Autonomous mode** (default): samples memory, generates candidate ideas, and uses a subagent selector to choose the best one.

## Inputs

- `--persona` (required): comma-separated persona IDs, e.g. `horus,embry`
- `--about` (optional): topic bias for memory recall
- `--seed` (optional): forces seed mode
- `--memory-url` (optional): memory service URL or UDS path
- `--selector` (optional): `scillm` (default) or `impact` fallback

## Output

`idea_contract.json` → consumed by s02 Memories / s03 Story

## Contract schema

`contracts/idea_contract.schema.json`

## Usage

```bash
# Autonomous idea generation
python pipeline/s01_idea/idea.py --persona horus,embry --about "SPARTA evidence cases"

# Seed mode
python pipeline/s01_idea/idea.py --persona embry --seed "A dream about learning to surf from her father"
```
