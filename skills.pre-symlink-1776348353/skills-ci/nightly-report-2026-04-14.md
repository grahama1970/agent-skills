# Nightly Health Report — 2026-04-14

**Summary**: 5 ERRORS, 124 warnings

## Skills CI: 5 errors, 124 warnings
- **runtime.vague_triggers** (35): anvil, argue, batch-quality, battle, bootcamp +30 more
- **subprocess.venv_leak** (12): battle, create-evidence-case, dum-dum, embedding, extractor +7 more
- **python.file_length** (12): checkpoint, code-runner, create-evidence-case, create-evidence-case, create-evidence-case +7 more
- **python.argparse** (11): classifier-lab, classifier-lab, classifier-lab, embedding, ingest-sparta +6 more
- **skills.extra_docs** (7): code-runner, create-evidence-case, intent-mapper, project-knowledge, skills-ci +2 more
- **skills.missing_antipatterns** (6): code-runner, ingest-youtube, orchestrate, recommend-skill-chain, scillm +1 more
- **skills.skill_md_bloat** (5): best-practices-prompt, best-practices-skills, create-evidence-case, create-walkthrough, scillm
- **skills.memory_read_directive** (5): best-practices-skills, code-review-runner, create-gsn-diagram, create-qras, monitor-misuse
- **naming.noun_only** (5): code-review-runner, dum-dum, match-requirement, project-knowledge, remote-control
- **systemd-hardening** (5): embry-uxlab, embry-uxlab, embry-uxlab, embry-uxlab, embry-uxlab
- **deps.undeclared_import** (4): classifier-lab, embedding, embedding, pdf-lab
- **subprocess.stderr_fatal** (3): classifier-lab, classifier-lab, skills-ci
- **runtime.bare_python_no_uv** (3): memory, scillm, scillm
- **testing.no_blind_tests** (2): create-text, monitor-misuse
- **subprocess.hardcoded_skill_path** (2): embedding, pdf-lab
- **subprocess.service_bypass** (2): extractor, skills-ci
- **python.module_docstring** (2): pdf-lab, skills-ci
- **routing.ptc_candidate** (1): battle
- **routing.composes_common** (1): best-practices-cots
- **python.logging** (1): code-runner
- **subprocess.raw_aql** (1): create-evidence-case
- **testing.handwritten_tests** (1): create-qras
- **runtime.venv_python_313** (1): match-requirement
- **python.requests** (1): skills-ci
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