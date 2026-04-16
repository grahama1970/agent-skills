import React, { useState, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { ChatLauncherIcon, EmbryChatLauncherIcon, EmbryTopbarLogo } from "@embry/logo/react";

// ── NVIS MIL-STD-3009 Color System ──────────────────────────────────────────
const NVIS = {
  red:    "#ff4444",  // NVIS RED (Embry-OS canonical)
  amber:  "#ffaa00",  // NVIS AMBER
  green:  "#00ff88",  // NVIS GREEN
  blue:   "#4a9eff",  // NVIS BLUE
  bg:     "#141414",  // Embry-OS canonical BG
  border: "rgba(255, 255, 255, 0.13)",
} as const;

// ── Types ───────────────────────────────────────────────────────────────────

interface ControlResolution {
  exists: boolean;
  name: string;
  qra_count: number;
  technique_context?: string;
  tactic?: string;
  match_type?: string;
  confidence?: number;
}

interface Decomposition {
  question: string;
  given_components: string[];
  then_components: string[];
  component_queries?: Record<string, string>;
  component_entity_types?: Record<string, string>;
}

interface EvidenceCase {
  verdict: string;
  grade: string;
  score: number;
  grounding_ok: boolean;
  grounding_issues: string[];
  grounding_warnings?: Array<{
    term?: string;
    category?: string;
    type?: string;
    suggestion?: string;
    fuzzy_matches?: Array<Record<string, unknown>>;
  }>;
  needs_clarification?: boolean;
  primary_state?: string;
  blocking_reason_classes?: string[];
  clarification_items?: ClarificationItem[];
  citation_alignment: string;
  plausibility: string;
  recommendation: string;
  answer_in_corpus: boolean;
  resolution_map?: Record<string, ControlResolution>;
  all_control_ids?: string[];
  recall_count?: number;
  elapsed_s?: number;
  decomposition?: Decomposition;
  technique_groups?: Record<string, number | {
    technique?: string;
    evidence_count?: number;
    avg_confidence?: number;
    control_ids?: string[];
    best_evidence?: Record<string, unknown>;
  }>;
  sub_claims?: Array<string | {
    technique?: string;
    evidence_count?: number;
    avg_confidence?: number;
    control_ids?: string[];
    best_evidence?: {
      confidence?: number;
      control_ids?: string[];
      result?: {
        technique?: string;
      };
    };
  }>;
  citations?: string[];
  lean4_result?: {
    success?: boolean;
    verified?: boolean;
    provable?: boolean;
    prediction?: string;
    provable_confidence?: number;
    proof_attempted?: boolean;
    proof_success?: boolean;
    proof_skipped?: boolean;
    gate_blocked?: boolean;
    elapsed_ms?: number;
    stdout?: string;
    error?: string | null;
    reason?: string;
    proof_data?: {
      success?: boolean;
      verified?: boolean;
      lean_code?: string;
      code?: string;
      compiler_output?: string;
      stdout?: string;
      error_message?: string;
    };
  };
  gate_trace?: Array<{
    gate: string;
    passed: boolean;
    detail?: string;
    data?: Record<string, unknown>;
  }>;
  claim?: {
    text?: string;
    category?: string;
    id?: string;
    verdict?: string;
    control_ids?: string[];
    gate_results?: EvidenceCase["gate_trace"];
  };
  verdict_data?: {
    state?: string;
    grade?: string;
    score?: number;
    reasoning?: string;
  };
  evidence?: Array<Record<string, unknown>>;
  total_ms?: number;
  explicit_question_controls?: Array<{
    mention?: string;
    control_id?: string;
    name?: string;
    tactic?: string;
    technique_context?: string;
    position?: number;
  }>;
  semantic_relation?: {
    related?: boolean | null;
    answerable?: boolean | null;
    rationale?: string;
    clarifying_question?: string;
    backend?: string;
    controls?: Array<Record<string, unknown>>;
    bridge_evidence?: Record<string, unknown>;
  };
}

type IssueClass =
  | "misspelling"
  | "possible_typo"
  | "framework_misspelling"
  | "not_in_corpus"
  | "fabricated_context"
  | "insufficient_evidence";

interface ClarificationItem {
  kind: IssueClass;
  label: string;
  detail: string;
  recoverable: boolean;
}

type PrimaryState = "SATISFIED" | "NEEDS_CLARIFICATION" | "INCONCLUSIVE" | "NOT_SATISFIED";

interface QRAItem {
  review_id: number;
  qra_id: number;
  question: string;
  answer: string;
  citations: string[];
  grounding_score: number;
  gemini_grade: string;
  gemini_confidence: number;
  v7_grade: string;
  v7_confidence: number;
  v9_grade: string;
  v9_confidence: number;
  majority_vote: string;
  human_grade: string;
  evidence_case?: EvidenceCase;
}

interface ProcessStep {
  label: string;
  status: "success" | "warning" | "error" | "pending";
  detail: string;
}

function getFabricatedTerms(resolutionMap?: Record<string, ControlResolution>): string[] {
  if (!resolutionMap) return [];
  return Object.entries(resolutionMap)
    .filter(([term, resolution]) => {
      const lower = term.toLowerCase();
      return resolution?.exists === false && lower !== "space" && lower !== "cyber";
    })
    .map(([term]) => term);
}

function getClarificationItems(
  ec?: EvidenceCase,
  resolutionMap?: Record<string, ControlResolution>,
): ClarificationItem[] {
  if (!ec) return [];
  if (ec.clarification_items?.length) return ec.clarification_items;

  const items: ClarificationItem[] = [];
  const warningItems = Array.isArray(ec.grounding_warnings) ? ec.grounding_warnings : [];
  const fabricatedTerms = getFabricatedTerms(resolutionMap);

  if (warningItems.length) {
    for (const warning of warningItems) {
      const term = String(warning.term || "").trim();
      if (!term) continue;
      const category = String(warning.category || warning.type || "");
      if (category === "fabricated_id") {
        items.push({
          kind: "fabricated_context",
          label: term,
          detail: `The term '${term}' does not ground to the mission corpus and should be treated as a hard blocker.`,
          recoverable: false,
        });
      } else if (category === "not_in_corpus") {
        items.push({
          kind: "not_in_corpus",
          label: term,
          detail: `The term '${term}' needs a SPARTA-native restatement before disposition.`,
          recoverable: true,
        });
      } else if (category === "misspelling" || category === "framework_misspelling") {
        const suggestion = String(warning.suggestion || "").trim();
        items.push({
          kind: category === "framework_misspelling" ? "framework_misspelling" : "misspelling",
          label: term,
          detail: suggestion
            ? `Possible correction: '${suggestion}'. Clarify before disposition.`
            : `The term '${term}' appears misspelled and needs clarification before disposition.`,
          recoverable: true,
        });
      } else if (category === "possible_typo") {
        items.push({
          kind: "possible_typo",
          label: term,
          detail: `The term '${term}' may be a typo and should be clarified before disposition.`,
          recoverable: true,
        });
      }
    }
  } else {
    for (const issue of ec.grounding_issues || []) {
      items.push({
        kind: "not_in_corpus",
        label: issue,
        detail: `The term '${issue}' needs a SPARTA-native restatement before disposition.`,
        recoverable: true,
      });
    }
  }

  for (const term of fabricatedTerms.slice(0, 3)) {
    if (!items.some((item) => item.label === term && item.kind === "fabricated_context")) {
      items.push({
        kind: "fabricated_context",
        label: term,
        detail: `The term '${term}' does not ground to the mission corpus and should be treated as a hard blocker.`,
        recoverable: false,
      });
    }
  }

  if (!items.length && (ec.needs_clarification || ec.verdict === "INCONCLUSIVE")) {
    items.push({
      kind: "insufficient_evidence",
      label: "Mission-specific scope",
      detail: "The current evidence is not specific enough to dispose this case without a clarification turn.",
      recoverable: true,
    });
  }

  return items;
}

function normalizeEvidenceCase(raw?: EvidenceCase | Record<string, unknown> | null): EvidenceCase | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const ec = raw as EvidenceCase;
  if (!("claim" in ec) || !("verdict" in ec && typeof ec.verdict !== "string")) {
    return ec;
  }

  const gateTrace = Array.isArray(ec.gate_trace)
    ? ec.gate_trace
    : Array.isArray(ec.claim?.gate_results)
      ? ec.claim?.gate_results
      : [];
  const recallStep = gateTrace?.find((gate) => gate.gate === "step_2_recall");
  const grounding = (recallStep?.data?.grounding_evidence as Record<string, unknown> | undefined) || {};
  const entities = (recallStep?.data?.entities as Record<string, unknown> | undefined) || {};
  const rawVerdict = (ec as unknown as { verdict?: Record<string, unknown> }).verdict;
  const verdictState = typeof rawVerdict?.state === "string"
    ? rawVerdict.state.toUpperCase()
    : ec.claim?.verdict || "INCONCLUSIVE";

  const groundingWarnings = Array.isArray(grounding.warnings) ? grounding.warnings as Array<Record<string, unknown>> : [];
  const groundingIssues = groundingWarnings
    .map((warning) => String(warning.term || "").trim())
    .filter(Boolean);

  return {
    verdict: verdictState,
    grade: typeof rawVerdict?.grade === "string" ? rawVerdict.grade : (ec.grade || "C"),
    score: typeof rawVerdict?.score === "number" ? rawVerdict.score : (ec.score || 0),
    grounding_ok: Boolean(grounding.grounding_ok),
    grounding_issues: groundingIssues,
    grounding_warnings: groundingWarnings as EvidenceCase["grounding_warnings"],
    citation_alignment: "",
    plausibility: "",
    recommendation: typeof rawVerdict?.reasoning === "string" ? rawVerdict.reasoning : "",
    answer_in_corpus: !groundingWarnings.some((warning) => warning.category === "not_in_corpus"),
    resolution_map: (grounding.resolution_map as Record<string, ControlResolution> | undefined)
      || (entities.resolution_map as Record<string, ControlResolution> | undefined)
      || ec.resolution_map,
    all_control_ids: Array.isArray(entities.all_control_ids)
      ? entities.all_control_ids as string[]
      : (ec.claim?.control_ids || ec.all_control_ids),
    recall_count: typeof recallStep?.data?.qra_count === "number"
      ? recallStep.data.qra_count as number
      : (Array.isArray(ec.evidence) ? ec.evidence.length : ec.recall_count),
    elapsed_s: typeof ec.total_ms === "number" ? ec.total_ms / 1000 : ec.elapsed_s,
    decomposition: ec.decomposition,
    technique_groups: (recallStep?.data?.technique_groups as Record<string, number> | undefined) || ec.technique_groups,
    sub_claims: ec.sub_claims,
    citations: ec.citations,
    lean4_result: ec.lean4_result,
    gate_trace: gateTrace,
    claim: ec.claim,
    evidence: ec.evidence,
    total_ms: ec.total_ms,
    explicit_question_controls: (raw as Record<string, unknown>).explicit_question_controls as EvidenceCase["explicit_question_controls"],
    semantic_relation: (raw as Record<string, unknown>).semantic_relation as EvidenceCase["semantic_relation"],
  };
}

