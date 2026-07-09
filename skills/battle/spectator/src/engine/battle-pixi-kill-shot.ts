import { AnimatedSprite, Container, Graphics, Sprite, type Texture } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane, LaneEvent } from "../lib/battle-types";
import { textureFromAtlas } from "./battle-race-atlas";
import { configureBattleSceneLayer } from "./battle-pixi-game-mechanics";
import { eventElapsedSeconds, fixtureUsesElapsedAxis, laneElapsedRange } from "../lib/battle-elapsed-axis";

export const KILL_SHOT_TRAVEL_SECONDS = 0.55;
export const KILL_SHOT_IMPACT_SECONDS = 0.42;

export type KillShotImpactKind = "blocked" | "killed" | "pending";

export type KillShotVisual = {
	laneId: string;
	eventId: string;
	blastSeconds: number;
	sourceX: number;
	targetX: number;
	y: number;
	progress: number;
	phase: "travel" | "impact";
	impactKind: KillShotImpactKind;
	impactAlpha: number;
	variant: "blue_sonic_blast" | "kill_cannon";
};

export type KillShotImpactBurstKind = "blocked" | "killed";

export type KillShotLayer = {
	container: Container;
	beam: Graphics;
	tipPool: Sprite[];
	burstPool: AnimatedSprite[];
	activeBurstKey: string | null;
};

export function impactBurstFrameNames(kind: KillShotImpactBurstKind): string[] {
	if (kind === "killed") return ["fx-killed", "marker-killed", "fx-killed"];
	return ["fx-blocked", "marker-blocked", "fx-blocked"];
}

export function impactBurstTextures(
	markerAtlas: Record<string, Texture>,
	kind: KillShotImpactBurstKind,
): Texture[] {
	return impactBurstFrameNames(kind)
		.map((frame) => textureFromAtlas(frame, markerAtlas))
		.filter((texture): texture is Texture => Boolean(texture));
}

export function killShotImpactFrameIndex(impactElapsed: number, frameCount: number): number {
	if (frameCount <= 1) return 0;
	const progress = Math.max(0, Math.min(1, impactElapsed / KILL_SHOT_IMPACT_SECONDS));
	return Math.min(frameCount - 1, Math.floor(progress * frameCount));
}

export function createKillShotLayer(): KillShotLayer {
	const container = configureBattleSceneLayer(new Container(), { label: "battle-kill-shots", cullable: true });
	const beam = new Graphics();
	beam.label = "battle-kill-shot-beam";
	container.addChild(beam);
	return { container, beam, tipPool: [], burstPool: [], activeBurstKey: null };
}

function secondsToWorldX(seconds: number, allottedSeconds: number, contentWidth: number): number {
	return (Math.max(0, seconds) / Math.max(1, allottedSeconds)) * contentWidth;
}

function runnerXAtSeconds(
	lane: Lane,
	seconds: number,
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): number {
	const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	const clamped = Math.max(start, Math.min(end, seconds));
	return secondsToWorldX(clamped, allottedSeconds, contentWidth);
}

export function resolveKillShotImpact(lane: Lane, blastEvent: LaneEvent, allottedSeconds: number, useElapsed: boolean): KillShotImpactKind {
	const blastSeconds = eventElapsedSeconds(blastEvent, allottedSeconds, useElapsed);
	let impact: KillShotImpactKind = "pending";
	for (const event of lane.events) {
		if (!event.proven) continue;
		if (event.id === blastEvent.id) continue;
		const eventSeconds = eventElapsedSeconds(event, allottedSeconds, useElapsed);
		if (eventSeconds + 0.001 < blastSeconds) continue;
		if (event.kind === "killed") return "killed";
		if (event.kind === "blocked" && impact === "pending") impact = "blocked";
	}
	return impact;
}

export function killShotVariant(event: LaneEvent): "blue_sonic_blast" | "kill_cannon" {
	if (event.animation === "kill_cannon") return "kill_cannon";
	return "blue_sonic_blast";
}

