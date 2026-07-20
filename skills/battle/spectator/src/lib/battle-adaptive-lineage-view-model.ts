import type { BattleNormalizedAdaptiveLineageFixtureV1, AdaptiveLineageEvent, AdaptiveLineageLane } from "./battle-adaptive-lineage-types";
import type { BattleEvent, BattleMemoryPromotion, BattleNormalizedUxFixture, Lane, LaneActivitySegment, LaneEvent } from "./battle-types";

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
