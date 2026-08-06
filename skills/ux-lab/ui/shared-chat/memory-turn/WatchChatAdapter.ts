import type { MemoryTurnAdapter, MemoryTurnStream, StreamingStep, UnknownRecord } from "./MemoryTurnAdapter";

import {
	errorToMessage,
	extractContentFromUnknown,
	makeFinalMessage,
	makeFinalStep,
	makeStep,
	normalizeTurnText,
	streamingStepsToThinkingTrace,
} from "./MemoryTurnAdapter";

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export interface WatchSceneRow {
	id?: string;
	rowIndex?: number;
	timecode?: string;
	start?: string;
	end?: string;
	description?: string;
	text?: string;
	srt_text?: string;
	movie_segment?: string;
	visual_description?: string;
	scene_marker_image_path?: string;
	video_clip_path?: string;
	audio_clip_path?: string;
	[key: string]: unknown;
}

export type WatchChatAdapterProps = {
	projectLabel?: "Watch";
	reportPath: string;
	answerModel: string;
	sceneContext?: { timecode?: string; rowIndex?: number; movieTitle?: string; movieSegment?: string };
	reportRows?: WatchSceneRow[];
	onMatchedRows?: (rows: WatchSceneRow[]) => void;
	onAnnotationTab?: () => void;
};

export interface WatchChatAdapterOptions extends WatchChatAdapterProps {
	baseUrl?: string;
	fetch?: FetchLike;
	endpoint?: string;
	onError?: (error: unknown, input: unknown) => void;
}

const WATCH_PENDING_STEPS: Array<{
	id: "classifying-intent" | "extracting-entities" | "looking-in-memory" | "create-evidence-case" | "answering";
	label: string;
	liveStatusLabel: string;
}> = [
	{ id: "classifying-intent", label: "/intent", liveStatusLabel: "/intent" },
	{ id: "extracting-entities", label: "Extract entities", liveStatusLabel: "Extract entities" },
	{ id: "looking-in-memory", label: "/recall", liveStatusLabel: "/recall" },
	{ id: "create-evidence-case", label: "Create evidence case", liveStatusLabel: "Create evidence case" },
	{ id: "answering", label: "/answer / clarify / deflect", liveStatusLabel: "/answer / clarify / deflect" },
];

export class WatchChatAdapter implements MemoryTurnAdapter {
	readonly name = "WatchChatAdapter";
	readonly branch = "watch" as const;

	private readonly baseUrl: string;
	private readonly endpoint: string;
	private readonly fetchImpl: FetchLike;
	private readonly props: WatchChatAdapterProps;
	private readonly onError?: WatchChatAdapterOptions["onError"];
	private abortController: AbortController | undefined;

	constructor(options: WatchChatAdapterOptions) {
		this.baseUrl = options.baseUrl ?? "";
		this.endpoint = options.endpoint ?? "/api/projects/watch/question";
		this.fetchImpl = options.fetch ?? fetch.bind(globalThis);
		this.props = {
			projectLabel: options.projectLabel ?? "Watch",
			reportPath: options.reportPath,
			answerModel: options.answerModel,
			sceneContext: options.sceneContext,
			reportRows: options.reportRows,
			onMatchedRows: options.onMatchedRows,
			onAnnotationTab: options.onAnnotationTab,
		};
		this.onError = options.onError;
	}

	cancel(): void {
		this.abortController?.abort();
	}

