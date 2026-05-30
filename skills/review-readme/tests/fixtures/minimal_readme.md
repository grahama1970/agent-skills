# Example Skill

## Purpose

Demonstration README for deterministic T0 checks in `/review-readme`.
This skill adjudicates onboarding documents without editing the repository
unless the human explicitly requests changes.

## Audience

Competent developers and technical agents who need a minimal successful path.

## Quick start

```bash
./run.sh tests/fixtures/minimal_readme.md --skip-oracle
```

## Verification

Expect exit code 0 when T0 checks pass and `--skip-oracle` is set.

## Troubleshooting

If T0 reports missing sections, add the corresponding heading and concrete steps.

## Limitations

Oracle prose review requires `--kimi-tab-id` and is not run in this fixture.
