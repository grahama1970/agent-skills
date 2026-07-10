import {
	PROOF_CARD_NODE_ORDER,
	type BattleNormalizedProofCardFixtureV1,
	type ProofCardMethod,
	type ProofCardNodeId,
	type ProofCardSource,
} from "./battle-proof-card-types";

export type ProofCardNodeView = {
	id: ProofCardNodeId;
	label: string;
	status: string;
	verdict: string;
	treatment: "pass" | "blocked" | "fail" | "missing" | "running";
	panelId: string;
};

export type MethodGroupId = "selected" | "inherited" | "research" | "deferred";

export type MethodGroupView = {
	id: MethodGroupId;
	label: string;
	methods: ProofCardMethod[];
};

export type ProofCardViewModel = {
	fixture: BattleNormalizedProofCardFixtureV1;
	headline: string;
	subhead: string;
	statusLabel: string;
	badges: Array<{ id: string; label: string; value: string; tone: "green" | "amber" | "red" | "gray" | "blue" | "purple" }>;
	nodes: ProofCardNodeView[];
	research: {
		query: string;
		method: string;
		externalToolCalled: boolean;
		providerLive: boolean;
		reviewRequired: boolean;
		sourceCount: number;
		sources: ProofCardSource[];
		designInputNotice: string;
	};
	methodGroups: MethodGroupView[];
	genome: {
		createdBy: string;
		agentic: boolean;
		providerLive: boolean;
		selected: ProofCardMethod[];
		deferred: ProofCardMethod[];
		strategy: Array<{ key: string; value: string }>;
		notCodeLabel: string;
	};
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
	};
	receipts: BattleNormalizedProofCardFixtureV1["receipt_refs"];
};

const NODE_LABELS: Record<ProofCardNodeId, string> = {
	"lineage-summarizer": "Lineage Summarizer",
	"research-scout": "Research Scout",
	"method-combiner": "Method Combiner",
	"exploit-code-author": "Exploit Code Author",
};

const NODE_PANELS: Record<ProofCardNodeId, string> = {
	"lineage-summarizer": "battle:proof-card:receipts",
	"research-scout": "battle:proof-card:research",
	"method-combiner": "battle:proof-card:genome",
	"exploit-code-author": "battle:proof-card:claim-boundary",
};

export function humanizeProofClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

export function nodeTreatment(status: string): ProofCardNodeView["treatment"] {
	const upper = status.toUpperCase();
	if (upper === "PASS") return "pass";
	if (upper === "BLOCKED") return "blocked";
	if (upper === "FAIL") return "fail";
	if (upper === "RUNNING" || upper === "PENDING") return "running";
	return "missing";
}

export function buildProofCardViewModel(fixture: BattleNormalizedProofCardFixtureV1): ProofCardViewModel {
	const methods = fixture.artifacts.child_candidate_methods.methods ?? [];
	const methodById = new Map(methods.map((method) => [method.method_id, method]));
	const genome = fixture.artifacts.child_exploit_genome;
	const selectedIds = new Set(genome.selected_method_ids ?? []);
	const rejectedIds = new Set(genome.rejected_method_ids ?? []);

	const selected = (genome.selected_method_ids ?? [])
		.map((id) => methodById.get(id))
		.filter(Boolean) as ProofCardMethod[];
	const deferred = (genome.rejected_method_ids ?? [])
		.map((id) => methodById.get(id) ?? { method_id: id, name: id })
		.filter(Boolean) as ProofCardMethod[];

	const inherited = methods.filter((method) => method.inherited && !rejectedIds.has(method.method_id));
	const researchBacked = methods.filter((method) => !method.inherited && !rejectedIds.has(method.method_id) && !selectedIds.has(method.method_id));

	const research = fixture.artifacts.child_research_receipts;
	const sourceReceipts = research.source_receipts ?? [];
	const reviewRequired = sourceReceipts.some((receipt) => receipt.review_required === true);
	const scoreboard = fixture.scoreboard ?? {};

	return {
		fixture,
		headline: fixture.copy.headline,
		subhead: fixture.copy.subhead,
		statusLabel: fixture.copy.status_label,
		badges: [
			{ id: "mocked", label: "MOCKED", value: fixture.mocked ? "YES" : "NO", tone: fixture.mocked ? "red" : "green" },
			{
				id: "fixture-fallback",
				label: "FIXTURE FALLBACK",
				value: fixture.fixture_fallback_used ? "YES" : "NO",
				tone: fixture.fixture_fallback_used ? "red" : "green",
			},
			{
				id: "live-tau",
				label: "LIVE TAU DAG",
				value: fixture.live === "tau_dag_runtime" || fixture.tau_execution === "attempted" ? "YES" : "NO",
				tone: "purple",
			},
			{
				id: "external-tool",
				label: "EXTERNAL RESEARCH TOOL",
				value: research.query?.external_tool_called ? "YES" : "NO",
				tone: research.query?.external_tool_called ? "amber" : "gray",
			},
			{
				id: "provider-live",
				label: "PROVIDER LIVE",
				value: research.provider_live || genome.provider_live ? "YES" : "NO",
				tone: research.provider_live || genome.provider_live ? "amber" : "gray",
			},
			{
				id: "exploit-code-generated",
				label: "EXPLOIT CODE GENERATED",
				value: "NO",
				tone: "gray",
			},
			{
				id: "child-specimen-run",
				label: "CHILD SPECIMEN RUN",
				value: scoreboard.child_specimen_run ? "YES" : "NO",
				tone: scoreboard.child_specimen_run ? "amber" : "gray",
			},
			{
				id: "judge-verified",
				label: "JUDGE VERIFIED EXPLOITS",
				value: String(scoreboard.judge_verified_exploits ?? 0),
				tone: "blue",
			},
		],
		nodes: PROOF_CARD_NODE_ORDER.map((id) => {
			const status = fixture.node_status[id] ?? "MISSING";
			return {
				id,
				label: NODE_LABELS[id],
				status,
				verdict: fixture.node_verdict?.[id] ?? status,
				treatment: nodeTreatment(status),
				panelId: NODE_PANELS[id],
			};
		}),
		research: {
			query: research.query?.value ?? "not emitted",
			method: research.query?.method ?? "not emitted",
			externalToolCalled: research.query?.external_tool_called === true,
			providerLive: research.provider_live === true,
			reviewRequired,
			sourceCount: research.sources?.length ?? 0,
			sources: research.sources ?? [],
			designInputNotice:
				"These sources are design input. They do not prove exploitability or applicability to the target.",
		},
		methodGroups: [
			{ id: "selected", label: "Selected candidates", methods: selected },
			{ id: "inherited", label: "Inherited candidates", methods: inherited },
			{ id: "research", label: "New research-backed candidates", methods: researchBacked },
			{ id: "deferred", label: "Negative filters / rejected candidates", methods: deferred },
		],
		genome: {
			createdBy: genome.created_by ?? "not emitted",
			agentic: genome.agentic === true,
			providerLive: genome.provider_live === true,
			selected,
			deferred,
			strategy: Object.entries(genome.strategy ?? {}).map(([key, value]) => ({ key, value })),
			notCodeLabel: "GENOME CANDIDATE — NOT EXPLOIT CODE",
		},
		claimBoundary: {
			mayClaim: fixture.claim_boundary.may_claim.map(humanizeProofClaimKey),
			mustNotClaim: fixture.claim_boundary.must_not_claim.map(humanizeProofClaimKey),
		},
		receipts: fixture.receipt_refs,
	};
}
