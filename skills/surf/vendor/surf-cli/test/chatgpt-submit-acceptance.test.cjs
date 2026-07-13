const test = require('node:test');
const assert = require('node:assert/strict');

const { waitForSubmitAccepted } = require('../native/chatgpt-client.cjs');

function cdpState(state) {
  return async () => ({ result: { value: state } });
}

test('composer clearing alone does not prove prompt delivery', async () => {
  await assert.rejects(
    waitForSubmitAccepted(cdpState({
      stopVisible: false,
      composerStillContainsPrompt: false,
      composerChars: 0,
      assistantCount: 9,
      userCount: 56,
      lastUserContainsPrompt: false,
    }), 'batch prompt', 20, { assistantCount: 9, userCount: 56 }),
    /did not accept submitted prompt/,
  );
});

test('a matching new user turn proves prompt delivery', async () => {
  const state = await waitForSubmitAccepted(cdpState({
    stopVisible: false,
    composerStillContainsPrompt: false,
    composerChars: 0,
    assistantCount: 9,
    userCount: 57,
    lastUserContainsPrompt: true,
  }), 'batch prompt', 20, { assistantCount: 9, userCount: 56 });

  assert.equal(state.accepted, true);
});

test('generation or a new assistant turn proves prompt delivery', async () => {
  const generating = await waitForSubmitAccepted(cdpState({
    stopVisible: true,
    composerStillContainsPrompt: true,
    composerChars: 12,
    assistantCount: 9,
    userCount: 56,
    lastUserContainsPrompt: false,
  }), 'batch prompt', 20, { assistantCount: 9, userCount: 56 });
  assert.equal(generating.accepted, true);

  const answered = await waitForSubmitAccepted(cdpState({
    stopVisible: false,
    composerStillContainsPrompt: false,
    composerChars: 0,
    assistantCount: 10,
    userCount: 56,
    lastUserContainsPrompt: false,
  }), 'batch prompt', 20, { assistantCount: 9, userCount: 56 });
  assert.equal(answered.accepted, true);
});
