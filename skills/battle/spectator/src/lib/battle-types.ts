export type Team = "red" | "blue" | "judge" | "system";

export type ProofMode = "fixture" | "receipt_backed_fixture" | "mocked" | "live" | "pending" | "missing";

export type ActorKind =
	| "exploit_agent"
	| "patch_agent"
	| "tau_exploit_subagent"
	| "tau_patch_subagent"
	| "battle_orchestrator"
	| "judge"
	| "scorekeeper";

export type Importance = "background" | "visible" | "spectator" | "hero";

export type FinisherPhase = "idle" | "lock_on" | "incoming" | "impact" | "killed" | "settled";

export type BlueFinisherState = {
	laneId: string;
	phase: FinisherPhase;
	blueSourceId: string;
	receiptId?: string;
};

export type RunnerState =
	| "advance"
	| "research"
	| "stderr"
	| "self_heal"
	| "mutate"
	| "retry"
	| "detected"
	| "blocked_handoff"
	| "blocked"
	| "killed"
	| "promoted"
	| "fastest_crash";

export type RunnerAnimation =
	| "advance"
	| "pause_terminal"
	| "scan_research"
	| "self_heal_pulse"
	| "mutate_pulse"
	| "retry_charge"
	| "blue_scan_lock"
	| "runner_hit_by_blast"
	| "runner_collapse_skull"
	| "child_ignite"
	| "victory_surge"
	| "blue_force_push_destroy";

export type BlueAnimation =
	| "patch_agent_inspect"
	| "patch_agent_test"
	| "patch_wave_deploy"
	| "blue_sonic_blast"
	| "shield_wall_materialize";

export type SoundCue =
	| "none"
	| "scan_ping"
	| "mutate_chirp"
	| "retry_tick"
	| "blue_patch_deploy"
	| "blue_blast"
	| "kill_cannon"
	| "spawn_rise"
	| "victory_hit";

export type BattleEventType =
	| "battle.run_started"
	| "battle.scenario_loaded"
	| "tau.turn_started"
	| "tau.tool_call"
	| "tau.stdout"
	| "tau.stderr"
	| "tau.learned"
	| "tau.mutated"
	| "tau.retrying"
	| "tau.handoff_created"
	| "tau.spawned_child"
	| "tau.proof_pending"
	| "tau.killed"
	| "tau.blocked"
	| "tau.promoted"
	| "tau.fastest_crash"
	| "tau.artifact_blocked"
	| "red.agent_state"
	| "red.stdout"
	| "red.stderr"
	| "red.learned"
	| "red.mutated"
	| "red.retrying"
	| "red.detected"
	| "red.killed"
	| "red.blocked_handoff"
	| "red.spawned"
	| "red.promoted"
	| "red.fastest_crash"
	| "blue.agent_state"
	| "blue.patch_started"
	| "blue.patch_tested"
	| "blue.patch_deployed"
	| "blue.detected_red"
	| "blue.blocked_red"
	| "blue.kill_confirmed"
	| "judge.receipt_verified"
	| "judge.verdict"
	| "judge.insufficient_evidence";

export type BattleSkillEvent = {
	name: string;
	kind: "skill" | "tool" | "unregistered";
	status: "running" | "ok" | "failed" | "mocked" | "pending";
	timestamp?: string;
	summary?: string;
	receipt_id?: string;
	proof_mode: ProofMode;
};

export type BattleReceiptRef = {
	receipt_id: string;
	receipt_type: string;
	receipt_path?: string;
	artifact_ref?: string;
	summary?: string;
	proof_mode: ProofMode;
	pair_id?: string;
	red_worker_id?: string;
	red_lane_id?: string;
	blue_worker_id?: string;
	blue_action_id?: string;
};

export type BattlePublicTrace = {
	observation?: string;
	hypothesis?: string;
	action?: string;
	result?: string;
	learned?: string;
	next_move?: string;
};

export type ProofLabel = "LIVE PROOF" | "FIXTURE TRACE" | "FIXTURE SKILL TRACE" | "MOCKED SKILL" | "PROOF PENDING" | "MISSING PROOF";

export type BattleReplayCta = {
	label: "REPLAY IN DOCKER";
	icon: "container";
	state: "receipt_only" | "executable";
	visible: boolean;
	disabled_reason: string | null;
	tooltip: string;
	proof_mode: ProofMode;
};

