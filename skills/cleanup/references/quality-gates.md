# Quality Gates Contract

This reference defines cleanup's project-native validation lane. It gives agents
an inspectable proof path without turning cleanup into full CI.

## Required Behavior

`$cleanup --quality-gate` may run:

- Python parse checks for tracked Python files;
- configured Ruff lint and format checks;
- shell syntax checks for tracked shell scripts;
- configured ShellCheck when `.shellcheckrc` exists;
- configured `npm run lint`, `npm run typecheck`, and `npm run test` scripts.

Default assessment reports quality-gate blockers without running expensive
commands. The selected lane runs only the quality checks and prints JSON.

## Closure Criteria

Quality-gate blockers close only when deterministic receipts exist:

1. Required configured gates pass, or the report marks them not applicable with
   a concrete rationale.
2. Missing required tools are installed or the repository removes the required
   configuration that declared the gate.
3. The receipt states exactly which commands/files were exercised.
4. The report states what remains unverified, including full CI and release
   readiness when those were not run.

## Non-Claims

- A quality-gate receipt is not full CI.
- A parse/lint/type/test pass does not prove unused code, runtime behavior, UI
  behavior, deployment readiness, or public-release safety unless the configured
  project-native command explicitly covers that predicate.
- Cleanup does not format files, install tools, edit package config, or mutate
  source as part of this lane.
