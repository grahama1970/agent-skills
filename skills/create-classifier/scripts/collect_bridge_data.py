#!/usr/bin/env python3
"""Collect training data for bridge classifier from memory extractions.

Mines labeled examples from:
1. Existing taxonomy extractions in ArangoDB (documents with bridges field)
2. QRA pairs with taxonomy tags
3. Synthetic augmentation using scillm

Usage:
    python collect_bridge_data.py \
        --output data/bridge_classifier/raw.jsonl \
        --min-per-class 200 \
        --augment

Output format (JSONL):
    {"text": "How does stress affect decisions", "labels": ["Resilience", "Fragility"]}
"""

import os
import typer
import json
import random
import subprocess
from pathlib import Path

from loguru import logger
import httpx

# Federated Taxonomy bridges
BRIDGE_LABELS = [
    "Corruption",
    "Precision",
    "Resilience",
    "Fragility",
    "Loyalty",
    "Stealth",
]

# Keywords associated with each bridge (for synthetic data)
BRIDGE_KEYWORDS = {
    "Corruption": [
        "moral decay", "entropy", "power dynamics", "institutional failure",
        "bias", "manipulation", "exploitation", "decay", "erosion", "corruption",
        "abuse of power", "unethical", "compromised", "degradation",
    ],
    "Precision": [
        "exactness", "clarity", "measurement", "accuracy", "scientific method",
        "precise", "detailed", "specific", "quantitative", "metrics",
        "typography", "accessibility", "usability", "standards", "compliance",
        "WCAG", "contrast ratio", "font size", "touch target",
    ],
    "Resilience": [
        "recovery", "adaptation", "stress response", "neuroplasticity",
        "bounce back", "robust", "fault tolerant", "redundancy", "healing",
        "coping", "adaptive", "flexible", "durable", "persistence",
    ],
    "Fragility": [
        "vulnerability", "trauma", "system failure", "breaking point",
        "fragile", "brittle", "weakness", "sensitive", "exposed",
        "risk", "failure mode", "edge case", "crash", "breakdown",
    ],
    "Loyalty": [
        "trust", "commitment", "relationship dynamics", "allegiance",
        "faithful", "devoted", "reliable", "consistent", "dependable",
        "partnership", "collaboration", "team", "bond", "connection",
    ],
    "Stealth": [
        "hidden operations", "unconscious processes", "covert", "implicit",
        "subtle", "unnoticed", "background", "invisible", "latent",
        "subliminal", "indirect", "masked", "concealed", "quiet",
    ],
}

# Example queries for each bridge (seed data)
BRIDGE_EXAMPLES = {
    "Corruption": [
        "How do power dynamics affect organizational ethics?",
        "What causes institutional decay over time?",
        "How can we detect bias in decision-making systems?",
        "What are signs of moral erosion in leadership?",
    ],
    "Precision": [
        "What is the correct contrast ratio for accessibility?",
        "How should typography be scaled for different viewing distances?",
        "What are WCAG guidelines for touch targets?",
        "How do we measure usability precisely?",
        "What font size is readable at 10 feet?",
    ],
    "Resilience": [
        "How does stress affect neuroplasticity?",
        "What makes systems fault tolerant?",
        "How do people recover from trauma?",
        "What builds adaptive capacity in teams?",
    ],
    "Fragility": [
        "What are common system failure modes?",
        "How do we identify vulnerability in designs?",
        "What edge cases cause crashes?",
        "Where are the breaking points in this architecture?",
    ],
    "Loyalty": [
        "How do we build trust with users?",
        "What creates strong team bonds?",
        "How do relationships affect collaboration?",
        "What makes partnerships succeed long-term?",
    ],
    "Stealth": [
        "What unconscious biases affect design decisions?",
        "How do implicit processes influence behavior?",
        "What hidden operations run in the background?",
        "How do subtle cues affect user perception?",
    ],
}


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def extract_bridges_from_text(text: str) -> list[str]:
    """Extract likely bridges from text using keyword matching."""
    text_lower = text.lower()
    bridges = []
    for bridge, keywords in BRIDGE_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            bridges.append(bridge)
    return bridges


