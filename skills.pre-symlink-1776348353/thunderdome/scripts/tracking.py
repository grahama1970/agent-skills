"""Store tournament rounds and dogpile results to /memory via Unix socket."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from .scoring import RoundResult

SKILL_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = SKILL_DIR / ".artifacts"
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"


def _memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost",
                        timeout=httpx.Timeout(10.0, connect=2.0))


def _learn(problem: str, solution: str, tags: list[str], scope: str) -> bool:
    try:
        c = _memory_client()
        r = c.post("/learn", json={"problem": problem, "solution": solution,
                                    "tags": tags, "scope": scope})
        c.close()
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"/memory learn failed: {e}")
        return False


def recall_prior(name: str, scope: str = "") -> list[dict]:
    try:
        c = _memory_client()
        r = c.post("/recall", json={"q": f"THUNDERDOME:{name}", "k": 10,
                                     "scope": scope or name})
        c.close()
        data = r.json()
        return data.get("items", []) if data.get("found") else []
    except Exception as e:
        logger.warning(f"/memory recall failed: {e}")
        return []


def store_round(name: str, rr: RoundResult, scope: str) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "event_type": "thunderdome_round", "timestamp": int(time.time()),
        "tournament": name, "round": rr.round_num,
        "winner_name": rr.winner_name, "winner_score": rr.winner_score,
        "gate_passed": rr.gate_passed,
        "strategy_scores": [{"name": s.name, "score": s.score} for s in rr.strategy_scores],
    }
    p = ARTIFACTS_DIR / f"round_{name}_r{rr.round_num}_{int(time.time())}.json"
    p.write_text(json.dumps(artifact, indent=2))

    gate = "PASS" if rr.gate_passed else "FAIL"
    _learn(
        f"THUNDERDOME:{name}:round{rr.round_num} — winner={rr.winner_name} "
        f"score={rr.winner_score:.4f} gate={gate}",
        json.dumps(artifact), ["thunderdome", name, f"round-{rr.round_num}"], scope,
    )
    logger.info(f"Stored round {rr.round_num} to /memory + {p.name}")


def store_dogpile(name: str, query: str, result: str, round_num: int,
                  phase: str, scope: str) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "event_type": "thunderdome_dogpile", "timestamp": int(time.time()),
        "tournament": name, "round": round_num, "phase": phase,
        "query": query, "result_length": len(result or ""),
    }
    p = ARTIFACTS_DIR / f"dogpile_{name}_r{round_num}_{int(time.time())}.json"
    p.write_text(json.dumps(artifact, indent=2))

    _learn(
        f"DOGPILE:{name}:round{round_num}:{phase}",
        json.dumps(artifact), ["thunderdome", "dogpile-tracking", name], scope,
    )
    logger.info(f"Stored dogpile: tournament={name} round={round_num} phase={phase}")