export function killShotVisualForEvent(args: {
	lane: Lane;
	blastEvent: LaneEvent;
	rowY: number;
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
}): KillShotVisual | null {
	const { lane, blastEvent, rowY, currentSeconds, allottedSeconds, contentWidth, useElapsed } = args;
	if (blastEvent.kind !== "blue_blast" || !blastEvent.proven) return null;

	const blastSeconds = eventElapsedSeconds(blastEvent, allottedSeconds, useElapsed);
	if (currentSeconds < blastSeconds) return null;

	const travelEnd = blastSeconds + KILL_SHOT_TRAVEL_SECONDS;
	const impactEnd = travelEnd + KILL_SHOT_IMPACT_SECONDS;
	if (currentSeconds > impactEnd) return null;

	const { start } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	const sourceX = secondsToWorldX(start, allottedSeconds, contentWidth);
	const targetX = runnerXAtSeconds(lane, travelEnd, allottedSeconds, contentWidth, useElapsed);
	const impactKind = resolveKillShotImpact(lane, blastEvent, allottedSeconds, useElapsed);
	const elapsed = currentSeconds - blastSeconds;

	let progress = 0;
	let phase: KillShotVisual["phase"] = "travel";
	let impactAlpha = 0;

	if (currentSeconds < travelEnd) {
		const raw = elapsed / KILL_SHOT_TRAVEL_SECONDS;
		progress = 1 - (1 - raw) ** 3;
	} else {
		phase = "impact";
		progress = 1;
		const impactElapsed = currentSeconds - travelEnd;
		impactAlpha = Math.max(0.12, 1 - impactElapsed / KILL_SHOT_IMPACT_SECONDS);
	}

	return {
		laneId: lane.id,
		eventId: blastEvent.id ?? `${lane.id}:blue_blast:${blastSeconds}`,
		blastSeconds,
		sourceX,
		targetX,
		y: rowY,
		progress,
		phase,
		impactKind,
		impactAlpha,
		variant: killShotVariant(blastEvent),
	};
}

function drawKillShotBeam(beam: Graphics, shot: KillShotVisual) {
	beam.clear();
	const headX = shot.sourceX + (shot.targetX - shot.sourceX) * shot.progress;
	const coreWidth = shot.variant === "kill_cannon" ? 5 : 3;
	const glowWidth = shot.variant === "kill_cannon" ? 10 : 7;
	const coreColor = shot.variant === "kill_cannon" ? 0x93c5fd : 0x7dd3fc;
	const glowColor = shot.variant === "kill_cannon" ? 0x2563eb : 0x38bdf8;

	beam.setStrokeStyle({ width: glowWidth, color: glowColor, alpha: shot.phase === "travel" ? 0.28 : 0.12 });
	beam.moveTo(shot.sourceX, shot.y);
	beam.lineTo(headX, shot.y);
	beam.stroke();

	beam.setStrokeStyle({ width: coreWidth, color: coreColor, alpha: shot.phase === "travel" ? 0.95 : 0.35 });
	beam.moveTo(shot.sourceX, shot.y);
	beam.lineTo(headX, shot.y);
	beam.stroke();

	if (shot.phase === "travel") {
		beam.circle(headX, shot.y, shot.variant === "kill_cannon" ? 7 : 5);
		beam.fill({ color: 0xe0f2fe, alpha: 0.85 });
	}
}

function placeKillShotTip(pool: Sprite[], container: Container, index: number, texture: Texture | undefined, x: number, y: number, scale: number, alpha: number): number {
	if (!texture) return index;
	let sprite = pool[index];
	if (!sprite) {
		sprite = new Sprite({ anchor: 0.5, eventMode: "none" });
		sprite.cullable = true;
		container.addChild(sprite);
		pool[index] = sprite;
	}
	sprite.texture = texture;
	sprite.x = x;
	sprite.y = y;
	sprite.scale.set(scale);
	sprite.alpha = alpha;
	sprite.visible = true;
	return index + 1;
}

function hideKillShotTips(pool: Sprite[], used: number) {
	for (let index = used; index < pool.length; index += 1) {
		pool[index].visible = false;
	}
}


function hideKillShotBursts(pool: AnimatedSprite[], used: number) {
	for (let index = used; index < pool.length; index += 1) {
		pool[index].visible = false;
		pool[index].stop();
	}
}

function syncKillShotBurstSprite(args: {
	sprite: AnimatedSprite;
	textures: Texture[];
	burstKey: string;
	layer: KillShotLayer;
	x: number;
	y: number;
	scale: number;
	alpha: number;
	frameIndex: number;
	tickerDeltaRatio: number;
}): number {
	const { sprite, textures, burstKey, layer, x, y, scale, alpha, frameIndex, tickerDeltaRatio } = args;
	if (layer.activeBurstKey !== burstKey || sprite.textures !== textures) {
		sprite.textures = textures.length ? textures : sprite.textures;
		sprite.loop = false;
		layer.activeBurstKey = burstKey;
	}

	const frameCount = Math.max(1, textures.length);
	const clampedFrame = Math.max(0, Math.min(frameCount - 1, frameIndex));
	sprite.animationSpeed = 0.22 * tickerDeltaRatio;
	sprite.gotoAndStop(clampedFrame);

	sprite.x = x;
	sprite.y = y;
	sprite.scale.set(scale * (1 + clampedFrame * 0.12));
	sprite.alpha = alpha;
	sprite.visible = true;
	return clampedFrame;
}

