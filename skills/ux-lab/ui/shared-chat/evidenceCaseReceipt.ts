/**
 * Pure helpers for the Embry Console evidence receipt card (lean-in).
 * Full adjudication lives in EvidenceWorkspace — this module only shapes the compact receipt.
 */
import type { Artifact, EvidenceCaseData } from "./types";

export function normalizeVerdictLabel(verdict: string | undefined): string {
	const raw = String(verdict ?? "pending")
		.toUpperCase()
		.replace(/-/g, "_");
	if (raw === "PASS" || raw === "PASSED" || raw === "SATISFIED") return "SATISFIED";
	if (raw === "FAIL" || raw === "FAILED" || raw === "NOT_SATISFIED") return "NOT SATISFIED";
	if (raw === "INCONCLUSIVE" || raw === "PENDING") return "INCONCLUSIVE";
	return raw.replace(/_/g, " ");
}

export function normalizeResponseAction(action: string | undefined): string {
	const raw = String(action ?? "clarify").toUpperCase();
	if (raw === "ANSWER" || raw === "DEFLECT" || raw === "CLARIFY") return raw;
	return raw.replace(/_/g, " ");
}

export function deriveReceiptStateLine(data: EvidenceCaseData): string {
	return `${normalizeVerdictLabel(data.verdict)} · ${normalizeResponseAction(data.response_action)}`;
}

export function deriveReceiptReason(data: EvidenceCaseData): string {
	const explicit = (data as EvidenceCaseData & { blocker_reason?: string }).blocker_reason;
	if (explicit?.trim()) return explicit.trim().replace(/\.$/, "");

	const gates = data.gate_trace ?? data.metadata?.gate_trace ?? [];
	const failed = gates.find((g) => !g.passed);
	if (failed?.gate) {
		const gate = failed.gate.toLowerCase();
		if (gate.includes("provenance")) return "source-page provenance missing";
		if (gate.includes("approval") || gate.includes("reviewer")) return "reviewer approval pending";
		if (failed.detail) return failed.detail.replace(/\.$/, "").toLowerCase();
		return `${failed.gate} incomplete`;
	}

	const approval = String(data.human_review_state ?? data.approval_state ?? "").toLowerCase();
	if (approval && approval !== "approved") return "reviewer approval pending";

	const hash = String(data.artifact_hash ?? data.artifact?.sha256 ?? "");
	if (/mock|demo|pending/i.test(hash)) return "source-page provenance missing";

	if (data.gates_total > 0 && data.gates_passed < data.gates_total) {
		return "evidence gates incomplete";
	}

	return "evidence trace incomplete";
}

export function deriveArtifactStateLine(data: EvidenceCaseData): string {
	const name = data.artifact?.name || data.bound_artifact;
	if (!name || name === "Artifact pending") return "none bound";

	const hash = String(data.artifact_hash ?? data.artifact?.sha256 ?? "");
	const trace = String(data.trace_state ?? "").toLowerCase();
	const approval = String(data.human_review_state ?? data.approval_state ?? "").toLowerCase();

	if (/mock|demo/i.test(hash)) return `${name} · provenance pending`;
	if (trace === "bound" && approval === "approved") return `${name} · bound`;
	if (approval && approval !== "approved") return `${name} · review pending`;
	if (trace === "bound") return `${name} · bound`;
	return `${name} · provenance pending`;
}

export type ReceiptRailTone = "satisfied" | "blocked" | "pending";

export function deriveReceiptRailTone(data: EvidenceCaseData): ReceiptRailTone {
	const verdict = normalizeVerdictLabel(data.verdict);
	const action = normalizeResponseAction(data.response_action);
	if (verdict === "SATISFIED" && action === "ANSWER") return "satisfied";
	if (action === "DEFLECT" || verdict === "NOT SATISFIED") return "blocked";
	return "pending";
}

