# Brandon Bailey SPARTA Assessment

**Run ID:** run-recovery-verify
**Date:** 2026-02-07T07:48:30.138501
**Grade:** C (NEEDS WORK)
**Overall Score:** 0.75

## Brandon's Commentary

This needs significant improvement before I'd present it to stakeholders. SQL injection on a satellite? Please review the CWE mappings for space relevance.

## Dimension Results

### qra_quality (25%)
Score: 0.80

### source_fidelity (20%)
Score: 1.00

### cwe_relevance (20%)
Score: 0.00

**Issues:**
- Error querying CWE data: Binder Error: Referenced column "CWE" not found in FROM clause!
Candidate bindings: "CWE Classes"

LINE 3:             WHERE "CWE" IS NOT NULL AND "CWE" != ''
                          ^
- No CWE mappings found in database

### cross_reference (15%)
Score: 1.00

### coverage (10%)
Score: 1.00

### control_quality (10%)
Score: 1.00

