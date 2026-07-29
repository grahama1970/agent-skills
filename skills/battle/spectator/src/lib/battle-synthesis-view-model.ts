import { SYNTHESIS_NODE_ORDER, type BattleNormalizedSynthesisFixtureV1 } from "./battle-synthesis-types";

export type SynthesisNodeView = {
	id: string;
	label: string;
	status: string;
	verdict: string;
	treatment: "pass" | "blocked" | "fail" | "missing";
};

export type SynthesisViewModel = {
	fixture: BattleNormalizedSynthesisFixtureV1;
	headline: string;
	subhead: string;
	statusLabel: string;
	boundaryNotice: string;
	badges: Array<{ id: string; label: string; value: string; tone: "green" | "amber" | "red" | "gray" | "blue" | "purple" }>;
	nodes: SynthesisNodeView[];
	provider: {
		observedProvider: string;
		observedModel: string;
		requestedProvider: string;
		requestedModel: string;
		authoredBy: string;
		runIdPresent: boolean;
		sessionIdPresent: boolean;
		requestIdPresent: boolean;
		responseIdPresent: boolean;
		callCount: number;
		runRefSha256: string;
		codeSha256: string;
		codeBytes: number;
		providerLive: boolean;
		goalHashBound: boolean;
		outputHashBound: boolean;
		claimBoundaryPassed: boolean;
	};
	banners: Array<{ id: string; label: string; tone: "purple" | "gray" | "amber" | "blue" }>;
	specimen: {
		id: string;
		language: string;
		label: string;
		createdBy: string;
		lineCount: number;
		previewLines: string[];
		truncated: boolean;
		selectedMethods: string[];
	};
	executionBoundary: Array<{ id: string; label: string; value: string }>;
	claimBoundary: { mayClaim: string[]; mustNotClaim: string[] };
	genome: { createdBy: string; selected: string[]; deferred: string[]; rationale: string };
	receipts: BattleNormalizedSynthesisFixtureV1["receipt_refs"];
	stageScope: BattleNormalizedSynthesisFixtureV1["stage_scope"];
};

const NODE_LABELS: Record<string, string> = {
	"lineage-summarizer": "Lineage Summarizer",
	"research-scout": "Research Scout",
	"method-combiner": "Method Combiner",
	"exploit-code-author": "Exploit Code Author",
};

export function humanizeClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

export function buildSynthesisViewModel(fixture: BattleNormalizedSynthesisFixtureV1): SynthesisViewModel {
	const preview = fixture.specimen.code_preview;
	return {
		fixture,
		headline: fixture.copy.headline,
		subhead: fixture.copy.subhead,
		statusLabel: fixture.copy.status_label,
		boundaryNotice: fixture.copy.boundary_notice ?? "Provider-authored specimen only — not compiled, executed, or Judge verified.",
		badges: [
			{ id: "mocked", label: "MOCKED", value: "NO", tone: "green" },
			{ id: "fixture-fallback", label: "FIXTURE FALLBACK", value: "NO", tone: "green" },
			{ id: "provider-live", label: "PROVIDER LIVE", value: "YES", tone: "purple" },
			{ id: "compiled", label: "COMPILED", value: "NO", tone: "gray" },
			{ id: "executed", label: "EXECUTED", value: "NO", tone: "gray" },
			{ id: "judge-verified", label: "JUDGE VERIFIED", value: String(fixture.execution_boundary.judge_verified_exploits), tone: "blue" },
		],
		nodes: SYNTHESIS_NODE_ORDER.map((id) => {
			const status = fixture.node_status[id] ?? "MISSING";
			return {
				id,
				label: NODE_LABELS[id] ?? id,
				status,
				verdict: fixture.node_verdict?.[id] ?? status,
				treatment: status === "PASS" ? "pass" : status === "BLOCKED" ? "blocked" : status === "FAIL" ? "fail" : "missing",
			};
		}),
		provider: {
			observedProvider: fixture.provider_authorship.observed_provider,
			observedModel: fixture.provider_authorship.observed_model,
			requestedProvider: String(fixture.provider_authorship.requested_provider ?? "not emitted"),
			requestedModel: String(fixture.provider_authorship.requested_model ?? "not emitted"),
			authoredBy: fixture.provider_authorship.authored_by,
			runIdPresent: fixture.provider_authorship.provider_run_id_present,
			sessionIdPresent: fixture.provider_authorship.provider_session_id_present,
			requestIdPresent: fixture.provider_authorship.provider_request_id_present,
			responseIdPresent: fixture.provider_authorship.provider_response_id_present,
			callCount: fixture.provider_authorship.provider_call_count,
			runRefSha256: String(fixture.provider_authorship.provider_run_ref_sha256 ?? "not emitted"),
			codeSha256: fixture.provider_authorship.code_sha256,
			codeBytes: fixture.provider_authorship.code_bytes,
			providerLive: fixture.provider_authorship.provider_live,
			goalHashBound: Boolean(fixture.provider_authorship.goal_hash_bound),
			outputHashBound: Boolean(fixture.provider_authorship.output_hash_bound),
			claimBoundaryPassed: Boolean(fixture.provider_authorship.claim_boundary_passed),
		},
		banners: [
			{ id: "provider-authored", label: "PROVIDER-AUTHORED SPECIMEN", tone: "purple" },
			{ id: "not-compiled", label: "NOT COMPILED", tone: "gray" },
			{ id: "not-executed", label: "NOT EXECUTED", tone: "gray" },
			{ id: "not-judge-verified", label: "NOT JUDGE VERIFIED", tone: "blue" },
		],
		specimen: {
			id: fixture.specimen.specimen_id,
			language: fixture.specimen.language,
			label: fixture.specimen.code_artifact_label,
			createdBy: String(fixture.specimen.created_by ?? "not emitted"),
			lineCount: preview.line_count_total,
			previewLines: preview.lines,
			truncated: Boolean(preview.truncated),
			selectedMethods: fixture.specimen.selected_method_ids ?? [],
		},
		executionBoundary: [
			{ id: "compile_status", label: "compile", value: fixture.execution_boundary.compile_status },
			{ id: "runtime_status", label: "runtime", value: fixture.execution_boundary.runtime_status },
			{ id: "target_contact", label: "target contact", value: fixture.execution_boundary.target_contact },
			{ id: "judge_status", label: "judge", value: fixture.execution_boundary.judge_status },
			{ id: "packet_behavior", label: "packet behavior", value: fixture.execution_boundary.packet_behavior },
			{ id: "memory_promotion", label: "memory promotion", value: fixture.execution_boundary.memory_promotion },
		],
		claimBoundary: {
			mayClaim: fixture.claim_boundary.may_claim.map(humanizeClaimKey),
			mustNotClaim: fixture.claim_boundary.must_not_claim.map(humanizeClaimKey),
		},
		genome: {
			createdBy: fixture.genome.created_by ?? "not emitted",
			selected: fixture.genome.selected_method_ids ?? [],
			deferred: fixture.genome.deferred_method_ids ?? [],
			rationale: fixture.genome.rationale_summary ?? "not emitted",
		},
		receipts: fixture.receipt_refs,
		stageScope: fixture.stage_scope,
	};
}
