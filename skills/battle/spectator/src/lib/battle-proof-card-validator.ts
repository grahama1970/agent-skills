import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./battle.normalized_proof_card_fixture.v1.schema.json";
import { PROOF_CARD_NODE_ORDER, type BattleNormalizedProofCardFixtureV1, type ProofCardLoadError } from "./battle-proof-card-types";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateSchema = ajv.compile(schema);

const FORBIDDEN_PATH_FRAGMENTS = [
	"command-loop/command-artifacts",
	"tau-dag-run/",
	"/tmp/",
	"provider session",
	"docker workspaces",
] as const;

/** Required PR3b node statuses — semantic, not expressible by JSON Schema alone. */
export const REQUIRED_PR3B_NODE_STATUS: Record<(typeof PROOF_CARD_NODE_ORDER)[number], string> = {
	"lineage-summarizer": "PASS",
	"research-scout": "PASS",
	"method-combiner": "PASS",
	"exploit-code-author": "BLOCKED",
};

/** Required must-not-claim keys for honest PR3b proof-card rendering. */
export const REQUIRED_MUST_NOT_CLAIM = [
	"child_exploit_generated",
	"child_exploit_compiled",
	"child_exploit_runnable",
	"exploit_success",
] as const;

export function proofCardSchemaError(data: unknown): ProofCardLoadError | null {
	if (!data || typeof data !== "object") {
		return {
			code: "UNSUPPORTED_SCHEMA",
			title: "UNSUPPORTED SCHEMA",
			detail: "Expected battle.normalized_proof_card_fixture.v1.",
		};
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== "battle.normalized_proof_card_fixture.v1") {
		return {
			code: "UNSUPPORTED_SCHEMA",
			title: "UNSUPPORTED SCHEMA",
			detail: `Expected battle.normalized_proof_card_fixture.v1, got ${String(record.schema ?? "missing")}.`,
		};
	}
	return null;
}

export function validateProofCardFixture(
	data: unknown,
): { ok: true; fixture: BattleNormalizedProofCardFixtureV1 } | { ok: false; error: ProofCardLoadError } {
	const schemaError = proofCardSchemaError(data);
	if (schemaError) return { ok: false, error: schemaError };

	const valid = validateSchema(data);
	if (!valid) {
		const detail = formatAjvErrors(validateSchema.errors);
		return {
			ok: false,
			error: {
				code: "CONTRACT_VALIDATION_FAILED",
				title: "CONTRACT VALIDATION FAILED",
				detail: detail || "The fixture cannot be rendered safely.",
			},
		};
	}

	const fixture = data as BattleNormalizedProofCardFixtureV1;
	const semanticError = validateProofCardSemantics(fixture);
	if (semanticError) return { ok: false, error: semanticError };

	return { ok: true, fixture };
}

/** Semantic guards beyond JSON Schema: node statuses, claim boundary, Tau path exclusion, execution honesty. */
export function validateProofCardSemantics(fixture: BattleNormalizedProofCardFixtureV1): ProofCardLoadError | null {
	if (!Array.isArray(fixture.claim_boundary?.may_claim) || !Array.isArray(fixture.claim_boundary?.must_not_claim)) {
		return contractFailed("claim_boundary.may_claim and must_not_claim are required.");
	}

	for (const [nodeId, expected] of Object.entries(REQUIRED_PR3B_NODE_STATUS)) {
		const actual = fixture.node_status?.[nodeId];
		if (actual !== expected) {
			return contractFailed(`node_status.${nodeId} must be ${expected}, got ${String(actual ?? "missing")}.`);
		}
	}

	const mustNot = new Set(fixture.claim_boundary.must_not_claim);
	for (const required of REQUIRED_MUST_NOT_CLAIM) {
		if (!mustNot.has(required)) {
			return contractFailed(`claim_boundary.must_not_claim must include ${required}.`);
		}
	}

	const research = fixture.artifacts?.child_research_receipts;
	const methods = fixture.artifacts?.child_candidate_methods;
	const genome = fixture.artifacts?.child_exploit_genome;

	if (research?.query?.external_tool_called === true) {
		return contractFailed("PR3b proof-card requires external_tool_called:false (manual/source-validated research only).");
	}
	if (research?.provider_live === true || methods?.provider_live === true || genome?.provider_live === true) {
		return contractFailed("PR3b proof-card requires provider_live:false until PR3c provider authorship exists.");
	}
	if (genome?.agentic === true) {
		return contractFailed("PR3b genome must remain non-agentic (deterministic combiner, not model authorship).");
	}

	const serialized = JSON.stringify(fixture).toLowerCase();
	for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
		if (serialized.includes(fragment.toLowerCase())) {
			return contractFailed(`Normalized fixture must not contain Tau runtime path fragment: ${fragment}`);
		}
	}

	// Soft honesty: headline/copy must not claim exploit code was generated.
	const copyBlob = `${fixture.copy?.headline ?? ""} ${fixture.copy?.subhead ?? ""} ${fixture.copy?.status_label ?? ""}`.toLowerCase();
	if (copyBlob.includes("exploit code generated") || copyBlob.includes("child exploit generated")) {
		return contractFailed("copy must not claim exploit code was generated.");
	}

	return null;
}

function contractFailed(detail: string): ProofCardLoadError {
	return {
		code: "CONTRACT_VALIDATION_FAILED",
		title: "CONTRACT VALIDATION FAILED",
		detail,
	};
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
	if (!errors?.length) return "The fixture cannot be rendered safely.";
	return errors
		.slice(0, 4)
		.map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
		.join("; ");
}
