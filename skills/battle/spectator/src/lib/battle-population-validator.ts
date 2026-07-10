import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./battle.normalized_population_fixture.v1.schema.json";
import type { BattleNormalizedPopulationFixtureV1, PopulationLoadError } from "./battle-population-types";

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
	"full_autonomous_population_engine",
	"live_tau_code_generation",
	"provider_authored_specimens",
	"exploit_success",
	"judge_success",
] as const;

export const REQUIRED_MAY_CLAIM = [
	"multiple_specimens_materialized",
	"generation_metadata_recorded",
	"parent_child_lineage_recorded",
	"judge_not_run",
] as const;

export function validatePopulationFixture(
	data: unknown,
): { ok: true; fixture: BattleNormalizedPopulationFixtureV1 } | { ok: false; error: PopulationLoadError } {
	if (!data || typeof data !== "object") {
		return { ok: false, error: unsupportedSchema("Expected battle.normalized_population_fixture.v1.") };
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== "battle.normalized_population_fixture.v1") {
		return {
			ok: false,
			error: unsupportedSchema(
				`Expected battle.normalized_population_fixture.v1, got ${String(record.schema ?? "missing")}.`,
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

	const fixture = data as BattleNormalizedPopulationFixtureV1;
	const semantic = validatePopulationSemantics(fixture);
	if (semantic) return { ok: false, error: semantic };
	return { ok: true, fixture };
}

export function validatePopulationSemantics(fixture: BattleNormalizedPopulationFixtureV1): PopulationLoadError | null {
	if (fixture.mocked !== false) return contractFailed("PR5 population requires mocked:false.");
	if (fixture.campaign?.full_population_engine_proven !== false) {
		return contractFailed("campaign.full_population_engine_proven must be false.");
	}
	if (!Array.isArray(fixture.specimen_cards) || fixture.specimen_cards.length < 2) {
		return contractFailed("specimen_cards must include multiple specimens.");
	}
	if (!Array.isArray(fixture.generation_axis) || fixture.generation_axis.length < 2) {
		return contractFailed("generation_axis must include multiple generations.");
	}
	if (!Array.isArray(fixture.lineage_edges) || fixture.lineage_edges.length < 1) {
		return contractFailed("lineage_edges must include at least one parent-child edge.");
	}

	for (const card of fixture.specimen_cards) {
		if (card.judge_status !== "NOT_RUN") {
			return contractFailed(`${card.specimen_id}: judge_status must be NOT_RUN for PR5 population.`);
		}
		if (card.judge_verified_exploits !== 0) {
			return contractFailed(`${card.specimen_id}: judge_verified_exploits must be 0.`);
		}
		if (card.fitness?.judge_confirmed_exploit === true) {
			return contractFailed(`${card.specimen_id}: fitness.judge_confirmed_exploit must be false.`);
		}
		if (card.provider_authorship?.provider_live === true) {
			return contractFailed(`${card.specimen_id}: provider_live must be false in this population fixture.`);
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
	if (fixture.claim_boundary?.population_fixture_is_not_full_engine !== true) {
		return contractFailed("claim_boundary.population_fixture_is_not_full_engine must be true.");
	}
	if (fixture.claim_boundary?.target_contact_is_not_exploit_success !== true) {
		return contractFailed("claim_boundary.target_contact_is_not_exploit_success must be true.");
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
	const overclaims =
		(/exploit success/.test(copyBlob) && !/not claimed|not prove|without/.test(copyBlob)) ||
		/full autonomous genetic population engine exists|provider-authored specimen materialized/.test(copyBlob);
	if (overclaims) {
		return contractFailed("copy must not overclaim exploit success, full engine, or provider authorship.");
	}

	return null;
}

function unsupportedSchema(detail: string): PopulationLoadError {
	return { code: "UNSUPPORTED_SCHEMA", title: "UNSUPPORTED SCHEMA", detail };
}

function contractFailed(detail: string): PopulationLoadError {
	return { code: "CONTRACT_VALIDATION_FAILED", title: "CONTRACT VALIDATION FAILED", detail };
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
	if (!errors?.length) return "The fixture cannot be rendered safely.";
	return errors
		.slice(0, 4)
		.map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
		.join("; ");
}
