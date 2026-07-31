// Shared reader for the Pixi-side timeline structure contract. The timeline well
// is 100% Pixi (no DOM hit-targets), so proofs read lane/marker structure from
// the stage-host datasets (data-battle-lanes / data-battle-markers) written each
// frame by the render tick, instead of querying per-lane DOM elements.

const STAGE = '[data-qid="battle:pixi:stage"]';

export async function readLanes(page) {
  return page.evaluate((sel) => JSON.parse(document.querySelector(sel)?.dataset.battleLanes || "[]"), STAGE);
}

export async function readMarkers(page) {
  return page.evaluate((sel) => JSON.parse(document.querySelector(sel)?.dataset.battleMarkers || "[]"), STAGE);
}

export async function laneIds(page) {
  return (await readLanes(page)).map((lane) => lane.id);
}

export async function hasLane(page, id) {
  return (await readLanes(page)).some((lane) => lane.id === id);
}

export async function waitForLane(page, id, timeout = 20000) {
  await page.waitForFunction(
    ([sel, laneId]) => JSON.parse(document.querySelector(sel)?.dataset.battleLanes || "[]").some((lane) => lane.id === laneId),
    [STAGE, id],
    { timeout },
  );
}

// Click the in-canvas Pixi label for a lane using real pointer events (Pixi v8
// requires pointerdown). Selects the lane via the scene's eventMode handler.
export async function clickLane(page, id) {
  await waitForLane(page, id);
  const lane = (await readLanes(page)).find((l) => l.id === id);
  if (!lane) throw new Error(`clickLane: lane ${id} not present in contract`);
  const box = await page.locator("canvas.pixiRaceCanvas").boundingBox();
  await page.mouse.click(box.x + (lane.cx ?? 120), box.y + (lane.cy ?? 20));
}
