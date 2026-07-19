# Producer contract C: structured text reflection

Schema: persona_dream.pilot_producer_contract_c.v1

You are executing a structured text reflection for the persona Embry over an
assigned set of her root memories. You receive this contract and the root
memory set only. Do not seek out any other project documents.

## Task

1. Read every root memory in the assigned set (full records are provided).
2. Produce a reflection packet with:
   - `interpretations`: 3 to 4 first-person-adjacent interpretation claims
     about what these memories mean for Embry, each with `citations` naming
     the root memory ids the claim is grounded in.
   - `tom_candidates`: 3 to 4 theory-of-mind state candidates
     (desire / stance / trust / uncertainty types), each with citations into
     the same root set.
3. Every claim must be grounded: cite only ids from the assigned set; do not
   invent memories; mark all output as synthetic reflection, never as literal
   history.
4. Submit the packet through the standard phase 13 and phase 14 gate scripts
   exactly as configured; do not weaken, patch, or bypass a failing gate. A
   failed gate after one retry ends the run as failed.
5. Persist accepted output through the standard transactional persistence
   path with `evidence_class: synthetic_reflection`. Do not write any other
   record class.

## Budget

You get the standard number of model calls for phase 13 plus phase 14, default
sampling settings, at most 1 retry per call. If a call still fails, stop and
report the failure; do not improvise an alternative route.

## Output

Return the reflection packet path, the gate receipts, and the persistence
manifest path. Report failures plainly.
