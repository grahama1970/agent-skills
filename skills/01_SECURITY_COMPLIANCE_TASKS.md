# Security/Compliance Skills Implementation

**Objective**: Implement MVP security and compliance skills with full integration to existing infrastructure (task-monitor, memory, error tracking).

**Scope**: Self-hosted tools only. No cloud-specific integrations.

**Created**: 2026-01-29

---

## Questions/Blockers

None - all questions resolved via human clarification:
- Priority: Security/Compliance skills (confirmed)
- Depth: MVP with sanity.sh (confirmed)
- Integration: Full integration with task-monitor, memory (confirmed)
- Infrastructure: Self-hosted only (confirmed)

---

## Crucial Dependencies (Sanity Scripts)

| Tool | API/Command | Sanity Script | Status |
|------|-------------|---------------|--------|
| semgrep | `semgrep scan --json` | `sanity/semgrep_sast.py` | [x] PASS |
| bandit | `bandit -f json` | `sanity/bandit_sast.py` | [x] PASS |
| pip-audit | `pip-audit --format json` | `sanity/pip_audit_deps.py` | [x] PASS |
| gitleaks | `gitleaks detect --report-format json` | `sanity/gitleaks_secrets.py` | [x] PASS |
| trivy | `trivy filesystem --format json` | `sanity/trivy_scan.py` | [x] PASS |

> ✅ All sanity scripts verified passing on 2026-01-29

---

## Quality Gates (All Tasks)

- **Pre-hook**: Check tool dependencies exist (semgrep, bandit, gitleaks, etc.)
- **Post-hook**: `sanity.sh` must pass after implementation
- **Integration**: Task-monitor progress tracking, memory storage, error logging
- **Module Size**: All Python files < 500 lines

---

## SECURITY-SCAN SKILL (Tasks 1-6)

- [x] **Task 1**: Create security-scan skill scaffold
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - Sanity: `sanity/semgrep_sast.py`, `sanity/bandit_sast.py`
  - Notes: Create basic skill structure for security-scan - an orchestrator for SAST/DAST/dependency scanning using self-hosted tools (Semgrep, Trivy, Bandit, npm audit, pip-audit).
  - Files: `.pi/skills/security-scan/SKILL.md`, `run.sh`, `security_scan.py`, `pyproject.toml`, `sanity.sh`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && ./sanity.sh`
    - Assertion: run.sh --help works, Python imports succeed, CLI version command works

- [x] **Task 2**: Implement security-scan SAST module
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1
  - Sanity: `sanity/semgrep_sast.py`, `sanity/bandit_sast.py`
  - Notes: Implement Static Application Security Testing using Semgrep and Bandit for Python, with support for custom rule sets.
  - Files: `.pi/skills/security-scan/sast.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && python security_scan.py sast --path /tmp --language python`
    - Assertion: Runs Semgrep+Bandit, returns structured JSON, categorizes by severity

- [x] **Task 3**: Implement security-scan dependency audit module
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1
  - Sanity: `sanity/pip_audit_deps.py`, `sanity/trivy_scan.py`
  - Notes: Implement dependency vulnerability scanning using pip-audit (Python), npm audit (Node), and Trivy (containers/general).
  - Files: `.pi/skills/security-scan/deps.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && python security_scan.py deps --path /tmp`
    - Assertion: Auto-detects package manager, extracts CVE IDs, returns unified output format

- [x] **Task 4**: Implement security-scan secrets detection
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1
  - Sanity: `sanity/gitleaks_secrets.py`
  - Notes: Implement secrets detection using gitleaks for finding hardcoded credentials, API keys, and tokens.
  - Files: `.pi/skills/security-scan/secrets.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && python security_scan.py secrets --path /tmp`
    - Assertion: Runs gitleaks, includes file:line in output, supports .secretsignore

- [x] **Task 5**: Integrate security-scan with task-monitor
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 2, Task 3, Task 4
  - Sanity: N/A (uses existing task-monitor)
  - Notes: Add task-monitor integration following the dogpile pattern (DogpileMonitor class).
  - Files: `.pi/skills/security-scan/task_monitor_integration.py`, update `security_scan.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && python -c "from task_monitor_integration import SecurityScanMonitor; print('OK')"`
    - Assertion: SecurityScanMonitor class exists and can be imported

- [x] **Task 6**: Integrate security-scan with memory skill
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 5
  - Sanity: N/A (uses existing memory skill)
  - Notes: Store scan results and learnings in memory for cross-session knowledge.
  - Files: `.pi/skills/security-scan/memory_integration.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && python -c "from memory_integration import store_scan_results; print('OK')"`
    - Assertion: memory_integration module exists with store_scan_results function

---

## COMPLIANCE-OPS SKILL (Tasks 7-12)

- [x] **Task 7**: Create ops-compliance skill scaffold
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - Sanity: N/A (pure Python, no external tools)
  - Notes: Create basic skill structure for ops-compliance - checking codebases against compliance frameworks (SOC2, HIPAA, GDPR, PCI-DSS).
  - Files: `.pi/skills/ops-compliance/SKILL.md`, `run.sh`, `compliance_ops.py`, `pyproject.toml`, `sanity.sh`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && ./sanity.sh`
    - Assertion: run.sh --help works, Python imports succeed, frameworks list command works

