# Interaction Test Report: Datalake Explorer
**Date**: 2026-04-04 13:01
**Persona**: nico-bailon
**Results**: 27 PASS / 3 FAIL / 0 WARN / 30 total

## DOM Assertion Results

| Surface | Element | Action | Status | Evidence |
|---------|---------|--------|--------|----------|
| datalake-explorer | tab-overview | click | PASS | clicked <BUTTON> 'Overview' |
| datalake-explorer | tab-corpus | click | PASS | clicked <BUTTON> 'Corpus' |
| datalake-explorer | tab-extraction | click | PASS | clicked <BUTTON> 'Extraction' |
| datalake-explorer | tab-requirements | click | PASS | clicked <BUTTON> 'Requirements' |
| datalake-explorer | tab-traceability | click | PASS | clicked <BUTTON> 'Traceability' |
| datalake-explorer | tab-cascade | click | PASS | clicked <BUTTON> 'Cascade' |
| datalake-explorer | tab-metrics | click | PASS | clicked <BUTTON> 'Metrics' |
| datalake-explorer | metrics-text | screenshot | PASS | captured /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalak |
| datalake-explorer | metrics-visual | screenshot | PASS | captured /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalak |
| datalake-explorer | tab-quarantine | click | PASS | clicked <BUTTON> 'Quarantine' |
| datalake-explorer | quarantine-filter-all | click | PASS | clicked <BUTTON> 'All(0)' |
| datalake-explorer | quarantine-filter-lowconf | click | PASS | clicked <BUTTON> 'LowConf(0)' |
| datalake-explorer | quarantine-filter-exterr | click | PASS | clicked <BUTTON> 'ExtErr(0)' |
| datalake-explorer | quarantine-filter-novel | click | PASS | clicked <BUTTON> 'Novel(0)' |
| datalake-explorer | quarantine-filter-timeout | click | PASS | clicked <BUTTON> 'Timeout(0)' |
| datalake-explorer | quarantine-filter-all-reset | click | PASS | clicked <BUTTON> 'All(0)' |
| datalake-explorer | quarantine-layout-balanced | click | PASS | clicked <BUTTON> 'Balanced' |
| datalake-explorer | quarantine-layout-review | click | PASS | clicked <BUTTON> 'Review' |
| datalake-explorer | quarantine-layout-inspect | click | PASS | clicked <BUTTON> 'Inspect' |
| datalake-explorer | quarantine-layout-wide | click | PASS | clicked <BUTTON> 'Wide Content' |
| datalake-explorer | quarantine-layout-chat | click | PASS | clicked <BUTTON> 'Chat' |
| datalake-explorer | quarantine-search | click | PASS | clicked <INPUT> '' |
| datalake-explorer | quarantine-search | type | PASS | typed '0000ea', value='0000ea' |
| datalake-explorer | quarantine-select-all | click | PASS | clicked <BUTTON> 'Select All' |
| datalake-explorer | quarantine-batch-approve | screenshot | PASS | captured /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalak |
| datalake-explorer | scope-extractor | click | PASS | clicked <DIV> 'extractor0' |
| datalake-explorer | scope-fort-worth | click | **FAIL** | selector not found: [data-qid='datalake:scope:fort_worth_f36'] |
| datalake-explorer | scope-search | click | **FAIL** | selector not found: [data-qid='datalake:search'] |
| datalake-explorer | scope-search | type | **FAIL** | selector not found |
| datalake-explorer | sidebar-new-project | screenshot | PASS | captured /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalak |

## Failures

### datalake-explorer > scope-fort-worth > click
- **Description**: Select fort_worth_f36 scope
- **Evidence**: selector not found: [data-qid='datalake:scope:fort_worth_f36']
- **Screenshot**: /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalake-explorer/scope-fort-worth_click.png

### datalake-explorer > scope-search > click
- **Description**: Focus scope search
- **Evidence**: selector not found: [data-qid='datalake:search']
- **Screenshot**: /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalake-explorer/scope-search_click.png

### datalake-explorer > scope-search > type
- **Description**: Filter scopes
- **Evidence**: selector not found
- **Screenshot**: /home/graham/workspace/experiments/pi-mono/packages/ux-lab/captures/datalake-qid-v3/datalake-explorer/scope-search_type.png


## Visual Design Review

*Skipped — /review-design not available or returned no output.*

## Final Assessment

*nico-bailon overall verdict via /scillm text-gemini:*

The Datalake Explorer is currently at a 90% pass rate, but the three failures represent critical breakdowns in core navigation and search functionality. Specifically, the