import type {
	BattleLiveTransportContractLoadError,
	BattleLiveTransportContractV1,
} from "./battle-live-transport-contract-types";

const REQUIRED_GENETIC = [
	"research_started",
	"research_receipt_materialized",
	"genome_selected",
	"method_added",
	"method_rejected",
	"code_author_started",
	"specimen_materialized",
	"compile_failed",
	"repair_started",
	"repair_materialized",
	"compile_passed",
	"target_contact_unproven",
	"judge_pending",
	"judge_exploit_success",
	"genome_promoted",
	"branch_abandoned",
] as const;

const REQUIRED_MUST_NOT = [
	"sse_endpoint_implemented",
	"websocket_endpoint_implemented",
	"live_stream_executed",
	"live_genetic_events_emitted",
	"exploit_success",
] as const;

function fail(
	code: BattleLiveTransportContractLoadError["code"],
	title: string,
	detail: string,
): BattleLiveTransportContractLoadError {
	return { code, title, detail };
}

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function validateLiveTransportContract(
	data: unknown,
): { ok: true; contract: BattleLiveTransportContractV1 } | { ok: false; error: BattleLiveTransportContractLoadError } {
	const record = asRecord(data);
	if (!record) {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "Contract must be an object.") };
	}
	if (record.schema !== "battle.live_transport_contract.v1") {
		return {
			ok: false,
			error: fail("UNSUPPORTED_SCHEMA", "UNSUPPORTED SCHEMA", "Expected battle.live_transport_contract.v1."),
		};
	}
	if (record.status !== "CONTRACT_PUBLISHED") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "status must be CONTRACT_PUBLISHED."),
		};
	}
	if (record.mocked !== false) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "mocked must be false."),
		};
	}
	if (record.live !== "contract_only") {
		return {
			ok: false,
			error: fail(
				"CONTRACT_VALIDATION_FAILED",
				"CONTRACT VALIDATION FAILED",
				"live must be contract_only until a real SSE endpoint is published.",
			),
		};
	}
	if (record.authority !== "backend_receipts_to_normalized_snapshot_and_events_to_renderer") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "authority mismatch."),
		};
	}

	const transport = asRecord(record.transport);
	if (!transport || transport.kind !== "sse" || transport.content_type !== "text/event-stream") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "transport must be SSE text/event-stream."),
		};
	}
	if (typeof transport.endpoint !== "string" || !transport.endpoint.startsWith("/")) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "transport.endpoint must be an absolute path."),
		};
	}
	if (transport.event_schema !== "battle.live_event.v1") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "transport.event_schema mismatch."),
		};
	}
	const websocket = asRecord(record.websocket);
	if (
		!websocket ||
		websocket.kind !== "websocket" ||
		websocket.event_schema !== "battle.live_event.v1" ||
		websocket.first_message_schema !== "battle.snapshot.v1"
	) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "websocket endpoint shape required."),
		};
	}
	if (typeof websocket.endpoint !== "string" || !websocket.endpoint.startsWith("/")) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "websocket.endpoint must be an absolute path."),
		};
	}

	const snapshot = asRecord(record.initial_snapshot);
	if (!snapshot || snapshot.schema !== "battle.snapshot.v1" || typeof snapshot.endpoint !== "string") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "initial_snapshot endpoint/schema required."),
		};
	}

	const eventStream = asRecord(record.event_stream);
	if (
		!eventStream ||
		eventStream.schema !== "battle.live_event.v1" ||
		eventStream.ordered_by !== "seq" ||
		eventStream.id_field !== "event_id" ||
		eventStream.seq_field !== "seq" ||
		eventStream.receipt_ref_field !== "payload.receipt_id"
	) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "event_stream ordering fields mismatch."),
		};
	}
	const genetic = Array.isArray(eventStream.genetic_event_types_when_live)
		? eventStream.genetic_event_types_when_live.filter((item): item is string => typeof item === "string")
		: [];
	for (const required of REQUIRED_GENETIC) {
		if (!genetic.includes(required)) {
			return {
				ok: false,
				error: fail(
					"CONTRACT_VALIDATION_FAILED",
					"CONTRACT VALIDATION FAILED",
					`genetic_event_types_when_live missing ${required}.`,
				),
			};
		}
	}

	const reconnect = asRecord(record.reconnect);
	if (!reconnect || typeof reconnect.last_event_id_header !== "string" || typeof reconnect.resume_from !== "string") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "reconnect semantics required."),
		};
	}

	const gap = asRecord(record.gap_semantics);
	if (!gap || typeof gap.gap_detection !== "string" || typeof gap.gap_response !== "string") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "gap_semantics required."),
		};
	}

	const claim = asRecord(record.claim_boundary);
	if (!claim) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "claim_boundary required."),
		};
	}
	const mustNot = new Set(
		Array.isArray(claim.must_not_claim) ? claim.must_not_claim.filter((item): item is string => typeof item === "string") : [],
	);
	for (const required of REQUIRED_MUST_NOT) {
		if (!mustNot.has(required)) {
			return {
				ok: false,
				error: fail(
					"CONTRACT_VALIDATION_FAILED",
					"CONTRACT VALIDATION FAILED",
					`claim_boundary.must_not_claim missing ${required}.`,
				),
			};
		}
	}
	if (claim.live_contract_is_not_endpoint_execution !== true) {
		return {
			ok: false,
			error: fail(
				"CONTRACT_VALIDATION_FAILED",
				"CONTRACT VALIDATION FAILED",
				"live_contract_is_not_endpoint_execution must be true.",
			),
		};
	}

	const handoff = asRecord(record.frontend_handoff);
	if (
		!handoff ||
		typeof handoff.route !== "string" ||
		typeof handoff.snapshot_endpoint !== "string" ||
		typeof handoff.sse_endpoint !== "string"
	) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "frontend_handoff route/endpoints required."),
		};
	}

	const raw = asRecord(record.raw_path_boundary);
	const forbidden = [
		...(Array.isArray(raw?.frontend_must_not_read) ? raw!.frontend_must_not_read : []),
		...(Array.isArray(raw?.transport_must_not_emit) ? raw!.transport_must_not_emit : []),
	]
		.filter((item): item is string => typeof item === "string")
		.join("\n");
	for (const fragment of ["tau-dag-run/", "command-loop/command-artifacts"]) {
		if (!forbidden.includes(fragment.replace(/\/$/, "")) && !forbidden.includes(fragment)) {
			// soft: backend lists with /** suffix
			if (!forbidden.includes(fragment.split("/")[0]!)) {
				return {
					ok: false,
					error: fail(
						"CONTRACT_VALIDATION_FAILED",
						"CONTRACT VALIDATION FAILED",
						`raw_path_boundary must forbid ${fragment}.`,
					),
				};
			}
		}
	}

	return { ok: true, contract: record as unknown as BattleLiveTransportContractV1 };
}
