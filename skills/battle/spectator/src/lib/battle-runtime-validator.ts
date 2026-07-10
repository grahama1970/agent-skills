import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./battle.normalized_runtime_judge_fixture.v1.schema.json";
import type { BattleNormalizedRuntimeJudgeFixtureV1, RuntimeLoadError } from "./battle-runtime-types";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateSchema = ajv.compile(schema);

const FORBIDDEN_PATH_FRAGMENTS = [
	"command-loop/command-artifacts",
	"tau-dag-run/",
	"/tmp/",
	"provider-workspace",
	"scillm-worker",
] as const;

export const REQUIRED_MUST_NOT_CLAIM = [
	"exploit_success",
	"judge_success",
	"blue_block",
	"packet_level_behavior",
	"memory_promotion",
] as const;

export const REQUIRED_MAY_CLAIM = [
	"docker_specimen_execution_attempted",
	"runtime_failed",
	"target_contact_unproven",
	"judge_not_run",
] as const;

export function validateRuntimeJudgeFixture(
	data: unknown,
): { ok: true; fixture: BattleNormalizedRuntimeJudgeFixtureV1 } | { ok: false; error: RuntimeLoadError } {
	if (!data || typeof data !== "object") {
		return { ok: false, error: unsupportedSchema("Expected battle.normalized_runtime_judge_fixture.v1.") };
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== "battle.normalized_runtime_judge_fixture.v1") {
		return {
			ok: false,
			error: unsupportedSchema(
				`Expected battle.normalized_runtime_judge_fixture.v1, got ${String(record.schema ?? "missing")}.`,
			),
		};
	}

	const valid = validateSchema(data);
	if (!valid) {
		return {
			ok: false,
			error: {
				code: "CONTRACT_VALIDATION_FAILED",
				title: "CONTRACT VALIDATION FAILED",
				detail: formatAjvErrors(validateSchema.errors),
			},
		};
	}

	const fixture = data as BattleNormalizedRuntimeJudgeFixtureV1;
	const semantic = validateRuntimeJudgeSemantics(fixture);
	if (semantic) return { ok: false, error: semantic };
	return { ok: true, fixture };
}

export function validateRuntimeJudgeSemantics(fixture: BattleNormalizedRuntimeJudgeFixtureV1): RuntimeLoadError | null {
	if (fixture.mocked !== false) return contractFailed("PR4 runtime/Judge requires mocked:false.");
	if (!fixture.runtime?.docker?.image) return contractFailed("runtime.docker.image is required.");
	if (!fixture.runtime?.docker?.network) return contractFailed("runtime.docker.network is required.");
	if (typeof fixture.runtime?.docker?.timeout_seconds !== "number") {
		return contractFailed("runtime.docker.timeout_seconds is required.");
	}
	if (!Array.isArray(fixture.runtime?.specimen_runs) || fixture.runtime.specimen_runs.length < 1) {
		return contractFailed("runtime.specimen_runs must include at least one run.");
	}

	if (fixture.judge?.judge_status !== "NOT_RUN") {
		return contractFailed("PR4 fixture requires judge.judge_status:NOT_RUN until Judge receipts exist.");
	}
	if (fixture.judge?.judge_verified_exploits !== 0) {
		return contractFailed("judge.judge_verified_exploits must be 0.");
	}
	if (!fixture.judge?.judge_progression?.includes("JUDGE_NOT_RUN")) {
		return contractFailed("judge.judge_progression must include JUDGE_NOT_RUN.");
	}

	const mustNot = new Set(fixture.claim_boundary?.must_not_claim ?? []);
	for (const required of REQUIRED_MUST_NOT_CLAIM) {
		if (!mustNot.has(required)) {
			return contractFailed(`claim_boundary.must_not_claim must include ${required}.`);
		}
	}
	const may = new Set(fixture.claim_boundary?.may_claim ?? []);
	for (const required of REQUIRED_MAY_CLAIM) {
		if (!may.has(required)) {
			return contractFailed(`claim_boundary.may_claim must include ${required}.`);
		}
	}
	if (fixture.claim_boundary?.compile_passed_is_not_runnable !== true) {
		return contractFailed("claim_boundary.compile_passed_is_not_runnable must be true.");
	}
	if (fixture.claim_boundary?.target_contact_is_not_exploit_success !== true) {
		return contractFailed("claim_boundary.target_contact_is_not_exploit_success must be true.");
	}

	for (const run of fixture.runtime.specimen_runs) {
		if (run.target_contact?.status === "TARGET_CONTACT_UNPROVEN" && run.target_contact.observed !== true) {
			return contractFailed(`${run.specimen_id}: TARGET_CONTACT_UNPROVEN requires observed:true.`);
		}
		const blob = `${run.runtime_status} ${(run.does_not_prove ?? []).join(" ")}`.toLowerCase();
		if (run.runtime_status === "TARGET_CONTACT_UNPROVEN" && blob.includes("exploit success") === false) {
			// does_not_prove should mention exploit success for honesty
			if (!(run.does_not_prove ?? []).some((item) => /exploit success/i.test(item))) {
				return contractFailed(`${run.specimen_id}: target-contact runs must state exploit success is not proved.`);
			}
		}
	}

	if (fixture.provenance?.raw_paths_redacted !== true) {
		return contractFailed("provenance.raw_paths_redacted must be true.");
	}

	const serialized = JSON.stringify(fixture).toLowerCase();
	for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
		if (serialized.includes(fragment.toLowerCase())) {
			return contractFailed(`Normalized fixture must not contain runtime path fragment: ${fragment}`);
		}
	}

	const copyBlob = `${fixture.copy?.headline ?? ""} ${fixture.copy?.subhead ?? ""} ${fixture.copy?.status_label ?? ""}`.toLowerCase();
	if (copyBlob.includes("exploit success") || copyBlob.includes("judge verified") || copyBlob.includes("blue block")) {
		return contractFailed("copy must not overclaim exploit/Judge/Blue success.");
	}

	return null;
}

function unsupportedSchema(detail: string): RuntimeLoadError {
	return { code: "UNSUPPORTED_SCHEMA", title: "UNSUPPORTED SCHEMA", detail };
}

function contractFailed(detail: string): RuntimeLoadError {
	return { code: "CONTRACT_VALIDATION_FAILED", title: "CONTRACT VALIDATION FAILED", detail };
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
	if (!errors?.length) return "The fixture cannot be rendered safely.";
	return errors
		.slice(0, 4)
		.map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
		.join("; ");
}
