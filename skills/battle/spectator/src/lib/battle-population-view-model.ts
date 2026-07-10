import type { BattleNormalizedPopulationFixtureV1, GenerationAxisEntry, LineageEdge, SpecimenCard } from "./battle-population-types";

export type PopulationSpecimenView = {
	id: string;
	generation: number;
	parentId: string | null;
	compileStatus: string;
	runtimeStatus: string;
	judgeStatus: string;
	judgeVerified: number;
	methods: Array<{ id: string; name: string }>;
	inheritedMethods: string[];
	providerAuthoredBy: string;
	providerLive: boolean;
	targetStatus: string;
	targetEntrypoint: string;
	fitnessTier: number;
	fitnessLabel: string;
	fitnessFlags: { compileOk: boolean; runtimeOk: boolean; targetUnproven: boolean; judgeConfirmed: boolean };
	noveltyHash: string;
	noveltyMethodCount: number;
	selectionStatus: string;
	selectionReason: string;
	promoted: boolean;
	selectedBest: boolean;
};

export type PopulationViewModel = {
	fixture: BattleNormalizedPopulationFixtureV1;
	headline: string;
	subhead: string;
	statusLabel: string;
	boundaryNotice: string;
	badges: Array<{ id: string; label: string; value: string; tone: "green" | "amber" | "red" | "gray" | "blue" | "purple" }>;
	banners: Array<{ id: string; label: string; tone: "purple" | "gray" | "amber" | "blue" | "red" | "green" }>;
	campaign: {
		id: string;
		specimenCount: number;
		generationCount: number;
		bestSpecimenId: string;
		verdict: string;
		fullEngineProven: boolean;
		limitations: string[];
	};
	generations: GenerationAxisEntry[];
	specimens: PopulationSpecimenView[];
	edges: Array<{
		id: string;
		fromId: string;
		toId: string;
		type: string;
		spawnCause: string;
		inheritedMethods: string[];
		promoted: boolean;
		abandoned: boolean;
	}>;
	lineageSummary: { parentChild: number; recombination: number; promoted: number; abandoned: number };
	selectedGeneration: number | null;
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
		notFullEngine: boolean;
		targetNotExploit: boolean;
		runnableNotExploit: boolean;
	};
	receipts: BattleNormalizedPopulationFixtureV1["receipt_refs"];
};

export function humanizeClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

function toSpecimenView(card: SpecimenCard, bestId: string): PopulationSpecimenView {
	return {
		id: card.specimen_id,
		generation: card.generation,
		parentId: card.parent_specimen_id ?? null,
		compileStatus: card.compile_status,
		runtimeStatus: card.runtime_status,
		judgeStatus: card.judge_status,
		judgeVerified: card.judge_verified_exploits,
		methods: (card.selected_methods?.length
			? card.selected_methods.map((method) => ({ id: method.method_id, name: method.name }))
			: card.selected_method_ids.map((id) => ({ id, name: id }))),
		inheritedMethods: card.inherited_methods ?? [],
		providerAuthoredBy: card.provider_authorship.authored_by,
		providerLive: card.provider_authorship.provider_live,
		targetStatus: card.target_contact.status,
		targetEntrypoint: card.target_contact.entrypoint ?? "not observed",
		fitnessTier: card.fitness.tier,
		fitnessLabel: card.fitness.tier_label,
		fitnessFlags: {
			compileOk: card.fitness.compile_ok,
			runtimeOk: card.fitness.runtime_ok,
			targetUnproven: card.fitness.target_contact_unproven,
			judgeConfirmed: card.fitness.judge_confirmed_exploit,
		},
		noveltyHash: card.novelty.method_combo_hash,
		noveltyMethodCount: card.novelty.method_count,
		selectionStatus: card.selection.status,
		selectionReason: card.selection.reason,
		promoted: Boolean(card.selection.promoted),
		selectedBest: card.specimen_id === bestId,
	};
}

