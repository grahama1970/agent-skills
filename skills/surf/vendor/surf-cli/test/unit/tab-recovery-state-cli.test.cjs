const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = process.cwd();
const cliPath = path.join(root, 'skills/surf/vendor/surf-cli/native/cli.cjs');
const helpers = require('../../native/host-helpers.cjs');

test('tab.recovery-state maps one exact tab without mutation fields', () => {
  assert.deepEqual(
    helpers.mapToolToMessage('tab.recovery-state', {}, 837358033),
    { type: 'TAB_RECOVERY_STATE', tabId: 837358033 },
  );
  assert.throws(
    () => helpers.mapToolToMessage('tab.recovery-state', {}, undefined),
    /positive integer tabId required/,
  );
});

test('CLI registers tab.recovery-state and preserves strict tab identity', () => {
  const source = fs.readFileSync(cliPath, 'utf8');
  assert.match(source, /"tab\.recovery-state"/);
  assert.match(source, /Number\.isSafeInteger\(tid\)/);

  const malformed = spawnSync(process.execPath, [cliPath, 'tab.recovery-state', '--tab-id', '837358033oops', '--json'], {
    cwd: root,
    encoding: 'utf8',
  });
  assert.notEqual(malformed.status, 0);
  assert.match(malformed.stderr, /--tab-id must be a positive integer/);

  const missing = spawnSync(process.execPath, [cliPath, 'tab.recovery-state', '--json'], {
    cwd: root,
    encoding: 'utf8',
  });
  assert.notEqual(missing.status, 0);
  assert.match(missing.stderr, /requires --tab-id/);
});
