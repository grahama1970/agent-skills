import type { BattleNormalizedAdaptiveLineageFixtureV1, AdaptiveLineageEvent, AdaptiveLineageLane } from "./battle-adaptive-lineage-types";
import type {
	AdaptiveLineageNode,
	BattleAdaptiveLineageMechanicsFixtureV1,
	BattleEvent,
	BattleMemoryPromotion,
	BattleNormalizedUxFixture,
	BattleReceiptRef,
	Lane,
	LaneActivitySegment,
	LaneEvent,
} from "./battle-types";

function pct(seconds: number, duration: number): number {
	return Math.max(0, Math.min(100, (seconds / Math.max(1, duration)) * 100));
}

function receiptId(event: AdaptiveLineageEvent): string {
	return event.receipt_ref.receipt_id ?? `${event.receipt_ref.schema}:${event.receipt_ref.sha256.slice(0, 12)}`;
}

function laneEventKind(event: AdaptiveLineageEvent): LaneEvent["kind"] {
	if (event.event_type === "child_research_materialized" || event.event_type === "memory_use_acknowledged") return "handoff";
	if (event.event_type === "genome_mutated") return "genome_selected";
	// Pair-level Judge verdict. BLUE_SUCCESS = Blue intervention blocked Red (claim boundary
	// forbids rendering Red exploit success unless the verdict is RED_SUCCESS), so a Blue-blast
	// marker is the strongest honest cue; any non-BLUE_SUCCESS verdict stays a neutral marker.
	if (event.event_type === "judge_verdict") {
		return String((event.payload as Record<string, unknown>).verdict) === "BLUE_SUCCESS" ? "blue_blast" : "useful";
	}
	return "useful";
}

function laneEventLabel(event: AdaptiveLineageEvent): string {
	const payload = event.payload as Record<string, unknown>;
	if (event.event_type === "judge_verdict") {
		return payload.verdict != null ? `JUDGE VERDICT · ${String(payload.verdict)}` : "JUDGE VERDICT";
	}
	if (event.event_type === "selection_decision") {
		return payload.red_selected_generation != null && payload.blue_selected_generation != null
			? `SELECTION · RED G${String(payload.red_selected_generation)} / BLUE G${String(payload.blue_selected_generation)}`
			: "SELECTION DECIDED";
	}
	if (event.event_type === "memory_evaluation") {
		const decisions = Array.isArray(payload.decisions) ? payload.decisions.map(String) : [];
		return decisions.length ? `MEMORY EVAL · ${decisions.join(" / ")}` : "MEMORY EVALUATION";
	}
	const labels: Record<string, string> = {
		parent_observation_materialized: "OBSERVATION RECEIPT",
		generation_observation_materialized: "GENERATION OBSERVATION",
		fitness_materialized: "FITNESS MEASURED",
		spawn_requested: "SPAWN REQUESTED",
		spawn_authorized: "SPAWN AUTHORIZED · PENDING",
		knowledge_packet_materialized: "KNOWLEDGE TRANSFER",
		child_research_materialized: "CHILD RESEARCH ACTIVE",
		child_knowledge_acknowledged: "INHERITANCE VERIFIED",
		genome_mutated: "MUTATION EVIDENCE VERIFIED",
		memory_promoted: "MEMORY PROMOTED · PENDING",
		memory_written: "MEMORY WRITTEN",
		memory_recalled: "MEMORY RECALLED",
		memory_use_acknowledged: "MEMORY USE ACKNOWLEDGED",
		memory_generation_evaluated: "MEMORY GENERATION EVALUATED",
	};
	return labels[event.event_type] ?? event.event_type.replace(/_/g, " ").toUpperCase();
}

function toLaneEvent(event: AdaptiveLineageEvent, duration: number): LaneEvent {
	return {
		id: event.event_id,
		kind: laneEventKind(event),
		x: pct(event.elapsed_seconds, duration),
		label: laneEventLabel(event),
		timeLabel: "receipt commit",
		proven: true,
		proofMode: "receipt_backed_fixture",
		receiptId: receiptId(event),
		order_index: event.seq,
		elapsed_seconds: event.elapsed_seconds,
		at_seconds: event.elapsed_seconds,
		label_band: event.seq % 2 === 0 ? "upper" : "lower",
		marker_priority: event.event_type === "spawn_authorized" || event.event_type === "child_research_materialized" ? 90 : 60,
		collision_group: `adaptive:${event.seq}`,
	};
}

