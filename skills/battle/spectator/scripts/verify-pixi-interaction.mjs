#!/usr/bin/env node
// Verifies in-canvas Pixi interaction (label selection + playhead scrub) using
// real pointer events via Playwright — the browser-automation click tool cannot
// emit pointerdown, which Pixi v8 requires.
import { chromium } from "playwright";

const host = process.env.BATTLE_HOST ?? "http://127.0.0.1:3003";
const base = `${host}/#battle/receipt?fixture=battle-004-parent-spawn`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const results = {};

async function stageLanes() {
  return page.evaluate(() => JSON.parse(document.querySelector('[data-qid="battle:pixi:stage"]').dataset.battleLanes || "[]"));
}
async function playhead() {
  return page.textContent(".playheadLabel");
}
async function canvasBox() {
  return page.locator("canvas.pixiRaceCanvas").boundingBox();
}

// 1) Scrub: click the track region on the live (non-frozen) route -> playhead moves.
await page.goto(base, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 });
await page.waitForTimeout(1500);
const before = await playhead();
let box = await canvasBox();
await page.mouse.click(box.x + box.width * 0.6, box.y + 24);
await page.waitForTimeout(600);
const after = await playhead();
results.scrub = { before, after, moved: before !== after };

// 2) Selection: on the frozen route with both lanes, click the lane-2 Pixi label -> selection flips.
await page.goto(`${base}&pixiTest=1&pixiSeconds=100`, { waitUntil: "networkidle", timeout: 60000 });
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 });
await page.waitForTimeout(1500);
// select lane-1 first via lane-2 label toggle baseline
const selBefore = (await stageLanes()).filter((l) => l.selected).map((l) => l.id);
box = await canvasBox();
// Click whichever lane is NOT currently selected. Label column is stage x ~120;
// lane rows: lane1 center ~46, lane2 center ~135 (canvas CSS maps stage 1:1).
const wantLane1 = !selBefore.includes("payload-857-receipt");
const targetY = wantLane1 ? 46 : 135;
const expectId = wantLane1 ? "payload-857-receipt" : "payload-857-red-1";
await page.mouse.click(box.x + 120, box.y + targetY);
await page.waitForTimeout(800);
const selAfter = (await stageLanes()).filter((l) => l.selected).map((l) => l.id);
results.selection = { selBefore, selAfter, expectId, changed: selAfter.includes(expectId) && !selAfter.includes(selBefore[0]) };

await browser.close();
const pass = results.scrub.moved && results.selection.changed;
console.log(JSON.stringify({ ...results, pass }, null, 2));
if (!pass) process.exit(1);
console.log("VERIFY_PIXI_INTERACTION_PASS");
