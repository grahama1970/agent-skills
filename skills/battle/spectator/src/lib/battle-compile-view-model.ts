import { COMPILE_NODE_ORDER, type BattleNormalizedCompileFixtureV1, type SpecimenVersion } from "./battle-compile-types";

export type CompileNodeView = {
	id: string;
	label: string;
	status: string;
	verdict: string;
	treatment: "pass" | "blocked" | "fail" | "missing";
};

export type CompileViewModel = {
	fixture: BattleNormalizedCompileFixtureV1;
	headline: string;
	subhead: string;
	statusLabel: string;
	boundaryNotice: string;
	badges: Array<{ id: string; label: string; value: string; tone: "green" | "amber" | "red" | "gray" | "blue" | "purple" }>;
	banners: Array<{ id: string; label: string; tone: "purple" | "gray" | "amber" | "blue" | "red" | "green" }>;
	nodes: CompileNodeView[];
	compile: {
		status: string;
		verdict: string;
		compiler: string;
		attempted: boolean;
		failed: boolean;
		passed: boolean;
		sourceVersionId: string;
		compiledVersionId: string;
		doesNotProve: string[];
		stderrLines: string[];
		stderrAvailable: boolean;
		stderrRedacted: boolean;
	};
	repair: {
		attempted: boolean;
		exhausted: boolean;
		attemptCount: number;
		providerRepairLive: boolean;
	};
	versions: Array<{
		id: string;
		role: string;
		label: string;
		sha256: string;
		bytes: number;
		compileStatus: string;
		attempted: boolean;
		failed: boolean;
		passed: boolean;
		sourceVersionId: string | null;
		selected: boolean;
	}>;
	selectedVersion: {
		id: string;
		sha256: string;
		compileStatus: string;
		failed: boolean;
		passed: boolean;
	};
	versionDiff: {
		available: boolean;
		fromId: string;
		toId: string;
		sameHash: boolean;
		summary: string;
	};
	executionBoundary: Array<{ id: string; label: string; value: string }>;
	claimBoundary: { mayClaim: string[]; mustNotClaim: string[]; compilePassedIsNotRunnable: boolean };
	receipts: BattleNormalizedCompileFixtureV1["receipt_refs"];
	provider: {
		observedProvider: string;
		observedModel: string;
		authoredBy: string;
		providerLive: boolean;
	};
};

const NODE_LABELS: Record<string, string> = {
	"lineage-summarizer": "Lineage Summarizer",
	"research-scout": "Research Scout",
	"method-combiner": "Method Combiner",
	"exploit-code-author": "Exploit Code Author",
	"compile-repair": "Compile Repair",
};

export function humanizeClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

function versionLabel(version: SpecimenVersion): string {
	return version.code_artifact_label ?? version.version_id;
}