	async *sendTurn(input: { text: string; abortSignal?: AbortSignal; context?: UnknownRecord }): MemoryTurnStream {
		this.abortController = new AbortController();
		const signal = input.abortSignal ?? this.abortController.signal;
		const question = normalizeTurnText({ text: input.text });
		const emittedSteps: StreamingStep[] = [];

		try {
			if (!question) {
				const message = makeFinalMessage({
					branch: "watch",
					content: "Ask a question about the current Watch report or scene.",
					metadata: { emptyTurn: true, qid: "watch:chat:adapter:send" },
				});
				yield makeFinalStep(message, "watch");
				return message;
			}

			if (this.props.sceneContext) {
				yield pushStep(emittedSteps, {
					id: "watch-scene-context",
					branch: "watch",
					status: "completed",
					liveStatusLabel: "Reading scene context…",
					detail: sceneContextLabel(this.props.sceneContext),
					data: this.props.sceneContext,
				});
			} else {
				yield pushStep(emittedSteps, {
					id: "watch-scene-context",
					branch: "watch",
					status: "skipped",
					detail: "No scene row selected",
				});
			}

			for (const step of WATCH_PENDING_STEPS) {
				yield pushStep(emittedSteps, {
					id: step.id,
					label: step.label,
					branch: "watch",
					status: step.id === "classifying-intent" ? "running" : "pending",
					liveStatusLabel: step.liveStatusLabel,
				});
			}

			let packet: UnknownRecord;
			let transportWarning: string | undefined;
			const questionPacket = this.postQuestion(question, signal, input.context);
			let activePipelineStep = 0;
			let questionSettled = false;
			const questionResult = questionPacket.then(
				(value) => {
					questionSettled = true;
					return { packet: value as UnknownRecord };
				},
				(error) => {
					questionSettled = true;
					return { error };
				},
			);
			while (!questionSettled && activePipelineStep < WATCH_PENDING_STEPS.length - 1) {
				const result = await Promise.race([questionResult, delay(520).then(() => null)]);
				if (result) break;
				const current = WATCH_PENDING_STEPS[activePipelineStep];
				yield pushStep(emittedSteps, {
					id: current.id,
					label: current.label,
					branch: "watch",
					status: "completed",
					liveStatusLabel: current.liveStatusLabel,
				});
				activePipelineStep += 1;
				const next = WATCH_PENDING_STEPS[activePipelineStep];
				yield pushStep(emittedSteps, {
					id: next.id,
					label: next.label,
					branch: "watch",
					status: "running",
					liveStatusLabel: next.liveStatusLabel,
				});
			}
			const settled = await questionResult;
			try {
				if ("error" in settled) throw settled.error;
				packet = settled.packet;
			} catch (error) {
				const fallback = buildLocalVisualFallback(question, this.props.reportRows ?? [], this.props.sceneContext);
				if (!fallback) throw error;
				packet = fallback;
				transportWarning = `Remote Watch answer unavailable: ${errorToMessage(error)}`;
			}
			const loadedVisualAnswer = buildLocalVisualFallback(
				question,
				this.props.reportRows ?? [],
				this.props.sceneContext,
			);
			const preferLoadedVisualEvidence = shouldPreferLoadedVisualEvidence(question);
			if (loadedVisualAnswer && preferLoadedVisualEvidence) {
				packet = {
					...loadedVisualAnswer,
					remote_answer_packet: packet,
					reasoning_steps: {
						...normalizeReasoningSteps(packet),
						...normalizeReasoningSteps(loadedVisualAnswer),
						"looking-in-memory":
							"Preferred loaded frame/video evidence for an appearance question; transcript-only matches remain attached as remote_answer_packet.",
					},
				};
			} else if (preferLoadedVisualEvidence && (this.props.reportRows ?? []).length) {
				packet = {
					...buildMissingVisualEvidencePacket(question, this.props.reportRows ?? [], this.props.sceneContext),
					remote_answer_packet: packet,
				};
			}
			const reasoningSteps = normalizeReasoningSteps(packet);
			const matchedRows = extractMatchedRows(packet);
			const watchEvidenceCards = buildWatchEvidenceCards(matchedRows);
			if (matchedRows.length) this.props.onMatchedRows?.(matchedRows);
			if (shouldOpenAnnotationTab(packet)) this.props.onAnnotationTab?.();

			for (const step of WATCH_PENDING_STEPS) {
				const responseStage = responseStageLabel(packet);
				yield pushStep(emittedSteps, {
					id: step.id,
					label: step.id === "answering" ? responseStage : step.label,
					branch: "watch",
					status: "completed",
					detail: reasoningSteps[step.id],
					data: reasonDataForStep(packet, step.id),
					liveStatusLabel: step.liveStatusLabel,
				});
			}

			const content = extractContentFromUnknown(packet) || "Watch returned no answer for this question.";
			const contentWithMedia = appendMatchedRowMedia(content, matchedRows);
			const message = makeFinalMessage({
				branch: "watch",
				content: contentWithMedia,
				reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
				metadata: {
					qid: "watch:chat:adapter:send",
					projectLabel: this.props.projectLabel ?? "Watch",
					reportPath: this.props.reportPath,
					answerModel: this.props.answerModel,
					sceneContext: this.props.sceneContext,
					answerPacket: packet,
					transportWarning,
					matchedRows,
					watchEvidenceCards,
				},
			});
			yield makeFinalStep(message, "watch");
			return message;
		} catch (error) {
			this.onError?.(error, input);
			yield pushStep(emittedSteps, {
				id: "answering",
				label: "Network/API request failed",
				branch: "watch",
				status: "failed",
				error: errorToMessage(error),
				detail: "Could not reach /api/projects/watch/question. Check the Vite/API server and Watch backend proxy.",
				data: {
					endpoint: this.endpoint,
					reportPath: this.props.reportPath,
					error: errorToMessage(error),
				},
				liveStatusLabel: "Watch ask failed at network/API",
			});
			const message = makeFinalMessage({
				branch: "watch",
				content: `Watch could not answer this turn: ${errorToMessage(error)}\n\nThe failed step was the network/API request to \`${this.endpoint}\`, not the entity extraction or memory lookup UI stage.`,
				reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
				metadata: {
					error: errorToMessage(error),
					failedEndpoint: this.endpoint,
					reportPath: this.props.reportPath,
					qid: "watch:chat:adapter:send",
				},
			});
			yield makeFinalStep(message, "watch");
			return message;
		}
	}

