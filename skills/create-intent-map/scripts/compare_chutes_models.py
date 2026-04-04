#!/usr/bin/env python3
"""Compare Chutes models for QuerySpec generation quality.

Tests different models to find the best performing (lowest params that work well).
"""

import json
import os
import time
from dataclasses import dataclass

import httpx
from loguru import logger

# Test cases with expected outputs
TEST_CASES = [
    {
        "id": "rf_jamming",
        "query": "How do I detect RF jamming attacks on satellite communications?",
        "expected_action": "QUERY",
        "expected_tier1": ["Detect"],
    },
    {
        "id": "weather_oos",
        "query": "What's the weather forecast for tomorrow?",
        "expected_action": "NO_MATCH",
    },
    {
        "id": "t1071",
        "query": "What controls mitigate T1071 application layer protocol attacks?",
        "expected_action": "QUERY",
        "expected_entities": ["T1071"],
    },
    {
        "id": "ambiguous",
        "query": "How do I make it more secure?",
        "expected_action": "CLARIFY",
    },
    {
        "id": "cwe_787",
        "query": "How can CWE-787 buffer overflow vulnerabilities be prevented in spacecraft software?",
        "expected_action": "QUERY",
        "expected_entities": ["CWE-787"],
    },
]

# Models to test (ordered by approximate cost/size)
MODELS_TO_TEST = [
    # Smaller/cheaper first
    ("Qwen/Qwen3-14B", "14B", 0.05),
    ("Qwen/Qwen2.5-Coder-32B-Instruct", "32B", 0.03),
    ("Qwen/Qwen3-32B", "32B", 0.08),
    ("Qwen/Qwen3-30B-A3B-Instruct-2507", "30B-MoE", 0.08),
    ("deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "70B", 0.03),
    # Larger/more expensive
    ("Qwen/Qwen2.5-72B-Instruct", "72B", 0.30),
    ("deepseek-ai/DeepSeek-V3-0324-TEE", "V3", 0.19),
]

SYSTEM_PROMPT = """You are a SPARTA QuerySpec generator. Convert user questions about space cybersecurity into structured JSON.

CRITICAL: Output ONLY valid JSON. No explanation, no reasoning, no text before or after the JSON.

Output this exact structure:
{
  "action": "QUERY" | "CLARIFY" | "NO_MATCH",
  "scope": "sparta",
  "lanes": ["bm25", "dense"],
  "entities": [],
  "tier0": [],
  "tier1": [],
  "keywords": [],
  "min_grounding": 0.7,
  "k": 12
}

Field Rules:
- action: "QUERY" for valid space/satellite cybersecurity questions
- action: "NO_MATCH" for out-of-scope (weather, recipes, general IT, non-space)
- action: "CLARIFY" for ambiguous questions needing more context
- entities: Extract MITRE ATT&CK IDs (T####), CWE IDs (CWE-###), or SPARTA control IDs (CM-####) if mentioned
- tier0: Conceptual tags from [Corruption, Fragility, Loyalty, Precision, Resilience, Stealth]
- tier1: Tactical tags from [Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore]

Output ONLY the JSON. Nothing else."""


@dataclass
class ModelResult:
    model: str
    size: str
    cost: float
    json_rate: float
    action_accuracy: float
    entity_accuracy: float
    total_time: float
    passed_cases: list
    failed_cases: list


def call_chutes(model: str, query: str) -> tuple[str, float]:
    """Call Chutes API with the given model and query."""
    api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123") or os.environ.get("CHUTES_API_TOKEN")
    if not api_key:
        raise ValueError("SCILLM_PROXY_KEY or CHUTES_API_TOKEN not set")

    start = time.time()

    with httpx.Client(timeout=60) as client:
        response = client.post(
            os.environ.get("SCILLM_API_BASE", "http://localhost:4001") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
        )
        response.raise_for_status()

    elapsed = time.time() - start
    data = response.json()
    content = data["choices"][0]["message"]["content"]

    return content, elapsed


def parse_json_from_response(text: str) -> dict | None:
    """Extract JSON from response, handling potential reasoning traces."""
    import re

    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Try finding JSON object in text
    try:
        # Find first { and match to closing }
        start = text.find('{')
        if start >= 0:
            depth = 0
            for i, char in enumerate(text[start:], start):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[start:i+1])
    except json.JSONDecodeError:
        pass

    return None