export function buildCompileViewModel(fixture: BattleNormalizedCompileFixtureV1): CompileViewModel {
	const selectedId = fixture.selected_version.version_id;
	const versions = fixture.specimen_versions.map((version) => ({
		id: version.version_id,
		role: version.role,
		label: versionLabel(version),
		sha256: version.code_sha256,
		bytes: version.code_bytes,
		compileStatus: version.compile_status,
		attempted: version.compile_attempted,
		failed: Boolean(version.compile_failed),
		passed: Boolean(version.compile_passed),
		sourceVersionId: version.source_version_id ?? null,
		selected: version.version_id === selectedId,
	}));

	const providerAuthored = versions.find((v) => v.role === "provider_authored") ?? versions[0];
	const selected = versions.find((v) => v.selected) ?? versions[versions.length - 1];
	const sameHash = providerAuthored.sha256 === selected.sha256;

	const compileFailed = fixture.compile.compile_failed;
	const compilePassed = fixture.compile.compile_passed;

	return {
		fixture,
		headline: fixture.copy.headline,
		subhead: fixture.copy.subhead,
		statusLabel: fixture.copy.status_label,
		boundaryNotice:
			fixture.copy.boundary_notice ??
			"Compile status is not runtime proof. Runtime, target contact, and Judge remain NOT_RUN.",
		badges: [
			{ id: "mocked", label: "MOCKED", value: "NO", tone: "green" },
			{ id: "fixture-fallback", label: "FIXTURE FALLBACK", value: "NO", tone: "green" },
			{ id: "provider-live", label: "PROVIDER LIVE", value: "YES", tone: "purple" },
			{
				id: "compile",
				label: "COMPILE",
				value: compilePassed ? "PASSED" : compileFailed ? "FAILED" : fixture.compile.status,
				tone: compilePassed ? "green" : compileFailed ? "red" : "amber",
			},
			{ id: "repair", label: "REPAIR", value: fixture.repair.repair_attempted ? "ATTEMPTED" : "NO", tone: "gray" },
			{ id: "runtime", label: "RUNTIME", value: "NOT RUN", tone: "gray" },
			{ id: "judge-verified", label: "JUDGE VERIFIED", value: "0", tone: "blue" },
		],
		banners: [
			{
				id: "compile-status",
				label: compilePassed ? "COMPILE PASSED" : compileFailed ? "COMPILE FAILED" : `COMPILE ${fixture.compile.status}`,
				tone: compilePassed ? "green" : compileFailed ? "red" : "amber",
			},
			{ id: "not-runnable", label: "NOT RUNNABLE", tone: "gray" },
			{ id: "runtime-not-run", label: "RUNTIME NOT RUN", tone: "gray" },
			{ id: "not-judge-verified", label: "NOT JUDGE VERIFIED", tone: "blue" },
		],
		nodes: COMPILE_NODE_ORDER.map((id) => {
			const status = fixture.node_status[id] ?? "MISSING";
			return {
				id,
				label: NODE_LABELS[id] ?? id,
				status,
				verdict: fixture.node_verdict?.[id] ?? status,
				treatment: status === "PASS" ? "pass" : status === "BLOCKED" ? "blocked" : status === "FAIL" ? "fail" : "missing",
			};
		}),
		compile: {
			status: fixture.compile.status,
			verdict: fixture.compile.verdict ?? fixture.compile.status,
			compiler: fixture.compile.compiler ?? "not emitted",
			attempted: fixture.compile.compile_attempted,
			failed: fixture.compile.compile_failed,
			passed: fixture.compile.compile_passed,
			sourceVersionId: fixture.compile.source_version_id ?? "not emitted",
			compiledVersionId: fixture.compile.compiled_version_id ?? "not emitted",
			doesNotProve: fixture.compile.does_not_prove ?? [],
			stderrLines: fixture.compile.stderr_summary?.lines ?? [],
			stderrAvailable: Boolean(fixture.compile.stderr_summary?.available),
			stderrRedacted: Boolean(fixture.compile.stderr_summary?.redacted),
		},
		repair: {
			attempted: fixture.repair.repair_attempted,
			exhausted: fixture.repair.repair_exhausted,
			attemptCount: fixture.repair.attempt_count ?? 0,
			providerRepairLive: Boolean(fixture.repair.provider_repair_live),
		},
		versions,
		selectedVersion: {
			id: fixture.selected_version.version_id,
			sha256: fixture.selected_version.code_sha256,
			compileStatus: fixture.selected_version.compile_status,
			failed: Boolean(fixture.selected_version.compile_failed),
			passed: Boolean(fixture.selected_version.compile_passed),
		},
		versionDiff: {
			available: Boolean(providerAuthored && selected && providerAuthored.id !== selected.id),
			fromId: providerAuthored?.id ?? "not emitted",
			toId: selected?.id ?? "not emitted",
			sameHash,
			summary: sameHash
				? "Selected compile version shares the provider-authored code hash — no code diff emitted in this fixture."
				: "Version hashes differ. Code diff text was not emitted in the normalized fixture.",
		},
		executionBoundary: [
			{ id: "runtime_status", label: "runtime", value: fixture.execution_boundary.runtime_status },
			{ id: "target_contact", label: "target contact", value: fixture.execution_boundary.target_contact },
			{ id: "judge_status", label: "judge", value: fixture.execution_boundary.judge_status },
			{ id: "packet_behavior", label: "packet behavior", value: fixture.execution_boundary.packet_behavior },
			{ id: "memory_promotion", label: "memory promotion", value: fixture.execution_boundary.memory_promotion },
		],
		claimBoundary: {
			mayClaim: fixture.claim_boundary.may_claim.map(humanizeClaimKey),
			mustNotClaim: fixture.claim_boundary.must_not_claim.map(humanizeClaimKey),
			compilePassedIsNotRunnable: fixture.claim_boundary.compile_passed_is_not_runnable === true,
		},
		receipts: fixture.receipt_refs,
		provider: {
			observedProvider: fixture.provider_authorship.observed_provider,
			observedModel: fixture.provider_authorship.observed_model,
			authoredBy: fixture.provider_authorship.authored_by,
			providerLive: fixture.provider_authorship.provider_live,
		},
	};
}
