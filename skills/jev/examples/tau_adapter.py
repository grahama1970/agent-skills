"""Example: construct and choose validated code-recall requests, without executing them.

Run only with explicitly authorized, non-restricted task data. The caller's Tau
executor owns permissions, current-state revalidation, execution and completion.
"""
from __future__ import annotations
import asyncio
from jev_runtime import Jev, Policy, select, tool


@tool(name="memory.code_recall")
def code_recall(q: str, repo: str) -> dict:
    """Retrieve indexed code relevant to a bug before scanning the repository."""
    return {"q": q, "collections": ["code_symbols"],
            "selector": {"schema": "memory.recall_selector.v1", "repo": repo, "lifecycle_mode": "current"}}


async def main() -> None:
    # Registration validates arguments; it does not invoke code_recall or Memory.
    options = [code_recall.jev.candidate(q="Why does retry stop after a timeout?", repo="synthetic-demo")]
    async with Jev(Policy()) as client:  # Deliberately blocked until explicitly authorized.
        proposal = await select(client, {"request": "Investigate this synthetic retry failure"}, options)
    print(proposal.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