function activitySegments(source: AdaptiveLineageLane, events: AdaptiveLineageEvent[], duration: number, isMemory: boolean): LaneActivitySegment[] {
	if (source.role === "parent") return [];
	const activation = events.find((event) => event.event_type === (isMemory ? "memory_use_acknowledged" : "child_research_materialized") && event.lane_id === source.lane_id);
	const judge = events.find((event) => event.event_type === (isMemory ? "memory_generation_evaluated" : "judge_verdict") && event.generation === source.generation);
	const mutation = events.find((event) => event.event_type === "genome_mutated" && event.lane_id === source.lane_id);
	const activeAt = activation?.elapsed_seconds ?? source.active_from_elapsed_seconds;
	const judgeAt = judge?.elapsed_seconds ?? duration;
	const segments: LaneActivitySegment[] = [
		{
			id: `${source.lane_id}:authorized-pending`,
			phase: "authorized_pending",
			label: isMemory ? "MEMORY PROMOTED · PENDING" : "AUTHORIZED · PENDING",
			start_x: pct(source.visible_from_elapsed_seconds, duration),
			end_x: pct(activeAt, duration),
			start_elapsed_seconds: source.visible_from_elapsed_seconds,
			end_elapsed_seconds: activeAt,
			proof_mode: "receipt_backed_fixture",
		},
		{
			id: `${source.lane_id}:materialize`,
			phase: "materialize",
			label: isMemory ? "MEMORY USE ACKNOWLEDGED" : "CHILD RESEARCH MATERIALIZED",
			start_x: pct(activeAt, duration),
			end_x: pct(Math.min(activeAt + 1.5, judgeAt), duration),
			start_elapsed_seconds: activeAt,
			end_elapsed_seconds: Math.min(activeAt + 1.5, judgeAt),
			proof_mode: "receipt_backed_fixture",
		},
		{
			id: `${source.lane_id}:research`,
			phase: "research",
			label: isMemory ? "MEMORY-INFORMED GENERATION" : "CHILD RESEARCH",
			start_x: pct(Math.min(activeAt + 1.5, judgeAt), duration),
			end_x: pct(judgeAt, duration),
			start_elapsed_seconds: Math.min(activeAt + 1.5, judgeAt),
			end_elapsed_seconds: judgeAt,
			proof_mode: "receipt_backed_fixture",
		},
	];
	if (mutation) {
		segments.push({
			id: `${source.lane_id}:mutation-evidence`,
			phase: "mutation_evidence",
			label: "MUTATION EVIDENCE VERIFIED",
			start_x: pct(mutation.elapsed_seconds, duration),
			end_x: pct(Math.min(duration, mutation.elapsed_seconds + 0.75), duration),
			start_elapsed_seconds: mutation.elapsed_seconds,
			end_elapsed_seconds: Math.min(duration, mutation.elapsed_seconds + 0.75),
			proof_mode: "receipt_backed_fixture",
		});
	}
	return segments;
}

function memoryPromotionForLane(
	source: AdaptiveLineageLane,
	fixture: BattleNormalizedAdaptiveLineageFixtureV1,
): BattleMemoryPromotion | undefined {
	if (fixture.live_source !== "adaptive_memory_v14") return undefined;
	const childLaneId = source.role === "child"
		? source.lane_id
		: fixture.lineage_edges.find((edge) => edge.parent_lane_id === source.lane_id)?.child_lane_id;
	if (!childLaneId) return undefined;
	const events = fixture.events.filter((event) => event.lane_id === childLaneId);
	const promoted = events.find((event) => event.event_type === "memory_promoted");
	if (!promoted) return undefined;
	if (source.role === "parent") {
		return {
			present: true,
			candidate_id: receiptId(promoted),
			durable_promoted: events.some((event) => event.event_type === "memory_written"),
			promotion_scope: String(promoted.payload.visibility_scope ?? `${source.team}_only`),
			reason: "selected evidence promoted to durable team memory",
		};
	}
	const latest = ["memory_use_acknowledged", "memory_recalled", "memory_written", "memory_promoted"]
		.map((eventType) => events.find((event) => event.event_type === eventType))
		.find(Boolean);
	const reasonByType: Record<string, string> = {
		memory_promoted: "promotion pending",
		memory_written: "written to durable team memory",
		memory_recalled: "exact recall completed",
		memory_use_acknowledged: "provider use acknowledged",
	};
	return {
		present: true,
		candidate_id: receiptId(promoted),
		durable_promoted: events.some((event) => event.event_type === "memory_written"),
		promotion_scope: String(promoted.payload.visibility_scope ?? `${source.team}_only`),
		reason: latest ? reasonByType[latest.event_type] : "promotion pending",
	};
}

