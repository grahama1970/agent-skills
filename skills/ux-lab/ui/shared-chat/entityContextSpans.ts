import type { EvidenceCaseSpan } from "./types";

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
	return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function spanPair(value: unknown): [number, number] | null {
	if (!Array.isArray(value) || value.length !== 2) return null;
	const [start, end] = value;
	return typeof start === "number" && typeof end === "number" && end > start ? [start, end] : null;
}

function spanFromExtractEntityNode(value: unknown): EvidenceCaseSpan | null {
	if (!isRecord(value)) return null;
	const extracted = isRecord(value.extracted) ? value.extracted : {};
	const metadata = isRecord(value.metadata) ? value.metadata : {};
	const span = spanPair(value.span) ?? spanPair(extracted.span);
	if (!span) return null;
	const nodeKind = typeof value.node_kind === "string" ? value.node_kind : "";
	const proofRole = typeof value.proof_role === "string" ? value.proof_role : "";
	const kind = extracted.kind ?? value.kind ?? nodeKind ?? metadata.type;
	const framework = metadata.framework ?? value.framework;
	const isDisplayEntity =
		nodeKind === "control" ||
		nodeKind === "control_descriptor" ||
		proofRole === "entity_anchor" ||
		proofRole === "validated_context" ||
		kind === "control_id" ||
		kind === "control_descriptor" ||
		kind === "aerospace_term" ||
		kind === "domain_term" ||
		kind === "countermeasure" ||
		kind === "supplemental_control" ||
		framework === "SPARTA" ||
		metadata.framework === "SPARTA" ||
		value.grounded_to_framework === true;
	if (!isDisplayEntity) return null;
	const grounded =
		metadata.grounded === true ||
		metadata.exists === true ||
		value.grounded === true ||
		value.exists === true ||
		value.status === "grounded" ||
		value.grounded_to_framework === true;
	if (!grounded) return null;
	const text = value.mention ?? value.text ?? value.entity ?? extracted.text ?? metadata.control_id ?? metadata.name;
	const name = metadata.name ?? value.name ?? text;
	return {
		text: typeof text === "string" ? text : undefined,
		span,
		kind: typeof kind === "string" ? kind : undefined,
		framework: typeof framework === "string" ? framework : undefined,
		name: typeof name === "string" ? name : undefined,
		grounded_to_framework: true,
	};
}

function collectExtractEntitySpans(value: unknown): EvidenceCaseSpan[] {
	if (Array.isArray(value))
		return value.map(spanFromExtractEntityNode).filter((span): span is EvidenceCaseSpan => Boolean(span));
	if (!isRecord(value)) return [];

	const spans: EvidenceCaseSpan[] = [];
	for (const key of ["entitySpans", "entity_spans", "spans", "glossary", "entity_nodes"]) {
		spans.push(...collectExtractEntitySpans(value[key]));
	}
	const nodes = isRecord(value.nodes) ? value.nodes : undefined;
	if (nodes) {
		for (const key of ["anchors", "validated_context", "context_terms", "unsupported"]) {
			spans.push(...collectExtractEntitySpans(nodes[key]));
		}
	}
	const packet = isRecord(value.proof_packet) ? value.proof_packet : undefined;
	if (packet) {
		for (const key of ["anchors", "validated_context", "context_terms", "unsupported"]) {
			spans.push(...collectExtractEntitySpans(packet[key]));
		}
	}
	return spans;
}

export function entitySpansFromStructuredContext(content: string, sources: unknown[]): EvidenceCaseSpan[] {
	if (!content) return [];
	const seen = new Set<string>();
	return sources
		.flatMap(collectExtractEntitySpans)
		.map((span) => {
			const pair = spanPair(span.span);
			if (!pair || pair[0] < 0 || pair[1] > content.length) return null;
			const renderedSlice = content.slice(pair[0], pair[1]);
			const expected = [span.text, span.name, span.mention, span.label, span.entity]
				.filter((value): value is string => typeof value === "string" && value.length > 0);
			if (expected.length === 0 || expected.some((value) => value === renderedSlice)) {
				return { ...span, span: pair };
			}
			const repairedText = expected.find((value) => content.includes(value));
			if (!repairedText) return null;
			const start = content.indexOf(repairedText);
			return { ...span, text: span.text ?? repairedText, span: [start, start + repairedText.length] as [number, number] };
		})
		.filter((span): span is EvidenceCaseSpan & { span: [number, number] } => Boolean(span))
		.sort((left, right) => left.span[0] - right.span[0])
		.filter((span) => {
			const key = `${span.span[0]}:${span.span[1]}:${span.text ?? ""}`;
			if (seen.has(key)) return false;
			seen.add(key);
			return true;
		});
}
