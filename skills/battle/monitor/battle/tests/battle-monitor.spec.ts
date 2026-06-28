import { expect, test } from "@playwright/test";

test("renders generated Battle artifacts", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/battle-001");

  await expect(page.getByText("Battle Monitor")).toBeVisible();
  await expect(page.getByText("battle-001", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "BLUE_SUCCESS" })).toBeVisible();
  await expect(page.getByText("Isstvan")).toBeVisible();
  await expect(page.getByText("Phalanx")).toBeVisible();
  await expect(page.getByText("Battle Scorekeeper")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Battle Chat" })).toBeVisible();
  await expect(page.getByText("Shared Watch-style chat UX")).toBeVisible();
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

test("fails closed when artifacts are missing", async ({ page }) => {
  await page.goto("/?artifactBase=/artifacts/does-not-exist");

  await expect(page.getByRole("heading", { name: "BATTLE MONITOR BLOCKED" })).toBeVisible();
  await expect(page.getByText(/Missing or unreadable Battle artifact/)).toBeVisible();
});
