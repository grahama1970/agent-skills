import { Assets, Graphics, GraphicsContext } from "pixi.js";
import type { LaneEvent } from "../lib/battle-types";

/**
 * Lucide marker glyphs rendered inside the PixiJS canvas as vector Graphics
 * (per /pixijs pixijs-assets: SVG → `GraphicsContext` via
 * `Assets.load({ parser: 'svg', data: { parseAsGraphicsContext: true } })`).
 *
 * DOM Lucide SVG components cannot be nested in a PIXI.Container; the correct v8
 * path is to parse the raw SVG string into a shared, GPU-resident GraphicsContext
 * and instance cheap `new Graphics(context)` per marker — crisp at any scale.
 * `Texture.from(url)` is NOT used: in v8 it only reads the cache, never fetches.
 */

const V = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

/** Raw Lucide glyphs, stroke pre-tinted to the marker's tactical tone. */
const LUCIDE_MARKER_SVGS: Partial<Record<LaneEvent["kind"], string>> = {
	killed: `<svg ${V} stroke="#ff4d5c"><path d="m12.5 17-.5-1-.5 1h1z"/><path d="M15 22a1 1 0 0 0 1-1v-1a2 2 0 0 0 1.56-3.25 8 8 0 1 0-11.12 0A2 2 0 0 0 8 20v1a1 1 0 0 0 1 1z"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="12" r="1"/></svg>`,
	blocked: `<svg ${V} stroke="#5aadff"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9-5 5"/><path d="m9.5 9 5 5"/></svg>`,
	blue_blast: `<svg ${V} stroke="#5aadff"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>`,
	detected: `<svg ${V} stroke="#5aadff"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>`,
	promoted: `<svg ${V} stroke="#3cf07a"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>`,
	fastest_crash: `<svg ${V} stroke="#3cf07a"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>`,
	useful: `<svg ${V} stroke="#ffd24d"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>`,
	handoff: `<svg ${V} stroke="#c47aff"><line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>`,
};

const contexts = new Map<LaneEvent["kind"], GraphicsContext>();
let loadPromise: Promise<void> | null = null;

function svgDataUrl(svg: string): string {
	return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** Load every marker glyph into a shared GraphicsContext. Idempotent. */
export async function loadLucideMarkerContexts(): Promise<void> {
	if (!loadPromise) {
		loadPromise = (async () => {
			await Promise.all(
				(Object.entries(LUCIDE_MARKER_SVGS) as Array<[LaneEvent["kind"], string]>).map(async ([kind, svg]) => {
					if (contexts.has(kind)) return;
					const context = await Assets.load<GraphicsContext>({
						src: svgDataUrl(svg),
						parser: "svg",
						data: { parseAsGraphicsContext: true },
					});
					// The svg parser can hand back a Texture (not a GraphicsContext) when it
					// falls back to raster loading; only a real GraphicsContext can back a
					// `new Graphics(context)`, so guard the instance type explicitly.
					if (context instanceof GraphicsContext) contexts.set(kind, context);
				}),
			);
		})().catch((error) => {
			loadPromise = null;
			throw error;
		});
	}
	return loadPromise;
}

export function hasLucideMarker(kind: LaneEvent["kind"]): boolean {
	return contexts.has(kind);
}

/**
 * A fresh `Graphics` instance backed by the shared context for this marker kind,
 * or null if the kind has no lucide glyph (caller falls back to the atlas).
 * The context is shared/GPU-resident; the Graphics wrapper is cheap and poolable.
 */
export function lucideMarkerGraphic(kind: LaneEvent["kind"]): Graphics | null {
	const context = contexts.get(kind);
	if (!context) return null;
	const graphic = new Graphics(context);
	graphic.pivot.set(12, 12); // lucide 24x24 viewBox center
	graphic.eventMode = "none";
	graphic.cullable = true;
	return graphic;
}
