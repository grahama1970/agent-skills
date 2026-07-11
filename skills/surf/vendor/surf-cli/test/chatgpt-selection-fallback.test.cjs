const assert = require("node:assert/strict");
const test = require("node:test");

const { attemptOptionalSelection } = require("../native/chatgpt-client.cjs");

test("records a selected optional browser setting", async () => {
  const result = await attemptOptionalSelection("Model", "Pro", async () => "Pro", () => {});
  assert.deepEqual(result, {
    requested: "Pro",
    selected: "Pro",
    status: "selected",
    error: null,
  });
});

test("preserves current browser setting when requested option is unavailable", async () => {
  const logs = [];
  const result = await attemptOptionalSelection(
    "Reasoning",
    "Nonexistent",
    async () => { throw new Error("Reasoning option not found: Nonexistent"); },
    (message) => logs.push(message),
  );
  assert.deepEqual(result, {
    requested: "Nonexistent",
    selected: null,
    status: "unavailable_using_current",
    error: "Reasoning option not found: Nonexistent",
  });
  assert.match(logs[0], /preserving current browser setting/);
});