def evaluate_response(response: str, expected: dict) -> dict:
    """Evaluate a response against expected values."""
    result = {"raw": response[:300], "json_parsed": False, "errors": []}

    parsed = parse_json_from_response(response)
    if not parsed:
        result["errors"].append("Failed to parse JSON")
        return result

    result["json_parsed"] = True
    result["parsed"] = parsed

    # Check action
    if "expected_action" in expected:
        if parsed.get("action") == expected["expected_action"]:
            result["action_correct"] = True
        else:
            result["action_correct"] = False
            result["errors"].append(f"Action: {parsed.get('action')} vs {expected['expected_action']}")

    # Check entities
    if "expected_entities" in expected:
        found = set(parsed.get("entities", []))
        want = set(expected["expected_entities"])
        if want.issubset(found):
            result["entities_correct"] = True
        else:
            result["entities_correct"] = False
            result["errors"].append(f"Entities: {found} vs {want}")
    else:
        result["entities_correct"] = True  # N/A

    # Check tier1
    if "expected_tier1" in expected:
        found = set(parsed.get("tier1", []))
        want = set(expected["expected_tier1"])
        if want.intersection(found):
            result["tier1_correct"] = True
        else:
            result["tier1_correct"] = False

    return result


def test_model(model: str, size: str, cost: float) -> ModelResult:
    """Test a model on all test cases."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing: {model} ({size})")
    logger.info(f"{'='*60}")

    results = []
    total_time = 0
    passed = []
    failed = []

    for test in TEST_CASES:
        logger.info(f"  Test: {test['id']}")

        try:
            response, elapsed = call_chutes(model, test["query"])
            total_time += elapsed

            eval_result = evaluate_response(response, test)
            eval_result["test_id"] = test["id"]
            eval_result["latency"] = elapsed
            results.append(eval_result)

            if eval_result["json_parsed"] and eval_result.get("action_correct", True):
                passed.append(test["id"])
                logger.success(f"    PASS ({elapsed:.2f}s)")
            else:
                failed.append(test["id"])
                logger.error(f"    FAIL: {eval_result.get('errors', [])[:1]}")

        except Exception as e:
            logger.error(f"    ERROR: {e}")
            failed.append(test["id"])
            results.append({"test_id": test["id"], "error": str(e)})

    # Calculate metrics
    json_rate = sum(1 for r in results if r.get("json_parsed", False)) / len(results)
    action_acc = sum(1 for r in results if r.get("action_correct", False)) / len(results)
    entity_acc = sum(1 for r in results if r.get("entities_correct", False)) / len(results)

    return ModelResult(
        model=model,
        size=size,
        cost=cost,
        json_rate=json_rate,
        action_accuracy=action_acc,
        entity_accuracy=entity_acc,
        total_time=total_time,
        passed_cases=passed,
        failed_cases=failed,
    )


def main():
    logger.info("SPARTA QuerySpec Model Comparison")
    logger.info("=" * 60)

    all_results = []

    for model, size, cost in MODELS_TO_TEST:
        try:
            result = test_model(model, size, cost)
            all_results.append(result)

            # Rate limit between models
            time.sleep(2)

        except Exception as e:
            logger.error(f"Failed to test {model}: {e}")

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY - Models sorted by action accuracy then cost")
    logger.info("=" * 80)

    # Sort by accuracy (desc) then cost (asc)
    all_results.sort(key=lambda r: (-r.action_accuracy, r.cost))

    print(f"\n{'Model':<45} {'Size':<10} {'JSON%':<8} {'Action%':<10} {'Cost':<8} {'Time':<8}")
    print("-" * 90)

    for r in all_results:
        print(f"{r.model:<45} {r.size:<10} {r.json_rate*100:>5.0f}%   {r.action_accuracy*100:>6.0f}%    ${r.cost:<6.2f} {r.total_time:>5.1f}s")

    # Save results
    output = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_cases": len(TEST_CASES),
        "results": [
            {
                "model": r.model,
                "size": r.size,
                "cost": r.cost,
                "json_rate": r.json_rate,
                "action_accuracy": r.action_accuracy,
                "entity_accuracy": r.entity_accuracy,
                "total_time": r.total_time,
                "passed": r.passed_cases,
                "failed": r.failed_cases,
            }
            for r in all_results
        ],
    }

    with open("model_comparison_results.json", "w") as f:
        json.dump(output, f, indent=2)

    logger.info("\nResults saved to model_comparison_results.json")

    # Recommend best model
    if all_results:
        best = all_results[0]
        logger.info(f"\n🏆 RECOMMENDED: {best.model}")
        logger.info(f"   Accuracy: {best.action_accuracy*100:.0f}%, Cost: ${best.cost}/1K tokens")


if __name__ == "__main__":
    main()
