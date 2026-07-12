const assert = require("node:assert/strict");
const test = require("node:test");

const { extractAssistantResponse } = require("../native/chatgpt-client.cjs");
const { mapToolToMessage } = require("../native/host-helpers.cjs");

test("maps same-turn wait extraction options into the native request", () => {
  const message = mapToolToMessage("chatgpt.extract", {
    "tab-id": "123",
    sentinel: "done",
    wait: true,
    "stable-polls": "4",
    "no-activate": true,
    timeout: "300",
  });
  assert.equal(message.wait, true);
  assert.equal(message.stablePolls, 4);
  assert.equal(message.noActivate, true);
  assert.equal(message.timeout, 300000);
});

test("wait extraction resumes the existing turn until its sentinel stabilizes", async () => {
  const sentinel = "<<<WEBGPT_DONE:resume-test>>>";
  let polls = 0;
  const cdpEvaluate = async (_tabId, expression) => {
    assert.match(expression, /data-message-author-role/);
    polls += 1;
    const text = polls < 2 ? "still generating" : `finished\n${sentinel}`;
    return { result: { value: {
      text,
      messageId: "turn-current",
      turnIndex: 4,
      source: "assistant-dom",
      sentinelMatch: text.includes(sentinel) ? sentinel : null,
      pageTextContainsSentinel: text.includes(sentinel),
      stopVisible: polls < 2,
      finished: polls >= 2,
      documentHidden: false,
      visibilityState: "visible",
    } } };
  };

  const result = await extractAssistantResponse({
    tabId: 123,
    sentinel,
    timeout: 5000,
    wait: true,
    stablePolls: 1,
    cdpEvaluate,
  });

  assert.equal(result.hasSentinel, true);
  assert.match(result.response, new RegExp(sentinel.replace(/[<>]/g, "\\$&")));
  assert.ok(polls >= 3);
});
