// Constrained-agentic service-privacy assessment: Pi investigates, Python decides, the kernel enforces. The workflow may PROPOSE; it never applies.
// Config: agent-skills/.pi/assess-update.json (unit, max_investigation_rounds, dry_run).
// Terminal states: NEEDS_HUMAN | REQUALIFIED_UNCHANGED | PRIVACY_BOUNDARY_VIOLATION | INCONCLUSIVE | BLOCKED.
// Diagram: workflows/assess-update.diagram.md — lanes: detect, gather, qualify, investigate (sole model touch-point), validate, terminal; gate: validate-delta.
// Launch: subagent({ workflowScriptPath: '/home/graham/workspace/experiments/agent-skills/skills/service-privacy/workflows/assess-update.workflow.js',
//                    cwd: '/home/graham/workspace/experiments/agent-skills/skills/service-privacy', async: true, globalConcurrencyLimit: 1 })

// TRUST SPLIT (encoded below, enforced by structure):
//   Pi investigates   — only the INVESTIGATE lane touches a model, and only to
//                       EXPLAIN sanitized evidence and DRAFT a candidate delta.
//   Python decides    — QualificationReceipt disposition (Python) and DeltaVerdict
//                       (Python) are authoritative; the workflow never overrides.
//   The kernel enforces — nothing here applies policy. ACCEPTED_FOR_HUMAN_REVIEW
//                       ends at a NEEDS_HUMAN receipt. NEVER an APPLY path.

const UNIT_DEFAULT = 'launcher.kolide-k2.service';
const SKILL_DIR = '/home/graham/workspace/experiments/agent-skills/skills/service-privacy';
const CLI = 'cd ' + SKILL_DIR + ' && SERVICE_PRIVACY_PYTHON=${SERVICE_PRIVACY_PYTHON:-/tmp/usp/venv/bin/python} ./run.sh';

const changeSchema = {
  type: 'object', required: ['disposition', 'raw'],
  properties: {
    disposition: { type: 'string', enum: ['NO_CHANGE', 'NO_BASELINE', 'REQUALIFICATION_REQUIRED', 'REQUALIFIED_UNCHANGED', 'INCONCLUSIVE'] },
    raw: { type: 'string' }
  }
};
const evidenceSchema = {
  type: 'object', required: ['status', 'evidence_classes'],
  properties: {
    status: { type: 'string', enum: ['PASS', 'BLOCKED'] },
    evidence_classes: { type: 'array', items: { type: 'string' } }
  }
};
const qualifySchema = {
  type: 'object', required: ['disposition', 'raw'],
  properties: {
    disposition: { type: 'string', enum: ['NO_CHANGE', 'REQUALIFIED_UNCHANGED', 'POLICY_CHANGE_PROPOSED', 'NEEDS_HUMAN', 'PRIVACY_BOUNDARY_VIOLATION', 'INCONCLUSIVE', 'FAILED'] },
    raw: { type: 'string' }
  }
};
const investigateSchema = {
  type: 'object', required: ['explanation', 'proposal_file'],
  properties: {
    explanation: { type: 'string' },
    proposal_file: { type: 'string', description: 'path to candidate PolicyDeltaProposal JSON, or empty string when none can be drafted' },
    verdict_claim: { type: 'string', description: 'advisory only; NEVER used as the decision' }
  }
};
const validateSchema = {
  type: 'object', required: ['verdict'],
  properties: {
    verdict: { type: 'string', enum: ['ACCEPTED_FOR_HUMAN_REVIEW', 'REJECTED_PROTECTED_OVERLAP', 'REJECTED_WRITABLE_EXEC', 'REJECTED_CAP_RESTORE', 'REJECTED_NNP_WEAKEN', 'REJECTED_NETWORK_BROADEN', 'REJECTED_DENY_REMOVAL', 'INCONCLUSIVE_NO_EVIDENCE'] }
  }
};

// Step 1 DETECT — deterministic CLI; nonzero exit is drift signal, parsed as data not error.
const detect = await runs.run('gate-detect-change', {
  agent: 'general-purpose',
  task: 'Run (timeout 300): ' + CLI + ' change-snapshot --unit ' + UNIT_DEFAULT + '\n' +
        'Capture stdout JSON even if exit code is nonzero (nonzero = drift/needs-human, not an error to hide). ' +
        'Return its disposition field verbatim and the full JSON line as raw.',
  outputSchema: changeSchema,
  lane: { version: 1, key: 'gate-detect-change', mode: 'gate' }
});
const changeDisposition = detect.structuredOutput.disposition;

