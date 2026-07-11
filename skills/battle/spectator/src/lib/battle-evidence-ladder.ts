/** Educational evidence ladder — never invents Battle truth. */

export type EvidenceLadderRungId =
	| "research"
	| "generated"
	| "compiled"
	| "ran"
	| "target_contact"
	| "judge_verdict";

export type EvidenceLadderRung = {
	id: EvidenceLadderRungId;
	label: string;
	explanation: string;
	status: "present" | "not_emitted" | "unknown";
};

const RING_EVENTS: Record<EvidenceLadderRungId, string[]> = {
	research: ["research_started", "research_receipt_materialized"],
	generated: ["code_author_started", "specimen_materialized", "genome_selected", "method_added"],
	compiled: ["compile_passed", "compile_failed", "repair_materialized"],
	ran: [], // requires runtime receipts — unknown unless present runtime events appear later
	target_contact: ["target_contact_unproven"],
	judge_verdict: ["judge_exploit_success", "judge_pending", "genome_promoted"],
};

export function buildEvidenceLadder(present: string[], notEmitted: string[]): EvidenceLadderRung[] {
	const presentSet = new Set(present);
	const notSet = new Set(notEmitted);
	const rungs: Array<Omit<EvidenceLadderRung, "status"> & { id: EvidenceLadderRungId }> = [
		{
			id: "research",
			label: "RESEARCH",
			explanation: "Sources and questions exist. Research is not exploit success.",
		},
		{
			id: "generated",
			label: "GENERATED",
			explanation: "Generated is not compiled.",
		},
		{
			id: "compiled",
			label: "COMPILED",
			explanation: "Compiled is not runnable.",
		},
		{
			id: "ran",
			label: "RAN",
			explanation: "Runnable is not exploit success.",
		},
		{
			id: "target_contact",
			label: "TARGET CONTACT",
			explanation: "Target contact is not exploit success.",
		},
		{
			id: "judge_verdict",
			label: "JUDGE VERDICT",
			explanation: "Judge determines the outcome.",
		},
	];
	return rungs.map((rung) => {
		const events = RING_EVENTS[rung.id];
		let status: EvidenceLadderRung["status"] = "unknown";
		if (events.some((event) => presentSet.has(event))) status = "present";
		else if (events.length && events.every((event) => notSet.has(event))) status = "not_emitted";
		else if (rung.id === "ran") status = "unknown"; // PR6 composite has no single-run Docker runtime continuity
		else if (events.some((event) => notSet.has(event)) && !events.some((event) => presentSet.has(event))) {
			status = "not_emitted";
		}
		return { ...rung, status };
	});
}
