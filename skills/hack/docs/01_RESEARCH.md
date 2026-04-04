# Research: Hack Skill

## Goal

Create a robust `hack` skill for the agent.

## Conventions Checklist

- [ ] `SKILL.md`: Metadata, triggers, description.
- [ ] `run.sh`: Entry point.
- [ ] `pyproject.toml`: Dependency management.
- [ ] `sanity.sh`: Verification script.
- [ ] Implementation (Python/Bash).

## Automated Tooling Recommendations (from Dogpile)

A robust automated security skill should combine SAST, SCA, and DAST approaches with strict scope control.

### Static Application Security Testing (SAST)

- **Semgrep**: Highly recommended for pattern matching and custom rules.
- **Bandit**: Essential for Python-specific security analysis.

### Software Composition Analysis (SCA)

- **pip-audit**: For auditing Python environments.
- **OWASP dep-scan**: Broad dependency scanning.

### Dynamic Application Security Testing (DAST)

- **OWASP ZAP (Zed Attack Proxy)**: Powerful DAST scanner. Can be controlled via API (Python client `zaproxy`).
- **Nuclei**: Fast, template-based vulnerability scanner (Go-based, can be invoked via wrapper).

### Key Architectures

- **Scope Control**: Strictly define allowlists to prevent unauthorized scanning.
- **Correlation**: Combine findings from SBOM + SAST + DAST to reduce noise.
- **Reporting**: Structured output (JSON/SARIF) for agent consumption.

## Educational Resources (Low Level & Theory)

### Low-Level Software Exploits

These teach stack/heap overflows, ROP, shellcode, and format strings at the assembly/C level.

- _Hacking: The Art of Exploitation_ (Jon Erickson)
- _The Shellcoder's Handbook_ (Chris Anley et al.)

### Hardware and Firmware Exploits

- _Microcontroller Exploits_ (Travis Goodspeed)
- _The Car Hacker's Handbook_ (Craig Smith)

### High-Level Web (Context)

- _The Web Application Hacker’s Handbook_ (Dafydd Stuttard, Marcus Pinto)
