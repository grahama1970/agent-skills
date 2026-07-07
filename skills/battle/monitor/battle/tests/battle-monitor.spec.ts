import { expect, test } from "@playwright/test";

test("renders Arena Tau recap graph, drill-down, replay, and chat", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/arena-tau-public-only-002");

  await expect(page.locator('[data-qid="battle:arena:shell"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "Signed token duplicate-claim authorization bypass" })).toBeVisible();
  await expect(page.locator('[data-qid="battle:graph:force"]')).toBeVisible();
  await expect(page.locator('[data-qid="battle:sankey:chart"]')).toBeVisible();
  await expect(page.getByText("BLUE_SUCCESS").first()).toBeVisible();

  await page.locator('[data-qid="battle:graph:node:red"]').click();
  await expect(page.locator('[data-qid="battle:detail:json"]')).toContainText("red_exploit_submission.py");

  await page.locator('[data-qid="battle:graph:node:blue"]').click();
  await expect(page.locator('[data-qid="battle:detail:json"]')).toContainText("blue_patch");

  await page.locator('[data-qid="battle:replay:play"]').click();
  await expect(page.locator('[data-qid="battle:replay:stage"]')).toContainText("Patched replay");
  await page.locator('[data-qid="battle:replay:reset"]').click();
  await expect(page.locator('[data-qid="battle:replay:stage"]')).toContainText("Original replay");

  await page.locator('[data-qid="battle:rail:replay"]').click();
  await expect(page.locator('[data-qid="battle:replay:stage"]')).toContainText("Original replay");

  await page.locator('[data-qid="battle:shared-chat:well:input"]').fill("Pause and inspect the Judge replay receipt.");
  await page.locator('[data-qid="battle:shared-chat:well:send"]').click();
  await expect(page.locator('[data-qid="battle:shared-chat:well:messages"]')).toContainText("battle.human_interjection.v1");

  await page.screenshot({
    path: "test-results/battle-arena-recap.png",
    fullPage: true
  });
});

test("fails closed when Arena artifacts are missing", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/does-not-exist");

  await expect(page.getByRole("heading", { name: "BATTLE MONITOR BLOCKED" })).toBeVisible();
  await expect(page.getByText(/run-receipt\.json/)).toBeVisible();
});