function adaptiveLifecycleFields(
	source: AdaptiveLineageLane,
	fixture: BattleNormalizedAdaptiveLineageFixtureV1,
	events: AdaptiveLineageEvent[],
): Pick<Lane, "knowledge_packet" | "spawn_request" | "tau_branch_decision"> {
	const childLane = fixture.lanes.find((lane) => lane.parent_lane_id === source.lane_id);
	const lineageEvents = childLane
		? [...events, ...fixture.events.filter((event) => event.lane_id === childLane.lane_id)]
		: events;
	const observation = events.find(
		(event) =>
			event.event_type === "parent_observation_materialized" ||
			event.event_type === "generation_observation_materialized",
	);
	const fitness = events.find((event) => event.event_type === "fitness_materialized");
	const request = events.find((event) => event.event_type === "spawn_requested");
	const authorization = events.find((event) => event.event_type === "spawn_authorized");
	const packet = lineageEvents.find((event) => event.event_type === "knowledge_packet_materialized");
	const acknowledgement = lineageEvents.find((event) => event.event_type === "child_knowledge_acknowledged");
	const observedEvidenceRefs = [observation, fitness]
		.filter((event): event is AdaptiveLineageEvent => Boolean(event))
		.map(receiptId);

	return {
		knowledge_packet: packet
			? {
					present: true,
					status: packet.receipt_ref.status ?? "materialized",
					packet_id: packet.payload.packet_id == null ? null : String(packet.payload.packet_id),
					parent_packet_id: null,
					research_goals: [],
					parent_analysis: {},
					child_ack: {
						required: true,
						received: Boolean(acknowledgement),
						ack_source: acknowledgement ? receiptId(acknowledgement) : null,
					},
				}
			: undefined,
		spawn_request: request
			? {
					present: true,
					schema: request.receipt_ref.schema,
					request_id: receiptId(request),
					claim_authority: "parent-authored request (pre-policy)",
					requested_decision:
						request.payload.requested_action == null ? undefined : String(request.payload.requested_action),
					child_exploit_id: childLane?.lane_id ?? null,
					battle_allowed: false,
					policy_owner: "battle",
				}
			: undefined,
		tau_branch_decision: request
			? {
					present: true,
					schema: authorization?.receipt_ref.schema ?? request.receipt_ref.schema,
					decision_id: receiptId(authorization ?? request),
					decision_authority: authorization ? "battle" : "parent",
					battle_policy_authority: "battle",
					decision: "spawn_requested",
					observed_evidence_refs: observedEvidenceRefs,
					battle_policy_result: authorization ? "allowed" : "pending",
				}
			: undefined,
	};
}

function toLane(source: AdaptiveLineageLane, fixture: BattleNormalizedAdaptiveLineageFixtureV1): Lane {
	const duration = fixture.campaign.elapsed_seconds;
	// Lifecycle/segment derivation stays keyed on this lane's own `lane_id` events (parent-authored
	// observation/fitness/spawn semantics). Visible timeline markers additionally include every event
	// whose `affected_lane_ids` names this lane — this is what surfaces the pair-level Judge verdict,
	// the campaign selection_decision, and memory_evaluation (all carry `lane_id: null`) onto the lanes.
	const laneScopedEvents = fixture.events.filter((event) => event.lane_id === source.lane_id);
	const laneMarkerEvents = fixture.events.filter((event) => event.affected_lane_ids.includes(source.lane_id));
	const childLane = fixture.lanes.find((lane) => lane.parent_lane_id === source.lane_id);
	const isMemory = fixture.live_source === "adaptive_memory_v14";
	const lifecycle = adaptiveLifecycleFields(source, fixture, laneScopedEvents);
	return {
		id: source.lane_id,
		name: source.display_name,
		payloadId: `${source.team}-generation-${source.generation}`,
		generation: source.generation,
		team: source.team,
		parentId: source.parent_lane_id ?? undefined,
		parent_id: source.parent_lane_id ?? undefined,
		children: childLane ? [childLane.lane_id] : [],
		xStart: pct(source.visible_from_elapsed_seconds, duration),
		xEnd: 100,
		start_elapsed_seconds: source.visible_from_elapsed_seconds,
		visible_from_elapsed_seconds: source.visible_from_elapsed_seconds,
		first_active_segment_elapsed_seconds: source.active_from_elapsed_seconds,
		end_elapsed_seconds: source.end_elapsed_seconds,
		duration_elapsed_seconds: source.end_elapsed_seconds - source.visible_from_elapsed_seconds,
		runnerX: 100,
		runnerState: source.role === "child" ? "research" : "advance",
		runnerVerb: source.role === "child" ? "inherit" : "observe",
		lineColor: source.team === "red" ? (source.role === "parent" ? "red" : "green") : "purple",
		terminal: "none",
		events: laneMarkerEvents.map((event) => toLaneEvent(event, duration)),
		activitySegments: activitySegments(source, fixture.events, duration, isMemory),
		...lifecycle,
		memory_promotion: memoryPromotionForLane(source, fixture),
		lineageGroupId: `lineage:${source.team}`,
		collapsible: source.role === "parent",
		expandedByDefault: true,
		proofMode: "receipt_backed_fixture",
		actor_visual: {
			schema: "battle.actor_visual.v1",
			actor_id: source.lane_id,
			lane_id: source.lane_id,
			role: source.role,
			team: source.team,
			archetype: "adaptive-lineage-runner",
			variant_id: source.actor_visual.variant_id,
			style_family: fixture.sprite_theme.theme_id,
			initial_state: source.role === "child" ? "authorized_pending" : "idle",
			state_source: "battle.normalized_adaptive_lineage_fixture.v1",
		},
	};
}

