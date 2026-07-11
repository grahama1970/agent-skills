export type BattleLiveTransportContractV1 = {
	schema: "battle.live_transport_contract.v1";
	battle_id: string;
	run_id: string;
	status: "CONTRACT_PUBLISHED";
	mocked: false;
	live: "contract_only";
	authority: "backend_receipts_to_normalized_snapshot_and_events_to_renderer";
	generated_at?: string;
	transport: {
		kind: "sse";
		endpoint: string;
		method?: string;
		content_type: "text/event-stream";
		event_schema: "battle.live_event.v1";
		line_format?: {
			id?: string;
			event?: string;
			data?: string;
		};
	};
	initial_snapshot: {
		endpoint: string;
		method?: string;
		schema: "battle.snapshot.v1";
		purpose?: string;
	};
	event_stream: {
		schema: "battle.live_event.v1";
		ordered_by: "seq";
		id_field: "event_id";
		seq_field: "seq";
		receipt_ref_field: "payload.receipt_id";
		immutable_receipt_refs_required?: boolean;
		normalized_event_only?: boolean;
		genetic_event_types_when_live: string[];
		terminal_outcome_rules?: Record<string, string>;
	};
	reconnect: {
		last_event_id_header: string;
		resume_from: string;
		duplicate_policy: string;
		server_may_send_snapshot_required?: boolean;
	};
	gap_semantics: {
		gap_detection: string;
		gap_response: string;
		snapshot_resync_required?: boolean;
		client_must_not_interpolate_missing_events?: boolean;
	};
	raw_path_boundary: {
		frontend_must_not_read: string[];
		transport_must_not_emit: string[];
	};
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
		live_contract_is_not_endpoint_execution?: boolean;
		compile_passed_is_not_runnable?: boolean;
		target_contact_is_not_exploit_success?: boolean;
	};
	frontend_handoff: {
		route: string;
		snapshot_endpoint: string;
		sse_endpoint: string;
		stop_condition?: string;
	};
	source_contracts?: Record<string, string>;
};

export type BattleLiveTransportContractLoadError = {
	code:
		| "UNSUPPORTED_BATTLE"
		| "CONTRACT_UNAVAILABLE"
		| "UNSUPPORTED_SCHEMA"
		| "CONTRACT_VALIDATION_FAILED";
	title: string;
	detail: string;
};

export type BattleLiveTransportContractViewModel = {
	battleId: string;
	runId: string;
	status: string;
	live: "contract_only";
	mocked: false;
	transportKind: "sse";
	sseEndpoint: string;
	snapshotEndpoint: string;
	contentType: string;
	geneticEventTypes: string[];
	geneticEventCount: number;
	mayClaim: string[];
	mustNotClaim: string[];
	reconnectHeader: string;
	gapResponse: string;
	route: string;
	stopCondition: string;
	sseClientArmed: boolean;
	sseClientConnected: boolean;
	endpointExecutionClaimed: false;
};