// Step 2 GATHER — sanitized evidence ONLY.
// PRIVACY BOUNDARY: the ONLY evidence any later (model-facing) step may see is
// the SanitizedDenial output (resource_class + operation + count). Raw denial
// paths are dropped at the Python sanitize boundary (#1744) and must never be
// forwarded, quoted, or re-derived here. This gate reduces the stream to
// resource classes before anything model-visible exists downstream.
const gather = await runs.run('gate-gather-sanitized-evidence', {
  agent: 'general-purpose',
  task: 'Run (timeout 300): ' + CLI + ' sanitize-denials --unit ' + UNIT_DEFAULT + '\n' +
        'From stdout, keep ONLY lines with schema_version "ubuntu_service_privacy.sanitized_denial.v1" and report the DISTINCT resource_class values with their counts summed, e.g. ["UNKNOWN:2013", "PROTECTED_CLIENT_DATA:1"]. ' +
        'If status is BLOCKED (ROOT_REQUIRED), report evidence_classes: [] and status BLOCKED. ' +
        'Never include, quote, or summarize raw filesystem paths from journalctl output — they are dropped at the Python boundary and this workflow must not reintroduce them.',
  outputSchema: evidenceSchema,
  lane: { version: 1, key: 'gate-gather-sanitized-evidence', mode: 'gate' }
});

// Step 3 QUALIFY — PYTHON's disposition is authoritative; the workflow/model never overrides it.
const qualify = await runs.run('gate-qualify', {
  agent: 'general-purpose',
  task: 'Run (timeout 300): ' + CLI + ' assess-update --unit ' + UNIT_DEFAULT + '\n' +
        'Capture stdout JSON even on nonzero exit. Return its disposition verbatim and the JSON line as raw. Do not interpret or soften it.',
  outputSchema: qualifySchema,
  lane: { version: 1, key: 'gate-qualify', mode: 'gate' }
});
const qualificationDisposition = qualify.structuredOutput.disposition;

// Non-proposing terminal states decided purely by Python, before any model lane runs.
if (qualificationDisposition === 'PRIVACY_BOUNDARY_VIOLATION') {
  return { terminal_state: 'PRIVACY_BOUNDARY_VIOLATION',
           evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition },
           human_action: 'canary rung FAILED — investigate host immediately; no policy change is proposed.' };
}
if (qualificationDisposition === 'REQUALIFIED_UNCHANGED' || qualificationDisposition === 'NO_CHANGE') {
  return { terminal_state: 'REQUALIFIED_UNCHANGED',
           evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition } };
}
if (qualificationDisposition === 'INCONCLUSIVE' || qualificationDisposition === 'FAILED') {
  return { terminal_state: 'INCONCLUSIVE',
           evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition },
           human_action: 're-run with root for the ROOT_REQUIRED rungs or fix the failed rung.' };
}
if (qualificationDisposition === 'NEEDS_HUMAN') {
  return { terminal_state: 'NEEDS_HUMAN',
           evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition, proposed_delta: null, validator_verdict: 'NOT_REACHED' },
           human_action: 'no baseline exists — record one via change-snapshot --record-baseline (owner, root) before any delta work. This workflow never applies; human approval is the only apply path.' };
}

// Shared provider preflight before the sole model lane (degrade, never launch blind).
const pre = await runs.run('gate-preflight', {
  agent: 'general-purpose',
  task: 'Run (timeout 300): bash /home/graham/.pi/agent/workflows/model-preflight.sh --timeout 90 — report capacity only.',
  outputSchema: { type: 'object', required: ['capacity'],
    properties: { capacity: { type: 'string', enum: ['ok', 'degraded', 'none'] }, detail: { type: 'string' } } },
  lane: { version: 1, key: 'gate-preflight', mode: 'gate' }
});
if (pre.structuredOutput.capacity === 'none') {
  return { terminal_state: 'BLOCKED', detail: 'no provider capacity for the investigate lane: ' + (pre.structuredOutput.detail || '') };
}