function toBattleEvent(event: AdaptiveLineageEvent, fixture: BattleNormalizedAdaptiveLineageFixtureV1): BattleEvent {
	const team = event.team ?? "system";
	const memoryNonclaim = event.event_type === "memory_use_acknowledged" || event.event_type === "memory_generation_evaluated";
	return {
		id: event.event_id,
		ts: event.elapsed_seconds,
		battle_id: fixture.battle_id,
		team,
		actor_id: event.lane_id ?? `battle-${event.scope}`,
		actor_kind: team === "red" ? "exploit_agent" : team === "blue" ? "patch_agent" : "battle_orchestrator",
		elapsed_seconds: event.elapsed_seconds,
		at_seconds: event.elapsed_seconds,
		event_type: event.event_type as BattleEvent["event_type"],
		summary: laneEventLabel(event),
		proof_mode: "receipt_backed_fixture",
		payload: { ...event.payload, scope: event.scope, affected_lane_ids: event.affected_lane_ids, source_seq: event.seq },
		evidence: { stream: "receipt", receipt_id: receiptId(event), proof_mode: "receipt_backed_fixture" },
		ui: {
			importance: event.scope === "lane" ? "visible" : "hero",
			runner_state: event.event_type === "genome_mutated" ? "mutate" : "advance",
			runner_animation: event.event_type === "genome_mutated" ? "mutate_pulse" : "advance",
			sound_cue: "none",
			spectator_caption: `${laneEventLabel(event)} at receipt commit ${event.elapsed_seconds.toFixed(3)}s.`,
		},
		claim_boundary: {
			does_not_prove: event.event_type === "selection_decision" ? ["child improvement", "victory"] : memoryNonclaim ? ["memory improved either team", "victory"] : ["action occurrence time independent of receipt commit"],
			victory_requires_judge_receipt: true,
		},
	};
}

function edgeVisibilityReceipt(edge: BattleNormalizedAdaptiveLineageFixtureV1["lineage_edges"][number]) {
	return edge.edge_kind === "memory_continuation" ? edge.promoted_receipt_ref : edge.authorized_receipt_ref;
}

export function adaptiveLineageToRaceFixture(source: BattleNormalizedAdaptiveLineageFixtureV1): BattleNormalizedUxFixture {
	const duration = source.campaign.elapsed_seconds;
	const lanes = source.lanes.map((lane) => toLane(lane, source));
	return {
		schema: "battle.normalized_ux_fixture.v1",
		battle_id: source.battle_id,
		proof_mode: "receipt_backed_fixture",
		generated_at: "source-receipt-time-not-published",
		mocked: false,
		live_source: source.live_source,
		status: "PASS",
		claims: { proves: source.claim_boundary.may_claim, does_not_prove: source.claim_boundary.must_not_claim },
		battle_clock: {
			mode: "receipt_elapsed",
			allotted_seconds: duration,
			elapsed_seconds: duration,
			remaining_seconds: 0,
			started_at: null,
			ended_at: null,
			proof_mode: "receipt_backed_fixture",
			source_receipt_id: source.fixture_id,
		},
		timeline_elapsed_axis_model: {
			x_position_is_elapsed_time: true,
			x_axis_mode: "elapsed_seconds",
			axis_max_elapsed_seconds: duration,
			keyframes: source.events.map((event) => ({ x: pct(event.elapsed_seconds, duration), receipt_order_x: pct(event.seq, source.events.length), elapsed_seconds: event.elapsed_seconds })),
			playhead: { current_x: 100, current_elapsed_seconds: duration },
			render_rules: ["Receipt commit elapsed_seconds controls replay order; it does not independently prove semantic action occurrence time."],
		},
		timeline: { mode: "elapsed_seconds", min_x: 0, max_x: 100, event_count: source.events.length, lane_count: lanes.length, supports_zoom: true, supports_pan: true },
		lineage: {
			mode: "receipt_backed",
			spawn_count: source.lineage_edges.length,
			parent_lane_ids: source.lineage_edges.map((edge) => edge.parent_lane_id),
			child_lane_ids: source.lineage_edges.map((edge) => edge.child_lane_id),
			groups: source.lineage_edges.map((edge) => {
				const receipt = edgeVisibilityReceipt(edge);
				return { group_id: `lineage:${edge.team}`, parent_lane_id: edge.parent_lane_id, child_lane_ids: [edge.child_lane_id], lane_ids: [edge.parent_lane_id, edge.child_lane_id], collapsible: true, expanded_by_default: true, spawn_receipt_ids: [receipt.receipt_id ?? receipt.sha256], lane_count: 2, proof_mode: "receipt_backed_fixture" };
			}),
			spawns: source.lineage_edges.map((edge) => {
				const child = source.lanes.find((lane) => lane.lane_id === edge.child_lane_id)!;
				const receipt = edgeVisibilityReceipt(edge);
				return { receipt_id: receipt.receipt_id ?? receipt.sha256, parent_lane_id: edge.parent_lane_id, child_lane_id: edge.child_lane_id, generation: child.generation, spawn_elapsed_seconds: edge.visible_from_elapsed_seconds, visible_from_elapsed_seconds: edge.visible_from_elapsed_seconds, child_start_elapsed_seconds: child.active_from_elapsed_seconds, first_active_segment_elapsed_seconds: child.active_from_elapsed_seconds, proof_mode: "receipt_backed_fixture" as const };
			}),
			proof_mode: "receipt_backed_fixture",
			does_not_prove: source.claim_boundary.must_not_claim,
		},
		sprite_theme: source.sprite_theme,
		lanes,
		events: source.events.map((event) => toBattleEvent(event, source)),
		leaderboard: [],
		receipts: source.receipt_refs.map((receipt) => ({ receipt_id: receipt.receipt_id ?? `${receipt.schema}:${receipt.sha256.slice(0, 12)}`, receipt_type: receipt.schema, artifact_ref: `sha256:${receipt.sha256}`, summary: receipt.verdict ?? receipt.status ?? "receipt", proof_mode: "receipt_backed_fixture" })),
		validation: { schema: "battle.adaptive_lineage_frontend_projection.v1", fail_closed: true, source_schema: source.schema, renderer_contract: source.renderer_contract },
	};
}

