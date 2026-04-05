# Fix Codebase Violations: fetcher

## Context
monitor-codebase scan found 149 issues (78 best-practices, 71 quality).

## Violations
```json
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "scillm"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "dogpile"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "scillm"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "dogpile"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "scillm"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "orchestrate"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "dogpile"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "child-skill"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-name-chars"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "missing-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "long-name"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "multiline-description"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "no-frontmatter"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "consecutive-hyphens"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "name-mismatch"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "unknown-field"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "invalid-yaml"}
{"rule": "missing-run-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "missing-sanity-sh", "skill": "best-practices-skills", "target": "valid-skill"}
{"rule": "handwritten-tests", "file": "tests/test_d3fend_markdown_vs_html_integration.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_mirror_refresher.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_metrics.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_environment_warnings.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_proxy_rotation.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_extract_utils.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_fetcher_helpers.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_outstanding_utils.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_consumer_downloads.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_consumer.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_fetcher_audit.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_paywall_utils.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_provenance.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": "tests/test_github_utils.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/cleanup/test_cleanup.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/prompt-lab/test_scillm.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/ask/test_e2e_fixes.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/ingest-yt-history/tests/test_profile.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/ingest-yt-history/tests/test_ingest.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
{"rule": "handwritten-tests", "file": ".skills/ingest-yt-history/tests/test_taxonomy.py", "line": 0, "message": "Test file has no test-lab markers \u2014 use /test-lab generate", "severity": "warn"}
```

## Instructions
1. Fix each violation following the rules in the relevant `best-practices-*` SKILL.md.
2. For banned imports: `logging` → `loguru`, `requests` → `httpx`, `argparse` → `typer`.
3. For inline prompts: move to /prompt-lab for versioning and evaluation.
4. For handwritten tests: replace with /test-lab blind tests.
5. For regex classifiers: use /taxonomy or /extract-entities.
6. Code must comply with best-practices-python/react/kde/skills/streamdeck as applicable.

## Blind Evaluation
This task uses the Blind Evaluation Gate. The coding agent:
- MUST NOT read test files directly
- Will receive only: rule category, natural language failure description, attempt count
- Has up to 5 retries before escalation