export type BattleReplayRef = {
	label: "REPLAY IN DOCKER";
	kind: "receipt_only" | "executable_endpoint";
	receipt_id: string;
	attempt_id: string;
	pair_id: string;
	red_worker_id: string;
	red_lane_id: string;
	blue_worker_id: string;
	blue_action_id: string;
	can_execute_now: boolean;
	endpoint: string | null;
	command_receipt_id: string | null;
	cta: BattleReplayCta;
	proof_mode: ProofMode;
};

export type BattleClock = {
	mode: "receipt_elapsed" | "live_stream" | "fixture_static" | string;
	started_at?: string | null;
	ended_at?: string | null;
	elapsed_seconds?: number | null;
	allotted_seconds?: number | null;
	remaining_seconds?: number | null;
	source_receipt_id?: string;
	proof_mode: ProofMode;
};

/** Canonical clock for live/replay — see BACKEND_UX_CONTRACT.md §1–§2 */
export type BattleClockV1 = {
	schema: "battle.clock.v1";
	round_id?: string;
	mode: "live" | "receipt_replay" | "paused_replay" | "design_fixture" | string;
	source: "server_wall_clock" | "receipt_timestamps" | "fixture_static" | string;
	started_at?: string | null;
	server_now?: string | null;
	ended_at?: string | null;
	allotted_seconds: number;
	elapsed_seconds: number;
	remaining_seconds: number;
	/** Playhead position; equals elapsed in live, may differ when scrubbing replay */
	current_seconds: number;
	team_budgets?: {
		red?: { allotted_seconds: number; used_seconds: number; remaining_seconds: number };
		blue?: { allotted_seconds: number; used_seconds: number; remaining_seconds: number };
	};
	proof_mode?: ProofMode;
};

export type TimelineFollowMode = "manual" | "scroll_after_threshold" | "center_playhead";

/** Backend timeline policy — seconds/percent only; UI derives pixel x — see BACKEND_UX_CONTRACT.md §11 */
export type BattleTimelineControlV1 = {
	schema: "battle.timeline_control.v1";
	clock_mode: BattleClockV1["mode"];
	time_domain: {
		start_seconds: number;
		end_seconds: number;
		allotted_seconds: number;
	};
	playhead: {
		current_seconds: number;
		current_pct?: number;
		can_animate: boolean;
	};
	viewport_defaults?: {
		follow_mode?: TimelineFollowMode;
		follow_threshold_pct?: number;
		can_override_locally?: boolean;
	};
	controls?: {
		can_play?: boolean;
		can_pause?: boolean;
		can_scrub?: boolean;
		can_zoom?: boolean;
		can_pan?: boolean;
	};
	render_guards?: {
		derive_x_positions_from_elapsed_seconds?: boolean;
		do_not_draw_lane_progress_before_lane_start?: boolean;
		do_not_reveal_terminal_outcome_before_receipt_time?: boolean;
		child_lane_requires_lineage_receipt?: boolean;
		terminal_outcome_requires_judge_receipt?: boolean;
		auto_scroll_only_while_playback_active?: boolean;
	};
};

/** Canonical semantic event — backend truth; UI maps to animation */
export type BattleSemanticEventV1 = {
	event_id: string;
	event_type: string;
	event_kind: LaneEventKind | string;
	lane_id?: string;
	at_seconds: number;
	phase?: string;
	status_after?: string;
	terminal?: boolean;
	receipt_id?: string;
	proof_mode: ProofMode;
	lineage_event?: {
		type: "spawn_child" | string;
		parent_lane_id: string;
		child_lane_id: string;
		at_seconds: number;
		parent_receipt_id?: string;
		child_receipt_id?: string;
		lineage_receipt_id?: string;
		inherited_context_receipt_ids?: string[];
	};
};

export type BattleActiveSegmentV1 = {
	lane_id: string;
	kind: string;
	started_at_seconds: number;
	last_heartbeat_at_seconds?: number;
	lease_expires_at_seconds?: number;
	provisional: boolean;
	pending_receipt: boolean;
};

export type BattleReceiptSegmentV1 = {
	segment_id: string;
	lane_id: string;
	kind: string;
	start_seconds: number;
	end_seconds: number;
	start_event_id: string;
	end_event_id: string;
	proof_mode: ProofMode;
};

export type BattleLiveEventEnvelopeV1 = {
	schema: "battle.live_event.v1";
	run_id: string;
	seq: number;
	event_id: string;
	at_seconds: number;
	observed_at: string;
	event_type: string;
	payload: Record<string, unknown>;
};