const MECHANICS_LANE_ORDER = ["G0", "G1-A", "G1-B", "G2"];
const MECHANICS_TEMPLATE_LANE_IDS = ["red-g1", "red-g2", "blue-g1", "blue-g2"];

function mechanicsNodeLabel(node: AdaptiveLineageNode): string {
	if (node.id === "G0") return "G0 SEED";
	if (node.selected) return `${node.id} SELECTED`;
	if (node.runner_up) return `${node.id} RUNNER-UP`;
	if (node.role === "descendant") return `${node.id} DESCENDANT`;
	return node.id;
}

function mechanicsReceipt(node: AdaptiveLineageNode, fixture: BattleAdaptiveLineageMechanicsFixtureV1): BattleReceiptRef {
	return {
		receipt_id: `${fixture.run_id}:${node.id}:fitness`,
		receipt_type: "battle.adaptive_lineage_node_fitness.v1",
		summary: node.judge_outcome
			? `fitness ${node.fitness_status ?? "evaluated"} · vulnerable original ${node.judge_outcome.vulnerable_original_confirmed ? "yes" : "no"}`
			: "seed specimen receipt",
		proof_mode: "receipt_backed_fixture",
	};
}

function judgeDurationLabel(node: AdaptiveLineageNode): string {
	return typeof node.judge_outcome?.duration_seconds === "number" ? `${node.judge_outcome.duration_seconds}s` : "no Judge duration";
}

function mechanicsOutputSummary(node: AdaptiveLineageNode, fixture: BattleAdaptiveLineageMechanicsFixtureV1): string {
	if (!node.judge_outcome) return `${node.id}: seed specimen · run ${fixture.run_id}`;
	return [
		`${node.id}: fitness ${node.fitness_status ?? "evaluated"}`,
		`run=${fixture.run_id}`,
		`novelty=${node.novelty_distance ?? "n/a"}`,
		`judge_duration=${judgeDurationLabel(node)}`,
		`vulnerable_original_confirmed=${node.judge_outcome.vulnerable_original_confirmed}`,
		`patched_bypass=${node.judge_outcome.patched_bypass}`,
	].join("; ");
}

function mechanicsLaneEvents(node: AdaptiveLineageNode, fixture: BattleAdaptiveLineageMechanicsFixtureV1, duration: number): LaneEvent[] {
	const mutationAt = node.id === "G0" ? 0 : node.generation === 1 ? duration * 0.42 : duration * 0.76;
	const events: LaneEvent[] = [];
	if (node.mutation_operator) {
		events.push({
			id: `${node.id}:mutation`,
			kind: "genome_selected",
			x: pct(mutationAt, duration),
			label: `${node.id} · ${node.mutation_operator}`,
			timeLabel: "adaptive receipt",
			proven: true,
			proofMode: "receipt_backed_fixture",
			receiptId: `${fixture.run_id}:${node.id}:mutation`,
			elapsed_seconds: mutationAt,
			at_seconds: mutationAt,
			order_index: node.generation,
			label_band: node.selected ? "upper" : "lower",
			marker_priority: node.selected || node.runner_up ? 95 : 80,
			collision_group: `adaptive-mechanics:${node.id}`,
		});
	}
	if (node.judge_outcome) {
		const judgeAt = node.generation === 1 ? duration * 0.54 : duration * 0.9;
		events.push({
			id: `${node.id}:fitness`,
			kind: "useful",
			x: pct(judgeAt, duration),
			label: `${node.id} · fitness ${node.fitness_status ?? "evaluated"}`,
			timeLabel: "Judge receipt",
			proven: true,
			proofMode: "receipt_backed_fixture",
			receiptId: mechanicsReceipt(node, fixture).receipt_id,
			elapsed_seconds: judgeAt,
			at_seconds: judgeAt,
			order_index: node.generation + 10,
			label_band: "upper",
			marker_priority: 100,
			collision_group: `adaptive-mechanics:${node.id}`,
		});
	}
	return events;
}