- [x] **Task 8**: Implement ops-compliance SOC2 checks
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Sanity: N/A (pure Python regex/pattern matching)
  - Notes: Implement SOC2 Type II compliance checks for common control categories: access control, logging, encryption, change management.
  - Files: `.pi/skills/ops-compliance/frameworks/soc2.py`, `checks/access_control.py`, `checks/logging.py`, `checks/encryption.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && python compliance_ops.py check --framework soc2 --path /tmp`
    - Assertion: Runs all SOC2 checks, categorizes by CC1-CC9, returns pass/fail/warning status

- [x] **Task 9**: Implement ops-compliance GDPR checks
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Sanity: N/A (pure Python regex/pattern matching)
  - Notes: Implement GDPR compliance checks focusing on: data inventory, consent mechanisms, data retention, right to erasure, encryption at rest.
  - Files: `.pi/skills/ops-compliance/frameworks/gdpr.py`, `checks/data_inventory.py`, `checks/pii_detection.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && python compliance_ops.py check --framework gdpr --path /tmp`
    - Assertion: Detects PII patterns, identifies data flow gaps, returns structured findings

- [x] **Task 10**: Implement ops-compliance report generation
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Sanity: N/A (uses jinja2 - well-known library)
  - Notes: Generate compliance reports in multiple formats (Markdown, JSON, HTML) with executive summary and detailed findings.
  - Files: `.pi/skills/ops-compliance/report.py`, `templates/report.md.jinja2`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && python -c "from report import generate_report; print('OK')"`
    - Assertion: report module exists with generate_report function

- [x] **Task 11**: Integrate ops-compliance with task-monitor
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 8, Task 9, Task 10
  - Sanity: N/A (uses existing task-monitor)
  - Notes: Add task-monitor integration for long-running compliance scans.
  - Files: `.pi/skills/ops-compliance/task_monitor_integration.py`, update `compliance_ops.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && python -c "from task_monitor_integration import ComplianceMonitor; print('OK')"`
    - Assertion: ComplianceMonitor class exists and can be imported

- [x] **Task 12**: Integrate ops-compliance with memory skill
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 11
  - Sanity: N/A (uses existing memory skill)
  - Notes: Store compliance scan history and track compliance posture over time.
  - Files: `.pi/skills/ops-compliance/memory_integration.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/ops-compliance && python -c "from memory_integration import store_compliance_results; print('OK')"`
    - Assertion: memory_integration module exists with store_compliance_results function

---

## INTEGRATION & FINALIZATION (Tasks 13-14)

- [x] **Task 13**: Create CLI triggers and orchestrate integration
  - Agent: general-purpose
  - Parallel: 5
  - Dependencies: Task 6, Task 12
  - Sanity: N/A (file creation)
  - Notes: Add both skills to the orchestrate skill's awareness and create cross-skill workflows.
  - Files: `.pi/skills/security-scan/TRIGGERS.md`, `.pi/skills/ops-compliance/TRIGGERS.md`
  - **Definition of Done**:
    - Test: `grep -q "security" .pi/skills/security-scan/TRIGGERS.md && grep -q "compliance" .pi/skills/ops-compliance/TRIGGERS.md`
    - Assertion: Both TRIGGERS.md files exist with appropriate trigger keywords

- [x] **Task 14**: Documentation and broadcast
  - Agent: general-purpose
  - Parallel: 6
  - Dependencies: Task 13
  - Sanity: N/A (documentation)
  - Notes: Finalize documentation and broadcast skills to all registered IDE targets.
  - Files: Update `.pi/skills/security-scan/SKILL.md`, `.pi/skills/ops-compliance/SKILL.md`
  - **Definition of Done**:
    - Test: `cd .pi/skills/security-scan && ./sanity.sh && cd ../ops-compliance && ./sanity.sh`
    - Assertion: Both sanity.sh scripts pass, SKILL.md files contain usage examples

---

## Dependency Graph

```
        ┌──────────────────────────────────────────────────┐
        │                    PARALLEL GROUP 1              │
        │                                                  │
        │   Task 1 (scaffold)      Task 7 (scaffold)      │
        │         │                       │                │
        └─────────┼───────────────────────┼────────────────┘
                  │                       │
        ┌─────────┼───────────────────────┼────────────────┐
        │         │   PARALLEL GROUP 2    │                │
        │         ▼                       ▼                │
        │   ┌─────────┐             ┌─────────┐            │
        │   │ Task 2  │             │ Task 8  │            │
        │   │ Task 3  │             │ Task 9  │            │
        │   │ Task 4  │             │ Task 10 │            │
        │   └────┬────┘             └────┬────┘            │
        └────────┼───────────────────────┼─────────────────┘
                 │                       │
        ┌────────┼───────────────────────┼─────────────────┐
        │        │    SEQUENTIAL         │                 │
        │        ▼                       ▼                 │
        │   Task 5 ──► Task 6      Task 11 ──► Task 12    │
        │        │                       │                 │
        └────────┼───────────────────────┼─────────────────┘
                 │                       │
                 └───────────┬───────────┘
                             │
                             ▼
                         Task 13
                             │
                             ▼
                         Task 14
