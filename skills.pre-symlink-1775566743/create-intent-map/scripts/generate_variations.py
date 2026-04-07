#!/usr/bin/env python3
"""Generate question variations for intent mapper training.

Creates diverse phrasings of the same query to improve model robustness:
- Layperson: Non-technical phrasing
- Project Manager: Risk/compliance focused
- Security Expert: MITRE ATT&CK terminology
- Reversal: Different word order, same meaning

Usage:
    python generate_variations.py --input data/sft/train_from_qra.json \
        --output data/sft/train_augmented.jsonl \
        --sample 500 \
        --batch-size 50
"""

import json
import random
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from pydantic import BaseModel

# Ensure scillm is importable
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SKILLS_DIR / "scillm") not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR / "scillm"))

app = typer.Typer()

# Variation generation prompt
VARIATION_SYSTEM_PROMPT = """You are a query variation generator for a space cybersecurity knowledge base (SPARTA).

Given an original query and its target QuerySpec, generate 4 alternative phrasings that should produce the SAME QuerySpec output.

Output JSON with exactly these fields:
{
  "layperson": "Non-technical phrasing a beginner would use",
  "project_manager": "Risk/compliance focused, business language",
  "security_expert": "Uses MITRE ATT&CK IDs, technical jargon",
  "reversal": "Same meaning, different word order/structure"
}

Rules:
- All variations must map to the SAME intent (action, entities, tier1 tags)
- Layperson should avoid acronyms and technical terms
- Project manager focuses on "risk", "compliance", "mitigation", "controls"
- Security expert uses T-xxxx technique IDs, CWE-xxx, formal terminology
- Reversal changes structure but keeps meaning (e.g., "detect X" → "X detection methods")
- Keep variations realistic - these are queries a human would actually ask"""

VARIATION_USER_TEMPLATE = """Original query: {query}

Target QuerySpec:
{spec}

Generate 4 variations that should produce the same QuerySpec."""


class VariationOutput(BaseModel):
    layperson: str
    project_manager: str
    security_expert: str
    reversal: str