def collect_from_memory(limit: int = 5000) -> list[dict]:
    """Collect labeled examples from memory via /memory sample."""
    examples = []

    collections_to_check = ["lessons", "qra_pairs", "persona_knowledge", "taxonomy_extractions"]

    for collection in collections_to_check:
        try:
            results = _memory_cmd([
                "sample", "--collection", collection,
                "--filter", "bridges!=null",
                "--random", "--limit", str(limit),
            ])
            docs = results if isinstance(results, list) else results.get("results", [])

            for doc in docs:
                # Pick the best text field available
                text = doc.get("problem") or doc.get("question") or doc.get("text") or doc.get("content")
                bridges = doc.get("bridges")
                if not text or not bridges:
                    continue

                if isinstance(bridges, dict):
                    labels = [k for k, v in bridges.items() if v and v > 0.3]
                elif isinstance(bridges, list):
                    labels = bridges
                else:
                    continue

                if labels:
                    examples.append({
                        "text": text,
                        "labels": labels,
                        "source": collection,
                    })
        except Exception as e:
            logger.warning(f"Error querying {collection}: {e}")

    logger.info(f"Collected {len(examples)} examples from memory")
    return examples


def generate_synthetic_examples(min_per_class: int = 200) -> list[dict]:
    """Generate synthetic examples from seed data and keywords."""
    examples = []

    # Use seed examples
    for bridge, seed_texts in BRIDGE_EXAMPLES.items():
        for text in seed_texts:
            examples.append({
                "text": text,
                "labels": [bridge],
                "source": "seed",
            })

    # Generate variations using keywords
    templates = [
        "How does {kw} affect system design?",
        "What is the impact of {kw}?",
        "Can you explain {kw} in this context?",
        "How should we handle {kw}?",
        "What does research say about {kw}?",
        "Best practices for dealing with {kw}",
        "{kw} considerations for UX",
        "Understanding {kw} in complex systems",
    ]

    for bridge, keywords in BRIDGE_KEYWORDS.items():
        for kw in keywords[:8]:  # Limit keywords per bridge
            for template in templates:
                text = template.format(kw=kw)
                examples.append({
                    "text": text,
                    "labels": [bridge],
                    "source": "synthetic",
                })

    # Generate multi-label examples (combinations)
    multi_label_templates = [
        ("How do {kw1} and {kw2} interact?", 2),
        ("Relationship between {kw1}, {kw2}, and {kw3}", 3),
        ("Balancing {kw1} with {kw2}", 2),
    ]

    bridge_list = list(BRIDGE_KEYWORDS.keys())
    for template, n_bridges in multi_label_templates:
        for _ in range(50):  # Generate 50 examples per template
            selected_bridges = random.sample(bridge_list, n_bridges)
            kws = {f"kw{i+1}": random.choice(BRIDGE_KEYWORDS[b])
                   for i, b in enumerate(selected_bridges)}
            text = template.format(**kws)
            examples.append({
                "text": text,
                "labels": selected_bridges,
                "source": "synthetic_multi",
            })

    logger.info(f"Generated {len(examples)} synthetic examples")
    return examples


