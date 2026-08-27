# Gates: <task>

OWNS: <repo-relative paths>

Scope: <one-sentence requested outcome>

- [ ] G1: named skills were read before task actions
  CHECK: <command that records or checks the relevant skill contract readback>
  EXPECT: SKILL_CONTRACT_READBACK_OK
  EVIDENCE: pending

- [ ] G2: requested artifact or behavior exists
  CHECK: <command that reads the artifact/service/receipt directly>
  EXPECT: ARTIFACT_READBACK_OK
  EVIDENCE: pending

- [ ] G3: retained agentic eval covers the change
  CHECK: skills/agentic-evals/run.sh run <skill>/fixtures/agentic_eval.json --case <case> --output /tmp/<case>.json
  EXPECT: "readiness": "READY"
  EVIDENCE: pending

- [ ] G4: relevant files are retained on main
  CHECK: git diff --cached --name-status && git ls-remote origin refs/heads/main
  EXPECT: refs/heads/main
  EVIDENCE: pending

- [ ] G5: final status preserves immutable-goal boundary
  CHECK: <command that checks status/receipt text for NOT_MET or ACHIEVED_WITH_RECEIPT>
  EXPECT: IMMUTABLE_GOAL_BOUNDARY_OK
  EVIDENCE: pending
