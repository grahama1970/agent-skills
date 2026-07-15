const assert = require("node:assert/strict");
const test = require("node:test");

const { KeyedRequestQueue } = require("../native/ai-request-queue.cjs");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("runs requests for different tab keys concurrently", async () => {
  const queue = new KeyedRequestQueue();
  const releaseA = deferred();
  let tabBStarted = false;

  const tabA = queue.enqueue("chatgpt:111", async () => {
    await releaseA.promise;
    return "a";
  });
  const tabB = queue.enqueue("chatgpt:222", async () => {
    tabBStarted = true;
    return "b";
  });

  assert.equal(await tabB, "b");
  assert.equal(tabBStarted, true);
  releaseA.resolve();
  assert.equal(await tabA, "a");
});

test("serializes requests sharing the same tab key", async () => {
  const queue = new KeyedRequestQueue();
  const releaseFirst = deferred();
  const events = [];

  const first = queue.enqueue("chatgpt:111", async () => {
    events.push("first-start");
    await releaseFirst.promise;
    events.push("first-end");
  });
  const second = queue.enqueue("chatgpt:111", async () => {
    events.push("second-start");
  });

  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(events, ["first-start"]);
  releaseFirst.resolve();
  await Promise.all([first, second]);
  assert.deepEqual(events, ["first-start", "first-end", "second-start"]);
});