// Step 4 INVESTIGATE — the ONLY model touch-point in the whole workflow.
// Bounded to ONE round: research informs the EXPLANATION and drafts a candidate
// PolicyDeltaProposal; it NEVER decides the verdict (Step 5's deterministic validator
// decides) and it NEVER sees raw paths — only the sanitized classes from Step 2.
const investigationRounds = 1;
for (let round = 0; round < investigationRounds; round++) {
  const investigation = await runs.run('investigate-' + UNIT_DEFAULT + '-' + round, {
    agent: 'general-purpose',
    task: 'You are a privacy reviewer. The deterministic qualification said POLICY_CHANGE_PROPOSED.\n' +
          'Sanitized evidence classes (the ONLY evidence you may use — resource_class:count, never raw paths): ' +
          JSON.stringify(gather.structuredOutput.evidence_classes) + '\n' +
          'Change disposition: ' + changeDisposition + '\n' +
          'Write ONE candidate PolicyDeltaProposal JSON file (ubuntu_service_privacy.policy_delta_proposal.v1: add_read_roots, resource_class, reason, required_for_observed_check, protected_overlap) to /tmp/assess-update-candidate.json ' +
          'using your read-only knowledge of the unit profile under ' + SKILL_DIR + '/profiles. Set protected_overlap honestly (it is re-derived, never trusted). ' +
          'If the sanitized evidence does not justify ANY widening, write no file and return proposal_file: "". ' +
          'Your verdict_claim is advisory only — research informs the explanation, NEVER the verdict. Do not modify the repo.',
    outputSchema: investigateSchema,
    toolTimeoutMs: 300000, timeoutMs: 600000, toolBudget: { hard: 20 },
    lane: { version: 1, key: 'investigate-' + round, mode: 'worker' }
  });
  if (!investigation.structuredOutput.proposal_file) {
    return { terminal_state: 'NEEDS_HUMAN',
             evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition, proposed_delta: null, validator_verdict: 'NO_CANDIDATE_DRAFTED' },
             explanation: investigation.structuredOutput.explanation,
             human_action: 'model could not justify a widening from sanitized evidence — human decides. The workflow never applies; human approval is the only apply path.' };
  }

  // Step 5 VALIDATE — deterministic DeltaVerdict decides eligibility. REJECTED_*/INCONCLUSIVE kills the proposal here.
  const validation = await runs.run('gate-validate-delta-' + round, {
    agent: 'general-purpose',
    task: 'Run (timeout 300): ' + CLI + ' validate-delta ' + investigation.structuredOutput.proposal_file + '\n' +
          'Capture the verdict from stdout even on nonzero exit. Return it verbatim. Do not soften REJECTED_*.',
    outputSchema: validateSchema,
    lane: { version: 1, key: 'gate-validate-delta-' + round, mode: 'gate' }
  });
  const verdict = validation.structuredOutput.verdict;
  if (verdict !== 'ACCEPTED_FOR_HUMAN_REVIEW') {
    // Proposal dies here. The loop is capped at 1 round, so this is terminal.
    return { terminal_state: 'NEEDS_HUMAN',
             evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition, proposed_delta: investigation.structuredOutput.proposal_file, validator_verdict: verdict },
             human_action: 'candidate delta rejected deterministically (' + verdict + ') — a human must author any replacement. This workflow never applies; human approval is the only apply path.' };
  }

  // Step 6 TERMINAL — the ONLY exit after an eligible proposal: human approval.
  // There is deliberately no APPLY branch anywhere in this file.
  return { terminal_state: 'NEEDS_HUMAN',
           evidence_chain: { change_disposition: changeDisposition, evidence_classes: gather.structuredOutput.evidence_classes, qualification_disposition: qualificationDisposition, proposed_delta: investigation.structuredOutput.proposal_file, validator_verdict: verdict },
           explanation: investigation.structuredOutput.explanation,
           human_action: 'candidate is ACCEPTED_FOR_HUMAN_REVIEW — review the proposal and apply manually via the owner-approved deploy path if satisfied. This workflow never applies; human approval is the only apply path.' };
}

// Unreachable given the cap, but honest failure reporting demands a labeled exit.
return { terminal_state: 'BLOCKED', detail: 'investigation loop exhausted without a labeled exit' };
