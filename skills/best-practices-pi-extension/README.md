# best-practices-pi-extension

Typo-compatible alias for `best-practices-pi-extensions`.

This folder exists because agents should not make humans pay a tax for spelling,
singular/plural drift, or slash-command ambiguity. If someone asks for
`/best-practices-pi-extension` or mistypes `/best-practices-pi-extenstion`, route
to the canonical Pi extension standard instead of pretending the skill is
missing.

Canonical skill:

```text
skills/best-practices-pi-extensions/
```

Read in order:

1. `../best-practices-pi-extensions/SKILL.md`
2. `../best-practices-pi-extensions/README.md`
3. `../best-practices-pi-extensions/PROJECT_KNOWLEDGE.md`
4. `../best-practices-pi-extensions/fixtures/agentic_eval.json`

The Shame-Shame-Shame lesson applies here too: do not create a bespoke parallel
standard when the correct move is to use the existing one.

This alias has its own `$agentic-evals` fixture so routing drift is executable,
not merely documented.
