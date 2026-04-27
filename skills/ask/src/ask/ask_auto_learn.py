"""Auto-learn support for the ask skill."""

import time

from loguru import logger as log

from .monitor import AskMonitor
from .persona import detect_persona
from .persona_routing import extract_persona_from_question
from .pipeline import learn as learn_func
from .skills_exec import parse_memory_output, run_memory_recall

def _auto_learn(
    result: dict,
    question: str,
    scope: str,
    collection: str,
    k: int,
    use_bridges: bool,
) -> dict:
    """Trigger the learn pipeline when no knowledge is found, then re-query."""
    detected_persona = extract_persona_from_question(question)
    learn_topic = detected_persona if detected_persona else question

    log.info(
        "No knowledge found -- triggering auto-learn for q=%r scope=%r (topic=%r, persona=%s)",
        question, scope, learn_topic, detected_persona is not None,
    )

    if detected_persona:
        print(f"\n  No knowledge found. Detected persona: {detected_persona}")
        print(f'  Auto-learning about "{detected_persona}" (from question)')
    else:
        print(f'\n  No knowledge found. Auto-learning about "{question}"...')
    print(f"  (scope={scope}, collection={collection})")
    print()

    monitor = AskMonitor(
        topic=learn_topic,
        scope=scope,
        name="ask-auto-learn",
    )

    learn_stats = learn_func(
        topic=learn_topic,
        scope=scope,
        collection=collection,
        monitor=monitor,
    )

    result["auto_learned"] = True
    result["detected_persona"] = detected_persona
    result["learn_stats"] = {
        "topic": learn_topic,
        "is_persona": detect_persona(learn_topic),
        "books_discovered": learn_stats.get("books_discovered", 0),
        "youtube_ingested": learn_stats.get("youtube_ingested", 0),
        "qra_extracted": learn_stats.get("qra_extracted", 0),
        "stored": learn_stats.get("stored", 0),
    }

    # Re-query after learning
    if learn_stats.get("stored", 0) > 0:
        log.info("Auto-learn stored %d items -- re-querying memory", learn_stats["stored"])
        print("\n  Re-querying after learning...")

        time.sleep(2)

        requery_result = run_memory_recall(question, scope, k)
        if requery_result["returncode"] == 0:
            new_items = parse_memory_output(requery_result["stdout"])
            result["items"].extend(new_items)
            log.info("Re-query: %d items found after auto-learn", len(new_items))
        else:
            log.warning("Re-query failed after auto-learn")

        # Bridge traversal on new knowledge
        if use_bridges and result["bridges_found"]:
            for bridge in result["bridges_found"]:
                bridge_query = f"{question} {bridge.lower()}"
                bridge_result = run_memory_recall(bridge_query, scope, k=3, timeout=10)
                if bridge_result["returncode"] == 0:
                    bridge_items = parse_memory_output(bridge_result["stdout"])
                    existing_problems = {i.get("problem", "") for i in result["items"]}
                    for item in bridge_items:
                        if item.get("problem", "") not in existing_problems:
                            item["via_bridge"] = bridge
                            result["items"].append(item)
                            existing_problems.add(item.get("problem", ""))

    return result
