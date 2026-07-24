const assert = require("node:assert/strict");
const test = require("node:test");

const { recoverCloudflareChallenge } = require("../native/chatgpt-client.cjs");

function cloudflareCdp(blockedStates) {
  let index = 0;
  return async (expression) => {
    if (expression.includes("document.readyState")) {
      return { result: { value: "complete" } };
    }
    if (expression.includes("document.title.toLowerCase")) {
      return { result: { value: "chatgpt" } };
    }
    if (expression.includes("hasChallengeText")) {
      const blocked = blockedStates[Math.min(index, blockedStates.length - 1)];
      index += 1;
      return {
        result: {
          value: {
            hasChallengeText: blocked,
            hasComposer: !blocked,
            hasConversation: false,
            hasScript: blocked,
          },
        },
      };
    }
    throw new Error(`unexpected expression: ${expression}`);
  };
}

test("hard reloads the controlled tab once when Cloudflare clears", async () => {
  const commands = [];
  const logs = [];
  const result = await recoverCloudflareChallenge(
    cloudflareCdp([true, false]),
    async (method, params) => commands.push({ method, params }),
    (message) => logs.push(message),
    { reloadWaitMs: 0 },
  );

  assert.deepEqual(result, { detected: true, reloads: 1, recovered: true });
  assert.deepEqual(commands, [{ method: "Page.reload", params: { ignoreCache: true } }]);
  assert.match(logs.join("\n"), /Cloudflare challenge cleared/);
});

test("fails closed when Cloudflare remains after the automatic reload", async () => {
  await assert.rejects(
    recoverCloudflareChallenge(
      cloudflareCdp([true, true]),
      async () => {},
      () => {},
      { reloadWaitMs: 0 },
    ),
    (error) => {
      assert.equal(error.code, "cloudflare_challenge_persisted");
      assert.deepEqual(error.cloudflareRecovery, {
        detected: true,
        reloads: 1,
        recovered: false,
      });
      return true;
    },
  );
});