class ScillmClient:
    """Client for scillm batch completions via Chutes (delegates to scillm skill)."""

    def __init__(self, base_url: str = os.environ.get("SCILLM_API_BASE", "http://localhost:4001")):
        from batch import quick_completion
        self._quick_completion = quick_completion

    def complete(
        self,
        messages: list[dict],
        model: str = "deepseek-ai/DeepSeek-V3",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """Single completion call via scillm."""
        system = None
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            elif msg["role"] == "user":
                prompt = msg["content"]
        return self._quick_completion(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60,
        )

    def batch_complete(
        self,
        prompts: list[tuple[str, str]],  # (query, spec_json)
        model: str = "deepseek-ai/DeepSeek-V3",
        temperature: float = 0.7,
    ) -> list[Optional[VariationOutput]]:
        """Batch completion for variations."""
        results = []
        for query, spec_json in prompts:
            messages = [
                {"role": "system", "content": VARIATION_SYSTEM_PROMPT},
                {"role": "user", "content": VARIATION_USER_TEMPLATE.format(
                    query=query, spec=spec_json
                )},
            ]
            try:
                response = self.complete(messages, model, temperature)
                parsed = self._parse_json(response)
                if parsed:
                    results.append(VariationOutput(**parsed))
                else:
                    results.append(None)
            except Exception as e:
                logger.warning(f"Failed to generate variations for: {query[:50]}... Error: {e}")
                results.append(None)
        return results

    def _parse_json(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        import re
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None


def load_training_data(path: Path) -> list[dict]:
    """Load training data from JSON or JSONL."""
    logger.info(f"Loading training data from {path}")

    with open(path) as f:
        if path.suffix == ".json":
            data = json.load(f)
        else:  # jsonl
            data = [json.loads(line) for line in f]

    logger.info(f"Loaded {len(data)} examples")
    return data


def sample_for_variation(
    data: list[dict],
    n: int,
    seed: int = 42,
) -> list[dict]:
    """Sample examples for variation generation.

    Prioritizes diversity:
    - Mix of QUERY, NO_MATCH, CLARIFY actions
    - Variety of tier1 tags
    - Different entity types
    """
    random.seed(seed)

    # Group by action type
    by_action = {"QUERY": [], "NO_MATCH": [], "CLARIFY": []}
    for item in data:
        output = item.get("output", {})
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except Exception:
                continue
        action = output.get("action", "QUERY")
        by_action.get(action, by_action["QUERY"]).append(item)

    # Sample proportionally
    sampled = []

    # 80% QUERY, 15% NO_MATCH, 5% CLARIFY
    n_query = int(n * 0.80)
    n_no_match = int(n * 0.15)
    n_clarify = n - n_query - n_no_match

    if by_action["QUERY"]:
        sampled.extend(random.sample(by_action["QUERY"], min(n_query, len(by_action["QUERY"]))))
    if by_action["NO_MATCH"]:
        sampled.extend(random.sample(by_action["NO_MATCH"], min(n_no_match, len(by_action["NO_MATCH"]))))
    if by_action["CLARIFY"]:
        sampled.extend(random.sample(by_action["CLARIFY"], min(n_clarify, len(by_action["CLARIFY"]))))

    random.shuffle(sampled)
    logger.info(f"Sampled {len(sampled)} examples for variation generation")
    return sampled


def generate_variations_batch(
    data: list[dict],
    client: ScillmClient,
    batch_size: int = 50,
    output_path: Optional[Path] = None,
) -> list[dict]:
    """Generate variations for all examples in batches."""
    all_augmented = []

    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1}/{(len(data) + batch_size - 1) // batch_size}")

        # Prepare prompts
        prompts = []
        for item in batch:
            query = item["input"]
            output = item["output"]
            if isinstance(output, dict):
                spec_json = json.dumps(output, indent=2)
            else:
                spec_json = output
            prompts.append((query, spec_json))

        # Generate variations
        variations = client.batch_complete(prompts)

        # Create augmented examples
        for item, var in zip(batch, variations):
            # Always include original
            all_augmented.append(item)

            if var is None:
                continue

            # Add variations with same output
            for style in ["layperson", "project_manager", "security_expert", "reversal"]:
                varied_query = getattr(var, style)
                if varied_query and varied_query.strip():
                    all_augmented.append({
                        "input": varied_query,
                        "output": item["output"],
                        "variation_of": item["input"],
                        "variation_style": style,
                    })

        # Checkpoint save
        if output_path:
            with open(output_path, "w") as f:
                for aug in all_augmented:
                    f.write(json.dumps(aug) + "\n")
            logger.info(f"Checkpoint saved: {len(all_augmented)} examples")

    return all_augmented


@app.command()
def generate(
    input_file: Path = typer.Option(..., "--input", "-i", help="Input training data (JSON/JSONL)"),
    output_file: Path = typer.Option(..., "--output", "-o", help="Output augmented data (JSONL)"),
    sample: int = typer.Option(500, "--sample", "-n", help="Number of examples to augment"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Batch size for API calls"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed for sampling"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without API calls"),
):
    """Generate question variations for training data augmentation."""

    # Load data
    data = load_training_data(input_file)

    # Sample for variation
    sampled = sample_for_variation(data, sample, seed)

    if dry_run:
        logger.info("DRY RUN - showing sample of what would be processed:")
        for item in sampled[:5]:
            logger.info(f"  Query: {item['input'][:80]}...")
        logger.info(f"Total: {len(sampled)} examples would generate ~{len(sampled) * 5} augmented examples")
        return

    # Initialize client
    client = ScillmClient()

    # Generate variations
    output_file.parent.mkdir(parents=True, exist_ok=True)
    augmented = generate_variations_batch(sampled, client, batch_size, output_file)

    logger.info(f"Generated {len(augmented)} total examples (original + variations)")
    logger.info(f"Saved to {output_file}")


@app.command()
def stats(
    input_file: Path = typer.Option(..., "--input", "-i", help="Augmented data file (JSONL)"),
):
    """Show statistics about augmented training data."""

    with open(input_file) as f:
        data = [json.loads(line) for line in f]

    # Count by variation style
    by_style = {"original": 0, "layperson": 0, "project_manager": 0, "security_expert": 0, "reversal": 0}
    for item in data:
        style = item.get("variation_style", "original")
        by_style[style] = by_style.get(style, 0) + 1

    print(f"\nAugmented Data Statistics:")
    print(f"{'='*40}")
    print(f"Total examples: {len(data)}")
    print(f"\nBy variation style:")
    for style, count in sorted(by_style.items(), key=lambda x: -x[1]):
        print(f"  {style:20} {count:5} ({100*count/len(data):.1f}%)")


@app.command()
def validate(
    input_file: Path = typer.Option(..., "--input", "-i", help="Augmented data file (JSONL)"),
    check_duplicates: bool = typer.Option(True, "--check-duplicates", help="Check for duplicate queries"),
):
    """Validate augmented training data."""

    with open(input_file) as f:
        data = [json.loads(line) for line in f]

    issues = []

    # Check for empty queries
    empty = [i for i, d in enumerate(data) if not d.get("input", "").strip()]
    if empty:
        issues.append(f"Empty queries at indices: {empty[:10]}...")

    # Check for duplicates
    if check_duplicates:
        queries = [d["input"].lower().strip() for d in data]
        seen = {}
        duplicates = []
        for i, q in enumerate(queries):
            if q in seen:
                duplicates.append((i, seen[q]))
            else:
                seen[q] = i
        if duplicates:
            issues.append(f"Found {len(duplicates)} duplicate queries")

    # Check output format
    bad_outputs = []
    for i, d in enumerate(data):
        output = d.get("output")
        if output is None:
            bad_outputs.append(i)
            continue
        if isinstance(output, str):
            try:
                json.loads(output)
            except Exception:
                bad_outputs.append(i)
    if bad_outputs:
        issues.append(f"Invalid output JSON at {len(bad_outputs)} indices")

    if issues:
        print("Validation Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("Validation passed!")

    print(f"\nTotal examples: {len(data)}")


if __name__ == "__main__":
    app()