function mechanicsActivitySegments(node: AdaptiveLineageNode, visibleAt: number, activeAt: number, duration: number): LaneActivitySegment[] {
	if (!node.parentId) return [];
	return [
		{
			id: `${node.id}:authorized-pending`,
			phase: "authorized_pending",
			label: `${node.id} authorized from ${node.parentId}`,
			start_x: pct(visibleAt, duration),
			end_x: pct(activeAt, duration),
			start_elapsed_seconds: visibleAt,
			end_elapsed_seconds: activeAt,
			proof_mode: "receipt_backed_fixture",
		},
		{
			id: `${node.id}:mutation-evidence`,
			phase: "mutation_evidence",
			label: `${node.mutation_operator ?? "seed"} · ${node.id}`,
			start_x: pct(activeAt, duration),
			end_x: 100,
			start_elapsed_seconds: activeAt,
			end_elapsed_seconds: duration,
			proof_mode: "receipt_backed_fixture",
		},
	];
}

function mechanicsLaneTiming(node: AdaptiveLineageNode, duration: number) {
	const visibleAt = node.id === "G0" ? 0 : node.generation === 1 ? duration * 0.28 : duration * 0.58;
	const activeAt = node.id === "G0" ? 0 : Math.min(duration, visibleAt + duration * 0.06);
	return { visibleAt, activeAt };
}

function mechanicsLane(node: AdaptiveLineageNode, template: Lane | undefined, fixture: BattleAdaptiveLineageMechanicsFixtureV1, duration: number): Lane {
	const { visibleAt, activeAt } = mechanicsLaneTiming(node, duration);
	const receipt = mechanicsReceipt(node, fixture);
	const changedDimensions = node.changed_dimensions.map((dim) => dim.dimension);
	const selectionText = node.selected ? "selected G1" : node.runner_up ? "runner-up G1" : node.role;
	return {
		...(template ?? {}),
		id: node.id,
		name: mechanicsNodeLabel(node),
		payloadId: node.id,
		generation: node.generation,
		team: "red",
		parentId: node.parentId ?? undefined,
		parent_id: node.parentId ?? undefined,
		children: [],
		selected: node.selected,
		runner_up: node.runner_up,
		summary: `${node.id} · ${selectionText}${node.mutation_operator ? ` · ${node.mutation_operator}` : ""}`,
		xStart: pct(visibleAt, duration),
		xEnd: 100,
		start_elapsed_seconds: visibleAt,
		visible_from_elapsed_seconds: visibleAt,
		first_active_segment_elapsed_seconds: activeAt,
		end_elapsed_seconds: duration,
		duration_elapsed_seconds: duration - visibleAt,
		runnerX: 100,
		runnerState: node.role === "seed" ? "advance" : "mutate",
		runnerVerb: node.role === "seed" ? "seed" : "mutate",
		lineColor: node.runner_up ? "purple" : node.selected ? "green" : "red",
		terminal: "none",
		events: mechanicsLaneEvents(node, fixture, duration),
		activitySegments: mechanicsActivitySegments(node, visibleAt, activeAt, duration),
		lineageGroupId: node.parentId ? `adaptive:${node.parentId}` : `adaptive:${node.id}`,
		collapsible: fixture.edges.some((edge) => edge.from === node.id),
		expandedByDefault: true,
		inheritedContext: node.parentId ? [`parent=${node.parentId}`, `operator=${node.mutation_operator ?? "none"}`] : [],
		mutationRationale: node.technique_delta ?? undefined,
		stdout: [
			mechanicsOutputSummary(node, fixture),
		],
		stderr: [],
		cockpit: undefined,
		receipts: [receipt.receipt_id],
		proofMode: "receipt_backed_fixture",
		actor_visual: {
			schema: "battle.actor_visual.v1",
			actor_id: node.id,
			lane_id: node.id,
			role: node.role,
			team: "red",
			archetype: "adaptive-lineage-runner",
			variant_id: node.id,
			style_family: "adaptive-lineage",
			initial_state: node.role === "seed" ? "idle" : "mutate",
			state_source: "battle.adaptive_lineage_mechanics_fixture.v1",
		},
		knowledge_packet: node.parentId
			? {
					present: true,
					status: "PASS",
					packet_id: `${fixture.run_id}:${node.parentId}->${node.id}`,
					parent_packet_id: node.parentId,
					research_goals: [`derive ${node.id} from ${node.parentId}`],
					parent_analysis: {
						parent_id: node.parentId,
						mutation_operator: node.mutation_operator ?? "none",
						selection_binding: node.parentId === fixture.selection.selected_id ? "selected_parent" : "candidate_parent",
					},
					child_ack: {
						required: true,
						received: true,
						ack_source: `${fixture.run_id}:${node.id}:qualification`,
					},
				}
			: undefined,
		score_calibration: node.judge_outcome
			? {
					schema: "battle.adaptive_lineage_score_calibration.v1",
					outcome_class: `fitness ${node.fitness_status ?? "evaluated"}`,
					formula: "Qualification PASS requires Judge-backed vulnerable_original_confirmed and fail-closed adaptive checks.",
					profile_inputs: {
						node_id: node.id,
						parent_id: node.parentId,
						mutation_operator: node.mutation_operator,
						novelty_distance: node.novelty_distance,
						changed_dimensions: changedDimensions,
						judge_outcome: node.judge_outcome,
					},
				}
			: undefined,
		score_semantics: {
			schema: "battle.adaptive_lineage_lane_score_semantics.v1",
			lane_id: node.id,
			outcome_class: selectionText,
			outcome_tier: node.fitness_status ?? fixture.qualification.status,
			terminal_state: fixture.qualification.status === "PASS" ? "qualification_pass" : "qualification_pending",
			spawn_state: node.parentId ? `derived_from_${node.parentId}` : "seed",
			score_basis: node.technique_delta ?? `${node.id} adaptive lineage node`,
			proof_mode: "receipt_backed_fixture",
			rules: {
				qualification_pass: fixture.qualification.status === "PASS",
				selected: node.selected,
				runner_up: node.runner_up,
				vulnerable_original_confirmed: node.judge_outcome?.vulnerable_original_confirmed ?? false,
				patched_bypass: node.judge_outcome?.patched_bypass ?? false,
			},
		},
	};
}

