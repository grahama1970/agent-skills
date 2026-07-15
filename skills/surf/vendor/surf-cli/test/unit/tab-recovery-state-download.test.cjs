const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const sourcePath = path.join(__dirname, '../../src/service-worker/index.ts');
const source = fs.readFileSync(sourcePath, 'utf8');

test('TAB_RECOVERY_STATE includes a read-only active download guard', () => {
  const recoveryIndex = source.indexOf('case "TAB_RECOVERY_STATE"');
  assert.notEqual(recoveryIndex, -1, 'TAB_RECOVERY_STATE handler exists');

  const recoveryEnd = source.indexOf('case "ZOOM_GET"', recoveryIndex);
  assert.ok(recoveryEnd > recoveryIndex, 'TAB_RECOVERY_STATE handler has expected boundary');
  const recoveryBlock = source.slice(recoveryIndex, recoveryEnd);

  assert.match(recoveryBlock, /activeDownload:\s*activeDownloadGuard/, 'activeDownload guard is returned with existing guards');
  assert.match(recoveryBlock, /getActiveDownloadRecoveryGuard\(pageState\?\.locationHref \?\? tab\.url\)/, 'guard checks the current tab URL');
});

test('active download guard only queries in-progress downloads and does not mutate downloads', () => {
  assert.match(source, /chrome\.downloads\.search\(\{\s*state:\s*"in_progress"\s*\}\)/, 'queries only in-progress downloads');

  for (const mutator of ['cancel', 'open', 'pause', 'resume', 'erase', 'removeFile', 'acceptDanger']) {
    assert.doesNotMatch(source, new RegExp(`chrome\\.downloads\\.${mutator}\\s*\\(`), `does not call chrome.downloads.${mutator}`);
  }
});

test('active download guard is tri-state and treats errors as unknown', () => {
  assert.match(source, /type RecoveryGuardValue = true \| false \| "unknown";/, 'guard is true/false/unknown');
  assert.match(source, /value:\s*"unknown"[^}]*reason:/s, 'unknown includes a reason');
  assert.match(source, /value:\s*false[^}]*reason:/s, 'false includes a reason');
  assert.match(source, /value:\s*true[^}]*reason:/s, 'true includes a reason');
});
