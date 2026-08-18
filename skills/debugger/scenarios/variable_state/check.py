"""Assert a capture proof exposes the variable-state bug (stdlib only).

This is the deterministic oracle for the agentic eval: it does not re-run the
program, it reads the debugger's own proof and checks that the paused state at
the breakpoint reveals the shared-mutable-default leak. That is exactly what an
agent would read off the frame to *describe* the bug.

Usage:
    check.py <proof.json> final
        The tally-return breakpoint was placed in main; hits[0] must show the
        final aggregates first==6 and second==36 (second is wrong; 30 expected).
    check.py <proof.json> leak
        Breakpoint on the tally return line across the whole run: there must be
        five hits, and the second report's first call (hit index 3) must already
        carry the first report's values -- seen == [1, 2, 3, 10] -- which is the
        cross-call state leak made visible.

Exit 0 with a one-line verdict when the expected bug state is present; exit 1
and print the state actually observed otherwise.
"""

import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check.py <proof.json> <final|leak>", file=sys.stderr)
        return 2
    proof = json.loads(open(sys.argv[1], encoding="utf-8").read())
    mode = sys.argv[2]
    hits = proof.get("hits", [])

    if mode == "final":
        loc = hits[0]["locals"] if hits else {}
        if proof.get("hit_count") == 1 and loc.get("first") == "6" and loc.get("second") == "36":
            print(f"BUG-CONFIRMED second={loc['second']} expected=30 (leaked from first={loc['first']})")
            return 0
        print(f"UNEXPECTED-STATE hit_count={proof.get('hit_count')} locals={loc}", file=sys.stderr)
        return 1

    if mode == "leak":
        third = hits[3]["locals"] if len(hits) > 3 else {}
        if proof.get("hit_count") == 5 and third.get("seen") == "[1, 2, 3, 10]" and third.get("value") == "10":
            print("LEAK-CONFIRMED second report's first call already holds seen=[1, 2, 3, 10] from report one")
            return 0
        print(
            f"UNEXPECTED-STATE hit_count={proof.get('hit_count')} "
            f"frames={[h['locals'] for h in hits]}",
            file=sys.stderr,
        )
        return 1

    print(f"unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
