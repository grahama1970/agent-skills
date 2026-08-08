# grahama.co — visual-world contract

Human-readable companion to `site/design-world.yml` (machine source of truth),
per `best-practices-bespoke-design` and issue #1337. This locks the grammar and
the audit boundary; it does **not** redesign the homepage.

## Premise
> A claim becomes permissible only when it can be traced through evidence to a
> bounded judgment.

## Non-color invariants (recognizable without palette or logo)
1. **Narrative vs machine roles** — human prose and machine-emitted values never
   share a typeface; monospace marks program output only.
2. **Evidence margin** — a recurring device ties every claim to its artifact.
3. **Judgment + boundary** — consequential artifacts state the judgment *and* the
   proof boundary / unresolved remainder (visible gaps, never hidden).

## Prohibited structural residue
Identical section chrome on every beat · equal-weight cards for unequal work ·
one global type setting everywhere · **monospace on human labels** · systematic
numbering as the only organizing idea · ornament without a semantic job ·
simulated handcraft or deliberately-imperfect machine evidence.

## Check
```bash
skills/monitor-website/run.sh design-world-check --json
```
Validates the contract + the deterministically-checkable prohibitions. Returns
`NOT_TESTED` (never `PASS`) while rendered screenshots and blind-review artifacts
are absent — prose confidence is not acceptance.
