export type FamilyId =
	| "toc"
	| "section_heading"
	| "section_subtitle"
	| "section_label"
	| "list"
	| "paragraph_block"
	| "labeled_paragraph"
	| "labeled_controls"
	| "labeled_references"
	| "table"
	| "figure"
	| "caption"
	| "footnote"
	| "page_chrome_noise"
	| "human_decision";

export type BreadcrumbNodeKind =
	| "document"
	| "chapter"
	| "section"
	| "subsection"
	| "control_family"
	| "control"
	| "enhancement"
	| "local_role"
	| "unknown";

export interface BreadcrumbNode {
	level: number;
	kind: BreadcrumbNodeKind;
	label: string;
	id?: string;
	node_id?: string;
	parent_node_id?: string;
	source?:
		| "toc"
		| "outline"
		| "structure_tree"
		| "section_hierarchy"
		| "section_anchor"
		| "reverse_scan"
		| "preset"
		| "agent_second_pass"
		| "human";
	editable?: boolean;
	page?: number;
}

export interface ExportableRegion {
	family: FamilyId;
	bbox: [number, number, number, number];
	label?: string;
	text_hint?: string;
	lead_label?: string;
	breadcrumb?: string[];
	breadcrumb_nodes?: BreadcrumbNode[];
	notes?: string;
	semantic_role?: string;
	target_page?: number;
	dot_leader?: boolean;
	toc_title?: string;
	toc_entries?: TocEntry[];
}

export interface TocEntry {
	id: string;
	title: string;
	target_page: number;
	level: number;
	source_id?: string;
	bbox_hint?: [number, number, number, number];
	verification?: {
		status: "matched" | "mismatch" | "unchecked";
		expected_pdf_page_index?: number;
		matched_pdf_page_index?: number;
		method?: string;
	};
	children?: TocEntry[];
}

export interface ExpectedElement {
	family: FamilyId;
	bbox_hint: [number, number, number, number];
	label?: string | null;
	text_hint?: string;
	lead_label?: string;
	breadcrumb?: string[];
	breadcrumb_nodes?: BreadcrumbNode[];
	notes?: string;
	allowed_types?: string[];
	match_strategy?: string;
	desired_role?: string;
	desired_lead_label?: string;
	semantic_role?: string;
	target_page?: number;
	dot_leader?: boolean;
	toc_title?: string;
	toc_entries?: TocEntry[];
}

export const BREADCRUMB_NODE_KINDS: BreadcrumbNodeKind[] = [
	"document",
	"chapter",
	"section",
	"subsection",
	"control_family",
	"control",
	"enhancement",
	"local_role",
	"unknown",
];

const DEFAULT_ALLOWED_TYPES: Record<FamilyId, string[]> = {
	toc: ["toc", "TableOfContents"],
	section_heading: ["section_heading"],
	section_subtitle: ["section_subtitle", "section_heading", "paragraph_block"],
	section_label: ["section_label", "content_label", "paragraph_block"],
	list: ["list"],
	paragraph_block: ["paragraph_block"],
	labeled_paragraph: ["paragraph_block"],
	labeled_controls: ["labeled_controls", "paragraph_block"],
	labeled_references: ["labeled_references", "paragraph_block"],
	table: ["table"],
	figure: ["figure"],
	caption: ["caption"],
	footnote: ["footnote_block", "paragraph_block"],
	page_chrome_noise: ["header_footer_noise"],
	human_decision: [],
};

export function parseBreadcrumb(value: unknown): string[] | undefined {
	if (Array.isArray(value)) {
		const parts = value.map((part) => String(part).trim()).filter(Boolean);
		return parts.length ? parts : undefined;
	}
	if (typeof value === "string") {
		const separator = ["›", ">", "/", "|"].find((s) => value.includes(s));
		const parts = (separator ? value.split(separator) : [value]).map((part) => part.trim()).filter(Boolean);
		return parts.length ? parts : undefined;
	}
	return undefined;
}

export function formatBreadcrumb(value: string[] | undefined): string {
	return value?.join(" › ") ?? "";
}

function isBreadcrumbNodeKind(value: unknown): value is BreadcrumbNodeKind {
	return typeof value === "string" && BREADCRUMB_NODE_KINDS.includes(value as BreadcrumbNodeKind);
}