function getPrimaryState(
  ec?: EvidenceCase,
  resolutionMap?: Record<string, ControlResolution>,
): PrimaryState {
  if (!ec) return "INCONCLUSIVE";
  if (ec.primary_state === "SATISFIED" || ec.primary_state === "NEEDS_CLARIFICATION" || ec.primary_state === "INCONCLUSIVE" || ec.primary_state === "NOT_SATISFIED") {
    return ec.primary_state;
  }

  const clarificationItems = getClarificationItems(ec, resolutionMap);
  const explicitPair = (ec.explicit_question_controls?.length || 0) >= 2;
  const semanticDecision = ec.semantic_relation?.answerable ?? ec.semantic_relation?.related;

  if (clarificationItems.some((item) => !item.recoverable)) return "NOT_SATISFIED";
  if (clarificationItems.some((item) => item.recoverable)) return "NEEDS_CLARIFICATION";
  if (explicitPair && ec.semantic_relation == null) return "INCONCLUSIVE";
  if (explicitPair && semanticDecision === false) return "INCONCLUSIVE";
  if (ec.verdict === "NOT_SATISFIED") return "NOT_SATISFIED";
  if (ec.verdict === "SATISFIED") return "SATISFIED";
  return "INCONCLUSIVE";
}

function getNextAction(primaryState: PrimaryState): string {
  switch (primaryState) {
    case "SATISFIED":
      return "Review evidence and assign ground-truth label";
    case "NEEDS_CLARIFICATION":
      return "Run /memory clarify and resolve the blocking terms";
    case "NOT_SATISFIED":
      return "Reject or restate the question; do not synthesize an answer";
    default:
      return "Collect more evidence or route for deeper review";
  }
}

function getStateSubtitle(primaryState: PrimaryState): string {
  switch (primaryState) {
    case "SATISFIED":
      return "Disposition-ready evidence case";
    case "NEEDS_CLARIFICATION":
      return "Clarification required before disposition";
    case "NOT_SATISFIED":
      return "Hard blocker prevents acceptance";
    default:
      return "Evidence is insufficient for disposition";
  }
}

function getStateTone(primaryState: PrimaryState): { bg: string; border: string; text: string; badge: string } {
  switch (primaryState) {
    case "SATISFIED":
      return { bg: "rgba(0,255,136,0.12)", border: "#166534", text: NVIS.green, badge: "Disposition Ready" };
    case "NEEDS_CLARIFICATION":
      return { bg: "rgba(255,170,0,0.12)", border: "#92400e", text: NVIS.amber, badge: "Clarify Required" };
    case "NOT_SATISFIED":
      return { bg: "rgba(255,68,68,0.12)", border: "#991b1b", text: NVIS.red, badge: "Hard Failure" };
    default:
      return { bg: "rgba(74,158,255,0.12)", border: "#1d4ed8", text: NVIS.blue, badge: "Evidence Gap" };
  }
}

function getLean4Summary(ec?: EvidenceCase): { label: string; detail: string; tone: string } | null {
  if (!ec) return null;
  const lean4 = ec.lean4_result
    ?? ec.gate_trace?.find((gate) => gate.gate === "step_6_lean4" || gate.gate === "step_5_lean4")?.data as EvidenceCase["lean4_result"] | undefined;
  if (!lean4) {
    const haltedEarly = Array.isArray(ec.gate_trace)
      && ec.gate_trace.some((gate) => gate.gate === "step_2c_grounding_typo" || gate.gate === "step_4_clarify");
    if (haltedEarly) {
      return {
        label: "NOT RUN",
        detail: "Formal check was not reached because clarification is still required.",
        tone: NVIS.amber,
      };
    }
    return null;
  }

  const proofData = lean4.proof_data || {};
  const blocked = Boolean(lean4.gate_blocked);
  const skipped = Boolean(lean4.proof_skipped);
  const success = Boolean(
    lean4.proof_success
      || proofData.success
      || proofData.verified
  );
  const confidence = typeof lean4.provable_confidence === "number"
    ? `${Math.round(lean4.provable_confidence * 100)}%`
    : null;

  if (blocked) {
    return {
      label: "BLOCKED",
      detail: lean4.reason || "Formal verification gate was blocked.",
      tone: NVIS.red,
    };
  }
  if (skipped) {
    return {
      label: "SKIPPED",
      detail: confidence ? `Provability ${confidence}` : "Formal proof skipped.",
      tone: NVIS.blue,
    };
  }
  if (success) {
    return {
      label: "PROVED",
      detail: confidence ? `Provability ${confidence}` : "Formal proof verified.",
      tone: NVIS.green,
    };
  }
  return {
    label: "FAILED",
    detail: lean4.reason || proofData.error_message || "Formal proof did not verify.",
    tone: NVIS.red,
  };
}

function getFormalizableStatus(ec?: EvidenceCase): { label: string; tone: string; detail: string } | null {
  if (!ec) return null;
  const lean4 = ec.lean4_result
    ?? ec.gate_trace?.find((gate) => gate.gate === "step_6_lean4" || gate.gate === "step_5_lean4")?.data as EvidenceCase["lean4_result"] | undefined;
  const summary = getLean4Summary(ec);
  if (!lean4 && !summary) return null;

  const prediction = String(lean4?.prediction || "").trim().toLowerCase();
  const confidence = typeof lean4?.provable_confidence === "number"
    ? `${Math.round(lean4.provable_confidence * 100)}%`
    : null;

  if (prediction === "formalizable") {
    return {
      label: "YES",
      tone: NVIS.green,
      detail: confidence ? `Lean4 classifier marked this formalizable at ${confidence}.` : "Lean4 classifier marked this formalizable.",
    };
  }
  if (prediction === "not_formalizable") {
    return {
      label: "NO",
      tone: NVIS.red,
      detail: confidence ? `Lean4 classifier marked this not formalizable at ${confidence}.` : "Lean4 classifier marked this not formalizable.",
    };
  }
  if (summary?.label === "NOT RUN") {
    return {
      label: "NOT ASSESSED",
      tone: NVIS.amber,
      detail: summary.detail,
    };
  }
  if (summary?.label === "BLOCKED") {
    return {
      label: "BLOCKED",
      tone: NVIS.red,
      detail: summary.detail,
    };
  }
  return {
    label: "UNKNOWN",
    tone: NVIS.blue,
    detail: confidence ? `Provability confidence ${confidence}.` : "Formalizability classifier result unavailable.",
  };
}