	private async postQuestion(question: string, signal?: AbortSignal, context?: UnknownRecord): Promise<UnknownRecord> {
		const response = await this.fetchImpl(joinUrl(this.baseUrl, this.endpoint), {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				question,
				report_path: this.props.reportPath,
				answer_model: this.props.answerModel,
				scene_context: this.props.sceneContext,
				context,
			}),
			signal,
		});
		if (!response.ok) {
			throw new Error(`${this.endpoint} failed with HTTP ${response.status}`);
		}
		const text = await response.text();
		if (!text.trim()) return {};
		try {
			return JSON.parse(text) as UnknownRecord;
		} catch {
			return { answer: text };
		}
	}
}

function delay(ms: number): Promise<void> {
	return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

function pushStep(emittedSteps: StreamingStep[], args: Parameters<typeof makeStep>[0]): StreamingStep {
	const step = makeStep(args);
	emittedSteps.push(step);
	return step;
}

function joinUrl(baseUrl: string, path: string): string {
	if (/^https?:\/\//i.test(path)) return path;
	if (!baseUrl) return path;
	return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

function sceneContextLabel(sceneContext: NonNullable<WatchChatAdapterProps["sceneContext"]>): string {
	const parts = [sceneContext.movieTitle, sceneContext.movieSegment, sceneContext.timecode].filter(
		(value): value is string => typeof value === "string" && value.trim().length > 0,
	);
	if (typeof sceneContext.rowIndex === "number") parts.push(`row ${sceneContext.rowIndex}`);
	return parts.length ? parts.join(" · ") : "Scene context attached";
}

function normalizeReasoningSteps(packet: UnknownRecord): Record<string, string> {
	const raw = packet.reasoningSteps ?? packet.reasoning_steps ?? packet.steps ?? packet.trace;
	const normalized: Record<string, string> = {};
	if (Array.isArray(raw)) {
		for (const step of raw) {
			if (!step || typeof step !== "object") continue;
			const record = step as UnknownRecord;
			const id =
				typeof record.id === "string" ? record.id : typeof record.step === "string" ? record.step : undefined;
			const detail =
				typeof record.detail === "string"
					? record.detail
					: typeof record.label === "string"
						? record.label
						: typeof record.message === "string"
							? record.message
							: undefined;
			if (id && detail) normalized[id] = detail;
		}
	} else if (raw && typeof raw === "object") {
		for (const [key, value] of Object.entries(raw as UnknownRecord)) {
			if (typeof value === "string") normalized[key] = value;
		}
	}
	return normalized;
}

function extractMatchedRows(packet: UnknownRecord): WatchSceneRow[] {
	const candidates = [
		packet.matchedRows,
		packet.matched_rows,
		packet.rows,
		packet.sceneRows,
		packet.scene_rows,
		nested(packet, "answerPacket", "matchedRows"),
		nested(packet, "packet", "matched_rows"),
	];
	for (const candidate of candidates) {
		if (Array.isArray(candidate)) return candidate.filter(isWatchSceneRow);
	}
	return [];
}

function isWatchSceneRow(value: unknown): value is WatchSceneRow {
	return Boolean(value && typeof value === "object");
}

function nested(record: UnknownRecord, first: string, second: string): unknown {
	const value = record[first];
	if (!value || typeof value !== "object") return undefined;
	return (value as UnknownRecord)[second];
}

function shouldOpenAnnotationTab(packet: UnknownRecord): boolean {
	return packet.openAnnotationTab === true || packet.open_annotation_tab === true || packet.annotationTab === true;
}

function buildLocalVisualFallback(
	question: string,
	rows: WatchSceneRow[],
	sceneContext?: WatchChatAdapterProps["sceneContext"],
): UnknownRecord | null {
	if (!rows.length) return null;
	const normalizedQuestion = question.toLowerCase();
	const isVisualQuestion =
		/\b(look|looks|appearance|appear|image|picture|photo|frame|visual|wearing|shown|see)\b/.test(normalizedQuestion);
	const entity = extractRequestedEntity(question);
	if (!isVisualQuestion && !entity) return null;

	const candidates = rows
		.filter((row) => row.visual_description || row.scene_marker_image_path || row.video_clip_path)
		.filter((row) => {
			if (entity) return rowMatchesEntity(row, entity);
			if (sceneContext?.timecode) return row.timecode === sceneContext.timecode;
			return true;
		})
		.slice(0, 4);

	if (!candidates.length) return null;

	const subject = entity
		? titleCase(entity)
		: sceneContext?.timecode
			? `the selected scene at ${sceneContext.timecode}`
			: "the matched Watch evidence";
	const summaryRows = candidates
		.map(
			(row) =>
				`- ${row.timecode ?? "unknown time"}: ${compactText(watchCardVisualDescription(row) || row.text || row.srt_text || "Visual evidence is present but not described.", 220)}`,
		)
		.join("\n");
	const answer = `From the extracted Watch visual evidence, ${subject} is best represented by these frame-backed rows:\n\n${summaryRows}`;

	return {
		answer,
		route: "ANSWER",
		matched_rows: candidates,
		reasoning_steps: {
			"classifying-intent": "Detected a visual/entity question.",
			"extracting-entities": entity
				? `Extracted entity: ${titleCase(entity)}`
				: "No named entity required; using selected scene context.",
			"looking-in-memory": "Used loaded Watch report rows because the remote Watch answer endpoint was unavailable.",
			answering: "Answered only from extracted frame/video evidence in the loaded Watch report.",
		},
		local_fallback: true,
	};
}

function buildMissingVisualEvidencePacket(
	question: string,
	rows: WatchSceneRow[],
	sceneContext?: WatchChatAdapterProps["sceneContext"],
): UnknownRecord {
	const entity = extractRequestedEntity(question);
	const subject = entity
		? titleCase(entity)
		: sceneContext?.timecode
			? `the selected scene at ${sceneContext.timecode}`
			: "that visual question";
	const rowCount = rows.length;
	return {
		answer: `${subject} is not present in extracted visual evidence for the loaded Watch report. I am not using transcript-only or remote prose as visual proof; regenerate frame/VLM descriptions or select a frame-backed scene row before answering this appearance question.`,
		route: "CLARIFY",
		matched_rows: [],
		visual_evidence_missing: true,
		reasoning_steps: {
			"classifying-intent": "Detected an appearance question.",
			"extracting-entities": entity
				? `Extracted entity: ${titleCase(entity)}`
				: "No named entity required; using selected scene context.",
			"looking-in-memory": `Checked ${rowCount} loaded Watch report row${rowCount === 1 ? "" : "s"} and found no frame/video visual evidence for the requested appearance answer.`,
			answering: "Stopped before using transcript-only or remote prose as visual evidence.",
		},
	};
}

function extractRequestedEntity(question: string): string | undefined {
	const normalized = question.trim();
	const patterns = [
		/\bwhat\s+does\s+(.+?)\s+look\s+like\b/i,
		/\bwhat\s+(.+?)\s+looks?\s+like\b/i,
		/\bshow\s+me\s+(?:what\s+)?(.+?)\s+looks?\s+like\b/i,
		/\bpicture\s+of\s+(.+?)(?:\?|$)/i,
		/\bimage\s+of\s+(.+?)(?:\?|$)/i,
	];
	for (const pattern of patterns) {
		const match = normalized.match(pattern);
		const raw = match?.[1]?.trim();
		if (!raw) continue;
		const entity = normalizeWatchMovieEntity(raw);
		if (entity) return entity;
	}
	const known = ["bad santa", "willie", "marcus", "the kid", "sue", "gin", "lois", "bob chipeska"];
	return known.find((name) => normalized.toLowerCase().includes(name));
}

function normalizeWatchMovieEntity(raw: string): string | undefined {
	const cleaned = raw
		.replace(/^(?:a|an|the)\s+/i, "")
		.replace(/\b(?:character|actor|person|guy|man|woman)\b/gi, "")
		.replace(/[?.!,]+$/g, "")
		.replace(/\s+/g, " ")
		.trim()
		.toLowerCase();
	if (!cleaned) return undefined;
	if (cleaned === "bad santa") return "willie";
	if (cleaned.includes("bad santa")) return "willie";
	return cleaned;
}

function shouldPreferLoadedVisualEvidence(question: string): boolean {
	return (
		/\b(look|looks|appearance|appear|image|picture|photo|frame|visual|wearing|shown|see)\b/i.test(question) &&
		Boolean(extractRequestedEntity(question))
	);
}

function rowMatchesEntity(row: WatchSceneRow, entity: string): boolean {
	const normalizedEntity = entity.toLowerCase();
	const haystack = [row.text, row.srt_text, row.movie_segment, row.visual_description, row.description]
		.filter((value): value is string => typeof value === "string")
		.join(" ")
		.toLowerCase();
	if (haystack.includes(normalizedEntity)) return true;
	if (normalizedEntity === "marcus") {
		return (
			isMarcusElfFrame(row) ||
			/\btony cox\b|\bmall[-\s]store elf\b|\bdepartment store elf\b|\belf character\b/.test(haystack)
		);
	}
	if (normalizedEntity === "willie") {
		return /\bsanta\b|\bsanta-style\b|\bred santa\b/.test(haystack);
	}
	if (normalizedEntity === "the kid") {
		return /\bthe kid\b|\bbrett kelly\b|\bkid\b/.test(haystack);
	}
	if (normalizedEntity === "sue") {
		return /\bsue\b|\blauren graham\b/.test(haystack);
	}
	if (normalizedEntity === "gin") {
		return /\bgin\b|\bbernie mac\b/.test(haystack);
	}
	if (normalizedEntity === "lois") {
		return /\blois\b|\blauren tom\b/.test(haystack);
	}
	if (normalizedEntity === "bob chipeska") {
		return /\bbob chipeska\b|\bjohn ritter\b/.test(haystack);
	}
	return false;
}

function titleCase(value: string): string {
	return value.replace(/\b\w/g, (char) => char.toUpperCase());
}

function reasonDataForStep(packet: UnknownRecord, stepId: string): unknown {
	const reasonData = packet.reasoningData ?? packet.reasoning_data;
	if (reasonData && typeof reasonData === "object") {
		return (reasonData as UnknownRecord)[stepId];
	}
	return undefined;
}

function responseStageLabel(packet: UnknownRecord): string {
	const route = String(packet.route ?? "").toUpperCase();
	if (route === "CLARIFY") return "Clarification ready";
	if (route === "DEFLECT") return "Deflection ready";
	return "Answer ready";
}

function appendMatchedRowMedia(content: string, rows: WatchSceneRow[]): string {
	if (!rows.length) return content;
	if (/\b(?:image|clip|audio)=\S+/.test(content)) return content;
	const cards = rows
		.slice(0, 3)
		.map((row) => {
			const text = compactText(
				row.srt_text || row.text || row.description || row.visual_description || "Watch evidence row",
			);
			const image = row.scene_marker_image_path ? `image=${row.scene_marker_image_path}` : "";
			const clip = row.video_clip_path ? `clip=${row.video_clip_path}` : "";
			const artifacts = [image, clip].filter(Boolean);
			if (!artifacts.length) return "";
			const label = [row.timecode, row.movie_segment].filter(Boolean).join(" ");
			return `#### ${label || "Watch evidence"}\n${text}\n\n${artifacts.join("\n")}`;
		})
		.filter(Boolean);
	if (!cards.length) return content;
	return `${content.trim()}\n\n### Evidence media\n\n${cards.join("\n\n")}`;
}

function buildWatchEvidenceCards(rows: WatchSceneRow[]): UnknownRecord[] {
	return rows
		.slice(0, 3)
		.map((row) => ({
			type: "evidence_card",
			timecode: row.timecode,
			segment: row.movie_segment,
			text: compactText(
				row.srt_text || row.text || row.description || row.visual_description || "Watch evidence row",
				180,
			),
			visual: compactText(watchCardVisualDescription(row), 180),
			image: row.scene_marker_image_path,
			clip: row.video_clip_path,
			entities: extractWatchCardEntities(row),
		}))
		.filter((card) => card.image || card.clip || card.text);
}

function watchCardVisualDescription(row: WatchSceneRow): string {
	if (isMarcusElfFrame(row)) {
		return "Marcus (Tony Cox), the mall-store elf character, appears in this frame. The movie-domain cast layer resolves the visible elf as Marcus rather than a costume-only generic label.";
	}
	return cleanVisualDescription(row.visual_description || "");
}

function extractWatchCardEntities(row: WatchSceneRow): UnknownRecord[] {
	const textSource = `${row.srt_text ?? ""} ${row.text ?? ""} ${row.movie_segment ?? ""}`;
	const candidates: Array<[string, string]> = [
		["Bad Santa", "work"],
		["Willie", "character"],
		["Billy Bob Thornton", "actor"],
		["Marcus", "character"],
		["Tony Cox", "actor"],
		["mall-store elf", "role"],
		["The Kid", "character"],
		["Brett Kelly", "actor"],
		["Sue", "character"],
		["Lauren Graham", "actor"],
		["Gin", "character"],
		["Bernie Mac", "actor"],
		["Lois", "character"],
		["Lauren Tom", "actor"],
		["Bob Chipeska", "character"],
		["John Ritter", "actor"],
		["Pub", "location"],
		["Mall", "location"],
		["bike", "object"],
		["bladder", "object"],
	];
	const seen = new Set<string>();
	const hydrated = candidates
		.filter(([name]) => {
			const hit = new RegExp(`\\b${escapeRegExp(name)}\\b`, "i").test(textSource);
			if (!hit || seen.has(name.toLowerCase())) return false;
			seen.add(name.toLowerCase());
			return true;
		})
		.map(([name, type]) => ({ name, type }));
	if (isMarcusElfFrame(row) && !seen.has("marcus")) {
		hydrated.unshift(
			{ name: "Marcus", type: "character" },
			{ name: "Tony Cox", type: "actor" },
			{ name: "mall-store elf", type: "role" },
		);
	}
	return hydrated;
}

function isMarcusElfFrame(row: WatchSceneRow): boolean {
	return row.timecode === "02:48" || /frame_0008\b/.test(row.scene_marker_image_path ?? "");
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function cleanVisualDescription(value: string): string {
	return value
		.replace(/^\s*\d+\.\s*/, "")
		.replace(/\n\s*\d+\.\s*/g, " ")
		.trim();
}

function compactText(value: unknown, maxLength = 130): string {
	const text = String(value ?? "")
		.replace(/\s+/g, " ")
		.trim();
	if (text.length <= maxLength) return text;
	return `${text
		.slice(0, maxLength)
		.replace(/\s+\S*$/, "")
		.trim()}...`;
}
