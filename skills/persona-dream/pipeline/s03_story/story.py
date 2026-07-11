#!/usr/bin/env python3
"""s03_story — Build a story contract from an idea contract and memory residue.

Consumes idea_contract.json + residue_links.json → produces story_contract.json
that conforms to persona_dream.story_contract.v1.

The story is synthesized by scillm, weaving the dream idea with memory residue
into a narrative with identified speaking characters and target duration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SCHEMA = "persona_dream.story_contract.v1"
SCILLM_URL = os.environ.get("SCILLM_URL", "http://127.0.0.1:4001")
SCILLM_KEY = os.environ.get("SCILLM_KEY", "sk-dev-proxy-123")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_id(seed: str) -> str:
    slug = seed.lower().replace(" ", "_").replace("/", "_")[:40]
    return f"{slug}_{int(time.time())}"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_story_prompt(
    idea: str,
    residue_texts: list[str],
    persona_ids: list[str],
) -> str:
    parts = [
        f"Write a short story from the perspective of {', '.join(persona_ids)}.",
        "",
        "Rules:",
        "- Weave the dream idea and ALL memory fragments below into one coherent narrative.",
        "- The tone should feel personal and reflective, as if the persona is remembering a meaningful moment.",
        "- Identify at least one speaking character (who talks in the story).",
        "- Keep it under 500 words. No bullet points. No meta-commentary. Just the story.",
        "",
        "--- DREAM IDEA ---",
        idea,
    ]

    if residue_texts:
        parts.append("")
        parts.append("--- MEMORY FRAGMENTS TO INCORPORATE ---")
        for i, text in enumerate(residue_texts, 1):
            parts.append(f"Fragment {i}: {text[:400]}")

    return "\n".join(parts)


def _parse_story_contract(
    seed: str,
    idea_contract: dict[str, Any],
    story_text: str,
) -> dict[str, Any]:
    """Parse the LLM story output into a story contract.

    The story text may contain a trailing JSON block with metadata.
    If not, the speaking characters and duration are extracted heuristically.
    """
    metadata = {"speaking_characters": ["unnamed_narrator"], "target_duration_s": 60}

    lines = story_text.strip().splitlines()
    if lines and lines[-1].strip().startswith("{"):
        try:
            meta_block = json.loads(lines[-1])
            if "speaking_characters" in meta_block:
                metadata["speaking_characters"] = meta_block["speaking_characters"]
            if "target_duration_s" in meta_block:
                metadata["target_duration_s"] = meta_block["target_duration_s"]
            story_text = "\n".join(lines[:-1]).strip()
        except json.JSONDecodeError:
            pass

    return {
        "schema": SCHEMA,
        "artifact_id": _artifact_id(seed),
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "input_idea_contract": idea_contract.get("artifact_id", ""),
        "seed": seed,
        "story": story_text,
        "target_duration_s": metadata["target_duration_s"],
        "speaking_characters": metadata["speaking_characters"],
    }


def synthesize_story(
    idea: str,
    residue_texts: list[str],
    persona_ids: list[str],
    *,
    model: str = "gpt-5.5",
    timeout: float = 120.0,
) -> str:
    """Call scillm to synthesize a story from the idea and memory residue."""
    prompt = _build_story_prompt(idea, residue_texts, persona_ids)
    try:
        response = httpx.post(
            f"{SCILLM_URL.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_KEY}",
                "X-Caller-Skill": "persona-dream-s03-story",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
        return content
    except Exception as exc:
        print(f"scillm call failed: {exc}", file=sys.stderr)
        return f"A story about {idea[:300]}."


def build_contract(
    idea_contract: dict[str, Any],
    residue_links: dict[str, Any],
    persona_ids: list[str],
    *,
    model: str = "gpt-5.5",
    scillm_timeout: float = 120.0,
) -> dict[str, Any]:
    idea = idea_contract.get("idea", "")
    seed = idea[:80]

    residue_texts: list[str] = []
    for entry in residue_links.get("residue", []):
        text = entry.get("text", "")
        if text:
            residue_texts.append(text)
    for entry in residue_links.get("contradictions", []):
        text = entry.get("text_a", "") or entry.get("text_b", "")
        if text:
            residue_texts.append(text)

    story_text = synthesize_story(
        idea, residue_texts, persona_ids,
        model=model, timeout=scillm_timeout,
    )

    return _parse_story_contract(seed, idea_contract, story_text)


def main() -> None:
    parser = argparse.ArgumentParser(description="s03_story — Build story contract from idea + residue")
    parser.add_argument("--idea", required=True, type=Path, help="Path to idea_contract.json")
    parser.add_argument("--residue", required=True, type=Path, help="Path to residue_links.json")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for story_contract.json")
    parser.add_argument("--persona-ids", nargs="*", default=["persona"], help="Persona ID(s) for perspective")
    parser.add_argument("--model", default="gpt-5.5", help="scillm model for story generation")
    parser.add_argument("--scillm-timeout", type=float, default=120.0, help="scillm request timeout")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    idea_contract = _load_json(args.idea)
    residue_links = _load_json(args.residue)

    contract = build_contract(
        idea_contract, residue_links, args.persona_ids,
        model=args.model, scillm_timeout=args.scillm_timeout,
    )

    out_path = args.out / "story_contract.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}")
    print(f"  story: {len(contract['story'])} chars, {contract['target_duration_s']}s, speaking: {contract['speaking_characters']}")


if __name__ == "__main__":
    main()
