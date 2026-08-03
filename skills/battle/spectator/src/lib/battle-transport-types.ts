import type { BattleHumanInterjectionPanelSource, BattleTimelineControlV1, Lane } from "./battle-types";

export type BattleTransportMode = "file_backed_replay_stream" | "live_sse_adapter" | "live_websocket_adapter";

export type BattleStreamContractV1 = {
	schema: "battle.stream_contract.v1";
	authority: string;
	event_schema: "battle.live_event.v1";
	snapshot_schema: "battle.snapshot.v1";
	lifecycle_schema: "battle.lifecycle_event.v1";
	transport: "append_only_jsonl" | "sse" | "websocket";
	phase: string;
	fail_closed_unknown_terminal_states: boolean;
};

export type BattleTransportManifestV1 = {
	schema: "battle.transport_manifest.v1";
	battle_id: string;
	run_id: string;
	mode: BattleTransportMode;
	mocked: boolean;
	live_source: string;
	event_count: number;
	last_seq: number;
	events_jsonl: "events.jsonl";
	latest_snapshot: "latest-snapshot.json";
	normalized_fixture_schema: "battle.normalized_ux_fixture.v1";
	proof_mode: string;
	stream_contract: BattleStreamContractV1;
	replay_compression_policy?: Record<string, unknown>;
	source_time_window?: Record<string, unknown>;
	renderer_boundary?: Record<string, unknown>;
};

export type BattleLifecycleEventV1 = {
	schema: "battle.lifecycle_event.v1";
	source_time_seconds: number;
	phase: string;
	importance: string;
	lane_id: string;
	exploit_id: string;
	spawn_type: string;
	outcome_class: string;
	score_delta: Record<string, unknown>;
	receipt_id: string;
	presentation_owner: string;
	proof_mode: string;
};

export type BattleLiveEventV1 = {
	schema: "battle.live_event.v1";
	run_id: string;
	battle_id: string;
	seq: number;
	event_id: string;
	at_seconds: number;
	observed_at: string;
	event_type: string;
	payload: Record<string, unknown>;
	lifecycle: BattleLifecycleEventV1;
};

export type BattleSnapshotV1Full = {
	schema: "battle.snapshot.v1";
	battle_id: string;
	run_id: string;
	last_seq: number;
	generated_at: string;
	mode: "live" | "receipt_replay" | "paused_replay" | "design_fixture" | string;
	clock?: Record<string, unknown> | null;
	battle_clock?: Record<string, unknown> | null;
	round_config?: Record<string, unknown> | null;
	battle_timeline_control?: BattleTimelineControlV1 | Record<string, unknown> | null;
	events: unknown[];
	segments?: unknown[];
	lanes: Lane[];
	lineage?: Record<string, unknown>;
	semantic_replay?: Record<string, unknown>;
	scoreboard?: Record<string, unknown>;
	claims?: Record<string, unknown>;
	validation?: Record<string, unknown>;
	human_interjection_panel?: BattleHumanInterjectionPanelSource;
	replay_compression_policy?: Record<string, unknown>;
	source_time_window?: Record<string, unknown>;
	normalized_fixture_path?: string;
	normalized_fixture_schema?: string;
	renderer_boundary?: Record<string, unknown>;
};

export type BattleTransportPackage = {
	manifest: BattleTransportManifestV1;
	snapshot: BattleSnapshotV1Full;
	events: BattleLiveEventV1[];
	streamBaseUrl: string;
	companionFixtureUrl: string;
};

export type BattleTransportLoadError = {
	code:
		| "UNSUPPORTED_FIXTURE"
		| "TRANSPORT_UNAVAILABLE"
		| "UNSUPPORTED_SCHEMA"
		| "CONTRACT_VALIDATION_FAILED"
		| "SEQUENCE_GAP"
		| "FIXTURE_MISMATCH";
	title: string;
	detail: string;
};

export type BattleTransportStatus =
	| "idle"
	| "loading"
	| "ready"
	| "following"
	| "scrubbing"
	| "gap_recovery"
	| "error"
	| "ended";

export type BattleTransportViewModel = {
	status: BattleTransportStatus;
	battleId: string;
	runId: string;
	mode: string;
	transport: string;
	phase: string;
	mocked: boolean;
	liveSource: string;
	eventCount: number;
	lastSeq: number;
	appliedSeq: number;
	cursorSeconds: number;
	liveSeconds: number;
	followLive: boolean;
	gapExpectedSeq: number | null;
	error: string | null;
	appliedEvents: BattleLiveEventV1[];
};