function mechanicsBattleEvents(nodes: AdaptiveLineageNode[], fixture: BattleAdaptiveLineageMechanicsFixtureV1, duration: number): BattleEvent[] {
	const events: BattleEvent[] = [];
	for (const node of nodes) {
		const { activeAt } = mechanicsLaneTiming(node, duration);
		if (node.mutation_operator) {
			events.push({
				id: `${node.id}:mutation`,
				ts: activeAt,
				battle_id: fixture.battle_id,
				team: "red",
				actor_id: node.id,
				actor_kind: "exploit_agent",
				parent_id: node.parentId ?? undefined,
				elapsed_seconds: activeAt,
				at_seconds: activeAt,
				event_type: "genome_selected",
				summary: `${node.id} · ${node.mutation_operator} · novelty ${node.novelty_distance ?? "n/a"}`,
				proof_mode: "receipt_backed_fixture",
				public_trace: {
					observation: node.parentId ? `${node.id} derived from ${node.parentId}` : "seed",
					action: node.technique_delta ?? node.mutation_operator,
					result: node.fitness_status ?? fixture.qualification.status,
					learned: node.changed_dimensions.map((dim) => dim.dimension).join(", "),
				},
				receipts: [mechanicsReceipt(node, fixture)],
				ui: {
					importance: node.role === "descendant" ? "hero" : "visible",
					runner_state: "mutate",
					runner_animation: "mutate_pulse",
					sound_cue: "mutate_chirp",
					spectator_caption: `${node.id} mutation evidence is bound to the adaptive qualification receipt.`,
					notification: `Adaptive lineage — ${node.id}: ${node.mutation_operator}`,
				},
			});
		}
		if (node.judge_outcome) {
			const judgeAt = node.generation === 1 ? duration * 0.54 : duration * 0.9;
			events.push({
				id: `${node.id}:fitness`,
				ts: judgeAt,
				battle_id: fixture.battle_id,
				team: "judge",
				actor_id: node.id,
				actor_kind: "judge",
				elapsed_seconds: judgeAt,
				at_seconds: judgeAt,
				event_type: "judge.verdict",
				summary: `${node.id} fitness ${node.fitness_status ?? "evaluated"} · vulnerable original ${node.judge_outcome.vulnerable_original_confirmed ? "confirmed" : "not confirmed"}`,
				proof_mode: "receipt_backed_fixture",
				receipts: [mechanicsReceipt(node, fixture)],
				judge_attempt: {
					pair_id: `${fixture.run_id}:${node.id}`,
					red_worker_id: node.id,
					red_lane_id: node.id,
					blue_worker_id: "qualification-judge",
					blue_action_id: "adaptive-lineage-fitness",
					verdict: node.judge_outcome.vulnerable_original_confirmed ? "QUALIFICATION_PASS" : "QUALIFICATION_FAIL",
					status: node.fitness_status ?? fixture.qualification.status,
				},
				ui: {
					importance: node.selected || node.role === "descendant" ? "hero" : "visible",
					runner_state: "advance",
					sound_cue: "none",
					spectator_caption: `${node.id} Judge-backed fitness is present in the adaptive qualification receipt.`,
					notification: `Adaptive lineage — ${node.id}: fitness ${node.fitness_status ?? "evaluated"}`,
				},
			});
		}
	}
	events.push({
		id: "adaptive-lineage-selection",
		ts: duration * 0.62,
		battle_id: fixture.battle_id,
		team: "system",
		actor_id: "adaptive-lineage-selection",
		actor_kind: "battle_orchestrator",
		target_actor_ids: [fixture.selection.selected_id, fixture.selection.runner_up_id].filter((id): id is string => Boolean(id)),
		elapsed_seconds: duration * 0.62,
		at_seconds: duration * 0.62,
		event_type: "judge.receipt_verified",
		summary: `Selection: ${fixture.selection.selected_id ?? "n/a"} over ${fixture.selection.runner_up_id ?? "n/a"} · ${fixture.selection.deciding_criterion ?? "criterion not emitted"}`,
		proof_mode: "receipt_backed_fixture",
		ui: {
			importance: "hero",
			runner_state: "advance",
			sound_cue: "none",
			spectator_caption: "Deterministic selection receipt binds both G1 outcomes before G2 reproduction.",
			notification: `Adaptive lineage — selected ${fixture.selection.selected_id ?? "n/a"} -> G2`,
		},
	});
	return events.sort((a, b) => Number(a.elapsed_seconds ?? 0) - Number(b.elapsed_seconds ?? 0));
}