export type BattleSnapshotV1 = {
	schema: "battle.snapshot.v1";
	run_id: string;
	last_seq: number;
	clock: BattleClockV1;
	events: BattleSemanticEventV1[];
	lanes: Lane[];
	scoreboard?: Record<string, unknown>;
	timeline_elapsed_axis_model?: {
		x_position_is_elapsed_time?: boolean;
		x_axis_mode?: string;
		axis_max_elapsed_seconds?: number;
	};
	battle_timeline_control?: BattleTimelineControlV1;
};

export type LaneDerivationProvenance = {
	source_event_ids?: string[];
	source_receipt_ids?: string[];
	validation?: {
		derived_from_canonical_events?: boolean;
		terminal_claims_receipt_backed?: boolean;
	};
};


export type BattleSpectatorShell = {
	schema: "battle.spectator_shell.v1";
	proof_mode: ProofMode;
	battle_title: string;
	subtitle: string;
	mode_badge: string;
	truth_label: string;
	facts: Array<{
		label: string;
		value: string;
	}>;
	score: {
		red: {
			label: string;
			sub: string;
			value: string;
		};
		blue: {
			label: string;
			sub: string;
			value: string;
		};
		verdict: string;
	};
	event_ticker: {
		label: string;
		count: number;
		latest_text: string;
		live: false;
		source: "events";
	};
	render_guards: string[];
};

export type BattleRendererBindingContract = {
	schema: "battle.renderer_binding_contract.v1";
	proof_mode: ProofMode;
	purpose: string;
	battle_shell: Record<string, string>;
	round_time: Record<string, string>;
	scrollable_timeline: Record<string, string>;
	moving_playhead: Record<string, string>;
	parent_spawn_and_collapse: Record<string, string>;
	lane_activity_and_label_layout: Record<string, string>;
	agent_detail_cockpit: Record<string, string>;
	docker_replay_cta: Record<string, string>;
};

export type BattleTimeline = {
	mode: "receipt_order" | "elapsed_seconds" | string;
	min_x: number;
	max_x: number;
	event_count: number;
	lane_count: number;
	supports_zoom: boolean;
	supports_pan: boolean;
	scroll_axis?: "horizontal";
	playhead?: {
		mode: "receipt_elapsed" | string;
		/** @deprecated Backend must send current_seconds; UI derives x from scale — BACKEND_UX_CONTRACT.md §11 */
		current_x: number;
		elapsed_seconds?: number | null;
		source_receipt_id?: string;
		can_animate: boolean;
		animation_semantics: "receipt_replay_only" | string;
		keyframes: Array<{
			x: number;
			lane_id: string;
			event_id: string;
			kind: string;
			label: string;
			proof_mode: ProofMode;
			spawn_elapsed_seconds?: number;
			visible_from_elapsed_seconds?: number;
			child_start_elapsed_seconds?: number;
			first_active_segment_elapsed_seconds?: number;
			spawn_duration_elapsed_seconds?: number;
		}>;
		proof_mode: ProofMode;
	};
	viewport?: {
		initial_min_x: number;
		initial_max_x: number;
		min_zoom: number;
		max_zoom: number;
		proof_mode: ProofMode;
	};
};

