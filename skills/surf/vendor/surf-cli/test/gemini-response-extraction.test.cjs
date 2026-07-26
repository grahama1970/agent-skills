const assert = require("node:assert/strict");
const test = require("node:test");

const {
  assistantSnapshotExpression,
  extractAssistantResponse,
} = require("../native/gemini-tab-client.cjs");

test("Gemini snapshot excludes user-query containers and selects the exact sentinel", () => {
  const sentinel = "<<<GEMINI_DONE:exact>>>";
  const expression = assistantSnapshotExpression(sentinel);

  assert.match(expression, /user-query-content/);
  assert.match(expression, /user-query-container/);
  assert.match(expression, /candidate\.text\.includes\(SENTINEL\)/);
  assert.match(
    expression,
    new RegExp(JSON.stringify(sentinel).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  );
});

test("Gemini extraction does not upgrade a page-level prompt echo to a response", async () => {
  const sentinel = "<<<GEMINI_DONE:prompt-echo>>>";
  const result = await extractAssistantResponse({
    tabId: 123,
    sentinel,
    cdpEvaluate: async () => ({
      result: {
        value: {
          text: "",
          source: "page-text",
          pageTextContainsSentinel: true,
          sentinelMatch: null,
          stopVisible: false,
          finished: false,
        },
      },
    }),
  });

  assert.equal(result.hasSentinel, false);
  assert.equal(result.pageTextContainsSentinel, true);
  assert.equal(result.response, "");
});