function inferBreadcrumbNodeKind(label: string, level: number): BreadcrumbNodeKind {
	if (/^[A-Z]{2}-\d+\s/.test(label)) return "control";
	if (/^\(\d+\)/.test(label)) return "enhancement";
	if (/^chapter\b/i.test(label)) return "chapter";
	if (level === 1 && /nist|pdf|document/i.test(label)) return "document";
	if (level === 1) return "section";
	if (level === 2) return "subsection";
	return "local_role";
}

export function normalizeBreadcrumbNodes(value: unknown, fallback?: string[]): BreadcrumbNode[] | undefined {
	if (Array.isArray(value)) {
		const nodes: BreadcrumbNode[] = [];
		value.forEach((rawNode, index) => {
			if (!rawNode || typeof rawNode !== "object") return;
			const record = rawNode as Record<string, unknown>;
			const label = String(record.label ?? "").trim();
			if (!label) return;
			const levelValue = Number(record.level);
			const level = Number.isFinite(levelValue) && levelValue > 0 ? levelValue : index + 1;
			const kind = isBreadcrumbNodeKind(record.kind) ? record.kind : inferBreadcrumbNodeKind(label, level);
			const node: BreadcrumbNode = { level, kind, label };
			if (typeof record.id === "string" && record.id.trim()) node.id = record.id.trim();
			if (typeof record.node_id === "string" && record.node_id.trim()) node.node_id = record.node_id.trim();
			if (typeof record.parent_node_id === "string" && record.parent_node_id.trim())
				node.parent_node_id = record.parent_node_id.trim();
			if (typeof record.source === "string" && record.source.trim())
				node.source = record.source as BreadcrumbNode["source"];
			if (typeof record.editable === "boolean") node.editable = record.editable;
			const page = Number(record.page);
			if (Number.isFinite(page)) node.page = page;
			nodes.push(node);
		});
		if (nodes.length) return renumberBreadcrumbNodes(nodes);
	}
	const breadcrumb = parseBreadcrumb(fallback);
	if (!breadcrumb?.length) return undefined;
	return breadcrumb.map((label, index) => ({
		level: index + 1,
		kind: inferBreadcrumbNodeKind(label, index + 1),
		label,
		source: "agent_second_pass",
	}));
}

export function breadcrumbNodesFromRegion(
	region: Pick<ExportableRegion, "breadcrumb" | "breadcrumb_nodes">,
): BreadcrumbNode[] {
	return normalizeBreadcrumbNodes(region.breadcrumb_nodes, region.breadcrumb) ?? [];
}

export function renumberBreadcrumbNodes(nodes: BreadcrumbNode[]): BreadcrumbNode[] {
	return nodes
		.filter((node) => node.label.trim())
		.map((node, index) => ({ ...node, level: index + 1, label: node.label.trim() }));
}

export function breadcrumbLabels(nodes: BreadcrumbNode[]): string[] | undefined {
	const labels = renumberBreadcrumbNodes(nodes).map((node) => node.label);
	return labels.length ? labels : undefined;
}

export function breadcrumbNodesFingerprint(region: Pick<ExportableRegion, "breadcrumb" | "breadcrumb_nodes">): string {
	return JSON.stringify(breadcrumbNodesFromRegion(region));
}

export function breadcrumbMetadataChanged(
	left: Pick<ExportableRegion, "breadcrumb" | "breadcrumb_nodes">,
	right: Pick<ExportableRegion, "breadcrumb" | "breadcrumb_nodes">,
): boolean {
	return (
		formatBreadcrumb(left.breadcrumb) !== formatBreadcrumb(right.breadcrumb) ||
		breadcrumbNodesFingerprint(left) !== breadcrumbNodesFingerprint(right)
	);
}

export function breadcrumbNodeIdentityKey(node: BreadcrumbNode): string {
	return [node.kind, node.label.trim(), node.node_id ?? "", Number.isFinite(node.page) ? String(node.page) : ""].join(
		"::",
	);
}

export function replaceBreadcrumbNodeManually(
	nodes: BreadcrumbNode[],
	index: number,
	patch: Partial<Pick<BreadcrumbNode, "kind" | "label">>,
): BreadcrumbNode[] {
	return nodes.map((node, nodeIndex) => {
		if (nodeIndex !== index) return node;
		return {
			level: node.level,
			kind: patch.kind ?? node.kind,
			label: patch.label ?? node.label,
			editable: true,
			source: "human" as const,
		};
	});
}

