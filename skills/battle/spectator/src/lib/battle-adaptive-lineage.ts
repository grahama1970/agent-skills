import type {
	AdaptiveLineageChangedDimension,
	AdaptiveLineageDataSource,
	AdaptiveLineageJudgeOutcome,
	AdaptiveLineageNode,
	BattleAdaptiveLineageMechanicsFixtureV1,
} from "./battle-types";

/**
 * View model for the adaptive-lineage MECHANICS comparison.
 *
 * Consumes a normalized battle.adaptive_lineage_mechanics_fixture.v1 and produces
 * the G0 -> {G1-A, G1-B} -> G2 tree, each edge labeled with its mutation operator,
 * changed AST dimensions, and novelty distance; the selected vs runner-up G1 with
 * the deciding criterion; and the overall qualification status.
 *
 * HONESTY: `badge.provesLive` is true ONLY when data_source === "live". Recorded
 * data must not be presented as a proven-live adaptive canary.
 */

export type AdaptiveLineageDataSourceBadge = {
	dataSource: AdaptiveLineageDataSource;
	label: "RECORDED · MECHANICS" | "LIVE";
	tone: "amber" | "green";
	/** True only for live receipts — never for recorded fixtures. */
	provesLive: boolean;
	caption: string;
};

export type AdaptiveLineageNodeView = {
	id: string;
	exploitShortName: string | null;
	role: string;
	generation: number;
	parentId: string | null;
	mutationOperator: string | null;
	techniqueDelta: string | null;
	noveltyDistance: number | null;
	deltaStatus: string | null;
	fitnessStatus: string | null;
	changedDimensions: AdaptiveLineageChangedDimension[];
	changedDimensionNames: string[];
	judgeOutcome: AdaptiveLineageJudgeOutcome | null;
	selected: boolean;
	runnerUp: boolean;
};

export type AdaptiveLineageEdgeView = {
	id: string;
	from: string;
	to: string;
	mutationOperator: string | null;
	noveltyDistance: number | null;
	changedDimensionNames: string[];
	label: string;
};

export type AdaptiveLineageViewModel = {
	schema: "battle.adaptive_lineage_comparison.v1";
	dataSource: AdaptiveLineageDataSource;
	badge: AdaptiveLineageDataSourceBadge;
	qualification: {
		status: string;
		stopCondition: string | null;
		passed: boolean;
		reasons: string[];
	};
	selection: {
		selectedId: string | null;
		runnerUpId: string | null;
		decidingCriterion: string | null;
	};
	seed: AdaptiveLineageNodeView | null;
	candidates: AdaptiveLineageNodeView[];
	selected: AdaptiveLineageNodeView | null;
	runnerUp: AdaptiveLineageNodeView | null;
	descendant: AdaptiveLineageNodeView | null;
	edges: AdaptiveLineageEdgeView[];
};

function toNodeView(node: AdaptiveLineageNode): AdaptiveLineageNodeView {
	const changedDimensions = node.changed_dimensions ?? [];
	return {
		id: node.id,
		exploitShortName: node.exploit_short_name ?? null,
		role: node.role,
		generation: node.generation,
		parentId: node.parentId,
		mutationOperator: node.mutation_operator,
		techniqueDelta: node.technique_delta,
		noveltyDistance: node.novelty_distance,
		deltaStatus: node.delta_status,
		fitnessStatus: node.fitness_status,
		changedDimensions,
		changedDimensionNames: changedDimensions.map((d) => d.dimension),
		judgeOutcome: node.judge_outcome,
		selected: node.selected,
		runnerUp: node.runner_up,
	};
}

function buildBadge(dataSource: AdaptiveLineageDataSource): AdaptiveLineageDataSourceBadge {
	if (dataSource === "live") {
		return {
			dataSource,
			label: "LIVE",
			tone: "green",
			provesLive: true,
			caption: "Live Tau + Judge receipts — adaptive lineage proven live.",
		};
	}
	return {
		dataSource,
		label: "RECORDED · MECHANICS",
		tone: "amber",
		provesLive: false,
		caption: "Recorded specimens replayed through the reducer. Proves the mechanics, NOT a live adaptive canary.",
	};
}

export function buildAdaptiveLineageViewModel(
	fixture: BattleAdaptiveLineageMechanicsFixtureV1,
): AdaptiveLineageViewModel | null {
	if (!fixture || fixture.schema !== "battle.adaptive_lineage_mechanics_fixture.v1") {
		return null;
	}
	const nodes = (fixture.nodes ?? []).map(toNodeView);
	const byId = new Map(nodes.map((n) => [n.id, n]));

	const seed = nodes.find((n) => n.role === "seed" || n.parentId === null) ?? null;
	const candidates = nodes.filter((n) => n.role === "candidate");
	const descendant = nodes.find((n) => n.role === "descendant") ?? null;

	const selectedId = fixture.selection?.selected_id ?? null;
	const runnerUpId = fixture.selection?.runner_up_id ?? null;
	const selected = (selectedId && byId.get(selectedId)) || candidates.find((n) => n.selected) || null;
	const runnerUp = (runnerUpId && byId.get(runnerUpId)) || candidates.find((n) => n.runnerUp) || null;

	const edges: AdaptiveLineageEdgeView[] = (fixture.edges ?? []).map((edge) => {
		const changedDimensionNames = (edge.changed_dimensions ?? []).map((d) => d.dimension);
		const parts: string[] = [];
		if (edge.mutation_operator) parts.push(edge.mutation_operator);
		if (typeof edge.novelty_distance === "number") parts.push(`novelty ${edge.novelty_distance}`);
		if (changedDimensionNames.length) parts.push(changedDimensionNames.join(", "));
		return {
			id: `${edge.from}->${edge.to}`,
			from: edge.from,
			to: edge.to,
			mutationOperator: edge.mutation_operator,
			noveltyDistance: edge.novelty_distance,
			changedDimensionNames,
			label: parts.join(" · "),
		};
	});

	const status = fixture.qualification?.status ?? "FAIL";

	return {
		schema: "battle.adaptive_lineage_comparison.v1",
		dataSource: fixture.data_source,
		badge: buildBadge(fixture.data_source),
		qualification: {
			status,
			stopCondition: fixture.qualification?.stop_condition ?? null,
			passed: status === "PASS",
			reasons: fixture.qualification?.reasons ?? [],
		},
		selection: {
			selectedId,
			runnerUpId,
			decidingCriterion: fixture.selection?.deciding_criterion ?? null,
		},
		seed,
		candidates,
		selected,
		runnerUp,
		descendant,
		edges,
	};
}
