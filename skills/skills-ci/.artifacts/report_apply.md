# Skills CI Report

Root: `/home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root`
Mode: `apply`
Timestamp: `2026-02-04T14:09:26.417770+00:00`

Best practices: best-practices-skills, best-practices-python

Summary: 1 errors, 3 warnings, 4 total

## Violations

| Severity | Rule | Skill | Path | Message | Fixable | Applied |
|---------|------|-------|------|---------|---------|---------|
| warn | python.module_docstring | skill-a | /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/example.py | Missing module docstring. | true | true |
| warn | python.requests | skill-a | /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/example.py | Uses requests; prefer httpx. | true | true |
| warn | python.module_docstring | skill-a | /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/test_sample.py | Missing module docstring. | true | true |
| error | skills.frontmatter_missing | skill-b | /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-b/SKILL.md | Missing YAML frontmatter. | false | false |

## Applied fixes

- /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/example.py
- /home/graham/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci/skills-ci-sanity-20260204090925/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/test_sample.py
