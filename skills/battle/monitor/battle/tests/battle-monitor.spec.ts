import { expect, test } from "@playwright/test";

test("renders generated Battle artifacts", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/battle-001");

  await expect(page.getByText("Battle Monitor")).toBeVisible();
  await expect(page.getByText("battle-001", { exact: true })).toBeVisible();
  await expect(page.locator(".summaryGrid").getByRole("heading", { name: "BLUE_SUCCESS" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Isstvan" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Phalanx" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Battle Scorekeeper" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Battle Chat" })).toBeVisible();
  await expect(page.getByText("Shared Watch-style chat UX")).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:svg"]')).toBeVisible();
  const artifactList = page.getByRole("list");
  await expect(artifactList.getByText("red-receipt.json", { exact: true })).toBeVisible();
  await expect(artifactList.getByText("scoreboard.json", { exact: true })).toBeVisible();

  await page.locator('[data-qid="battle:chat:input"]').fill("Pause and let the human inspect this exploit evidence.");
  await page.locator('[data-qid="battle:chat:send"]').click();
  await expect(page.locator('[data-qid="battle:chat:receipt-preview"]').getByText("battle.human_interjection.v1")).toBeVisible();
  await expect(page.getByText("LOCAL_PREVIEW")).toBeVisible();

  await page.screenshot({
    path: "test-results/battle-monitor.png",
    fullPage: true
  });
});

test("renders generated Battle v1 context graph artifacts", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/battle-003-arena-context");

  await expect(page.getByText("Battle Monitor")).toBeVisible();
  await expect(page.getByText("battle-003", { exact: true })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Arena Team" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "brandon-bailey" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "coder" })).toBeVisible();
  await expect(page.locator(".summaryGrid").getByRole("heading", { name: "BLUE_SUCCESS" })).toBeVisible();
  await expect(page.locator(".artifactList").getByText("context/memory-store-receipt.json")).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:svg"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:memory"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:scan"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:brave"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:warm-pond"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:warm-pond-execution"]')).toBeVisible();

  await page.locator('[data-qid="battle:graph:node:signal:warm-pond-execution"]').click();
  await expect(page.locator('[data-qid="battle:graph:inspector"]').getByText("executed attempts")).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:inspector"] strong').getByText("PASS", { exact: true })).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:inspector"]').getByText("4 passed / 4 selected / 0 failed")).toBeVisible();

  await page.screenshot({
    path: "test-results/battle-monitor-v1-context-graph.png",
    fullPage: true
  });
});

test("renders Battle v1 operational force graph artifacts", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/battle-v1-operational");

  await expect(page.getByText("Battle Monitor")).toBeVisible();
  await expect(page.getByText("Battle-003 Arena hidden vulnerability race")).toBeVisible();
  await expect(page.getByText("arena-hidden-sqli-xss-race-001")).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Arena Team" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "brandon-bailey" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "coder" })).toBeVisible();
  await expect(page.locator(".playersGrid").getByRole("heading", { name: "Scorekeeper" })).toBeVisible();
  await expect(page.locator(".summaryGrid").getByRole("heading", { name: "BLUE_SUCCESS" })).toBeVisible();
  await expect(page.locator(".artifactList").getByText("context/memory-promotion-receipt.json")).toBeVisible();
  await expect(page.locator(".artifactList").getByText("graph/battle-v1-force-graph.json")).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:svg"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:memory"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:node:signal:warm-pond-execution"]')).toBeVisible();

  await page.locator('[data-qid="battle:graph:node:signal:warm-pond-execution"]').click();
  await expect(page.locator('[data-qid="battle:graph:inspector"]').getByText("executed attempts")).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:inspector"]').getByText("4 passed / 4 selected / 0 failed")).toBeVisible();

  await page.screenshot({
    path: "test-results/battle-monitor-v1-operational.png",
    fullPage: true
  });
});

test("fails closed when artifacts are missing", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/does-not-exist");

  await expect(page.getByRole("heading", { name: "BATTLE MONITOR BLOCKED" })).toBeVisible();
  await expect(page.getByText(/Missing or unreadable Battle artifact/)).toBeVisible();
});
