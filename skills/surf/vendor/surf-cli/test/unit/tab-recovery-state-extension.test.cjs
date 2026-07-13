const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('skills/surf/vendor/surf-cli/src/service-worker/index.ts', 'utf8');

test('TAB_RECOVERY_STATE extension handler is read-only and near TAB_RELOAD', () => {
  const reloadIndex = source.indexOf('case "TAB_RELOAD"');
  const recoveryIndex = source.indexOf('case "TAB_RECOVERY_STATE"');
  assert.ok(reloadIndex !== -1, 'TAB_RELOAD handler exists');
  assert.ok(recoveryIndex !== -1, 'TAB_RECOVERY_STATE handler exists');
  assert.ok(recoveryIndex > reloadIndex, 'TAB_RECOVERY_STATE is after TAB_RELOAD');
  assert.ok(recoveryIndex - reloadIndex < 500, 'TAB_RECOVERY_STATE is near TAB_RELOAD');

  const nextCaseIndex = source.indexOf('case "ZOOM_GET"', recoveryIndex);
  const handler = source.slice(recoveryIndex, nextCaseIndex);

  assert.match(handler, /typeof tabId !== "number"/, 'requires an explicit numeric tabId');
  assert.match(handler, /chrome\.tabs\.get\(tabId\)/, 'reads tab identity');
  assert.match(handler, /loadState/, 'returns load state');
  assert.match(handler, /chatgptGeneration/, 'returns ChatGPT generation guard');
  assert.match(handler, /nonEmptyEditableDraft/, 'returns editable draft guard');
  assert.match(handler, /value: "unknown"/, 'guards can be unknown with a reason');
  assert.match(handler, /reason:/, 'guards include reasons');

  assert.doesNotMatch(handler, /chrome\.tabs\.(reload|update|create|remove)\(/, 'does not reload, activate, create, or close tabs');
  assert.doesNotMatch(handler, /postToNativeHost|download/i, 'does not add native routing or download inspection');
});