function toEdgeView(edge: LineageEdge) {
	return {
		id: edge.edge_id,
		fromId: edge.from_specimen_id,
		toId: edge.to_specimen_id,
		type: edge.edge_type,
		spawnCause: edge.spawn_cause ?? "not emitted",
		inheritedMethods: edge.inherited_methods ?? [],
		promoted: Boolean(edge.promoted),
		abandoned: Boolean(edge.abandoned),
	};
}

export function buildPopulationViewModel(
	fixture: BattleNormalizedPopulationFixtureV1,
	selectedGeneration: number | null = null,
): PopulationViewModel {
	const bestId = String(fixture.campaign.best_specimen_id ?? "");
	const specimens = fixture.specimen_cards.map((card) => toSpecimenView(card, bestId));
	const filtered =
		selectedGeneration === null ? specimens : specimens.filter((specimen) => specimen.generation === selectedGeneration);

	return {
		fixture,
		headline: fixture.copy.headline,
		subhead: fixture.copy.subhead,
		statusLabel: fixture.copy.status_label,
		boundaryNotice:
			fixture.copy.boundary_notice ??
			"Bounded population fixture only. Not a full genetic engine; exploit success requires Judge.",
		badges: [
			{ id: "mocked", label: "MOCKED", value: "NO", tone: "green" },
			{ id: "specimens", label: "SPECIMENS", value: String(fixture.campaign.specimen_count), tone: "purple" },
			{ id: "generations", label: "GENERATIONS", value: String(fixture.campaign.generation_count), tone: "blue" },
			{ id: "full-engine", label: "FULL ENGINE", value: "NO", tone: "gray" },
			{ id: "judge", label: "JUDGE", value: "NOT RUN", tone: "gray" },
			{ id: "exploit", label: "EXPLOIT SUCCESS", value: "NOT CLAIMED", tone: "amber" },
		],
		banners: [
			{ id: "population-fixture", label: "POPULATION FIXTURE", tone: "purple" },
			{ id: "not-full-engine", label: "NOT FULL GENETIC ENGINE", tone: "gray" },
			{ id: "judge-not-run", label: "JUDGE NOT RUN", tone: "gray" },
			{ id: "exploit-not-claimed", label: "EXPLOIT SUCCESS NOT CLAIMED", tone: "amber" },
		],
		campaign: {
			id: fixture.campaign.campaign_id,
			specimenCount: fixture.campaign.specimen_count,
			generationCount: fixture.campaign.generation_count,
			bestSpecimenId: bestId || "not emitted",
			verdict: String(fixture.campaign.verdict ?? "not emitted"),
			fullEngineProven: false,
			limitations: fixture.campaign.source_limitations ?? [],
		},
		generations: fixture.generation_axis,
		specimens: filtered,
		edges: fixture.lineage_edges.map(toEdgeView),
		lineageSummary: {
			parentChild: fixture.lineage_summary?.parent_child_edges ?? fixture.lineage_edges.filter((e) => e.edge_type === "parent_child").length,
			recombination: fixture.lineage_summary?.recombination_edges ?? 0,
			promoted: fixture.lineage_summary?.promoted_count ?? 0,
			abandoned: fixture.lineage_summary?.abandoned_count ?? fixture.lineage_edges.filter((e) => e.abandoned).length,
		},
		selectedGeneration,
		claimBoundary: {
			mayClaim: fixture.claim_boundary.may_claim.map(humanizeClaimKey),
			mustNotClaim: fixture.claim_boundary.must_not_claim.map(humanizeClaimKey),
			notFullEngine: fixture.claim_boundary.population_fixture_is_not_full_engine === true,
			targetNotExploit: fixture.claim_boundary.target_contact_is_not_exploit_success === true,
			runnableNotExploit: fixture.claim_boundary.runnable_is_not_exploit_success === true,
		},
		receipts: fixture.receipt_refs,
	};
}
