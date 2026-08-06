"""Thin MCP-shaped adapter over the ChangeSet API (#1232).

Exposes exactly three tools — pitchdeck_simulate, pitchdeck_apply,
pitchdeck_history — as pure handlers over the public change_set/revisions
API. Deliberately NOT exposed: token minting (the human trust anchor stays in
the CLI/workbench confirm action) and any direct file write. The module
imports only stdlib + the public pitchdeck API so a static import check can
prove there is no validator bypass. stdio loop: one JSON request per line,
one JSON response per line. Failure modes: unknown tool, invalid proposal,
and permission errors return {"error": ...}; nothing raises through the loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .change_set import EditProposal, apply_proposal, simulate_proposal
from .revisions import current_revision, undo_history

TOOLS = {
    "pitchdeck_simulate": "Dry-run an EditProposal; returns would_pass/error/governance.",
    "pitchdeck_apply": "Apply an EditProposal (governance ops need a human-minted token).",
    "pitchdeck_history": "Bundle revision + undoable archive list.",
}


def handle_request(request: dict) -> dict:
    tool = request.get("tool")
    args = request.get("arguments") or {}
    try:
        bundle_dir = Path(args["bundle_dir"])
        if tool == "pitchdeck_simulate":
            proposal = EditProposal.model_validate(args["proposal"])
            return simulate_proposal(bundle_dir, proposal)
        if tool == "pitchdeck_apply":
            proposal = EditProposal.model_validate(args["proposal"])
            return apply_proposal(
                bundle_dir,
                Path(args.get("ui_dir", bundle_dir / ".ui")),
                proposal,
                token=args.get("token"),
            )
        if tool == "pitchdeck_history":
            return {
                "revision": current_revision(bundle_dir),
                "undoable_archives": undo_history(bundle_dir),
            }
        return {"error": f"unknown tool '{tool}'; available: {sorted(TOOLS)}"}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            print(json.dumps({"error": f"invalid JSON: {exc}"}), flush=True)
            continue
        print(json.dumps(handle_request(request)), flush=True)


if __name__ == "__main__":
    main()