function FormalVerificationWell({ ec }: { ec?: EvidenceCase }) {
  const summary = getLean4Summary(ec);
  const formalizable = getFormalizableStatus(ec);
  if (!summary && !formalizable) return null;

  const lean4 = ec?.lean4_result
    ?? ec?.gate_trace?.find((gate) => gate.gate === "step_6_lean4" || gate.gate === "step_5_lean4")?.data as EvidenceCase["lean4_result"] | undefined;
  const proofData = lean4?.proof_data || {};
  const theoremSummary = ec?.claim?.text || ec?.decomposition?.question || "No formal claim summary recorded.";
  const leanCode = proofData.lean_code || proofData.code || "";
  const compilerOutput = proofData.compiler_output || proofData.stdout || lean4?.stdout || "";
  const proofError = lean4?.reason || proofData.error_message || lean4?.error || "";

  return (
    <div className="rounded-xl p-5 border bg-[#1a1a1a]" style={{ borderColor: NVIS.border }}>
      <div className="flex items-center justify-between gap-4 mb-4">
        <div className="text-[10px] font-bold uppercase tracking-widest text-indigo-400">Formalization &amp; Proof</div>
        {lean4?.elapsed_ms ? (
          <div className="text-[10px] font-medium text-slate-500">{Math.round(lean4.elapsed_ms)} ms</div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {formalizable && (
          <div className="rounded-lg border border-slate-800 bg-[#111827] p-3">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Formalizable</div>
            <div className="text-[16px] font-black" style={{ color: formalizable.tone }}>{formalizable.label}</div>
            <div className="text-[11px] leading-relaxed text-slate-400 mt-1">{formalizable.detail}</div>
          </div>
        )}
        {summary && (
          <div className="rounded-lg border border-slate-800 bg-[#111827] p-3">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Proof Status</div>
            <div className="text-[16px] font-black" style={{ color: summary.tone }}>{summary.label}</div>
            <div className="text-[11px] leading-relaxed text-slate-400 mt-1">{summary.detail}</div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3 mb-4">
        <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Theorem / Claim Summary</div>
        <div className="text-[12px] leading-relaxed text-slate-200">{theoremSummary}</div>
      </div>

      {(leanCode || compilerOutput || proofError) && (
        <details className="rounded-lg border border-slate-800 bg-[#0b1220]">
          <summary className="cursor-pointer list-none px-4 py-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Proof Artifacts</div>
              <div className="text-[12px] font-semibold text-slate-200">Lean4 code and compiler output</div>
            </div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Expand</div>
          </summary>
          <div className="px-4 pb-4 space-y-4 border-t border-slate-800">
            {leanCode && (
              <div className="pt-4">
                <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Lean4 Code</div>
                <pre className="rounded-lg border border-slate-800 bg-black/40 p-3 text-[11px] leading-relaxed text-slate-200 overflow-x-auto whitespace-pre-wrap">
                  <code>{leanCode}</code>
                </pre>
              </div>
            )}
            {compilerOutput && (
              <div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Compiler Output</div>
                <pre className="rounded-lg border border-slate-800 bg-black/40 p-3 text-[11px] leading-relaxed text-slate-300 overflow-x-auto whitespace-pre-wrap">
                  <code>{compilerOutput}</code>
                </pre>
              </div>
            )}
            {proofError && (
              <div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">Failure Detail</div>
                <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-[11px] leading-relaxed text-red-200">
                  {proofError}
                </div>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function SemanticRationaleWell({ ec }: { ec?: EvidenceCase }) {
  const semantic = ec?.semantic_relation;
  if (!semantic) return null;

  const answerable = semantic.answerable ?? semantic.related;
  const tone = answerable ? NVIS.green : NVIS.amber;
  const status = answerable ? "ANSWERABLE" : "CLARIFY";
  const controls = (ec?.explicit_question_controls || []).map((c) => c.control_id || c.mention).filter(Boolean);
  const clarifyingQuestion = semantic.clarifying_question?.trim();

  return (
    <div className="rounded-xl p-5 border bg-[#1a1a1a]" style={{ borderColor: NVIS.border }}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 mb-1">Semantic Rationale</div>
          <div className="text-[15px] font-black uppercase tracking-wide" style={{ color: tone }}>{status}</div>
        </div>
        {semantic.backend ? (
          <div className="text-[10px] text-slate-500">{semantic.backend}</div>
        ) : null}
      </div>

      {controls.length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-[#111827] p-3 mb-4">
          <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Controls Under Judgment</div>
          <div className="text-[12px] text-slate-200">{controls.join(" • ")}</div>
        </div>
      )}

      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3 mb-4">
        <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">LLM Rationale</div>
        <div className="text-[12px] leading-relaxed text-slate-200">
          {semantic.rationale || "No semantic rationale recorded."}
        </div>
      </div>

      {!answerable && clarifyingQuestion && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="text-[10px] font-bold uppercase tracking-widest text-amber-400 mb-1">Suggested /memory clarify</div>
          <div className="text-[12px] leading-relaxed text-slate-100">{clarifyingQuestion}</div>
        </div>
      )}
    </div>
  );
}

function ThoughtTrace({ ec }: { ec?: EvidenceCase }) {
  if (!ec) return null;
  const primaryState = getPrimaryState(ec, ec.resolution_map);
  const stages: ProcessStep[] = [
    { label: "Extract", status: "success", detail: "Entity IDs identified" },
    { label: "Decompose", status: "success", detail: "Given/Then clauses parsed" },
    { label: "Ground", status: ec.grounding_ok ? "success" : "warning", detail: ec.grounding_ok ? "Resolved in SPARTA" : "Grounding requires operator attention" },
    { label: "Retrieve", status: (ec.citations?.length ?? 0) > 0 ? "success" : "pending", detail: `${ec.citations?.length || 0} sources matched` },
    { label: "Verdict", status: primaryState === "SATISFIED" ? "success" : primaryState === "NEEDS_CLARIFICATION" ? "warning" : "error", detail: primaryState }
  ];

  return (
    <div className="px-6 py-3 border-b border-slate-800/80 bg-[#0b1326]">
      <div className="mx-auto flex max-w-[1600px] items-center justify-center gap-3 overflow-x-auto">
        {stages.map((s, i) => (
          <React.Fragment key={s.label}>
            <div className="flex items-center gap-2 whitespace-nowrap" title={s.detail}>
              <div className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${
                s.status === "success" ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.6)]" :
                s.status === "warning" ? "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.6)]" :
                "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.6)]"
              }`} />
              <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-300">
                {s.label}
              </span>
            </div>
            {i < stages.length - 1 && <div className="w-6 h-px bg-slate-700" />}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

type Grade = "PASS" | "FAIL" | "SKIP";
type FilterTab = "all" | "need_review" | "auto_fail" | "adversarial" | "done";
type LauncherVariant = "embry" | "chat";

const ENTITY_DB: Record<string, string> = {
  "IR-4": "Incident Handling: The organization implements an incident handling capability for systems that includes preparation, detection and analysis, containment, eradication, and recovery.",
  "IR-4(15)": "Public Relations and Reputation Repair: The organization coordinates with public affairs to repair the organization's reputation and trust following a high-visibility incident.",
  "IR-4(10)": "Incident Handling | Special Knowledge: The organization ensures that individuals with specialized knowledge are available to assist in incident handling.",
  "IR-5(1)": "Incident Monitoring: The organization tracks and documents system incidents on an ongoing basis.",
  "IR-6(1)": "Incident Reporting: The organization ensures that the reportable incidents are tracked and reported to the required authorities.",
  "ESA-T2007.004": "Develop/Obtain Capabilities: DSSS or Frequency hopping sequence. Adversaries may develop the sequence patterns needed to intercept or disrupt spread-spectrum communications.",
  "T1558.005": "Kerberos Ticket Cache: Adversaries may abuse Kerberos ticket cache files (ccache) to gain persistence or move laterally.",
  "CWE-276": "Incorrect Default Permissions: Permissions of a file or directory are set in a way that allows access to more users than intended during installation.",
  "T1542.001": "System Firmware: Adversaries may modify system firmware (BIOS, UEFI) to maintain persistence on a system below the operating system level.",
  "T1422.002": "Wi-Fi Discovery: Adversaries may search for information about Wi-Fi networks to support both ongoing and future campaigns.",
  "vulnerability": "A weakness in an information system, system security procedures, internal controls, or implementation that could be exploited or triggered by a threat source.",
  "threat": "Any circumstance or event with the potential to adversely impact organizational operations (including mission, functions, image, or reputation), organizational assets, individuals, other organizations, or the Nation through an information system via unauthorized access, destruction, disclosure, modification of information, and/or denial of service.",
  "risk": "A measure of the extent to which an entity is threatened by a potential circumstance or event, and typically a function of: (i) the adverse impacts that would arise if the circumstance or event occurs; and (ii) the likelihood of occurrence.",
  "asset": "An item of value to stakeholders. An asset may be tangible (e.g., a physical item such as hardware, software, firmware, a computing platform, network device, or other IT component) or intangible (e.g., information, data, trademark, copyright, software, intellectual property, image, or reputation).",
};

// ── Entity Chip with Tooltip ────────────────────────────────────────────────

const STOP_WORDS = new Set(["mission", "operations", "against", "system", "security", "control", "adversary", "adversaries", "process", "access", "data", "threat", "activity", "network", "information", "spacecraft", "ground", "segment"]);

const ENTITY_DB_KEYS = Object.keys(ENTITY_DB);

function EntityChip({ 
  id, 
  resolution, 
  hoveredId, 
  onHover,
  excludedEntities
}: { 
  id: string; 
  resolution: ControlResolution;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  excludedEntities: Set<string>;
}) {
  const [open, setOpen] = useState(false);
  const exists = resolution.exists;
  const chipColor = exists ? NVIS.green : NVIS.red;
  const textColor = exists ? "black" : "white";
  const isHovered = id === hoveredId;
  const isExcluded = excludedEntities.has(id.toLowerCase());
  const lowConfidence = (resolution.confidence || 1) < 0.7;

  if (isExcluded) return null;

  return (
    <span
      className={`relative inline-flex items-center transition-all duration-200 ${
        isHovered ? "scale-110 z-[50]" : ""
      }`}
      onMouseEnter={() => {
        setOpen(true);
        onHover?.(id);
      }}
      onMouseLeave={() => {
        setOpen(false);
        onHover?.(null);
      }}
    >
      <span
        className={`px-1.5 py-0.5 rounded text-[11px] font-bold whitespace-nowrap cursor-help transition-all duration-300 ${
          lowConfidence && exists ? "animate-pulse" : ""
        }`}
        style={{ 
          backgroundColor: isHovered ? NVIS.blue : chipColor, 
          color: isHovered ? "black" : textColor,
          boxShadow: isHovered ? `0 0 12px ${NVIS.blue}` : "none",
          border: lowConfidence && exists ? `1px dashed ${NVIS.amber}` : "none"
        }}
      >
        {id}
      </span>
      {exists && resolution.qra_count > 0 && (
        <span className="text-[9px] font-medium ml-0.5" style={{ color: chipColor }}>
          {resolution.qra_count}
        </span>
      )}
      {!exists && (
        <span className="text-[9px] font-medium ml-0.5" style={{ color: chipColor }}>
          {"\u2717"}
        </span>
      )}
      {open && (
        <span
          className="absolute top-full left-0 mt-1 z-[100] min-w-[280px] rounded-lg p-3 text-[11px] leading-relaxed shadow-2xl border bg-[#1e293b] animate-in fade-in zoom-in duration-200"
          style={{ borderColor: exists ? "rgba(46, 204, 113, 0.4)" : "rgba(231, 76, 60, 0.4)" }}
        >
          <span className="block font-bold mb-1" style={{ color: chipColor }}>{id.toUpperCase()}</span>
          {resolution.name && (
            <span className="block text-slate-100 font-bold mb-1 text-[12px] uppercase tracking-tight">{resolution.name}</span>
          )}
          <span className="block text-slate-400 italic mb-2">
            {ENTITY_DB[id.toLowerCase()] || ENTITY_DB[id] || (resolution as { definition?: string }).definition || "Definition not available in standard database."}
          </span>
          <div className="flex flex-col gap-1 border-t border-slate-700/50 pt-2 text-[10px]">
            <span className="text-slate-500 font-medium">
              {exists ? "STATUS: Grounded in Mission Corpus" : "STATUS: Potential Fabrication Alert"}
            </span>
            {resolution.technique_context && (
              <span className="text-slate-400">Context: {resolution.technique_context}</span>
            )}
            {resolution.tactic && (
              <span className="text-slate-400">Tactic: {resolution.tactic}</span>
            )}
            {resolution.match_type && (
              <span className="text-slate-500">
                Match: {resolution.match_type} ({(resolution.confidence || 0) * 100}%)
              </span>
            )}
          </div>
        </span>
      )}
    </span>
  );
}

// ── NVIS Entity Chip Highlighting ───────────────────────────────────────────
// Scans text for known control IDs / terms from the resolution map,
// wraps them in colored inline chips with hover tooltips.

function highlightEntities(
  text: string,
  resolutionMap: Record<string, ControlResolution> | undefined,
  hoveredId: string | null,
  onHover: (id: string | null) => void,
  excludedEntities: Set<string>
): ReactNode[] {
  if (!resolutionMap || !text) return [text];

  const terms = Object.keys(resolutionMap).filter(
    (t) => {
      const lowerT = t.toLowerCase();
      return t.length > 2 && 
             !STOP_WORDS.has(lowerT) &&
             lowerT !== "space" && 
             lowerT !== "cyber" &&
             lowerT !== "mission" &&
             lowerT !== "control";
    }
  );
  terms.sort((a, b) => b.length - a.length);
  if (terms.length === 0) return [text];

  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");

  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const termKey = terms.find((t) => t.toLowerCase() === part.toLowerCase());
    if (!termKey) return <span key={i}>{part}</span>;
    const resolution = resolutionMap[termKey];
    if (!resolution) return <span key={i}>{part}</span>;
    return (
      <EntityChip 
        key={i} 
        id={termKey} 
        resolution={resolution} 
        hoveredId={hoveredId}
        onHover={onHover}
        excludedEntities={excludedEntities}
      />
    );
  });
}

// ── Given/Then Sentence Decomposition ───────────────────────────────────────
// Renders the actual sentence fragments from DecompositionNode with inline
// entity highlighting. Each clause is readable prose with color-coded entities.

function GivenThenPanel({
  decomposition,
  resolutionMap,
  hoveredId,
  onHover,
  excludedEntities
}: {
  decomposition?: Decomposition;
  resolutionMap?: Record<string, ControlResolution>;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  excludedEntities: Set<string>;
}) {
  if (!decomposition) return null;
  const { given_components, then_components } = decomposition;
  if (!given_components?.length && !then_components?.length) return null;
  const trailingLabel = given_components.length > 0 ? "Then" : "Question Focus";

  return (
    <div className="rounded-lg p-4 mb-3" style={{ backgroundColor: "#1e293b" }}>
      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-3">
        Sentence Decomposition
      </div>
      {given_components.length > 0 && (
        <div className="mb-3">
          <span
            className="inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide mb-2"
            style={{ backgroundColor: "rgba(68,170,255,0.15)", color: "#44AAFF" }}
          >
            Given
          </span>
          <div className="flex flex-col gap-1.5 border-l-2 border-slate-700 ml-1.5 pl-3">
            {given_components.map((clause, i) => (
              <div key={i} className="text-slate-300 text-[13px] leading-relaxed flex items-baseline gap-2">
                <span className="flex-1">{highlightEntities(clause, resolutionMap, hoveredId, onHover, excludedEntities)}</span>
                {decomposition.component_entity_types?.[clause] && (
                  <span className="text-[9px] text-slate-500 italic shrink-0">
                    → {decomposition.component_entity_types[clause]}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {then_components.length > 0 && (
        <div>
          <span
            className="inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide mb-2"
            style={{ backgroundColor: "rgba(255,170,0,0.15)", color: NVIS.amber }}
          >
            {trailingLabel}
          </span>
          <div className="flex flex-col gap-1.5 border-l-2 border-slate-700 ml-1.5 pl-3">
            {then_components.map((clause, i) => (
              <div key={i} className="text-slate-300 text-[13px] leading-relaxed flex items-baseline gap-2">
                <span className="flex-1">{highlightEntities(clause, resolutionMap, hoveredId, onHover, excludedEntities)}</span>
                {decomposition.component_entity_types?.[clause] && (
                  <span className="text-[9px] text-slate-500 italic shrink-0">
                    → {decomposition.component_entity_types[clause]}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Entity Glossary Well ────────────────────────────────────────────────────
// Collapsible reference panel showing all extracted entities with definitions.

function EntityGlossary({ 
  resolutionMap, 
  explicitControls,
  excludedEntities, 
  setExcludedEntities 
}: { 
  resolutionMap?: Record<string, ControlResolution>;
  explicitControls?: EvidenceCase["explicit_question_controls"];
  excludedEntities: Set<string>;
  setExcludedEntities: (next: Set<string>) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!resolutionMap) return null;

  const explicitIds = new Set((explicitControls || []).map((control) => String(control.control_id || control.mention || "")).filter(Boolean));

  const entries = Object.entries(resolutionMap)
    .filter(([id]) => {
      const lowerId = id.toLowerCase();
      return id.length > 2 && 
             !STOP_WORDS.has(lowerId) &&
             lowerId !== "space" && 
             lowerId !== "cyber" &&
             lowerId !== "mission" &&
             lowerId !== "control" &&
             (explicitIds.size === 0 || explicitIds.has(id));
    })
    .map(([id, res]) => ({
      id,
      ...res,
      definition: ENTITY_DB[id.toLowerCase()] || ENTITY_DB[id] || (res as { definition?: string }).definition
    }))
    .sort((a, b) => {
      if (a.exists !== b.exists) return a.exists ? -1 : 1;
      return b.qra_count - a.qra_count;
    });

  if (entries.length === 0) return null;

  const resolved = entries.filter((r) => r.exists);
  const fabricated = entries.filter((r) => !r.exists);

  return (
    <div className="rounded-lg mb-4 border border-slate-700/50 overflow-hidden shadow-lg bg-[#0f172a]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/50 transition-colors group"
      >
        <div className="flex items-center gap-3">
          <span className={`text-[10px] text-slate-500 transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
          <span className="text-[11px] font-bold uppercase tracking-widest text-[#64748b]">
            Entity Glossary
          </span>
          <div className="flex items-center gap-2 text-[10px] text-slate-600 font-medium">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#2ecc71]"></span> {resolved.length} resolved</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#e74c3c]"></span> {fabricated.length} fabricated</span>
          </div>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 max-h-[400px] overflow-y-auto custom-scrollbar border-t border-slate-700/30 pt-4 bg-[#0a0f1d]">
          <div className="grid gap-6">
            {entries.map((res) => (
              <div key={res.id} className="group/item">
                <div className="flex items-center gap-3 mb-2">
                  <button
                    onClick={() => {
                      const next = new Set(excludedEntities);
                      const lower = res.id.toLowerCase();
                      if (next.has(lower)) next.delete(lower);
                      else next.add(lower);
                      setExcludedEntities(next);
                    }}
                    className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                      excludedEntities.has(res.id.toLowerCase()) 
                        ? "bg-slate-700 text-slate-500" 
                        : "bg-slate-800 text-slate-400 hover:bg-red-500/20 hover:text-red-400"
                    }`}
                    title="Toggle visibility"
                  >
                    {excludedEntities.has(res.id.toLowerCase()) ? "HIDDEN" : "HIDE"}
                  </button>
                  <div 
                    className={`px-2 py-1 rounded font-mono font-bold text-[11px] shadow-sm tracking-tight transition-all duration-300 ${
                      excludedEntities.has(res.id.toLowerCase()) ? "opacity-30" : "opacity-100"
                    }`}
                    style={{ 
                      backgroundColor: res.exists ? "rgba(46, 204, 113, 0.1)" : "rgba(231, 76, 60, 0.1)", 
                      color: res.exists ? "#2ecc71" : "#e74c3c",
                      border: `1px solid ${res.exists ? "rgba(46, 204, 113, 0.2)" : "rgba(231, 76, 60, 0.2)"}`
                    }}
                  >
                    {res.id}
                  </div>
                  <h4 className="text-[12px] font-bold text-slate-100 uppercase tracking-tight truncate">
                    {res.name || "Undefined Term"}
                  </h4>
                </div>
                <div className={`pl-3 border-l-2 border-slate-800 ml-2 py-1 transition-opacity ${
                  excludedEntities.has(res.id.toLowerCase()) ? "opacity-30" : "opacity-100"
                }`}>
                  <p className="text-[11px] leading-relaxed text-slate-400 font-medium">
                    {res.definition || `No definition found for this entity. It was ${res.exists ? 'verified against the mission corpus' : 'flagged as a likely hallucination/fabrication'}.`}
                  </p>
                  {res.qra_count > 0 && (
                    <div className="mt-2 text-[10px] text-slate-500 flex items-center gap-1.5 italic">
                      <span className="text-[#3b82f6]">◈</span> Referenced in {res.qra_count} related evidence cases
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Gate Trace Pipeline ─────────────────────────────────────────────────────
// Derives gate statuses from the evidence case fields.

interface Gate {
  name: string;
  status: "pass" | "warn" | "fail";
  fact: string;
  reason: string;
}

function deriveGates(ec: EvidenceCase, resolutionMap?: Record<string, ControlResolution>): Gate[] {
  const primaryState = getPrimaryState(ec, resolutionMap);
  const clarificationItems = getClarificationItems(ec, resolutionMap);
  const explicitControls = (ec.explicit_question_controls || [])
    .map((control) => control.control_id || control.mention)
    .filter((controlId): controlId is string => Boolean(controlId));
  const explicitResolutions = explicitControls
    .map((controlId) => ({ controlId, resolution: resolutionMap?.[controlId] }))
    .filter((entry) => entry.resolution);
  const bridgeGate = ec.gate_trace?.find((gate) => gate.gate === "step_3_technique_bridge");
  const semanticGate = ec.gate_trace?.find((gate) => gate.gate === "step_4_semantic_relation");
  const semantic = ec.semantic_relation;
  const hasHardBlocker = clarificationItems.some((item) => !item.recoverable);
  const missingControls = explicitResolutions.filter((entry) => entry.resolution?.exists === false).map((entry) => entry.controlId);
  const unresolvedExplicitCount = Math.max(explicitControls.length - explicitResolutions.length, 0);
  const explicitMissing = [...missingControls];
  if (unresolvedExplicitCount > 0) {
    explicitMissing.push(`${unresolvedExplicitCount} unresolved mention${unresolvedExplicitCount === 1 ? "" : "s"}`);
  }

  const termsExistGate: Gate = {
    name: "Terms Exist",
    status: explicitControls.length === 0 ? "warn" : explicitMissing.length === 0 ? "pass" : "fail",
    fact: explicitControls.length
      ? `${explicitControls.length}/${explicitControls.length} explicit controls parsed from the question.`
      : "No explicit control pair was parsed from the question.",
    reason: explicitMissing.length === 0
      ? `Resolved controls: ${explicitControls.join(", ")}.`
      : `Missing or unresolved: ${explicitMissing.join(", ")}.`
  };

  const corpusBlockers = clarificationItems.filter((item) => item.kind === "fabricated_context" || item.kind === "not_in_corpus");
  const inCorpusGate: Gate = {
    name: "In SPARTA Corpus",
    status: corpusBlockers.length === 0 ? "pass" : corpusBlockers.some((item) => !item.recoverable) ? "fail" : "warn",
    fact: corpusBlockers.length === 0
      ? "All explicit controls ground to SPARTA corpus entries."
      : `${corpusBlockers.length} corpus grounding issue${corpusBlockers.length === 1 ? "" : "s"} detected.`,
    reason: corpusBlockers.length === 0
      ? "No fabricated or off-corpus control IDs were detected."
      : corpusBlockers.slice(0, 2).map((item) => item.detail).join(" ")
  };

  const tacticSet = new Set(explicitResolutions.map((entry) => entry.resolution?.tactic).filter(Boolean));
  const techniqueSet = new Set(explicitResolutions.map((entry) => entry.resolution?.technique_context).filter(Boolean));
  const bridgePassed = Boolean(bridgeGate?.passed);
  const sharedContextLabel = tacticSet.size === 1
    ? `Shared tactic: ${Array.from(tacticSet)[0]}.`
    : techniqueSet.size === 1
      ? `Shared technique: ${Array.from(techniqueSet)[0]}.`
      : "No shared tactic or technique was established.";
  const sharedContextGate: Gate = {
    name: "Shared Technique / Row",
    status: hasHardBlocker ? "fail" : bridgePassed ? "pass" : "warn",
    fact: sharedContextLabel,
    reason: bridgePassed
      ? String(bridgeGate?.detail || "The controls were bridged inside the same SPARTA context.")
      : String(bridgeGate?.detail || "The backend did not confirm a shared SPARTA technique or worksheet row.")
  };

  const semanticGateCard: Gate = {
    name: "LLM Relation Judgment",
    status: semantic
      ? (semantic.answerable ?? semantic.related ? "pass" : "fail")
      : "warn",
    fact: semantic
      ? `Answerable: ${(semantic.answerable ?? semantic.related) ? "yes" : "no"}.`
      : "No semantic relation judgment was recorded.",
    reason: semantic
      ? (semantic.rationale || "No semantic rationale was returned.")
      : String(semanticGate?.detail || "The LLM did not return a relation rationale for this control pair.")
  };

  const outcomeReason = primaryState === "NEEDS_CLARIFICATION"
    ? `${clarificationItems.length} clarification item(s) still need /memory clarify.`
    : getNextAction(primaryState);
  const outcomeGate: Gate = {
    name: "Outcome",
    status: primaryState === "NEEDS_CLARIFICATION" ? "warn" : primaryState === "SATISFIED" ? "pass" : "fail",
    fact: `Primary state: ${primaryState.replaceAll("_", " ")}.`,
    reason: outcomeReason
  };

  return [termsExistGate, inCorpusGate, sharedContextGate, semanticGateCard, outcomeGate];
}

function GateTracePipeline({ ec, resolutionMap }: { ec?: EvidenceCase; resolutionMap?: Record<string, ControlResolution> }) {
  if (!ec) return null;

  const gates = deriveGates(ec, resolutionMap);
  const gateColors: Record<string, string> = {
    pass: NVIS.green,
    warn: NVIS.amber,
    fail: NVIS.red,
  };

  return (
    <div className="mb-4">
      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
        Decision Chain
      </div>
      <div className="space-y-2">
        {gates.map((gate, index) => (
          <div 
            key={gate.name} 
            className="relative flex flex-col gap-1 rounded-lg border border-slate-800/60 bg-slate-900/50 px-3 py-2.5 transition-all hover:bg-slate-900/80"
          >
            {index < gates.length - 1 && (
              <div className="absolute left-[15px] top-[34px] h-[calc(100%+10px)] w-px bg-slate-800/80" aria-hidden="true" />
            )}
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-bold uppercase tracking-tight text-slate-100 flex items-center gap-2">
                <span 
                  className="relative z-10 w-2 h-2 rounded-full" 
                  style={{ backgroundColor: gateColors[gate.status], boxShadow: `0 0 8px ${gateColors[gate.status]}` }}
                ></span>
                {gate.name}
              </span>
              <span 
                className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded"
                style={{ backgroundColor: `${gateColors[gate.status]}15`, color: gateColors[gate.status] }}
              >
                {gate.status}
              </span>
            </div>
            <p className="text-[11px] font-semibold leading-relaxed text-slate-100">{gate.fact}</p>
            <p className="text-[10px] leading-relaxed text-slate-400">{gate.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Small Components ────────────────────────────────────────────────────────

function GradeChip({ label, grade, confidence }: { label?: string; grade: string; confidence?: number }) {
  const isPASS = grade === "PASS";
  return (
    <div>
      {label && <div className="text-[10px] text-slate-500 mb-1">{label}</div>}
      <div
        className="px-3 py-1.5 rounded-md text-xs font-semibold"
        style={{
          backgroundColor: isPASS ? "#166534" : "#991b1b",
          color: isPASS ? NVIS.green : NVIS.red,
        }}
      >
        {grade} {confidence !== undefined && `(${(confidence * 100).toFixed(0)}%)`}
      </div>
    </div>
  );
}

// ── Embry Logo with D3 Force Ring ───────────────────────────────────────────

// EmbryLogo is now imported from components/EmbryLogo.tsx

function BlockingReasonPanel({ items }: { items: ClarificationItem[] }) {
  if (!items.length) return null;
  const visibleItems = items.slice(0, 3);

  return (
    <div className="px-4 py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Rationale</div>
        <div className="text-[10px] font-semibold text-slate-500">{items.length} total</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-[11px]">
          <thead className="bg-slate-900/90">
            <tr className="text-[9px] uppercase tracking-widest text-slate-500">
              <th className="px-3 py-2 font-bold">Type</th>
              <th className="px-3 py-2 font-bold">Term</th>
              <th className="px-3 py-2 font-bold">Action</th>
              <th className="px-3 py-2 font-bold">Why</th>
            </tr>
          </thead>
          <tbody>
        {visibleItems.map((item, index) => {
          const tone = item.recoverable
            ? { border: "rgba(255,170,0,0.25)", bg: "rgba(255,170,0,0.08)", text: NVIS.amber, badge: "Clarify" }
            : { border: "rgba(255,68,68,0.25)", bg: "rgba(255,68,68,0.08)", text: NVIS.red, badge: "Reject" };
          return (
            <tr
              key={`${item.label}-${index}`}
              className="border-t border-slate-800 align-top"
              style={{ backgroundColor: tone.bg }}
            >
              <td className="px-3 py-2">
                <span className="text-[9px] font-black uppercase tracking-widest" style={{ color: tone.text }}>
                  {item.kind.replaceAll("_", " ")}
                </span>
              </td>
              <td className="px-3 py-2 text-[12px] font-semibold text-slate-100">{item.label}</td>
              <td className="px-3 py-2">
                <div className="text-[9px] font-black uppercase tracking-widest" style={{ color: tone.text }}>
                  {tone.badge}
                </div>
              </td>
              <td className="px-3 py-2 text-[11px] leading-relaxed text-slate-300">{item.detail}</td>
            </tr>
          );
        })}
          </tbody>
        </table>
      </div>
      {items.length > visibleItems.length && (
        <div className="mt-2 text-[10px] text-slate-500">
          Showing first {visibleItems.length} items. Expand detail view for the remaining {items.length - visibleItems.length}.
        </div>
      )}
    </div>
  );
}

// ── Agent Chat Well ─────────────────────────────────────────────────────────
// Connecting to /subagent-service via bridge.

function AgentChatWell({ 
  excludedEntities, 
  setExcludedEntities 
}: { 
  excludedEntities: Set<string>; 
  setExcludedEntities: (next: Set<string>) => void;
}) {
  const launcherVariant = useMemo<LauncherVariant>(() => {
    if (typeof window === "undefined") return "chat";
    return new URLSearchParams(window.location.search).get("launcher") === "embry" ? "embry" : "chat";
  }, []);
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: "I am ready to help with this evidence case. Any corrections?" }
  ]);
  const [input, setInput] = useState("");

  const send = () => {
    if (!input.trim()) return;
    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");

    // Simulate "Steering" Logic (Simplified for brevity)
    setTimeout(() => {
      const lowerInput = userMsg.toLowerCase();
      let response = "Understood. I've updated my internal reasoning weights.";
      
      if (lowerInput.includes("hide") || lowerInput.includes("exclude") || lowerInput.includes("remove")) {
        const next = new Set(excludedEntities);
        if (lowerInput.includes("nist")) {
          ENTITY_DB_KEYS.filter(k => k.startsWith("IR-")).forEach(k => next.add(k.toLowerCase()));
          response = "I've demoted all NIST entities in the markup. Focusing solely on SPARTA TTPs.";
        } else if (lowerInput.includes("vulnerability")) {
          next.add("vulnerability");
          response = "Hiding generic 'vulnerability' terminology from the reasoning braid.";
        }
        setExcludedEntities(next);
      } else if (lowerInput.includes("focus") || lowerInput.includes("reset")) {
        setExcludedEntities(new Set());
        response = "Resetting all filters. All grounded entities are now visible in the braid.";
      }

      setMessages((prev) => [...prev, { role: "assistant", content: response }]);
    }, 600);
  };

  return (
    <>
      {/* Floating Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="group fixed bottom-6 right-6 z-[1000] flex h-16 w-16 items-center justify-center overflow-visible rounded-full border border-blue-500/42 bg-[#05070d] shadow-[0_0_18px_rgba(37,99,235,0.12)] transition-all duration-200 ease-out hover:scale-[1.03] hover:border-blue-400/60 hover:shadow-[0_10px_24px_rgba(15,23,42,0.38)] active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/55 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f172a]"
        title={`Agent Course Correction (${launcherVariant === "chat" ? "chat" : "Embry"} launcher)`}
      >
        {isOpen ? (
          <span className="text-xl font-bold text-slate-300">\u2715</span>
        ) : (
          launcherVariant === "chat"
            ? <ChatLauncherIcon size={34} className="text-slate-100 transition-all duration-200 ease-out group-hover:text-white group-hover:scale-[1.03]" />
            : <EmbryChatLauncherIcon size={56} state={isOpen ? "speaking" : "thinking"} />
        )}
      </button>

      {/* Slide-in Chat Console */}
      <div 
        className={`fixed bottom-24 right-6 w-[380px] h-[580px] rounded-2xl overflow-hidden border border-slate-700 shadow-[0_20px_50px_rgba(0,0,0,0.5)] z-[999] transition-all duration-500 transform ${
          isOpen ? "translate-y-0 opacity-100 scale-100" : "translate-y-10 opacity-0 scale-95 pointer-events-none"
        }`}
        style={{ 
          backgroundColor: "#0f172a",
          backgroundImage: "radial-gradient(circle at top right, rgba(37,99,235,0.06), transparent)"
        }}
      >
        <div className="px-4 py-3 border-b border-slate-700 bg-slate-800/80 backdrop-blur-md flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className="text-[12px] font-black uppercase tracking-widest text-slate-100">Course Correction</span>
          </div>
          <span className="text-[9px] text-slate-500 font-bold uppercase tracking-tight bg-slate-900 px-1.5 py-0.5 rounded border border-slate-700">AGENT BRIDGE :8620</span>
        </div>
        
        <div className="flex-1 h-[460px] overflow-y-auto p-4 flex flex-col gap-4 custom-scrollbar bg-slate-900/50">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] px-4 py-3 rounded-2xl text-[12px] leading-relaxed shadow-sm ${
                  m.role === "user" 
                    ? "bg-blue-600 text-white rounded-tr-none" 
                    : "bg-slate-800 text-slate-200 border border-slate-700/50 rounded-tl-none"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>

        <div className="absolute bottom-0 left-0 right-0 p-4 bg-slate-800/50 backdrop-blur-md border-t border-slate-700">
          <div className="flex gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-700 focus-within:border-blue-500 transition-colors shadow-inner">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Correct the reasoning course..."
              className="flex-1 bg-transparent border-none text-[13px] text-slate-100 placeholder:text-slate-500 px-2 outline-none"
            />
            <button
              onClick={send}
              className="bg-blue-600 hover:bg-blue-500 text-white w-8 h-8 rounded-lg flex items-center justify-center transition-colors shadow-lg active:scale-90"
            >
              <span className="text-lg">\u2714</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function SubClaimList({
  claims,
}: {
  claims?: Array<string | {
    technique?: string;
    evidence_count?: number;
    avg_confidence?: number;
    control_ids?: string[];
    best_evidence?: {
      confidence?: number;
      control_ids?: string[];
      result?: {
        technique?: string;
      };
    };
  }>;
}) {
  if (!claims?.length) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1.5">Sub-Claims</div>
      <div className="flex flex-col gap-1.5">
        {claims.map((claim, i) => {
          if (typeof claim === "string") {
            return (
              <div key={i} className="text-[11px] text-slate-300 pl-2 border-l border-slate-700 leading-relaxed">
                {claim}
              </div>
            );
          }

          const technique = claim.technique || claim.best_evidence?.result?.technique || "Unknown";
          const evidenceCount = claim.evidence_count ?? 0;
          const confidence = typeof claim.avg_confidence === "number"
            ? `${Math.round(claim.avg_confidence * 100)}%`
            : null;

          return (
            <div key={i} className="pl-2 border-l border-slate-700">
              <div className="text-[11px] font-semibold text-slate-200 leading-relaxed">
                {technique}
              </div>
              <div className="text-[10px] text-slate-400 leading-relaxed">
                {evidenceCount} evidence{evidenceCount === 1 ? "" : "s"}
                {confidence ? ` • avg confidence ${confidence}` : ""}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TechniqueGroupList({
  groups,
}: {
  groups?: Record<string, number | {
    technique?: string;
    evidence_count?: number;
    avg_confidence?: number;
    control_ids?: string[];
    best_evidence?: Record<string, unknown>;
  }>;
}) {
  if (!groups || Object.keys(groups).length === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1.5">Technique Groups</div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(groups).map(([name, value]) => {
          const evidenceCount = typeof value === "number"
            ? value
            : (typeof value?.evidence_count === "number" ? value.evidence_count : 0);
          const confidence = typeof value === "object" && value && typeof value.avg_confidence === "number"
            ? `${Math.round(value.avg_confidence * 100)}%`
            : null;
          return (
            <span
              key={name}
              className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-400"
              title={confidence ? `${name}: ${evidenceCount} evidence, avg confidence ${confidence}` : `${name}: ${evidenceCount} evidence`}
            >
              {name}: <span className="text-slate-200 font-bold">{evidenceCount}</span>
              {confidence && <span className="ml-1 text-slate-500">({confidence})</span>}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceManifest({ ec }: { ec?: EvidenceCase }) {
  if (!ec) {
    return (
      <div className="bg-slate-800/50 border border-slate-700 border-dashed rounded-lg p-4 text-slate-500 text-xs text-center italic">
        Evidence case not yet run. Pre-triage with /create-evidence-case to populate.
      </div>
    );
  }

  const explicitControls = ec.explicit_question_controls || [];
  const controlNames = explicitControls.map((control) => control.control_id || control.mention).filter(Boolean);
  const controlsExist = explicitControls.length >= 2 && explicitControls.every((control) => {
    const key = String(control.mention || control.control_id || "");
    const mapped = key ? ec.resolution_map?.[key] : undefined;
    return mapped?.exists !== false;
  });
  const inCorpus = ec.grounding_ok && !ec.grounding_issues?.length;
  const bridgeGate = ec.gate_trace?.find((gate) => gate.gate === "step_3_technique_bridge");
  const sharedTechnique = Boolean(bridgeGate?.passed);
  const sharedTechniqueDetail = String(bridgeGate?.detail || "No shared SPARTA technique or row was established.");
  const semantic = ec.semantic_relation;
  const semanticKnown = Boolean(semantic);
  const semanticAnswerable = semantic?.answerable ?? semantic?.related ?? false;
  const semanticDetail = semantic?.rationale || "No semantic relation judgment was recorded.";
  const outcome = semanticKnown
    ? (semanticAnswerable ? "Answer" : "/memory clarify")
    : (getPrimaryState(ec, ec.resolution_map) === "SATISFIED" ? "Unclear - verdict lacks semantic rationale" : getNextAction(getPrimaryState(ec, ec.resolution_map)));

  const checks = [
    {
      label: "Do the terms exist?",
      value: controlsExist ? "Yes" : "No",
      status: controlsExist ? "PASS" : "FAIL",
      detail: controlNames.length ? controlNames.join(" • ") : "No explicit controls identified in the question.",
    },
    {
      label: "Are they in the SPARTA corpus?",
      value: inCorpus ? "Yes" : "No",
      status: inCorpus ? "PASS" : "FAIL",
      detail: inCorpus ? "Grounding returned no corpus blockers." : (ec.grounding_issues?.join(", ") || "Grounding blockers require review."),
    },
    {
      label: "Are they under the same technique / row?",
      value: sharedTechnique ? "Yes" : "No",
      status: sharedTechnique ? "PASS" : "FAIL",
      detail: sharedTechniqueDetail,
    },
    {
      label: "Does the LLM judge them related enough?",
      value: semanticKnown ? (semanticAnswerable ? "Yes" : "No") : "Missing",
      status: semanticKnown ? (semanticAnswerable ? "PASS" : "FAIL") : "FAIL",
      detail: semanticDetail,
    },
    {
      label: "Outcome",
      value: outcome,
      status: semanticKnown ? (semanticAnswerable ? "PASS" : "FAIL") : "FAIL",
      detail: semanticKnown && !semanticAnswerable && semantic?.clarifying_question
        ? semantic.clarifying_question
        : outcome,
    },
  ] as const;

  const firstFailure = checks.find((check) => check.status === "FAIL");

  return (
    <div className="space-y-4">
      {firstFailure && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <div className="text-[10px] font-bold uppercase tracking-widest text-red-400 mb-1">First Failure</div>
          <div className="text-[13px] font-semibold text-slate-100">{firstFailure.label}</div>
          <div className="text-[12px] leading-relaxed text-slate-300 mt-1">{firstFailure.detail}</div>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-[11px]">
          <thead className="bg-slate-900/90">
            <tr className="text-[9px] uppercase tracking-widest text-slate-500">
              <th className="px-3 py-2 font-bold">Check</th>
              <th className="px-3 py-2 font-bold">Result</th>
              <th className="px-3 py-2 font-bold">Why</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((check) => {
              const tone = check.status === "PASS"
                ? { text: NVIS.green, bg: "rgba(0,255,136,0.05)" }
                : { text: NVIS.red, bg: "rgba(255,68,68,0.08)" };
              return (
                <tr key={check.label} className="border-t border-slate-800 align-top" style={{ backgroundColor: tone.bg }}>
                  <td className="px-3 py-3 text-[12px] font-semibold text-slate-100">{check.label}</td>
                  <td className="px-3 py-3">
                    <span className="text-[10px] font-black uppercase tracking-widest" style={{ color: tone.text }}>
                      {check.value}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-[11px] leading-relaxed text-slate-300">{check.detail}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-4">
        <TechniqueGroupList groups={ec.technique_groups} />
        <SubClaimList claims={ec.sub_claims} />
      </div>
    </div>
  );
}

// ── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [items, setItems] = useState<QRAItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [labels, setLabels] = useState<Record<number, Grade>>(() => {
    try {
      const saved = localStorage.getItem("cascade_gt_labels_v3");
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const [adversarial, setAdversarial] = useState<Record<number, boolean>>(() => {
    try {
      const savedAdv = localStorage.getItem("cascade_gt_adversarial_v1");
      return savedAdv ? JSON.parse(savedAdv) : {};
    } catch { return {}; }
  });
  const [filter, setFilter] = useState<FilterTab>("all");
  const [hoveredId, setHoveredId] = useState<string|null>(null);
  const [excludedEntities, setExcludedEntities] = useState<Set<string>>(new Set());

  useEffect(() => {
    type EvidenceCaseMap = Record<string, EvidenceCase | Record<string, unknown>>;

    const applyCases = (dataText: string, caseMap: EvidenceCaseMap) => {
      const parsed: QRAItem[] = dataText.trim().split("\n").map((l: string) => JSON.parse(l));
      for (const item of parsed) {
        const ec = normalizeEvidenceCase(
          caseMap[String(item.review_id)]
          ?? item.evidence_case
        );
        if (ec) item.evidence_case = ec;
      }
      setItems(parsed);
    };

    Promise.all([
      fetch("/data.jsonl").then((r) => r.text()),
      fetch("/evidence_cases.json").then((r) => r.json() as Promise<EvidenceCaseMap>).catch(() => ({} as EvidenceCaseMap)),
    ]).then(([dataText, reducedEvidenceCases]: [string, EvidenceCaseMap]) => {
      applyCases(dataText, reducedEvidenceCases);

      fetch("/evidence_cases_full.json")
        .then((r) => (r.ok ? r.json() : {} as EvidenceCaseMap))
        .then((fullEvidenceCases: EvidenceCaseMap) => {
          if (Object.keys(fullEvidenceCases).length) {
            applyCases(dataText, { ...reducedEvidenceCases, ...fullEvidenceCases });
          }
        })
        .catch(() => {});
    });
  }, []);

  const saveLabels = useCallback(
    (next: Record<number, Grade>) => {
      setLabels(next);
      localStorage.setItem("cascade_gt_labels_v3", JSON.stringify(next));
    },
    []
  );

  const toggleAdversarial = useCallback(
    (reviewId: number) => {
      const next = { ...adversarial, [reviewId]: !adversarial[reviewId] };
      setAdversarial(next);
      localStorage.setItem("cascade_gt_adversarial_v1", JSON.stringify(next));
    },
    [adversarial]
  );

  const filteredItems = useMemo(() => {
    switch (filter) {
      case "need_review":
        return items.filter((i) => !labels[i.review_id] && getPrimaryState(i.evidence_case, i.evidence_case?.resolution_map) !== "NOT_SATISFIED");
      case "auto_fail":
        return items.filter((i) => getPrimaryState(i.evidence_case, i.evidence_case?.resolution_map) === "NOT_SATISFIED" && !adversarial[i.review_id]);
      case "adversarial":
        return items.filter((i) => adversarial[i.review_id]);
      case "done":
        return items.filter((i) => labels[i.review_id]);
      default:
        return items;
    }
  }, [items, labels, adversarial, filter]);

  const counts = useMemo(() => {
    const autoFail = items.filter((i) => getPrimaryState(i.evidence_case, i.evidence_case?.resolution_map) === "NOT_SATISFIED" && !adversarial[i.review_id]).length;
    const advCount = items.filter((i) => adversarial[i.review_id]).length;
    const done = items.filter((i) => labels[i.review_id]).length;
    const needReview = items.filter((i) => !labels[i.review_id] && getPrimaryState(i.evidence_case, i.evidence_case?.resolution_map) !== "NOT_SATISFIED").length;
    return { all: items.length, need_review: needReview, auto_fail: autoFail, adversarial: advCount, done };
  }, [items, labels, adversarial]);

  const doLabel = useCallback(
    (grade: Grade) => {
      if (!filteredItems.length) return;
      const item = filteredItems[idx];
      if (!item) return;
      const next = { ...labels, [item.review_id]: grade };
      saveLabels(next);
      if (idx < filteredItems.length - 1) setIdx((i) => i + 1);
    },
    [filteredItems, idx, labels, saveLabels]
  );

  const navigate = useCallback(
    (delta: number) => {
      setIdx((i) => Math.max(0, Math.min(filteredItems.length - 1, i + delta)));
    },
    [filteredItems.length]
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key.toLowerCase()) {
        case "p": doLabel("PASS"); break;
        case "f": doLabel("FAIL"); break;
        case "s": doLabel("SKIP"); break;
        case "a":
          if (filteredItems[idx]) toggleAdversarial(filteredItems[idx].review_id);
          break;
        case "arrowleft": navigate(-1); break;
        case "arrowright": navigate(1); break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [doLabel, navigate, toggleAdversarial, filteredItems, idx]);

  const changeFilter = (f: FilterTab) => {
    setFilter(f);
    setIdx(0);
  };

  const exportResults = () => {
    const lines = items
      .map((item) => JSON.stringify({
        ...item,
        human_grade: labels[item.review_id] || "",
        is_adversarial: adversarial[item.review_id] || false,
        evidence_case: item.evidence_case || null,
      }))
      .join("\n");
    const blob = new Blob([lines], { type: "application/jsonl" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "human_reviewed_138.jsonl";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!items.length) return <div className="min-h-screen flex items-center justify-center text-slate-400" style={{ background: "#0f172a" }}>Loading...</div>;

  const item = filteredItems[idx];
  if (!item) return <div className="min-h-screen flex items-center justify-center text-slate-400" style={{ background: "#0f172a" }}>No items in this filter.</div>;

  const currentLabel = labels[item.review_id];
  const isAdversarial = adversarial[item.review_id];
  const labeledCount = Object.keys(labels).length;
  const progressPct = (labeledCount / items.length) * 100;
  const resMap = item.evidence_case?.resolution_map;
  const primaryState = getPrimaryState(item.evidence_case, resMap);
  const clarificationItems = getClarificationItems(item.evidence_case, resMap);
  const stateTone = getStateTone(primaryState);
  const lean4Summary = getLean4Summary(item.evidence_case);

  const tabs: { key: FilterTab; label: string; count: number }[] = [
    { key: "all", label: "All", count: counts.all },
    { key: "need_review", label: "Need Review", count: counts.need_review },
    { key: "auto_fail", label: "Auto-FAIL", count: counts.auto_fail },
    { key: "adversarial", label: "Adversarial", count: counts.adversarial },
    { key: "done", label: "Done", count: counts.done },
  ];

  return (
    <div className="min-h-screen text-slate-200 font-sans text-sm flex flex-col" style={{ background: "#0f172a" }}>
      <header className="fixed top-0 left-0 right-0 h-16 bg-[#0f172a]/95 backdrop-blur-xl border-b border-slate-800/50 flex items-center justify-between px-8 z-50">
        <div className="flex items-center gap-2">
          <EmbryTopbarLogo size={42} state="idle" />
          <div className="font-mono ml-2">
            <h1 className="text-xl font-black text-slate-100 tracking-tighter uppercase flex items-center gap-3">
              Evidence Case
              <span className="text-[9px] font-black bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20 tracking-[0.2em] ml-1">Ground Truth</span>
            </h1>
            <div className="text-[9px] font-bold text-slate-500 uppercase tracking-[0.4em] mt-0.5 ml-0.5">Automated Synthesis Pipeline</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => changeFilter(tab.key)}
              className={`px-3 py-1.5 rounded-md text-[10px] font-black uppercase tracking-widest transition-all ${
                filter === tab.key
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-900/40"
                  : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
            >
              {tab.label}
              <span className="ml-2 opacity-50 font-mono">[{tab.count}]</span>
            </button>
          ))}
        </div>
      </header>

      {/* Spacing for fixed header */}
      <div className="h-16 shrink-0" />

      {/* Progress bar */}
      <div className="h-1.5 shrink-0" style={{ background: "#1e293b" }}>
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${progressPct}%`, backgroundColor: "#22c55e" }}
        />
      </div>

      <ThoughtTrace ec={item.evidence_case} />

      {/* Waterfall Layout: 3 Columns */}
      <div className="flex flex-1 min-h-0 overflow-hidden" style={{ background: NVIS.bg }}>
        
        {/* PANE 1: CLAIM CONTEXT (30%) */}
        <div className="w-[30%] border-r p-6 overflow-y-auto custom-scrollbar flex flex-col gap-6" style={{ borderColor: NVIS.border }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-4 bg-blue-500 rounded-full" />
            <h2 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">Claim Context</h2>
          </div>
          {/* Question Card */}
          <div className="rounded-xl p-5 border bg-[#1a1a1a] shadow-inner" style={{ borderColor: NVIS.border }}>
            <div className="text-[10px] font-bold uppercase tracking-widest text-[#4a9eff] mb-3">Claim Question</div>
            <div className="text-slate-200 leading-relaxed text-[15px] font-medium">
              {highlightEntities(item.question, resMap, hoveredId, setHoveredId, excludedEntities)}
            </div>
          </div>

          {/* Answer Card */}
          <div className="rounded-xl p-5 border bg-[#1a1a1a]" style={{ borderColor: NVIS.border }}>
            <div className="flex items-center gap-2 mb-3">
              <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-500">Claim Answer</div>
              {item.evidence_case && !item.evidence_case.answer_in_corpus && (
                <span className="text-[9px] px-1.5 py-0.5 rounded font-black bg-red-500/10 text-red-500 border border-red-500/20">HALLUCINATION RISK</span>
              )}
            </div>
            <div className="text-slate-300 leading-relaxed text-[14px] whitespace-pre-wrap font-medium">
              {highlightEntities(item.answer, resMap, hoveredId, setHoveredId, excludedEntities)}
            </div>
          </div>

          <GivenThenPanel 
            decomposition={item.evidence_case?.decomposition} 
            resolutionMap={resMap} 
            hoveredId={hoveredId}
            onHover={setHoveredId}
            excludedEntities={excludedEntities}
          />
        </div>

        {/* PANE 2: EVIDENCE HUB (35%) */}
        <div className="w-[35%] border-r p-6 overflow-y-auto custom-scrollbar flex flex-col gap-6" style={{ borderColor: NVIS.border, backgroundColor: "#111111" }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-4 bg-emerald-500 rounded-full" />
            <h2 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">Evidence Hub</h2>
          </div>

          <GateTracePipeline ec={item.evidence_case} resolutionMap={resMap} />

          <EntityGlossary 
            resolutionMap={resMap} 
            explicitControls={item.evidence_case?.explicit_question_controls}
            excludedEntities={excludedEntities} 
            setExcludedEntities={setExcludedEntities}
          />

          {/* Evidence Sources */}
          <div className="rounded-xl p-5 border bg-[#1a1a1a]" style={{ borderColor: NVIS.border }}>
            <div className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 mb-4">Discrete Evidence Citations</div>
            <div className="space-y-4">
              {item.citations?.length ? (
                item.citations.map((c, i) => (
                  <div key={i} className="group relative">
                    <div className="flex gap-3">
                      <span className="text-[10px] font-black text-slate-600 mt-1">0{i + 1}</span>
                      <div className="text-slate-400 text-[12px] leading-relaxed group-hover:text-slate-200 transition-colors">
                        {c}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-slate-600 italic text-[12px]">No citations retrieved.</div>
              )}
            </div>
          </div>

          <SemanticRationaleWell ec={item.evidence_case} />
          <FormalVerificationWell ec={item.evidence_case} />
        </div>

        {/* PANE 3: VERDICT SYNTHESIS (35%) */}
        <div className="w-[35%] p-6 overflow-y-auto custom-scrollbar flex flex-col gap-4" style={{ backgroundColor: "#0c0c0c" }}>
          <div className="sticky top-0 z-20 pb-2" style={{ backgroundColor: "#0c0c0c" }}>
            <div className="rounded-xl border bg-[#111827]" style={{ borderColor: stateTone.border }}>
              <div
                className="px-5 py-4 border-b"
                style={{ borderColor: "rgba(255,255,255,0.08)", backgroundColor: stateTone.bg, color: stateTone.text }}
              >
                <div className="flex flex-col gap-2">
                  <span className="text-[32px] leading-none font-black tracking-tight">{primaryState.replaceAll("_", " ")}</span>
                  <span className="text-[13px] font-semibold opacity-90">{getStateSubtitle(primaryState)}</span>
                </div>
              </div>

              <div className="px-5 py-3 border-b border-slate-800 bg-[#0f172a]">
                <div className="grid grid-cols-[1fr_auto] gap-4 items-start">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Next</div>
                    <div className="text-[14px] font-semibold text-slate-100 leading-snug">{getNextAction(primaryState)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Blockers</div>
                    <div className="text-[18px] font-black text-slate-100">{clarificationItems.length}</div>
                  </div>
                </div>
              </div>

              {lean4Summary && (
                <div className="px-5 py-2.5 border-b border-slate-800 bg-[#0b1220]">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Formal Check</div>
                      <div className="text-[12px] font-black uppercase tracking-[0.15em]" style={{ color: lean4Summary.tone }}>
                        {lean4Summary.label}
                      </div>
                    </div>
                    <div className="text-right text-[11px] leading-snug text-slate-300 max-w-[65%]">
                      {lean4Summary.detail}
                    </div>
                  </div>
                </div>
              )}

              <BlockingReasonPanel items={clarificationItems} />
            </div>
          </div>

          <details className="rounded-xl border bg-[#111111]" style={{ borderColor: NVIS.border }}>
            <summary className="cursor-pointer list-none px-4 py-3 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Diagnostics</div>
                <div className="text-[12px] font-semibold text-slate-200">Model votes and evidence manifest</div>
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Expand</div>
            </summary>
            <div className="px-4 pb-4 space-y-4 border-t border-slate-800">
              <div className="pt-4 flex gap-2 flex-wrap opacity-80">
                <GradeChip label="Gemini Prediction" grade={item.gemini_grade} confidence={item.gemini_confidence} />
                <GradeChip label="V7 Model Check" grade={item.v7_grade} confidence={item.v7_confidence} />
                <GradeChip label="V9 Ensemble" grade={item.v9_grade} confidence={item.v9_confidence} />
              </div>

              <div className="text-[11px] text-slate-400">
                <span className="font-bold uppercase tracking-widest text-[9px] text-slate-500 mr-2">Legacy Verdict</span>
                <span className="font-semibold text-slate-200">{item.evidence_case?.verdict || "UNAVAILABLE"}</span>
              </div>

              <EvidenceManifest ec={item.evidence_case} />
            </div>
          </details>
          
          {/* Adversarial toggle */}
          <button
            onClick={() => toggleAdversarial(item.review_id)}
            className="w-full py-2 rounded-xl text-[10px] font-black uppercase tracking-widest cursor-pointer transition-all border mt-2 shadow-sm"
            style={{
              backgroundColor: isAdversarial ? "rgba(124, 58, 237, 0.1)" : "transparent",
              borderColor: isAdversarial ? "#7c3aed" : NVIS.border,
              color: isAdversarial ? "#a78bfa" : "#64748b",
            }}
          >
            {isAdversarial ? "Adversarial Training Marker ON" : "Mark as Adversarial Example (A)"}
          </button>

          <div className="mt-auto space-y-3">
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-widest text-center">Commit Ground Truth Label</div>
            <div className="flex gap-3">
              <button onClick={() => doLabel("PASS")} className="flex-1 py-4 rounded-xl font-black transition-all hover:scale-[1.02] active:scale-95 bg-emerald-600 text-white shadow-lg shadow-emerald-900/20">PASS</button>
              <button onClick={() => doLabel("FAIL")} className="flex-1 py-4 rounded-xl font-black transition-all hover:scale-[1.02] active:scale-95 bg-red-600 text-white shadow-lg shadow-red-900/20">FAIL</button>
              <button onClick={() => doLabel("SKIP")} className="flex-1 py-4 rounded-xl font-black transition-all hover:scale-[1.02] active:scale-95 bg-slate-700 text-white border border-slate-600">SKIP</button>
            </div>
            {currentLabel && <div className="text-center font-bold animate-bounce" style={{ color: NVIS.amber }}>RECORDED: {currentLabel}</div>}
          </div>

          <AgentChatWell 
            excludedEntities={excludedEntities} 
            setExcludedEntities={setExcludedEntities} 
          />
        </div>
      </div>

      {/* Bottom sticky bar */}
      <div className="h-12 border-t border-slate-700 flex items-center justify-between px-5 shrink-0" style={{ background: "#1e293b" }}>
        <div className="flex gap-2 items-center">
          <button
            onClick={() => navigate(-1)}
            disabled={idx === 0}
            className="text-slate-200 border-none px-3 py-1.5 rounded-md cursor-pointer text-xs disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "#374151" }}
          >
            Prev
          </button>
          <button
            onClick={() => navigate(1)}
            disabled={idx === filteredItems.length - 1}
            className="text-slate-200 border-none px-3 py-1.5 rounded-md cursor-pointer text-xs disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: "#374151" }}
          >
            Next
          </button>
          <span className="text-slate-500 text-xs ml-2">
            <span className="font-bold" style={{ color: NVIS.amber }}>{idx + 1}</span>/{filteredItems.length}
          </span>
        </div>

        <div className="text-slate-500 text-xs flex gap-3 items-center">
          <span><span className="font-bold" style={{ color: NVIS.green }}>{labeledCount}</span>/{items.length} labeled</span>
          <span className="text-slate-700">|</span>
          <kbd className="text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono" style={{ background: "#374151" }}>P</kbd>
          <kbd className="text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono" style={{ background: "#374151" }}>F</kbd>
          <kbd className="text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono" style={{ background: "#374151" }}>S</kbd>
          <kbd className="text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono" style={{ background: "#374151" }}>A</kbd>
          <kbd className="text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono" style={{ background: "#374151" }}>&larr;&rarr;</kbd>
        </div>

        <button
          onClick={exportResults}
          className="text-white border-none px-4 py-1.5 rounded-md cursor-pointer text-xs font-semibold"
          style={{ backgroundColor: "#3b82f6" }}
        >
          Export JSONL
        </button>
      </div>
    </div>
  );
}