export function applyAdaptiveMechanicsToRaceFixture(
	base: BattleNormalizedUxFixture,
	adaptiveLineage: BattleAdaptiveLineageMechanicsFixtureV1,
): BattleNormalizedUxFixture {
	const duration = base.battle_clock?.allotted_seconds ?? base.battle_clock?.elapsed_seconds ?? 120;
	const nodesById = new Map(adaptiveLineage.nodes.map((node) => [node.id, node]));
	const orderedNodes = MECHANICS_LANE_ORDER.map((id) => nodesById.get(id)).filter((node): node is AdaptiveLineageNode => Boolean(node));
	if (orderedNodes.length !== 4 || adaptiveLineage.qualification.status !== "PASS") {
		return { ...base, adaptive_lineage: adaptiveLineage };
	}
	const templateById = new Map(base.lanes.map((lane) => [lane.id, lane]));
	const lanes = orderedNodes.map((node, index) =>
		mechanicsLane(node, templateById.get(MECHANICS_TEMPLATE_LANE_IDS[index]), adaptiveLineage, duration),
	);
	const laneById = new Map(lanes.map((lane) => [lane.id, lane]));
	for (const edge of adaptiveLineage.edges) {
		const parent = laneById.get(edge.from);
		if (parent) parent.children = [...(parent.children ?? []), edge.to];
	}
	const events = mechanicsBattleEvents(orderedNodes, adaptiveLineage, duration);
	const spawns = adaptiveLineage.edges.map((edge) => {
		const child = laneById.get(edge.to);
		const visibleAt = child?.visible_from_elapsed_seconds ?? 0;
		const activeAt = child?.first_active_segment_elapsed_seconds ?? visibleAt;
		return {
			receipt_id: `${adaptiveLineage.run_id}:${edge.from}->${edge.to}`,
			parent_lane_id: edge.from,
			child_lane_id: edge.to,
			generation: child?.generation ?? 0,
			spawn_elapsed_seconds: visibleAt,
			visible_from_elapsed_seconds: visibleAt,
			child_start_elapsed_seconds: activeAt,
			first_active_segment_elapsed_seconds: activeAt,
			proof_mode: "receipt_backed_fixture" as const,
		};
	});
	return {
		...base,
		adaptive_lineage: adaptiveLineage,
		lanes,
		events,
		receipts: [
			...(base.receipts ?? []),
			...orderedNodes.map((node) => mechanicsReceipt(node, adaptiveLineage)),
		],
		timeline: base.timeline
			? { ...base.timeline, lane_count: lanes.length, event_count: events.length }
			: { mode: "elapsed_seconds", min_x: 0, max_x: 100, event_count: events.length, lane_count: lanes.length, supports_zoom: true, supports_pan: true },
		lineage: {
			...(base.lineage ?? { mode: "receipt_backed", spawn_count: 0 }),
			mode: "receipt_backed",
			spawn_count: adaptiveLineage.edges.length,
			parent_lane_ids: adaptiveLineage.edges.map((edge) => edge.from),
			child_lane_ids: adaptiveLineage.edges.map((edge) => edge.to),
			groups: adaptiveLineage.edges.map((edge) => ({
				group_id: `adaptive:${edge.from}`,
				parent_lane_id: edge.from,
				child_lane_ids: [edge.to],
				lane_ids: [edge.from, edge.to],
				collapsible: true,
				expanded_by_default: true,
				spawn_receipt_ids: [`${adaptiveLineage.run_id}:${edge.from}->${edge.to}`],
				lane_count: 2,
				proof_mode: "receipt_backed_fixture",
			})),
			spawns,
			proof_mode: "receipt_backed_fixture",
		},
	};
}