export function syncKillShots(args: {
	layer: KillShotLayer;
	markerAtlas: Record<string, Texture>;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
	allowEvent: (event: LaneEvent) => boolean;
	tickerDeltaRatio?: number;
}): { burstFrameIndex: number | null } {
	const {
		layer,
		markerAtlas,
		lanes,
		rowLayout,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed,
		allowEvent,
		tickerDeltaRatio = 1,
	} = args;

	const activeShots: KillShotVisual[] = [];
	for (const lane of lanes) {
		const row = rowLayout.find((item) => item.laneId === lane.id);
		if (!row) continue;
		const y = row.topPx + row.heightPx / 2;
		for (const event of lane.events) {
			if (event.kind !== "blue_blast") continue;
			if (!allowEvent(event)) continue;
			const shot = killShotVisualForEvent({
				lane,
				blastEvent: event,
				rowY: y,
				currentSeconds,
				allottedSeconds,
				contentWidth,
				useElapsed,
			});
			if (shot) activeShots.push(shot);
		}
	}

	if (activeShots.length === 0) {
		layer.beam.clear();
		hideKillShotTips(layer.tipPool, 0);
		hideKillShotBursts(layer.burstPool, 0);
		layer.activeBurstKey = null;
		return { burstFrameIndex: null };
	}

	const primary = activeShots[activeShots.length - 1];
	drawKillShotBeam(layer.beam, primary);

	let tipIndex = 0;
	const boltTexture = textureFromAtlas("marker-blue_blast", markerAtlas);
	if (primary.phase === "travel") {
		const headX = primary.sourceX + (primary.targetX - primary.sourceX) * primary.progress;
		const tipScale = primary.variant === "kill_cannon" ? 1.15 : 0.95;
		tipIndex = placeKillShotTip(layer.tipPool, layer.container, tipIndex, boltTexture, headX, primary.y, tipScale, 0.95);
	}

	hideKillShotTips(layer.tipPool, tipIndex);

	let burstFrameIndex: number | null = null;
	if (primary.phase === "impact" && (primary.impactKind === "killed" || primary.impactKind === "blocked")) {
		const burstTextures = impactBurstTextures(markerAtlas, primary.impactKind);
		const impactElapsed = currentSeconds - (primary.blastSeconds + KILL_SHOT_TRAVEL_SECONDS);
		const frameIndex = killShotImpactFrameIndex(impactElapsed, burstTextures.length);
		const burstKey = `${primary.laneId}:${primary.eventId}:${primary.impactKind}`;
		const impactScale = primary.variant === "kill_cannon" ? 1.35 : 1.15;
		let burstSprite = layer.burstPool[0];
		if (!burstSprite) {
			burstSprite = new AnimatedSprite({ textures: burstTextures.length ? burstTextures : [markerAtlas[Object.keys(markerAtlas)[0]]], anchor: 0.5, eventMode: "none" });
			burstSprite.cullable = true;
			burstSprite.loop = false;
			burstSprite.onComplete = () => {
				if (burstSprite.textures.length > 0) burstSprite.gotoAndStop(burstSprite.textures.length - 1);
			};
			layer.container.addChild(burstSprite);
			layer.burstPool[0] = burstSprite;
		}
		burstFrameIndex = syncKillShotBurstSprite({
			sprite: burstSprite,
			textures: burstTextures,
			burstKey,
			layer,
			x: primary.targetX,
			y: primary.y,
			scale: impactScale,
			alpha: primary.impactAlpha,
			frameIndex,
			tickerDeltaRatio,
		});
		hideKillShotBursts(layer.burstPool, 1);
	} else {
		hideKillShotBursts(layer.burstPool, 0);
		layer.activeBurstKey = null;
	}

	return { burstFrameIndex };
}

export function teardownKillShotLayer(layer: KillShotLayer): void {
	layer.beam.clear();
	for (const sprite of layer.tipPool) sprite.destroy();
	layer.tipPool.length = 0;
	for (const sprite of layer.burstPool) sprite.destroy();
	layer.burstPool.length = 0;
	layer.activeBurstKey = null;
}
