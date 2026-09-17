# assess-update.workflow.js

```
detect (change-snapshot, py) ─┐
                              ├─> qualify (assess-update, py) ── disposition (AUTHORITATIVE)
gather (sanitize-denials, py)─┘         │
      │ (resource_class+count ONLY)     ├─ PRIVACY_BOUNDARY_VIOLATION ──> terminal
      ▼                                 ├─ REQUALIFIED_UNCHANGED/NO_CHANGE ──> terminal
investigate (SOLE model touch-point,    ├─ INCONCLUSIVE/FAILED ──> terminal
  bounded 1 round, sanitized evidence   ├─ NEEDS_HUMAN (no baseline) ──> terminal
  only, explains + drafts candidate)    └─ POLICY_CHANGE_PROPOSED ──> investigate
                                               │
                                       validate (validate-delta, py) ── DeltaVerdict (AUTHORITATIVE)
                                               ├─ REJECTED_*/INCONCLUSIVE ──> NEEDS_HUMAN (proposal dies)
                                               └─ ACCEPTED_FOR_HUMAN_REVIEW ──> NEEDS_HUMAN receipt
                                                                              (human approval only; NO APPLY path)
```

Lanes: detect, gather, qualify (deterministic Python gates); investigate (sole
model lane); validate (deterministic gate); terminal. Terminal states:
NEEDS_HUMAN | REQUALIFIED_UNCHANGED | PRIVACY_BOUNDARY_VIOLATION |
INCONCLUSIVE | BLOCKED. The workflow may PROPOSE; it never applies.
