import type { BattleNormalizedRuntimeJudgeFixtureV1, SpecimenRun } from "./battle-runtime-types";

export type RuntimeRunView = {
	id: string;
	runtimeStatus: string;
	rawStatus: string;
	compileOk: boolean;
	runtimeOk: boolean;
	exitCode: number;
	elapsedSeconds: number | null;
	stdoutLines: string[];
	stderrLines: string[];
	stdoutAvailable: boolean;
	stderrAvailable: boolean;
	targetStatus: string;
	targetObserved: boolean;
	targetEntrypoint: string;
	doesNotProve: string[];
	tone: "red" | "amber" | "green" | "blue" | "gray";
};

export type RuntimeViewModel = {
	fixture: BattleNormalizedRuntimeJudgeFixtureV1;
	headline: string;
	subhead: string;
	statusLabel: string;
	boundaryNotice: string;
	badges: Array<{ id: string; label: string; value: string; tone: "green" | "amber" | "red" | "gray" | "blue" | "purple" }>;
	banners: Array<{ id: string; label: string; tone: "purple" | "gray" | "amber" | "blue" | "red" | "green" }>;
	docker: {
		image: string;
		network: string;
		timeoutSeconds: number;
		user: string;
		capDropAll: boolean;
		noNewPrivileges: boolean;
		commandShape: string[];
	};
	summary: {
		generated: number;
		compileFailed: number;
		runtimeFailed: number;
		runnableUnproven: number;
		targetContactUnproven: number;
		bestSpecimenId: string;
	};
	runs: RuntimeRunView[];
	selectedRunId: string;
	judge: {
		status: string;
		verifiedExploits: number;
		progression: string[];
		doesNotProve: string[];
	};
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
		compilePassedIsNotRunnable: boolean;
		targetContactIsNotExploitSuccess: boolean;
	};
	receipts: BattleNormalizedRuntimeJudgeFixtureV1["receipt_refs"];
};

export function humanizeClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

function runTone(status: string): RuntimeRunView["tone"] {
	const upper = status.toUpperCase();
	if (upper === "COMPILE_FAILED" || upper === "RUNTIME_FAILED") return "red";
	if (upper === "TARGET_CONTACT_UNPROVEN") return "amber";
	if (upper === "RUNNABLE_UNPROVEN") return "blue";
	if (upper.includes("PASS")) return "green";
	return "gray";
}

function toRunView(run: SpecimenRun): RuntimeRunView {
	return {
		id: run.specimen_id,
		runtimeStatus: run.runtime_status,
		rawStatus: run.raw_status ?? run.runtime_status,
		compileOk: run.compile_ok,
		runtimeOk: run.runtime_ok,
		exitCode: run.exit_code,
		elapsedSeconds: typeof run.elapsed_seconds === "number" ? run.elapsed_seconds : null,
		stdoutLines: run.stdout_summary?.lines ?? [],
		stderrLines: run.stderr_summary?.lines ?? [],
		stdoutAvailable: Boolean(run.stdout_summary?.available),
		stderrAvailable: Boolean(run.stderr_summary?.available),
		targetStatus: run.target_contact?.status ?? "NOT_OBSERVED",
		targetObserved: Boolean(run.target_contact?.observed),
		targetEntrypoint: run.target_contact?.entrypoint ?? "not observed",
		doesNotProve: run.does_not_prove ?? [],
		tone: runTone(run.runtime_status),
	};
}

export function buildRuntimeViewModel(fixture: BattleNormalizedRuntimeJudgeFixtureV1): RuntimeViewModel {
	const runs = fixture.runtime.specimen_runs.map(toRunView);
	const bestId = fixture.runtime.summary.best_specimen_id ?? runs[runs.length - 1]?.id ?? "not emitted";
	const hasTargetUnproven = runs.some((run) => run.runtimeStatus === "TARGET_CONTACT_UNPROVEN" || run.targetStatus === "TARGET_CONTACT_UNPROVEN");

	return {
		fixture,
		headline: fixture.copy.headline,
		subhead: fixture.copy.subhead,
		statusLabel: fixture.copy.status_label,
		boundaryNotice:
			fixture.copy.boundary_notice ??
			"Runnable and target contact are not exploit success. Judge replay is required for exploit or Blue outcome claims.",
		badges: [
			{ id: "mocked", label: "MOCKED", value: "NO", tone: "green" },
			{ id: "docker", label: "DOCKER", value: "RECORDED", tone: "purple" },
			{ id: "runtime-failed", label: "RUNTIME FAILED", value: String(fixture.runtime.summary.runtime_failed), tone: "red" },
			{ id: "target-unproven", label: "TARGET CONTACT UNPROVEN", value: String(fixture.runtime.summary.target_contact_unproven), tone: "amber" },
			{ id: "judge", label: "JUDGE", value: "NOT RUN", tone: "gray" },
			{ id: "judge-verified", label: "JUDGE VERIFIED", value: "0", tone: "blue" },
		],
		banners: [
			{ id: "docker-recorded", label: "DOCKER RUNTIME RECORDED", tone: "purple" },
			{ id: "judge-not-run", label: "JUDGE NOT RUN", tone: "gray" },
			{ id: "exploit-not-proven", label: "EXPLOIT SUCCESS NOT PROVEN", tone: "blue" },
			...(hasTargetUnproven
				? [{ id: "target-unproven", label: "TARGET CONTACT UNPROVEN", tone: "amber" as const }]
				: []),
		],
		docker: {
			image: fixture.runtime.docker.image,
			network: fixture.runtime.docker.network,
			timeoutSeconds: fixture.runtime.docker.timeout_seconds,
			user: String(fixture.runtime.docker.user ?? "not emitted"),
			capDropAll: Boolean(fixture.runtime.docker.cap_drop_all),
			noNewPrivileges: Boolean(fixture.runtime.docker.no_new_privileges),
			commandShape: fixture.runtime.docker.command_shape ?? [],
		},
		summary: {
			generated: fixture.runtime.summary.generated_specimens,
			compileFailed: fixture.runtime.summary.compile_failed,
			runtimeFailed: fixture.runtime.summary.runtime_failed,
			runnableUnproven: fixture.runtime.summary.runnable_unproven,
			targetContactUnproven: fixture.runtime.summary.target_contact_unproven,
			bestSpecimenId: String(bestId),
		},
		runs,
		selectedRunId: String(bestId),
		judge: {
			status: fixture.judge.judge_status,
			verifiedExploits: fixture.judge.judge_verified_exploits,
			progression: fixture.judge.judge_progression,
			doesNotProve: fixture.judge.does_not_prove ?? [],
		},
		claimBoundary: {
			mayClaim: fixture.claim_boundary.may_claim.map(humanizeClaimKey),
			mustNotClaim: fixture.claim_boundary.must_not_claim.map(humanizeClaimKey),
			compilePassedIsNotRunnable: fixture.claim_boundary.compile_passed_is_not_runnable === true,
			targetContactIsNotExploitSuccess: fixture.claim_boundary.target_contact_is_not_exploit_success === true,
		},
		receipts: fixture.receipt_refs,
	};
}