export function receiptShowsDraftToken(data: EvidenceCaseData): boolean {
	const approval = String(data.human_review_state ?? data.approval_state ?? "").toLowerCase();
	if (!approval || approval === "approved") return false;
	const verdict = normalizeVerdictLabel(data.verdict);
	const action = normalizeResponseAction(data.response_action);
	return !(verdict === "SATISFIED" && action === "ANSWER");
}

export function deriveReceiptSummary(data: EvidenceCaseData): string | null {
	const claims = data.claims ?? [];
	if (claims.length >= 2 && /mock|provenance|audit/i.test(claims[1])) {
		return "FPGA vendor risk found, but source proof is not audit-valid.";
	}
	const first = claims[0]?.trim();
	if (!first || first.length > 120) return null;
	return first.endsWith(".") ? first.slice(0, -1) : first;
}

export type ChatDistanceMode = "10ft" | "5ft" | "lean-in";

export function isReceiptChatMode(mode?: ChatDistanceMode): boolean {
	return mode === "5ft" || mode === "lean-in";
}

export function boundArtifactKey(data?: EvidenceCaseData): string | null {
	const name = data?.artifact?.name || data?.bound_artifact;
	if (!name || name === "Artifact pending") return null;
	return name.toLowerCase();
}

export function artifactDuplicatesBoundArtifact(artifact: Artifact, boundKey: string | null): boolean {
	if (!boundKey) return false;
	const title = String(artifact.title ?? "").toLowerCase();
	const id = String(artifact.id ?? "").toLowerCase();
	if (title === boundKey) return true;
	const boundStem = boundKey.replace(/\.[^.]+$/, "");
	if (
		(artifact.type === "pdf" || artifact.type === "document") &&
		(title.includes(boundStem) || id.includes(boundStem))
	) {
		return true;
	}
	return false;
}

export function distinctChatArtifacts(
	evidenceCase: EvidenceCaseData | undefined,
	artifacts: Artifact[] | undefined,
): Artifact[] {
	if (!artifacts?.length) return [];
	const boundKey = boundArtifactKey(evidenceCase);
	return artifacts.filter((artifact) => !artifactDuplicatesBoundArtifact(artifact, boundKey));
}

export function provenanceTagsFromArtifacts(artifacts: Artifact[] | undefined): string[] {
	if (!artifacts?.length) return [];
	const tags = new Set<string>();
	for (const artifact of artifacts) {
		const state = artifact.provenanceState ?? (artifact.sampleDerived ? "sample-derived" : undefined);
		if (state && state !== "bound") tags.add(state);
	}
	return [...tags];
}

export type EvidenceTierBadge = "informational" | "grounded" | "verified";

export function deriveEvidenceTierBadge(data: EvidenceCaseData): EvidenceTierBadge {
	const tier = String(data.tier ?? "").toLowerCase();
	const verdict = normalizeVerdictLabel(data.verdict);
	const approval = String(data.human_review_state ?? data.approval_state ?? "").toLowerCase();
	const trace = String(data.trace_state ?? "").toLowerCase();
	const gatesComplete = data.gates_total > 0 && data.gates_passed >= data.gates_total;

	if (verdict === "SATISFIED" && gatesComplete && trace === "bound" && approval === "approved") {
		return "verified";
	}
	if (tier === "t2" || tier.includes("llm")) {
		return "informational";
	}
	return "grounded";
}

export function evidenceTierBadgeTone(badge: EvidenceTierBadge): { color: string; bg: string; border: string } {
	switch (badge) {
		case "verified":
			return { color: "#00ff88", bg: "rgba(0,255,136,0.12)", border: "rgba(0,255,136,0.35)" };
		case "informational":
			return { color: "#ffaa00", bg: "rgba(255,170,0,0.12)", border: "rgba(255,170,0,0.35)" };
		default:
			return { color: "#4a9eff", bg: "rgba(74,158,255,0.12)", border: "rgba(74,158,255,0.35)" };
	}
}
