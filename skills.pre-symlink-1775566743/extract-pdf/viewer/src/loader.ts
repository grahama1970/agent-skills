import type { BatchResult, ExtractionResult } from "./types";

/**
 * Apply defaults for optional array fields so callers never have to
 * guard against undefined collections.
 */
function normalizeResult(raw: Partial<ExtractionResult>): ExtractionResult {
  return {
    version: raw.version ?? "unknown",
    engine: raw.engine ?? "pdf_oxide",
    engine_version: raw.engine_version ?? "unknown",
    profile: raw.profile ?? {
      domain: "unknown",
      preset: "unknown",
      complexity_score: 0,
      page_count: 0,
      is_scanned: false,
    },
    blocks: raw.blocks ?? [],
    sections: raw.sections ?? [],
    tables: raw.tables ?? [],
    figures: raw.figures ?? [],
    cascade_decisions: raw.cascade_decisions,
    taxonomy_tags: raw.taxonomy_tags,
  };
}

/**
 * Load a single ExtractionResult.
 *
 * Resolution order:
 *   1. URL query param `?file=<url-or-path>` — fetch that URL directly.
 *   2. Fall back to `/data.json` served from the public directory.
 *
 * Returns null on any fetch or parse failure (errors are logged to console).
 */
export async function loadExtractionData(): Promise<ExtractionResult | null> {
  const params = new URLSearchParams(window.location.search);
  const fileParam = params.get("file");
  const url = fileParam ? fileParam : "/data.json";

  try {
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`[loader] Failed to fetch ${url}: HTTP ${response.status}`);
      return null;
    }
    const raw = (await response.json()) as Partial<ExtractionResult>;
    return normalizeResult(raw);
  } catch (err) {
    console.error(`[loader] Error loading extraction data from ${url}:`, err);
    return null;
  }
}

/**
 * Load a batch result array from `/batch.json`.
 *
 * Returns an empty array on any fetch or parse failure.
 */
export async function loadBatchData(): Promise<BatchResult[]> {
  try {
    const response = await fetch("/batch.json");
    if (!response.ok) {
      console.error(`[loader] Failed to fetch /batch.json: HTTP ${response.status}`);
      return [];
    }
    const raw = (await response.json()) as unknown;
    if (!Array.isArray(raw)) {
      console.error("[loader] /batch.json did not return an array");
      return [];
    }
    return raw as BatchResult[];
  } catch (err) {
    console.error("[loader] Error loading batch data:", err);
    return [];
  }
}