def augment_with_scillm(examples: list[dict], variations_per_example: int = 3) -> list[dict]:
    """Use scillm to generate question variations."""
    logger.info("Augmenting with scillm variations...")

    augmented = []
    # Sample subset to augment (expensive operation)
    sample = random.sample(examples, min(100, len(examples)))

    for ex in sample:
        prompt = f"""Generate {variations_per_example} different ways to ask this question.
Keep the same meaning but vary the phrasing, formality, and specificity.

Original: {ex['text']}

Return one variation per line, no numbering."""

        try:
            result = subprocess.run(
                ["scillm", "complete", "--model", "haiku", "-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0:
                variations = result.stdout.strip().split("\n")
                for v in variations[:variations_per_example]:
                    v = v.strip()
                    if v and len(v) > 10:
                        augmented.append({
                            "text": v,
                            "labels": ex["labels"],
                            "source": "scillm_augment",
                        })
        except Exception as e:
            logger.debug(f"scillm augmentation failed: {e}")

    logger.info(f"Augmented with {len(augmented)} variations")
    return augmented


def balance_classes(examples: list[dict], min_per_class: int) -> list[dict]:
    """Balance classes by oversampling minority classes."""
    # Count examples per class
    class_counts = {bridge: 0 for bridge in BRIDGE_LABELS}
    for ex in examples:
        for label in ex["labels"]:
            if label in class_counts:
                class_counts[label] += 1

    logger.info(f"Class distribution before balancing: {class_counts}")

    # Find examples for each class
    class_examples = {bridge: [] for bridge in BRIDGE_LABELS}
    for ex in examples:
        for label in ex["labels"]:
            if label in class_examples:
                class_examples[label].append(ex)

    # Oversample minority classes
    balanced = list(examples)
    for bridge, count in class_counts.items():
        if count < min_per_class and class_examples[bridge]:
            needed = min_per_class - count
            to_add = random.choices(class_examples[bridge], k=needed)
            balanced.extend(to_add)
            logger.info(f"Oversampled {bridge}: +{needed} examples")

    return balanced


def split_data(examples: list[dict], train_ratio: float = 0.85) -> tuple[list, list]:
    """Split into train and validation sets."""
    random.shuffle(examples)
    split_idx = int(len(examples) * train_ratio)
    return examples[:split_idx], examples[split_idx:]


app = typer.Typer(help="Collect bridge classifier training data")


@app.command()
def main(
    output: Path = typer.Option(Path("data/bridge_classifier/raw.jsonl"), help="Output path for raw JSONL"),
    min_per_class: int = typer.Option(200, help="Minimum examples per class"),
    augment: bool = typer.Option(False, help="Use scillm augmentation"),
    split: bool = typer.Option(False, help="Also generate train/val split"),
    train_ratio: float = typer.Option(0.85, help="Training set ratio"),
    seed: int = typer.Option(42, help="Random seed"),
):
    random.seed(seed)

    # Collect from all sources
    all_examples = []

    # 1. Collect from memory via /memory subprocess
    try:
        memory_examples = collect_from_memory()
        all_examples.extend(memory_examples)
    except Exception as e:
        logger.warning(f"Memory collection failed: {e}")

    # 2. Generate synthetic examples
    synthetic_examples = generate_synthetic_examples(min_per_class)
    all_examples.extend(synthetic_examples)

    # 3. Augment with scillm (optional)
    if augment:
        augmented = augment_with_scillm(all_examples)
        all_examples.extend(augmented)

    # 4. Balance classes
    balanced_examples = balance_classes(all_examples, min_per_class)

    # Deduplicate by text
    seen = set()
    unique_examples = []
    for ex in balanced_examples:
        if ex["text"] not in seen:
            seen.add(ex["text"])
            unique_examples.append(ex)

    logger.info(f"Final dataset: {len(unique_examples)} unique examples")

    # Save
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for ex in unique_examples:
            f.write(json.dumps({"text": ex["text"], "labels": ex["labels"]}) + "\n")

    logger.info(f"Saved to {output}")

    # Split if requested
    if split:
        train, val = split_data(unique_examples, train_ratio)

        train_path = output.parent / "train.jsonl"
        val_path = output.parent / "val.jsonl"

        with open(train_path, "w") as f:
            for ex in train:
                f.write(json.dumps({"text": ex["text"], "labels": ex["labels"]}) + "\n")

        with open(val_path, "w") as f:
            for ex in val:
                f.write(json.dumps({"text": ex["text"], "labels": ex["labels"]}) + "\n")

        logger.info(f"Split: {len(train)} train, {len(val)} val")
        logger.info(f"Saved to {train_path} and {val_path}")


if __name__ == "__main__":
    app()
