import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./battle.normalized_synthesis_fixture.v1.schema.json";
import { SYNTHESIS_NODE_ORDER, type BattleNormalizedSynthesisFixtureV1, type SynthesisLoadError } from "./battle-synthesis-types";

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

export const REQUIRED_PR3C_NODE_STATUS: Record<(typeof SYNTHESIS_NODE_ORDER)[number], string> = {
	"lineage-summarizer": "PASS",
	"research-scout": "PASS",
	"method-combiner": "PASS",
	"exploit-code-author": "PASS",
};

export const REQUIRED_MUST_NOT_CLAIM = [
	"compiled",
	"compile_passed",
	"runnable",
	"runtime_success",
	"target_contact",
	"exploit_success",
	"judge_success",
] as const;

export function validateSynthesisFixture(
	data: unknown,
): { ok: true; fixture: BattleNormalizedSynthesisFixtureV1 } | { ok: false; error: SynthesisLoadError } {
	if (!data || typeof data !== "object") {
		return { ok: false, error: unsupportedSchema("Expected battle.normalized_synthesis_fixture.v1.") };
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== "battle.normalized_synthesis_fixture.v1") {
		return {
			ok: false,
			error: unsupportedSchema(`Expected battle.normalized_synthesis_fixture.v1, got ${String(record.schema ?? "missing")}.`),
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

	const fixture = data as BattleNormalizedSynthesisFixtureV1;
	const semantic = validateSynthesisSemantics(fixture);
	if (semantic) return { ok: false, error: semantic };
	return { ok: true, fixture };
}

export function validateSynthesisSemantics(fixture: BattleNormalizedSynthesisFixtureV1): SynthesisLoadError | null {
	if (fixture.provider_live !== true) {
		return contractFailed("PR3c synthesis requires provider_live:true.");
	}
	if (fixture.fixture_fallback_used !== false) {
		return contractFailed("PR3c synthesis forbids fixture_fallback_used.");
	}
	if (fixture.mocked !== false) {
		return contractFailed("PR3c synthesis requires mocked:false.");
	}
	if (!fixture.provider_authorship?.provider_live) {
		return contractFailed("provider_authorship.provider_live must be true.");
	}

	for (const [nodeId, expected] of Object.entries(REQUIRED_PR3C_NODE_STATUS)) {
		const actual = fixture.node_status?.[nodeId];
		if (actual !== expected) {
			return contractFailed(`node_status.${nodeId} must be ${expected}, got ${String(actual ?? "missing")}.`);
		}
	}

	const mustNot = new Set(fixture.claim_boundary?.must_not_claim ?? []);
	for (const required of REQUIRED_MUST_NOT_CLAIM) {
		if (!mustNot.has(required)) {
			return contractFailed(`claim_boundary.must_not_claim must include ${required}.`);
		}
	}

	const boundary = fixture.execution_boundary;
	for (const key of ["compile_status", "runtime_status", "target_contact", "judge_status"] as const) {
		if (boundary?.[key] !== "NOT_RUN") {
			return contractFailed(`execution_boundary.${key} must be NOT_RUN for PR3c synthesis.`);
		}
	}
	if (boundary?.judge_verified_exploits !== 0) {
		return contractFailed("execution_boundary.judge_verified_exploits must be 0.");
	}

	if (!fixture.specimen?.code_preview?.available || !Array.isArray(fixture.specimen.code_preview.lines)) {
		return contractFailed("specimen.code_preview.lines must be available.");
	}

	const serialized = JSON.stringify(fixture).toLowerCase();
	for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
		if (serialized.includes(fragment.toLowerCase())) {
			return contractFailed(`Normalized fixture must not contain runtime path fragment: ${fragment}`);
		}
	}

	const copyBlob = `${fixture.copy?.headline ?? ""} ${fixture.copy?.subhead ?? ""}`.toLowerCase();
	if (copyBlob.includes("compile passed") || copyBlob.includes("exploit success") || copyBlob.includes("judge verified")) {
		return contractFailed("copy must not overclaim compile/runtime/Judge success.");
	}

	return null;
}

function unsupportedSchema(detail: string): SynthesisLoadError {
	return { code: "UNSUPPORTED_SCHEMA", title: "UNSUPPORTED SCHEMA", detail };
}

function contractFailed(detail: string): SynthesisLoadError {
	return { code: "CONTRACT_VALIDATION_FAILED", title: "CONTRACT VALIDATION FAILED", detail };
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
	if (!errors?.length) return "The fixture cannot be rendered safely.";
	return errors
		.slice(0, 4)
		.map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
		.join("; ");
}
