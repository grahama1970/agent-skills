---
name: cui-marker
description: >
  Detect, classify, and mark Controlled Unclassified Information (CUI) per
  32 CFR Part 2002. Scans documents and ArangoDB collections for CUI indicators,
  applies proper markings, and tracks CUI flow through the system.
allowed-tools:
  - run_command
  - read_file
triggers:
  - cui
  - cui-marker
  - controlled unclassified
  - cui marking
  - cui detection
  - 32 cfr 2002
  - cui category
  - cui flow
metadata:
  short-description: CUI detection, marking, and flow tracking (32 CFR Part 2002)
provides:
  - cui-marker
composes:
  - memory
  - extractor
  - learn-datalake
  - task-monitor
  - agentic-evals
taxonomy:
  - security
  - compliance
disciplines:
  - compliance-security
  - extraction
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# CUI Marker

Detect, classify, and mark Controlled Unclassified Information per 32 CFR Part 2002.
Without this skill, CUI documents enter uncontrolled ArangoDB collections with no
marking, no distribution controls, and no audit trail — a compliance failure.

## Commands

| Command | Description |
|---------|-------------|
| `./run.sh scan <path>` | Scan file/directory for CUI indicators |
| `./run.sh scan --collection <name>` | Scan ArangoDB collection for unmarked CUI |
| `./run.sh mark <doc_id> --category <cat>` | Apply CUI marking to document |
| `./run.sh mark <doc_id> --auto` | Auto-detect and apply appropriate marking |
| `./run.sh verify <doc_id>` | Verify document has proper CUI markings |
| `./run.sh categories` | List CUI categories and subcategories |
| `./run.sh report` | Generate CUI inventory report |
| `./run.sh flow <doc_id>` | Trace CUI flow through system |
| `./run.sh audit` | Audit all collections for unmarked CUI |

## CUI Categories (Relevant to DIB)

| Category | Subcategory | Indicators |
|----------|-------------|------------|
| CTI | Controlled Technical Information | Engineering specs, test data, drawings |
| EXPT | Export Controlled | ITAR/EAR controlled data |
| PROPIN | Proprietary Business | Contractor proprietary, trade secrets |
| PRVCY | Privacy | PII, PHI |
| PROCURE | Procurement & Acquisition | Source selection, bid/proposal |
| INTEL | Intelligence | Threat data, assessments |
| INFOSEC | Information Security | Vulnerability data, pen test results |

## CUI Marking Format (per NARA CUI Registry)

```
CUI//SP-CTI
CUI//SP-EXPT
CUI//REL TO USA, AUS, GBR
CUI//NOFORN
```

Documents receive:
1. **Banner marking** — top/bottom of each page
2. **Portion marking** — individual paragraphs containing CUI
3. **Distribution statement** — who can receive
4. **Destruction notice** — how to dispose

## Common Mistakes

### WRONG: Ingesting documents into memory without CUI scanning first
```bash
/memory learn --file sensitive_spec.pdf --scope research  # unmarked CUI enters the graph!
```

### RIGHT: Scan for CUI before ingesting into any collection
```bash
./run.sh scan sensitive_spec.pdf
# If CUI detected, mark it first
./run.sh mark <doc_id> --auto
# Then ingest with proper CUI metadata
```

### WRONG: Using legacy markings (FOUO, SBU) instead of CUI
```markdown
FOUO - For Official Use Only  # legacy marking, non-compliant
```

### RIGHT: Use proper CUI markings per 32 CFR Part 2002
```markdown
CUI//SP-CTI  # correct CUI banner marking
```

### WRONG: Scanning individual files without auditing collections
```bash
./run.sh scan document.pdf  # only checks one file
```

### RIGHT: Audit entire ArangoDB collections for unmarked CUI
```bash
./run.sh audit  # scans all collections for unmarked CUI documents
```

## Detection Patterns

The scanner uses regex + LLM classification for:
- Technical data indicators (specifications, test procedures, drawings)
- Export control markers (ITAR, EAR, USML categories)
- PII patterns (SSN, DoD ID, clearance levels)
- Procurement language (source selection, FOUO markers)
- Legacy markings (FOUO, SBU, LES) that need CUI conversion
