import type {
	BattleKnowledgePacket,
	BattleLaneScoreSemantics,
	BattleMemoryPromotion,
	BattleNetworkSummary,
	BattleTauBranchDecision,
	BattleChildInheritedPlan,
	BattleChildInheritedProbe,
	BattleScoreCalibration,
	BattleSpawnRequest,
	Lane,
	LeaderboardEntry,
	ProofMode,
} from "./battle-types";

export type LaneLifecycleEvidenceView = {
	knowledgePacket: BattleKnowledgePacket;
	memoryPromotion: BattleMemoryPromotion;
	networkSummary: BattleNetworkSummary;
	tauBranchDecision: BattleTauBranchDecision;
	spawnRequest: BattleSpawnRequest;
	childPlan: BattleChildInheritedPlan;
	inheritedProbe: BattleChildInheritedProbe;
	scoreCalibration: BattleScoreCalibration | null;
	scoreSemantics: BattleLaneScoreSemantics | null;
	childAckLabel: string;
	spawnRequestLabel: string;
	childPlanLabel: string;
	inheritedProbeLabel: string;
	packetCaptureLabel: string;
	tauBranchDecisionLabel: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function readFromLaneOrCockpit<T>(lane: Lane, key: string): T | null {
	const laneValue = (lane as Record<string, unknown>)[key];
	if (laneValue) return laneValue as T;
	const cockpitValue = (lane.cockpit as Record<string, unknown> | undefined)?.[key];
	return (cockpitValue as T | undefined) ?? null;
}

export function knowledgePacketForLane(lane: Lane): BattleKnowledgePacket {
	const packet = readFromLaneOrCockpit<BattleKnowledgePacket>(lane, "knowledge_packet");
	if (packet) return packet;
	return {
		present: false,
		status: "absent",
		packet_id: null,
		parent_packet_id: null,
		research_goals: [],
		parent_analysis: {},
		child_ack: { required: false, received: false, ack_source: null },
	};
}

export function memoryPromotionForLane(lane: Lane): BattleMemoryPromotion {
	const promotion = readFromLaneOrCockpit<BattleMemoryPromotion>(lane, "memory_promotion");
	if (promotion) return promotion;
	return {
		present: false,
		candidate_id: null,
		durable_promoted: false,
		validator_required: true,
		reason: "not emitted",
	};
}

export function networkSummaryForLane(lane: Lane): BattleNetworkSummary {
	const direct = readFromLaneOrCockpit<BattleNetworkSummary>(lane, "network_summary");
	if (direct) return direct;
	const observation = asRecord(readFromLaneOrCockpit<unknown>(lane, "observation"));
	const nested = asRecord(observation?.network_summary);
	if (nested) return nested as BattleNetworkSummary;
	return {
		capture_requested: false,
		available: false,
		full_packet_capture_proven: false,
		reason: "not emitted",
		artifact_uri: null,
		sha256: null,
	};
}

export function spawnRequestForLane(lane: Lane): BattleSpawnRequest {
	const request = readFromLaneOrCockpit<BattleSpawnRequest>(lane, "spawn_request");
	if (request) return request;
	return { present: false, claim_authority: "none", child_exploit_id: null, battle_allowed: false, policy_owner: "battle" };
}

export function tauBranchDecisionForLane(lane: Lane): BattleTauBranchDecision {
	const decision = readFromLaneOrCockpit<BattleTauBranchDecision>(lane, "tau_branch_decision");
	if (decision) return decision;
	return {
		present: false,
		schema: "battle.tau_branch_decision.v1",
		decision_authority: "none",
		battle_policy_authority: "battle",
		decision: "none",
		observed_evidence_refs: [],
	};
}

export function childPlanForLane(lane: Lane): BattleChildInheritedPlan {
	const plan = readFromLaneOrCockpit<BattleChildInheritedPlan>(lane, "child_plan");
	if (plan) return plan;
	return { present: false, inherited_item_refs: [], used_before_first_probe: false, scope_inherited: false };
}

export function inheritedProbeForLane(lane: Lane): BattleChildInheritedProbe {
	const probe = readFromLaneOrCockpit<BattleChildInheritedProbe>(lane, "inherited_probe");
	if (probe) return probe;
	return { present: false, used_inherited_state: false, inherited_item_refs: [] };
}

export function scoreSemanticsForLane(lane: Lane): BattleLaneScoreSemantics | null {
	const laneSemantics = (lane as Record<string, unknown>).score_semantics;
	if (laneSemantics && typeof laneSemantics === "object") return laneSemantics as BattleLaneScoreSemantics;
	const cockpitSemantics = lane.cockpit?.score_semantics;
	return cockpitSemantics ?? null;
}

export function scoreCalibrationForLane(lane: Lane): BattleScoreCalibration | null {
	const direct = readFromLaneOrCockpit<BattleScoreCalibration>(lane, "score_calibration");
	if (direct) return direct;
	const semantics = scoreSemanticsForLane(lane);
	return semantics?.score_calibration ?? null;
}

export function packetCaptureLabel(summary: BattleNetworkSummary): string {
	if (summary.available && summary.full_packet_capture_proven) return "packet capture available";
	if (summary.capture_requested && !summary.available) {
		return summary.reason ? `packet capture unavailable: ${summary.reason}` : "packet capture unavailable";
	}
	return "packet capture not emitted";
}

export function childAckLabel(packet: BattleKnowledgePacket): string {
	const ack = packet.child_ack;
	if (!ack?.required) return "child ack not required";
	if (ack.received) return ack.ack_source ? `child ack received (${ack.ack_source})` : "child ack received";
	return "child ack required · not received";
}

export function spawnRequestLabel(request: BattleSpawnRequest): string {
	if (!request.present) return "not emitted";
	const authority = request.claim_authority ?? "unknown authority";
	const decision = request.requested_decision ?? "unknown decision";
	const allowed = request.battle_allowed ? "incorrectly self-approved" : "awaiting Battle policy";
	return `${decision} · ${authority} · ${allowed}`;
}

export function tauBranchDecisionLabel(decision: BattleTauBranchDecision): string {
	if (!decision.present) return "not emitted";
	const choice = decision.decision ?? "unknown";
	const authority = decision.decision_authority ?? "unknown authority";
	const policy = decision.battle_policy_result ?? "not_requested";
	const refs = decision.observed_evidence_refs?.length ?? 0;
	return `${choice} · ${authority} · Battle policy ${policy} · ${refs} refs`;
}

export function childPlanLabel(plan: BattleChildInheritedPlan): string {
	if (!plan.present) return "not emitted";
	const refCount = plan.inherited_item_refs?.length ?? 0;
	if (plan.used_before_first_probe && plan.scope_inherited) return `inherited plan before first probe · ${refCount} refs`;
	return `inherited plan incomplete · ${refCount} refs`;
}

export function inheritedProbeLabel(probe: BattleChildInheritedProbe): string {
	if (!probe.present) return "not emitted";
	const refCount = probe.inherited_item_refs?.length ?? 0;
	if (probe.used_inherited_state) return `used inherited state · ${refCount} refs`;
	return `did not use inherited state · ${refCount} refs`;
}

export function laneLifecycleEvidenceView(lane: Lane): LaneLifecycleEvidenceView {
	const knowledgePacket = knowledgePacketForLane(lane);
	const memoryPromotion = memoryPromotionForLane(lane);
	const networkSummary = networkSummaryForLane(lane);
	const tauBranchDecision = tauBranchDecisionForLane(lane);
	const spawnRequest = spawnRequestForLane(lane);
	const childPlan = childPlanForLane(lane);
	const inheritedProbe = inheritedProbeForLane(lane);
	return {
		knowledgePacket,
		memoryPromotion,
		networkSummary,
		tauBranchDecision,
		spawnRequest,
		childPlan,
		inheritedProbe,
		scoreCalibration: scoreCalibrationForLane(lane),
		scoreSemantics: scoreSemanticsForLane(lane),
		childAckLabel: childAckLabel(knowledgePacket),
		spawnRequestLabel: spawnRequestLabel(spawnRequest),
		childPlanLabel: childPlanLabel(childPlan),
		inheritedProbeLabel: inheritedProbeLabel(inheritedProbe),
		packetCaptureLabel: packetCaptureLabel(networkSummary),
		tauBranchDecisionLabel: tauBranchDecisionLabel(tauBranchDecision),
	};
}

export function receiptBackedTerminalStatus(lane: Lane): LeaderboardEntry["status"] | null {
	if (lane.terminal === "none") return null;
	const provenTerminalEvent = lane.events.some(
		(event) => event.proven && (event.kind === lane.terminal || (lane.terminal === "blocked_handoff" && event.kind === "blocked")),
	);
	const semantics = scoreSemanticsForLane(lane);
	const receiptBacked =
		lane.proofMode === "receipt_backed_fixture" ||
		semantics?.proof_mode === "receipt_backed_fixture" ||
		lane.cockpit?.proof_mode === "receipt_backed_fixture" ||
		provenTerminalEvent;
	if (!receiptBacked) return null;
	if (lane.terminal === "blocked_handoff") return "blocked";
	return lane.terminal;
}

export function terminalStatusCounts(lanes: Lane[]) {
	const counts = {
		running: 0,
		blocked: 0,
		killed: 0,
		promoted: 0,
		fastest_crash: 0,
		survivor: 0,
	};
	for (const lane of lanes) {
		const status = receiptBackedTerminalStatus(lane);
		if (!status) {
			counts.running += 1;
			continue;
		}
		if (status in counts) counts[status as keyof typeof counts] += 1;
	}
	return counts;
}

export function leaderboardEntryForLane(lane: Lane, rank: number): LeaderboardEntry | null {
	const status = receiptBackedTerminalStatus(lane);
	if (!status) return null;
	return {
		rank,
		laneId: lane.id,
		name: lane.name,
		status,
		time: "judge",
		proofMode: (lane.proofMode ?? lane.cockpit?.proof_mode ?? "missing") as ProofMode,
		summary: lane.mutationRationale ?? lane.cockpit?.blue_outcome?.status ?? "receipt-backed terminal",
	};
}
