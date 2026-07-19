# M5 blind read — operator instructions (human-only gate)

You judge two pairs. For each pair you get exactly two files:
`pair_r1_X.md` / `pair_r1_Y.md`, then `pair_r2_X.md` / `pair_r2_Y.md`.
They are normalized to the same template and the X/Y order is sealed
(random per pair, revealed only after your judgment). Do not ask any agent
to summarize them; read them yourself.

For each pair, answer the three frozen questions and write a judgment file
`judgment_r1.json` / `judgment_r2.json` in this directory, in exactly this
shape (values must be "X" or "Y"):

```json
{
  "author": "human",
  "pair_id": "r1",
  "states_central_conflict_more_precisely": "X",
  "reveals_something_other_does_not": "Y",
  "over_interprets": "X",
  "notes": "optional free text"
}
```

- `states_central_conflict_more_precisely` is the single PRIMARY question
  (decisive under the frozen rule). The other two are recorded as secondary.
- `over_interprets` means: which artifact reads MORE into the memories than
  they support (this one is a negative mark, answer names the worse one).
- Write the file only after reading both artifacts of that pair; do not
  reopen or edit it after the unseal step runs.

After both judgment files exist, the agent runs the unseal + result
assembly; the sealed order receipts prove the mapping was fixed before your
read.