export type BattleEvent = {
	id: string;
	time?: string;
	tone?: "red" | "blue" | "green" | "yellow" | "purple" | "slate";
	text?: string;
	ts: string;
	battle_id: string;
	team: Team;
	actor_id: string;
	actor_kind: ActorKind;
	target_actor_ids?: string[];
	parent_id?: string;
	parent_actor_id?: string;
	parent_tau_subagent_id?: string;
	spawned_children?: string[];
	payload_id?: string;
	tau_subagent_id?: string;
	tau_run_id?: string;
	tau_turn_id?: string;
	pair_id?: string;
	red_worker_id?: string;
	red_lane_id?: string;
	blue_worker_id?: string;
	blue_action_id?: string;
	elapsed_seconds?: number | null;
	at_seconds?: number | null;
	event_type: BattleEventType;
	summary: string;
	scenario?: {
		public_entrypoint?: string;
		hidden_vulnerability_family?: string;
		cwe?: string;
	};
	turn?: {
		loop_index?: number;
		phase?: string;
		current_action?: string;
		status?: string;
	};
	public_trace?: BattlePublicTrace;
	output?: {
		stdout_excerpt?: string;
		stderr_excerpt?: string;
	};
	skills?: BattleSkillEvent[];
	evidence?: {
		stream?: "stdout" | "stderr" | "jsonl" | "receipt" | "docker";
		excerpt?: string;
		receipt_id?: string;
		receipt_path?: string;
		artifact_ref?: string;
		replay_id?: string;
		docker_replay_id?: string;
		stdout_excerpt?: string;
		stderr_excerpt?: string;
		proof_mode?: ProofMode;
		pair_id?: string;
		red_worker_id?: string;
		red_lane_id?: string;
		blue_worker_id?: string;
		blue_action_id?: string;
	};
	receipts?: BattleReceiptRef[];
	handoff?: {
		handoff_schema: "tau.agent_handoff.v1";
		handoff_id: string;
		parent_tau_subagent_id: string;
		child_tau_subagent_ids: string[];
		inherited_context?: string[];
		leased_task?: string;
		goal?: string;
		receipt_id?: string;
		proof_mode: ProofMode;
	};
	judge_attempt?: {
		pair_id?: string;
		red_worker_id?: string;
		red_lane_id?: string;
		blue_worker_id?: string;
		blue_action_id?: string;
		verdict?: string;
		status?: string;
	};
	replay?: BattleReplayRef | null;
	ui: {
		lane_x?: number;
		runner_state?: RunnerState | string;
		runner_animation?: RunnerAnimation | string;
		blue_animation?: BlueAnimation | string;
		impact_animation?: "blue_sonic_blast" | "kill_cannon" | "handoff_ignite" | "victory_surge";
		target_animation?: "blue_force_push_destroy";
		sound_cue?: SoundCue;
		importance: Importance;
		spectator_caption?: string;
		notification?: string;
	};
	proof_mode?: ProofMode;
};

export type LaneTerminal = "none" | "killed" | "blocked" | "blocked_handoff" | "promoted" | "fastest_crash";

export type LaneEventKind =
	| "research"
	| "payload"
	| "useful"
	| "stderr"
	| "self_heal"
	| "mutate"
	| "retry"
	| "detected"
	| "blue_blast"
	| "handoff"
	| "killed"
	| "blocked"
	| "promoted"
	| "fastest_crash";

export type LaneEvent = {
	id: string;
	kind: LaneEventKind;
	x: number;
	label?: string;
	timeLabel?: string;
	proven?: boolean;
	proofMode?: ProofMode;
	receiptId?: string;
	blueSourceId?: string;
	animation?: RunnerAnimation | BlueAnimation | "kill_cannon" | "blue_sonic_blast";
	order_index?: number | null;
	elapsed_seconds?: number | null;
	at_seconds?: number | null;
	label_band?: "upper" | "lower" | "auto";
	marker_priority?: number;
	collision_group?: string;
};

export type LaneActivitySegment = {
	id: string;
	phase: "materialize" | "research" | "payload" | "useful_signal" | "handoff" | "patch_gate" | "judge_replay" | "receipt_event" | string;
	label: string;
	start_x: number;
	end_x: number;
	start_elapsed_seconds?: number;
	visible_from_elapsed_seconds?: number;
	first_active_segment_elapsed_seconds?: number;
	end_elapsed_seconds?: number;
	source_event_id?: string | null;
	proof_mode: ProofMode;
};

export type ActorVisual = {
	schema: "battle.actor_visual.v1";
	actor_id: string;
	lane_id: string;
	role: string;
	team: Team;
	archetype: string;
	variant_id: string;
	style_family?: string;
	facing?: string;
	scale_class?: string;
	initial_state?: string;
	state_source?: string;
	state_timeline?: Array<{
		at_seconds: number;
		state: string;
		source_event_id: string;
		source_receipt_id?: string;
		segment_id?: string;
		provisional?: boolean;
	}>;
};

export type LaneCockpit = {
	schema: "battle.lane_cockpit.v1";
	proof_mode: ProofMode;
	proof_label: ProofLabel;
	selected_tau_exploit_subagent: {
		actor_id: string;
		payload_id: string;
		tau_subagent_id: string;
		tau_run_id: string;
		tau_turn_id: string;
		worker_id: string;
		generation: number;
		missing_tau_id: boolean;
		parent_lane_id?: string;
		spawn_receipt_id?: string;
	};
	current_turn: {
		loop_index: number;
		phase: string;
		current_action: string;
		status: string;
	};
	public_trace: Required<BattlePublicTrace>;
	output: {
		stdout: string[];
		stderr: string[];
	};
	skills_tools: Array<{
		name: string;
		kind: "skill" | "tool" | "unregistered";
		status: "running" | "ok" | "failed" | "mocked" | "pending";
		proof_label: Exclude<ProofLabel, "FIXTURE TRACE">;
		receipt_id: string;
		proof_mode: ProofMode;
	}>;
	memory_project_knowledge_events: BattleSkillEvent[];
	learned: string;
	next_move: string;
	blue_outcome: {
		detected: boolean;
		blocked: boolean;
		killed: boolean;
		forced_handoff: boolean;
		status: string;
		receipt_id?: string | null;
		proof_mode: ProofMode;
	};
	latest_receipt_id: string;
	replay?: BattleReplayRef | null;
};

