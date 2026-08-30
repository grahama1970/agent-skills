#!/usr/bin/env python3
"""Verify DriveWealth client_interview_qa answers outrank generic lessons in Live Evidence."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from live_evidence.config import AppSettings
from live_evidence.retrieval.memory import MemoryEvidenceClient
from live_evidence.retrieval.ranker import rank_sources

QUERY = "An operations analyst asks why a customer account is blocked. What graph would you build including nodes, state, edges?"


async def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("LIVE_EVIDENCE_PROFILE", str(skill_root / "config" / "drivewealth.yaml"))
    settings = AppSettings.from_env(skill_root=skill_root)
    profile = settings.load_profile()
    result = await MemoryEvidenceClient(settings, profile).retrieve(QUERY)
    ranked = rank_sources(result.sources, QUERY, profile)
    top = ranked[0] if ranked else None
    receipt = {
        "schema": "live_evidence.drivewealth_client_qa_ranking.v1",
        "query": QUERY,
        "profile": profile.name,
        "memory_scope": profile.memory_scope,
        "ok": bool(top),
        "top_source": {
            "repository": top.repository,
            "path": top.path,
            "source": top.metadata.get("source"),
            "topic_kind": top.metadata.get("topic_kind"),
            "key": top.metadata.get("_key"),
        } if top else None,
        "sources": [
            {
                "repository": source.repository,
                "path": source.path,
                "source": source.metadata.get("source"),
                "topic_kind": source.metadata.get("topic_kind"),
                "key": source.metadata.get("_key"),
            }
            for source in ranked[:8]
        ],
    }
    out_path = Path(os.environ.get("LIVE_EVIDENCE_DRIVEWEALTH_RANKING_RECEIPT", "/tmp/live-evidence-drivewealth-client-qa-ranking.json"))
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not top or top.repository != "client_interview_qa" or top.metadata.get("source") != "client_interview_qa":
        print(json.dumps(receipt, indent=2, sort_keys=True))
        print("CLIENT_INTERVIEW_QA_TOP: FAIL")
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("CLIENT_INTERVIEW_QA_TOP: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
