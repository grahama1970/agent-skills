#!/usr/bin/env python3
"""Bad Santa watch canary.

The canary uses Brave-derived public expectations only as verification seeds.
Answers must come from watch extraction/memory evidence first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from video_memory import ask_movie_question  # noqa: E402


MEDIA_TITLE = "Bad Santa (2003)"
MEDIA_SLUG = "badsantaunrated2003brripxvidhd720p-npw"
MEDIA_PATH = "/mnt/storage12tb/media/movies/Bad Santa (2003)/Bad.Santa.Unrated.2003.BRRip.XvidHD.720p-NPW.avi"


CANARIES = [
    {
        "id": "plot_111000_miami",
        "kind": "plot",
        "question": "After stealing $111,000, what does Marcus plan to do, and what does Willie predict will happen?",
        "requires": ["transcript", "watch_content", "media_match"],
        "expected_terms": ["Miami", "car", "place", "bar", "beach", "drink", "next Christmas"],
    },
    {
        "id": "plot_bone_chip",
        "kind": "plot",
        "question": "What injuries does Willie mention in the opening monologue, including the bone chip?",
        "requires": ["transcript", "watch_content", "media_match"],
        "expected_terms": ["eye socket", "kidney", "bone chip", "ankle"],
    },
    {
        "id": "visual_santa_suit",
        "kind": "visual",
        "question": "What visual evidence shows Willie wearing a Santa suit in Bad Santa?",
        "requires": ["frame", "visual_description", "watch_content", "media_match"],
        "expected_terms": ["Santa", "suit", "red", "white"],
    },
    {
        "id": "visual_character_appearance",
        "kind": "visual",
        "question": "What does the Bad Santa character look like in the watched Bad Santa video?",
        "requires": ["frame", "visual_description", "watch_content", "media_match"],
        "expected_terms": ["Santa", "red"],
    },
]


def run_offline() -> dict:
    return {
        "schema": "watch.bad_santa_canary.v1",
        "mode": "offline",
        "media": {"title": MEDIA_TITLE, "slug": MEDIA_SLUG, "path": MEDIA_PATH},
        "status": "contract_ready",
        "canaries": [
            {
                **canary,
                "status": "pending_live_extraction",
                "rule": "Brave may seed expected facts; pass requires extracted watch evidence matching media slug.",
            }
            for canary in CANARIES
        ],
    }


def run_live(use_brave: bool) -> dict:
    results = []
    for canary in CANARIES:
        packet = ask_movie_question(
            canary["question"],
            movie_title=MEDIA_TITLE,
            media_slug=MEDIA_SLUG,
            extra_tags=["visual_evidence"] if canary["kind"] == "visual" else None,
            use_brave=use_brave,
            k=5,
        )
        recall = packet["watch_recall"]
        items = recall.get("items", [])
        top = items[0] if items else {}
        answer = str(top.get("answer") or top.get("visual_description") or "")
        expected_hits = [term for term in canary["expected_terms"] if term.lower() in answer.lower()]
        has_visual = (
            canary["kind"] != "visual"
            or str(top.get("_key", "")).startswith("watch-visual-")
            or bool(top.get("visual_description") or top.get("visual_description_status") == "described")
        )
        passed = bool(items) and len(expected_hits) >= max(1, len(canary["expected_terms"]) // 2) and has_visual
        results.append({
            **canary,
            "status": "pass" if passed else "fail",
            "top_key": top.get("_key"),
            "top_title": top.get("title"),
            "expected_hits": expected_hits,
            "media_match_count": recall.get("media_match_count"),
            "wrong_media_items": recall.get("wrong_media_items", []),
            "requires_visual_evidence": canary["kind"] == "visual",
            "has_visual_evidence": has_visual,
            "brave_available": bool(packet.get("brave_corroboration", {}).get("available")) if use_brave else False,
        })
    return {
        "schema": "watch.bad_santa_canary.v1",
        "mode": "live",
        "media": {"title": MEDIA_TITLE, "slug": MEDIA_SLUG, "path": MEDIA_PATH},
        "status": "pass" if all(r["status"] == "pass" for r in results) else "fail",
        "canaries": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Emit deterministic canary contract without live memory/Brave calls.")
    parser.add_argument("--no-brave", action="store_true", help="Skip Brave corroboration in live mode.")
    args = parser.parse_args()
    payload = run_offline() if args.offline else run_live(use_brave=not args.no_brave)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] in {"pass", "contract_ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
