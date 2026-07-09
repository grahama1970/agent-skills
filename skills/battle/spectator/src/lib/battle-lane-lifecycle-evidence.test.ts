import { describe, expect, it } from "vitest";
import {
	childPlanForLane,
	inheritedProbeForLane,
	knowledgePacketForLane,
	laneLifecycleEvidenceView,
	networkSummaryForLane,
	packetCaptureLabel,
	receiptBackedTerminalStatus,
	spawnRequestForLane,
	tauBranchDecisionForLane,
	terminalStatusCounts,
} from "./battle-lane-lifecycle-evidence";
import type { Lane } from "./battle-types";

function lane(overrides: Partial<Lane> = {}): Lane {
	return {
		id: "payload-857-red-1",
		name: "red-1",
		payloadId: "payload-857-red-1",
		generation: 2,
		team: "red",
		xStart: 0,
		xEnd: 100,
		runnerX: 50,
		runnerState: "blocked",
		lineColor: "red",
		terminal: "blocked",
		events: [{ id: "judge", kind: "blocked", x: 80, label: "BLOCK", proven: true }],
		proofMode: "receipt_backed_fixture",
		score_semantics: {
			schema: "battle.semantic_scoring.v1",
			terminal_state: "blocked",
			outcome_class: "post_spawn_child_contained",
			proof_mode: "receipt_backed_fixture",
		},
		...overrides,
	};
}

describe("battle-lane-lifecycle-evidence", () => {
	it("fails closed when packet capture is unavailable", () => {
		const summary = networkSummaryForLane(
			lane({
				network_summary: {
					capture_requested: true,
					available: false,
					full_packet_capture_proven: false,
					reason: "packet_capture_artifact_missing",
				},
			}),
		);
		expect(packetCaptureLabel(summary)).toContain("packet capture unavailable");
	});

	it("counts only receipt-backed terminal lanes", () => {
		const counts = terminalStatusCounts([
			lane(),
			lane({ id: "payload-857-receipt", terminal: "none", events: [], score_semantics: undefined, proofMode: undefined }),
			lane({ id: "payload-857", terminal: "killed", events: [], proofMode: undefined, score_semantics: undefined, cockpit: undefined }),
		]);
		expect(counts.blocked).toBe(1);
		expect(counts.killed).toBe(0);
		expect(counts.running).toBe(2);
		expect(receiptBackedTerminalStatus(lane())).toBe("blocked");
	});

	it("defaults knowledge packet to absent", () => {
		expect(knowledgePacketForLane(lane()).present).toBe(false);
	});

	it("surfaces live lifecycle spine fields for spawn inheritance", () => {
		const view = laneLifecycleEvidenceView(
			lane({
				spawn_request: {
					present: true,
					claim_authority: "tau_claim_only",
					requested_decision: "strategic_pre_kill",
					child_exploit_id: "payload-857-red-1",
					battle_allowed: false,
					policy_owner: "battle",
				},
				tau_branch_decision: {
					present: true,
					schema: "battle.tau_branch_decision.v1",
					decision_authority: "tau_subagent",
					battle_policy_authority: "battle",
					decision: "spawn_requested",
					observed_evidence_refs: ["probe", "drift", "threat"],
					rationale: "survive pressure",
					confidence: "medium",
					requested_child_profile: { child_exploit_id: "payload-857-red-1" },
					inherited_goals: ["inherit parent context"],
					battle_policy_result: "pending",
				},
				child_plan: {
					present: true,
					plan_id: "child-plan",
					knowledge_packet_id: "knowledge:parent",
					inherited_item_refs: ["knowledge:parent", "lineage"],
					used_before_first_probe: true,
					scope_inherited: true,
				},
				inherited_probe: {
					present: true,
					probe_id: "probe",
					child_plan_id: "child-plan",
					knowledge_packet_id: "knowledge:parent",
					used_inherited_state: true,
					inherited_item_refs: ["knowledge:parent"],
				},
			}),
		);
		expect(view.tauBranchDecisionLabel).toContain("spawn_requested");
		expect(view.tauBranchDecisionLabel).toContain("tau_subagent");
		expect(view.tauBranchDecisionLabel).toContain("Battle policy pending");
		expect(view.spawnRequestLabel).toContain("tau_claim_only");
		expect(view.spawnRequestLabel).toContain("awaiting Battle policy");
		expect(view.childPlanLabel).toContain("inherited plan before first probe");
		expect(view.inheritedProbeLabel).toContain("used inherited state");
	});

	it("fails closed when live lifecycle spine fields are absent", () => {
		const subject = lane();
		expect(spawnRequestForLane(subject).present).toBe(false);
		expect(tauBranchDecisionForLane(subject).present).toBe(false);
		expect(childPlanForLane(subject).present).toBe(false);
		expect(inheritedProbeForLane(subject).present).toBe(false);
	});
});
