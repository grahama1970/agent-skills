import { Container, Graphics, Sprite, type Texture } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane, LaneEvent } from "../lib/battle-types";
import { textureFromAtlas } from "./battle-race-atlas";
import { effectAtlasFrame } from "./battle-race-icon-map";
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

export type KillShotLayer = {
	container: Container;
	beam: Graphics;
	tipPool: Sprite[];
};

export function createKillShotLayer(): KillShotLayer {
	const container = configureBattleSceneLayer(new Container(), { label: "battle-kill-shots", cullable: true });
	const beam = new Graphics();
	beam.label = "battle-kill-shot-beam";
	container.addChild(beam);
	return { container, beam, tipPool: [] };
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

export function syncKillShots(args: {
	layer: KillShotLayer;
	markerAtlas: Record<string, Texture>;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed: boolean;
	disableParticles: boolean;
	allowEvent: (event: LaneEvent) => boolean;
}): void {
	const {
		layer,
		markerAtlas,
		lanes,
		rowLayout,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed,
		disableParticles,
		allowEvent,
	} = args;

	if (disableParticles) {
		layer.beam.clear();
		hideKillShotTips(layer.tipPool, 0);
		return;
	}

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
		return;
	}

	const primary = activeShots[activeShots.length - 1];
	drawKillShotBeam(layer.beam, primary);

	let tipIndex = 0;
	const boltTexture = textureFromAtlas("marker-blue_blast", markerAtlas);
	if (primary.phase === "travel") {
		const headX = primary.sourceX + (primary.targetX - primary.sourceX) * primary.progress;
		const tipScale = primary.variant === "kill_cannon" ? 1.15 : 0.95;
		tipIndex = placeKillShotTip(layer.tipPool, layer.container, tipIndex, boltTexture, headX, primary.y, tipScale, 0.95);
	} else {
		const impactTextureName =
			primary.impactKind === "killed" ? effectAtlasFrame("killed") : effectAtlasFrame("blocked");
		const impactTexture = textureFromAtlas(impactTextureName, markerAtlas);
		const impactScale = primary.variant === "kill_cannon" ? 1.35 : 1.15;
		tipIndex = placeKillShotTip(
			layer.tipPool,
			layer.container,
			tipIndex,
			impactTexture,
			primary.targetX,
			primary.y,
			impactScale,
			primary.impactAlpha,
		);
	}

	hideKillShotTips(layer.tipPool, tipIndex);
}

export function teardownKillShotLayer(layer: KillShotLayer): void {
	layer.beam.clear();
	for (const sprite of layer.tipPool) sprite.destroy();
	layer.tipPool.length = 0;
}
