# Auditable claim provenance

*What transfers out of Persona Dream, independent of whether dreaming works.*

Persona Dream is a research prototype asking a narrow question: does letting an
agent dream about what happened to it beat plainly remembering or reflecting?
That question is **unanswered**. This page is not about it.

It is about the machinery built to make the answer trustworthy either way — which
is reusable by any project that has to defend the sentence *"why should I believe
your attribution?"*

## The problem this addresses

In domains with high stakes, thin information, and experts who disagree, the hard
part is rarely producing a model of an agent. It is showing that a claim about
that agent is earned: which evidence produced it, what it does not cover, and
what happens to the claim when the evidence is later withdrawn.

Systems usually fail this in three specific ways, all of which are cheap to do
accidentally:

1. **A claim outlives its evidence.** A receipt is superseded; the prose is not.
2. **A claim borrows the wrong evidence.** A passing run in one subsystem is
   cited for a property it never tested.
3. **Commentary becomes fact.** A human's question, note, or correction is stored
   alongside observations and later recalls as something that happened.

## What is implemented

**Claims are objects, not prose.** Every present-tense claim lives in
[`CURRENT_STATUS.json`](../CURRENT_STATUS.json) with a status, a scope, a receipt
path, a receipt hash, and a paired `proves` / `does_not_prove`. The second field
is the load-bearing one: a claim that cannot say what it fails to cover has not
been thought through.

**Three gates run fail-closed.**

| Gate | What it refuses |
|---|---|
| `check_current_state_consistency.py` | a PASS without a receipt; a PASS while its successor issue is open; a surface that restores a superseded goal; a claim citing the wrong apparatus |
| `audit_readme_proof_claims.py` | a published proof row not bound to a named receipt; a status that disagrees with the receipt; positive language on an unproven row; one receipt earning two claims |
| `generate_readme_research_state.py` | prose drifting from the machine record — the published state block is generated, not written |

**Findings are recorded with their disposition.**
[`TRANSFER_LEDGER.md`](../TRANSFER_LEDGER.md) records, per completed experiment:
the finding, *what it falsified*, the transferable lesson, an
adopt / constrain / reject / retire decision, the destination repository, and
either a downstream PR or an explicit no-adoption decision.

**Provenance is carried in the data, not only the metadata.** When a human
discussion is written back into memory, each turn is stored as
`record_type=conversation_turn` with a speaker and the hash of the artifact
discussed — *and* its text is prefixed with who said it. A retrieval path that
drops the metadata still cannot present commentary as an observation. It comes
back as `human said, about my journal entry: …`, never as a bare event.

## Evidence the discipline holds under pressure

The ledger is not a portfolio of successes. It contains, on real cases:

- **A rejection** (#1127) — the project's own listener stimuli were found
  technically confounded against an 8-render noise floor, and were rejected
  rather than used.
- **A retirement** (#1059) — a mechanism was removed from scope after failing a
  controlled check.
- **A negative that stuck** (#1209) — the requested voice delivery tone was
  measured against the renderer's own stochastic spread, found inaudible, and
  every surface claiming emotional delivery was corrected. The instability across
  sample sizes was itself the finding: at n=6 two tones looked audible, at n=10
  one was marginal, at a fresh n=10 none were. A two-way pass/fail would have
  published the n=6 run as a success.
- **An apparatus repair** (#1131) — the measurement instrument was shown able to
  falsify its own preferred treatment before being trusted.

The gates caught real regressions, not hypothetical ones: a claim bound to a
receipt from an unrelated subsystem, a handoff that would have routed an agent
into collecting human ratings on stimuli already blocked as confounded, and a
return arc that stored a discussion but silently never drew it back.

## What is explicitly not claimed

- **No decision task.** This produces journals and persona state, not choices.
  Nothing here links attributes to decision outcomes, because there are no
  outcomes.
- **The axes are not instruments.** The psychological axes are invented
  vocabulary matched lexically. They are not validated psychometrics and should
  be treated as latent variables awaiting validation.
- **N=1, synthetic.** One persona, no population, no individual differences.
- **No human subjects.** No trust, delegation, or perception measurement.
- **Dreaming is unproven.** The loop closes and consecutive days differ; whether
  any of it helps is the unrun experiment.

## What would be needed to use this elsewhere

The gates are coupled to this repository's file layout. Extracting them means
generalizing the claim schema, the receipt-binding rule, and the
supersession relation into a standalone checker. The provenance convention for
attributed records transfers as-is — it is a convention, not code.

---

*Every statement above is bound to a receipt under
[`reports/goal_v5/`](../reports/goal_v5/) or to a ledger entry. The claim-by-claim
boundary, including what each receipt does not prove, is in
[`EVIDENCE.md`](EVIDENCE.md).*