export type Lane = {
	id: string;
	name: string;
	payloadId: string;
	generation: number;
	team: "red";
	parentId?: string;
	parent_id?: string;
	expanded?: boolean;
	selected?: boolean;
	summary?: string;
	xStart: number;
	xEnd: number;
	start_elapsed_seconds?: number;
	visible_from_elapsed_seconds?: number;
	first_active_segment_elapsed_seconds?: number;
	end_elapsed_seconds?: number;
	duration_elapsed_seconds?: number;
	runnerX: number;
	runnerState: RunnerState | string;
	runnerVerb?: string;
	lineColor: "red" | "green" | "purple";
	terminal: LaneTerminal;
	events: LaneEvent[];
	activitySegments?: LaneActivitySegment[];
	lineageGroupId?: string;
	collapsible?: boolean;
	expandedByDefault?: boolean;
	children?: string[];
	inheritedContext?: string[];
	mutationRationale?: string;
	stdout?: string[];
	stderr?: string[];
	receipts?: string[];
	proofMode?: ProofMode;
	actor_visual?: ActorVisual;
	scenario?: {
		battle_id?: string;
		public_entrypoint?: string;
		hidden_vulnerability_family?: string;
		scenario_id?: string;
	};
	replay?: BattleReplayRef | null;
	cockpit?: LaneCockpit;
};

export type BluePatchAction = {
	id: string;
	name: string;
	agentName: string;
	xStart: number;
	xEnd: number;
	targetLaneIds: string[];
	state: "inspecting" | "testing" | "deployed" | "impact";
	receiptId: string;
	proofMode?: ProofMode;
	summary?: string;
};

export type LeaderboardEntry = {
	rank: number;
	laneId: string;
	name: string;
	status: "fastest_crash" | "promoted" | "blocked" | "killed";
	time: string;
	proofMode?: ProofMode;
	summary?: string;
};