export function clearBreadcrumbNodeIdentity(nodes: BreadcrumbNode[], index: number): BreadcrumbNode[] {
	return replaceBreadcrumbNodeManually(nodes, index, {});
}

export function applyKnownBreadcrumbNode(
	nodes: BreadcrumbNode[],
	index: number,
	option: BreadcrumbNode,
): BreadcrumbNode[] {
	return nodes.map((node, nodeIndex) =>
		nodeIndex === index
			? {
					level: node.level,
					kind: option.kind,
					label: option.label,
					id: option.id,
					node_id: option.node_id,
					parent_node_id: option.parent_node_id,
					page: option.page,
					source: option.source,
					editable: option.editable,
				}
			: node,
	);
}

export function breadcrumbPatch(nodes: BreadcrumbNode[]): Pick<ExportableRegion, "breadcrumb" | "breadcrumb_nodes"> {
	const normalized = renumberBreadcrumbNodes(nodes);
	return {
		breadcrumb: breadcrumbLabels(normalized),
		breadcrumb_nodes: normalized.length ? normalized : undefined,
	};
}

export function collectBreadcrumbOptions(regions: ExportableRegion[]): BreadcrumbNode[] {
	const byKey = new Map<string, BreadcrumbNode>();
	const addNode = (node: BreadcrumbNode) => {
		const label = node.label.trim();
		if (!label) return;
		const key = breadcrumbNodeIdentityKey({ ...node, label });
		if (!byKey.has(key)) byKey.set(key, { ...node, label });
	};
	regions.forEach((region) => {
		breadcrumbNodesFromRegion(region).forEach(addNode);
		const candidateLabel = (region.label || region.text_hint || "").trim();
		if (!candidateLabel) return;
		if (region.family === "section_heading") {
			addNode({ level: 1, kind: "section", label: candidateLabel, source: "human" });
		} else if (region.family === "section_label") {
			addNode({ level: 1, kind: "local_role", label: candidateLabel, source: "human" });
		} else if (region.family === "labeled_controls") {
			addNode({ level: 1, kind: "control", label: candidateLabel, source: "human" });
		}
	});
	return Array.from(byKey.values()).sort((left, right) => {
		if (left.level !== right.level) return left.level - right.level;
		return left.label.localeCompare(right.label);
	});
}

export function regionsToExpected(
	regions: ExportableRegion[],
	slug = "manual_labeling",
): { schema_version: string; slice_id: string; captured_at: string; expected_elements: ExpectedElement[] } {
	return {
		schema_version: "pdf_lab.golden_slice.v2",
		slice_id: slug,
		captured_at: new Date().toISOString(),
		expected_elements: regions.map((r) => {
			const breadcrumbNodes = breadcrumbNodesFromRegion(r);
			const breadcrumb = r.breadcrumb?.length ? r.breadcrumb : breadcrumbLabels(breadcrumbNodes);
			const e: ExpectedElement = {
				family: r.family,
				bbox_hint: r.bbox,
				allowed_types: DEFAULT_ALLOWED_TYPES[r.family],
				match_strategy: r.text_hint ? "text_contains" : "type_only",
			};
			if (r.label) e.label = r.label;
			if (r.text_hint) e.text_hint = r.text_hint;
			if (breadcrumb?.length) e.breadcrumb = breadcrumb;
			if (breadcrumbNodes.length) e.breadcrumb_nodes = breadcrumbNodes;
			if (r.lead_label) {
				e.lead_label = r.lead_label;
				e.desired_role = "labeled_paragraph";
				e.desired_lead_label = r.lead_label;
			}
			if (r.notes) e.notes = r.notes;
			if (r.semantic_role) e.semantic_role = r.semantic_role;
			if (typeof r.target_page === "number") e.target_page = r.target_page;
			if (typeof r.dot_leader === "boolean") e.dot_leader = r.dot_leader;
			if (r.toc_title) e.toc_title = r.toc_title;
			if (r.toc_entries?.length) e.toc_entries = r.toc_entries;
			return e;
		}),
	};
}
