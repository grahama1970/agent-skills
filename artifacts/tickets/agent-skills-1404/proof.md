# Proof For agent-skills#1404

Ticket: https://github.com/grahama1970/agent-skills/issues/1404

Closure bar, quoted:

> Closure requires live separate-worktree writer receipts, patch/handoff digest
> readback, an independent reviewer and a clean unchanged caller checkout; two
> successful writers in a shared tree or an unverified patch file is not
> closure proof.

## What is delivered (Ask's half, per the ticket's own rule 4)

> Ask proposes path ownership and isolation; Tau authoritatively creates,
> leases, validates, captures and cleans worktrees.

`ask.writer_isolation.v1` compiles writing workstreams into explicit isolation
requirements and fails closed before Tau schedules anything. 23 tests.

| rule | behaviour |
| --- | --- |
| read-only roles never write | `scout`/`researcher`/`reviewer`/`judge`/`browser_reviewer` cannot declare `workspace_write` at all |
| one writer is the default | a single writer may share the tree |
| two writers need isolation | parallel writers without `managed_worktree` fail closed |
| immutable base binding | parallel writers must share one `base_commit` |
| overlap visible before execution | computed at compile time; blocks unless a declared `downstream_integrator` owns it |
| prose is not completion | a receipt without patch digest, changed files and test evidence is rejected |
| scope enforced | a changed file outside `allowed_paths`, or inside `denied_paths`, rejects the receipt |
| reviewer isolation | receives accepted manifests and digests only, `grants_filesystem_access: false` |

Path overlap is compared per segment, so `src/app` does not read as covering
`src/application` — a string-prefix check would have blocked unrelated
workstreams.

## Not proven — the live half

**The closure bar is NOT met.** It requires live separate-worktree writer
receipts, patch digest readback from a real capture, an independent reviewer
over real artifacts, and a verified-clean caller checkout. None of that is
demonstrated here.

Tau does have the machinery: `tau_coding/runtime_backends/worktrees.py`
provides `GitWorktreeLeaseManager`, `worktree_discard_authorization` and
cleanup receipts. What does not exist is the Ask→Tau wiring that turns an
`ask.writer_isolation.v1` contract into leased worktrees per writer, plus the
capture path that returns a patch digest Ask can read back.

I also declined to fabricate a live demonstration in this checkout. It
currently carries **171 registered worktrees, 47 of them dirty and owned by
other lanes** (the same sprawl that blocks `ticket close` and forced
`GH_TICKET_SKIP_WORKTREE_AUDIT=1` on every closure this session). Creating more
live worktrees to produce a proof artifact would add to a problem the repo
already has, and a proof run in a tree that is not clean could not honestly
claim "a clean unchanged caller checkout" either.

**Unblocks when** Tau exposes a per-node managed-worktree lease driven by the
isolation contract, with a capture that returns a patch digest. That is
upstream work in `grahama1970/tau`.

Commit: 7f7736e6a6