/** Versioned alias — schema battle.normalized_ux_fixture.v1 — see BATTLE_RACE_ENGINE_PIXI_SPIKE.md */
export type BattleNormalizedUxFixture = {
	schema: "battle.normalized_ux_fixture.v1";
	battle_id: string;
	source_proof_dir?: string;
	proof_mode: ProofMode;
	generated_at: string;
	mocked?: boolean;
	live_source?: string;
	status?: string;
	scenario?: {
		scenario_id?: string;
		title?: string;
		public_entrypoint?: string;
		hidden_vulnerability_family?: string;
		cwe?: string;
		difficulty?: string;
		target_language?: string;
		runtime_image?: string;
	};
	claims?: {
		proves?: string[];
		does_not_prove?: string[];
	};
	ux_contract?: {
		schema: "battle.ux_contract.v1";
		mode: string;
		proof_mode: ProofMode;
		authoritative_fields?: Record<string, string>;
		required_render_guards?: string[];
		receipt_backed_values?: {
			lane_count?: number;
			event_count?: number;
			child_spawn_count?: number;
			blue_blocked_lane_ids?: string[];
			judge_pair_count?: number;
			lineage_group_count?: number;
			playhead_current_x?: number;
		};
		forbidden_inferences?: string[];
	};
	battle_clock?: BattleClock;
	spectator_shell?: BattleSpectatorShell;
	renderer_binding_contract?: BattleRendererBindingContract;
	timeline?: BattleTimeline;
	timeline_elapsed_axis_model?: {
		x_position_is_elapsed_time?: boolean;
		x_axis_mode?: string;
		axis_max_elapsed_seconds?: number;
		keyframes?: Array<{ x?: number; receipt_order_x?: number; elapsed_seconds?: number }>;
		playhead?: { current_x?: number; current_elapsed_seconds?: number };
		render_rules?: string[];
	};
	lineage?: {
		mode: "missing" | "receipt_backed" | string;
		spawn_count: number;
		parent_lane_ids?: string[];
		child_lane_ids?: string[];
		groups?: Array<{
			group_id: string;
			parent_lane_id: string;
			child_lane_ids: string[];
			lane_ids: string[];
			collapsible: boolean;
			expanded_by_default: boolean;
			spawn_receipt_ids: string[];
			lane_count: number;
			proof_mode: ProofMode;
		}>;
		spawns?: Array<{
			receipt_id: string;
			receipt_path?: string;
			parent_lane_id: string;
			child_lane_id: string;
			parent_worker_id?: string;
			child_worker_id?: string;
			parent_tau_subagent_id?: string;
			child_tau_subagent_id?: string;
			generation?: number;
			spawn_x?: number;
			child_x_start?: number;
			label?: string;
			time_label?: string;
			inherited_context?: string[];
			leased_task?: string;
			goal?: string;
			proof_mode: ProofMode;
			spawn_elapsed_seconds?: number;
			visible_from_elapsed_seconds?: number;
			child_start_elapsed_seconds?: number;
			first_active_segment_elapsed_seconds?: number;
			spawn_duration_elapsed_seconds?: number;
		}>;
		proof_mode: ProofMode;
		does_not_prove?: string[];
	};
	scoreboard?: {
		red_score?: number;
		blue_score?: number;
		tdsr?: number;
		asc?: number;
		verdict?: string;
		judged_pair_count?: number;
		blue_success_count?: number;
		red_materialized_count?: number;
		blue_materialized_count?: number;
		requested_red_workers?: number;
		requested_blue_workers?: number;
		red_lane_count?: number;
		blue_action_count?: number;
		child_spawn_count?: number;
		per_pair?: Array<Record<string, unknown>>;
	};
	lanes: Lane[];
	events: BattleEvent[];
	leaderboard: LeaderboardEntry[];
	receipts: BattleReceiptRef[];
	bluePatchActions?: BluePatchAction[];
	battle_timeline_control?: BattleTimelineControlV1;
	validation?: {
		schema?: string;
		fail_closed?: boolean;
		[key: string]: unknown;
	};
};

/** Canonical versioned name for normalized fixture input */
export type BattleNormalizedUxFixtureV1 = BattleNormalizedUxFixture;

/** Shared DOM + Pixi viewport — see BATTLE_RACE_ENGINE.md */
export type BattleTimelineViewportState = {
	zoom: number;
	worldLeftSeconds: number;
	worldRightSeconds: number;
	currentSeconds: number;
	followMode: TimelineFollowMode;
	labelWidthPx: 290;
	rowHeightPx: number;
};

export type BattleRaceEngineMode = "design_fixture" | "receipt_replay" | "live";

export type BattleEffectCueKind = "spawn" | "blocked" | "killed" | "fastest_crash" | "promoted" | "useful";

export type BattleEffectCue = {
	eventId: string;
	laneId: string;
	cue: BattleEffectCueKind;
	atSeconds: number;
	receiptId: string;
	proofMode: "receipt_backed" | "live" | "design_fixture";
};

export type BattleEngineRenderTestMode = {
	freezeTime: true;
	currentSeconds: number;
	disableParticles: boolean;
	deterministicSeed: string;
};

export type PixiDisplaySpec = {
	kind: "glyph" | "sprite" | "shape";
	/** Spritesheet frame name when kind is sprite */
	texture?: string;
	color?: number;
	radius?: number;
	width?: number;
	height?: number;
	opacity?: number;
};

export type PixiEffectSpec = {
	kind: BattleEffectCueKind;
	durationMs: number;
	/** Spritesheet frame for burst ring */
	texture?: string;
	color?: number;
	intensity: number;
};

export type BattleSpriteTheme = {
	runnerForLane(lane: Lane): PixiDisplaySpec;
	markerForEvent(event: LaneEvent): PixiDisplaySpec;
	effectForEvent(event: LaneEvent): PixiEffectSpec | null;
};

export type BattleRaceEngineInput = {
	fixture: BattleNormalizedUxFixtureV1;
	mode: BattleRaceEngineMode;
	selectedLaneId: string | null;
	viewport: BattleTimelineViewportState;
	onSelectLane(id: string): void;
	onSelectEvent(id: string): void;
	onEffectCue?: (cue: BattleEffectCue) => void;
	testMode?: BattleEngineRenderTestMode;
};

export type BattleRaceEngineRowLayout = {
	laneId: string;
	topPx: number;
	heightPx: number;
	isChild: boolean;
};
