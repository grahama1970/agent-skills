import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./battle.normalized_compile_fixture.v1.schema.json";
import { COMPILE_NODE_ORDER, type BattleNormalizedCompileFixtureV1, type CompileLoadError } from "./battle-compile-types";

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
	"runnable",
	"runtime_success",
	"target_contact",
	"exploit_success",
	"judge_success",
] as const;

export const REQUIRED_MAY_CLAIM = [
	"compile_attempted",
	"compile_failed",
	"compile_passed",
	"repair_attempted",
	"specimen_version_hashes",
] as const;

export function validateCompileFixture(
	data: unknown,
): { ok: true; fixture: BattleNormalizedCompileFixtureV1 } | { ok: false; error: CompileLoadError } {
	if (!data || typeof data !== "object") {
		return { ok: false, error: unsupportedSchema("Expected battle.normalized_compile_fixture.v1.") };
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== "battle.normalized_compile_fixture.v1") {
		return {
			ok: false,
			error: unsupportedSchema(`Expected battle.normalized_compile_fixture.v1, got ${String(record.schema ?? "missing")}.`),
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

	const fixture = data as BattleNormalizedCompileFixtureV1;
	const semantic = validateCompileSemantics(fixture);
	if (semantic) return { ok: false, error: semantic };
	return { ok: true, fixture };
}

export function validateCompileSemantics(fixture: BattleNormalizedCompileFixtureV1): CompileLoadError | null {
	if (fixture.provider_live !== true) {
		return contractFailed("PR3d compile requires provider_live:true.");
	}
	if (fixture.fixture_fallback_used !== false) {
		return contractFailed("PR3d compile forbids fixture_fallback_used.");
	}
	if (fixture.mocked !== false) {
		return contractFailed("PR3d compile requires mocked:false.");
	}
	if (!Array.isArray(fixture.specimen_versions) || fixture.specimen_versions.length < 2) {
		return contractFailed("specimen_versions must include at least provider-authored and compile-selected versions.");
	}

	for (const nodeId of COMPILE_NODE_ORDER) {
		if (!fixture.node_status?.[nodeId]) {
			return contractFailed(`node_status.${nodeId} is required.`);
		}
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

	const boundary = fixture.execution_boundary;
	for (const key of ["runtime_status", "target_contact", "judge_status"] as const) {
		if (boundary?.[key] !== "NOT_RUN") {
			return contractFailed(`execution_boundary.${key} must be NOT_RUN for PR3d compile.`);
		}
	}
	if (boundary?.judge_verified_exploits !== 0) {
		return contractFailed("execution_boundary.judge_verified_exploits must be 0.");
	}

	if (fixture.compile?.compile_passed === true && mustNot.has("runnable") === false) {
		return contractFailed("compile_passed fixtures must still forbid runnable claims.");
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
	if (copyBlob.includes("runnable") || copyBlob.includes("exploit success") || copyBlob.includes("judge verified")) {
		return contractFailed("copy must not overclaim runnable/runtime/Judge success.");
	}
	if (fixture.compile?.compile_passed && copyBlob.includes("runnable")) {
		return contractFailed("compile passed must not be labeled runnable.");
	}

	return null;
}

function unsupportedSchema(detail: string): CompileLoadError {
	return { code: "UNSUPPORTED_SCHEMA", title: "UNSUPPORTED SCHEMA", detail };
}

function contractFailed(detail: string): CompileLoadError {
	return { code: "CONTRACT_VALIDATION_FAILED", title: "CONTRACT VALIDATION FAILED", detail };
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
	if (!errors?.length) return "The fixture cannot be rendered safely.";
	return errors
		.slice(0, 4)
		.map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
		.join("; ");
}