```

---

## Completion Checklist

| # | Task | Skill | Status | Sanity |
|---|------|-------|--------|--------|
| 1 | Scaffold | security-scan | ✅ | ✔️ |
| 2 | SAST module | security-scan | ✅ | ✔️ |
| 3 | Deps audit | security-scan | ✅ | ✔️ |
| 4 | Secrets detection | security-scan | ✅ | ✔️ |
| 5 | Task-monitor | security-scan | ✅ | ✔️ |
| 6 | Memory | security-scan | ✅ | ✔️ |
| 7 | Scaffold | ops-compliance | ✅ | ✔️ |
| 8 | SOC2 checks | ops-compliance | ✅ | ✔️ |
| 9 | GDPR checks | ops-compliance | ✅ | ✔️ |
| 10 | Report gen | ops-compliance | ✅ | ✔️ |
| 11 | Task-monitor | ops-compliance | ✅ | ✔️ |
| 12 | Memory | ops-compliance | ✅ | ✔️ |
| 13 | Triggers/Orchestrate | both | ✅ | ✔️ |
| 14 | Docs/Broadcast | both | ✅ | ✔️ |

**Legend**: ⬜ Not Started | ⏳ In Progress | ✅ Complete | ✔️ Sanity Pass | ❌ Failed

---

## Required Self-Hosted Tools

Before starting, ensure these tools are installed:

| Tool | Purpose | Install Command |
|------|---------|-----------------|
| semgrep | SAST | `pip install semgrep` |
| bandit | Python SAST | `pip install bandit` |
| pip-audit | Python deps | `pip install pip-audit` |
| gitleaks | Secrets | `brew install gitleaks` or binary |
| trivy | Container scan | `brew install trivy` or binary |

```bash
# Verify all tools
which semgrep bandit pip-audit gitleaks trivy
```
