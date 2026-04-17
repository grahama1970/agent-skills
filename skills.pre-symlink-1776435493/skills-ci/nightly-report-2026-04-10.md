# Nightly Health Report — 2026-04-10

**Summary**: 4 ERRORS, 91 warnings

## Skills CI: 4 errors, 91 warnings
- **runtime.vague_triggers** (35): anvil, argue, batch-quality, battle, bootcamp +30 more
- **python.file_length** (8): checkpoint, code-runner, create-evidence-case, create-evidence-case, ingest-code +3 more
- **subprocess.venv_leak** (7): battle, dum-dum, embedding, hack, ingest-code +2 more
- **skills.extra_docs** (5): code-runner, intent-mapper, skills-ci, taxonomy, test-interactions
- **skills.missing_antipatterns** (5): code-runner, orchestrate, recommend-skill-chain, scillm, test-lab
- **systemd-hardening** (5): embry-uxlab, embry-uxlab, embry-uxlab, embry-uxlab, embry-uxlab
- **python.argparse** (4): classifier-lab, classifier-lab, classifier-lab, embedding
- **deps.undeclared_import** (4): classifier-lab, embedding, embedding, pdf-lab
- **skills.skill_md_bloat** (3): best-practices-prompt, create-walkthrough, scillm
- **subprocess.stderr_fatal** (3): classifier-lab, classifier-lab, skills-ci
- **naming.noun_only** (3): code-review-runner, dum-dum, remote-control
- **subprocess.hardcoded_skill_path** (2): embedding, pdf-lab
- **python.module_docstring** (2): pdf-lab, skills-ci
- **routing.ptc_candidate** (1): battle
- **routing.composes_common** (1): best-practices-cots
- **skills.memory_read_directive** (1): code-review-runner
- **python.logging** (1): code-runner
- **subprocess.raw_aql** (1): create-evidence-case
- **testing.no_blind_tests** (1): create-text
- **python.requests** (1): skills-ci
- **subprocess.service_bypass** (1): skills-ci
- **runtime.docker_no_compose** (1): test-lab

## Monitor Codebase
- **web-ui**: CLEAN
- **web-ui**: CLEAN
- **web-ui**: CLEAN
- **web-ui**: CLEAN
- **web-ui**: CLEAN

## Action Required
- **ERRORS need immediate attention** — run `/skills-ci scan` to see details
- Warnings above 10 — consider a cleanup session