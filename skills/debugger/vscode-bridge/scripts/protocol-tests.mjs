import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import {
  AsyncKeyedQueue,
  assertExpectedStopSequence,
  assertWorkspacePath,
  assessProofValidity,
  assessSessionControlValidity,
  canonicalRequestHash,
  claimRequestId,
  decideOwnedStatusWritePath,
  enforceFreshRequest,
  invalidRequestStatusPath,
  isRequestAlreadyClaimed,
  resolveWorkspacePath,
  usesSharedRequestOwner,
  validateRequest,
  verifyPendingStatus,
  withFreshRequestMetadata,
  writeJsonFile,
  writeOwnedJsonFile,
} from '../out/protocol.js';

async function rejectsWith(fn, pattern) {
  await assert.rejects(fn, (error) => {
    assert.match(error.message, pattern);
    return true;
  });
}

function throwsWith(fn, pattern) {
  assert.throws(fn, (error) => {
    assert.match(error.message, pattern);
    return true;
  });
}

const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'debugger-bridge-protocol.'));
try {
  const workspace = path.join(tempRoot, 'workspace');
  const statusPath = path.join(workspace, '.vscode', 'debugger-bridge', 'status.json');
  const request = withFreshRequestMetadata({
    id: 'debugger-protocol-test',
    action: 'start',
    workspace,
    breakpoints: [{ file: 'src/app.ts', line: 12 }],
    locals: ['value'],
    createdAt: new Date().toISOString(),
    maxRequestAgeMs: 120000,
  });

  validateRequest(request);
  enforceFreshRequest(request);
  assert.equal(request.requestHash, canonicalRequestHash(request));
  assert.equal(resolveWorkspacePath(workspace, '.vscode/debugger-bridge/status.json', 'output'), statusPath);
  assertExpectedStopSequence({ stopSequence: 1 }, { action: 'inspect', expectedStopSequence: 1 });
  throwsWith(
    () => assertExpectedStopSequence({ stopSequence: 2 }, { action: 'inspect', expectedStopSequence: 1 }),
    /stale inspect rejected/,
  );
  validateRequest({
    ...request,
    action: 'inspect',
    sessionId: 'session-1',
    expectedStopSequence: 1,
    threadId: 7,
    frameId: 42,
    stackDepth: 3,
  });
  validateRequest({
    ...request,
    action: 'runTo',
    sessionId: 'session-1',
    expectedStopSequence: 1,
    threadId: 7,
    runTo: { file: 'src/app.ts', line: 13 },
  });
  validateRequest({
    ...request,
    action: 'removeBreakpoints',
    sessionId: 'session-1',
    expectedStopSequence: 1,
    removeBreakpoints: [{ file: 'src/app.ts', line: 12 }],
  });
  validateRequest({
    ...request,
    expectedRemoteName: 'ssh-remote',
    expectedWorkspaceUriScheme: 'file',
    expectedWorkspaceUriAuthority: '',
    expectedExtensionHostKind: 'workspace',
  });

  await writeFile(
    statusPath,
    JSON.stringify({ id: request.id, status: 'pending', requestHash: request.requestHash }, null, 2),
    'utf8',
  ).catch(async (error) => {
    if (error.code !== 'ENOENT') {
      throw error;
    }
    await import('node:fs/promises').then(({ mkdir }) => mkdir(path.dirname(statusPath), { recursive: true }));
    await writeFile(
      statusPath,
      JSON.stringify({ id: request.id, status: 'pending', requestHash: request.requestHash }, null, 2),
      'utf8',
    );
  });
  await verifyPendingStatus(statusPath, request);
  assert.equal(await isRequestAlreadyClaimed(statusPath, request.id, request.requestHash), false);
  await claimRequestId(statusPath, request.id, request.requestHash);
  assert.equal(await isRequestAlreadyClaimed(statusPath, request.id, request.requestHash), true);
  const processed = JSON.parse(await readFile(path.join(path.dirname(statusPath), 'processed-ids.json'), 'utf8'));
  assert.equal(typeof processed[request.id], 'number');
  await rejectsWith(
    () => isRequestAlreadyClaimed(statusPath, request.id, '1'.repeat(64)),
    /different requestHash/,
  );
  assert.equal(await claimRequestId(statusPath, request.id, request.requestHash), false);
  await rejectsWith(() => claimRequestId(statusPath, request.id, '2'.repeat(64)), /different requestHash/);

  assert.deepEqual(decideOwnedStatusWritePath(statusPath, request.id, request.requestHash, undefined), {
    outputPath: statusPath,
    superseded: false,
  });
  assert.deepEqual(
    decideOwnedStatusWritePath(statusPath, request.id, request.requestHash, {
      id: request.id,
      requestHash: request.requestHash,
    }),
    { outputPath: statusPath, superseded: false },
  );
  assert.deepEqual(
    decideOwnedStatusWritePath(statusPath, request.id, request.requestHash, {
      id: 'debugger-newer-request',
      requestHash: '3'.repeat(64),
    }),
    {
      outputPath: path.join(path.dirname(statusPath), `status.${request.id}.superseded.json`),
      superseded: true,
    },
  );
  assert.equal(
    invalidRequestStatusPath(statusPath, new Date('2026-05-26T20:00:01.234Z')),
    path.join(path.dirname(statusPath), 'status.invalid-request.20260526T200001234Z.json'),
  );
  assert.equal(usesSharedRequestOwner(statusPath), true);
  const perRequestStatusPath = path.join(path.dirname(statusPath), `status.${request.id}.json`);
  assert.equal(usesSharedRequestOwner(perRequestStatusPath), false);
  await writeFile(
    perRequestStatusPath,
    JSON.stringify({ id: request.id, status: 'pending', requestHash: request.requestHash }, null, 2),
    'utf8',
  );
  await verifyPendingStatus(perRequestStatusPath, request);

  const queue = new AsyncKeyedQueue();
  const order = [];
  let releaseFirst;
  const firstStarted = queue.run(statusPath, async () => {
    order.push('first-start');
    await new Promise((resolve) => {
      releaseFirst = resolve;
    });
    order.push('first-end');
    return 'first';
  });
  const secondStarted = queue.run(statusPath, async () => {
    order.push('second-start');
    return 'second';
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(order, ['first-start']);
  releaseFirst();
  assert.equal(await firstStarted, 'first');
  assert.equal(await secondStarted, 'second');
  assert.deepEqual(order, ['first-start', 'first-end', 'second-start']);

  const tampered = { ...request, requestHash: '0'.repeat(64) };
  throwsWith(() => validateRequest({ ...request, id: 'short' }), /request id/);
  throwsWith(() => validateRequest({ ...request, requestHash: 'not-a-hash' }), /requestHash/);
  throwsWith(() => validateRequest({ ...request, maxRequestAgeMs: 999999 }), /maxRequestAgeMs/);
  throwsWith(() => validateRequest({ ...request, watches: ['value + 1'] }), /allowWatchEval/);
  throwsWith(() => validateRequest({ ...request, action: 'inspect' }), /requires sessionId/);
  throwsWith(
    () => validateRequest({ ...request, action: 'stepOver', sessionId: 'session-1' }),
    /requires non-negative integer expectedStopSequence/,
  );
  throwsWith(
    () =>
      validateRequest({
        ...request,
        action: 'runTo',
        sessionId: 'session-1',
        expectedStopSequence: 1,
        runTo: { file: '', line: 0 },
      }),
    /Invalid debugger bridge runTo breakpoint/,
  );
  throwsWith(
    () =>
      validateRequest({
        ...request,
        action: 'inspect',
        sessionId: 'session-1',
        expectedStopSequence: 1,
        stackDepth: 99,
      }),
    /stackDepth/,
  );
  throwsWith(() => validateRequest({ ...request, expectedExtensionHostKind: 'browser' }), /expectedExtensionHostKind/);
  throwsWith(() => validateRequest({ ...request, expectedRemoteName: 42 }), /expectedRemoteName/);
  assert.notEqual(tampered.requestHash, canonicalRequestHash(tampered));

  const oldRequest = withFreshRequestMetadata({
    id: 'debugger-protocol-old',
    action: 'start',
    createdAt: new Date(Date.now() - 60_000).toISOString(),
    maxRequestAgeMs: 100,
  });
  throwsWith(() => enforceFreshRequest(oldRequest), /Stale debugger bridge request rejected/);
  throwsWith(() => assertWorkspacePath(workspace, path.join(tempRoot, 'outside.json'), 'output'), /must stay inside workspace/);
  throwsWith(() => resolveWorkspacePath(workspace, '../outside.json', 'output'), /must stay inside workspace/);

  await writeFile(statusPath, JSON.stringify({ id: request.id, status: 'starting', requestHash: request.requestHash }));
  await rejectsWith(() => verifyPendingStatus(statusPath, request), /pending status does not match/);

  const newerRequest = withFreshRequestMetadata({
    id: 'debugger-newer-owner',
    action: 'start',
    workspace,
    createdAt: new Date().toISOString(),
  });
  await writeJsonFile(statusPath, {
    id: newerRequest.id,
    status: 'pending',
    requestHash: newerRequest.requestHash,
  });
  const supersededWrite = await writeOwnedJsonFile(statusPath, request.id, request.requestHash, {
    id: request.id,
    status: 'stopped',
    requestHash: request.requestHash,
  });
  assert.equal(supersededWrite.superseded, true);
  assert.equal(supersededWrite.outputPath, path.join(path.dirname(statusPath), `status.${request.id}.superseded.json`));
  assert.deepEqual(JSON.parse(await readFile(statusPath, 'utf8')), {
    id: newerRequest.id,
    status: 'pending',
    requestHash: newerRequest.requestHash,
  });
  assert.deepEqual(JSON.parse(await readFile(supersededWrite.outputPath, 'utf8')), {
    id: request.id,
    status: 'stopped',
    requestHash: request.requestHash,
  });

  const invalidPath = invalidRequestStatusPath(statusPath, new Date('2026-05-26T20:00:02.000Z'));
  await writeJsonFile(invalidPath, {
    status: 'error',
    error: 'malformed request',
  });
  assert.deepEqual(JSON.parse(await readFile(statusPath, 'utf8')), {
    id: newerRequest.id,
    status: 'pending',
    requestHash: newerRequest.requestHash,
  });
  assert.equal(JSON.parse(await readFile(invalidPath, 'utf8')).error, 'malformed request');

  await rejectsWith(() => verifyPendingStatus(statusPath, request), /pending status does not match/);
  await writeJsonFile(statusPath, {
    id: request.id,
    status: 'pending',
    requestHash: request.requestHash,
  });
  await verifyPendingStatus(statusPath, request);

  const customStatusPath = path.join(workspace, '.vscode', 'debugger-bridge', 'custom-status.json');
  await writeJsonFile(customStatusPath, {
    id: request.id,
    status: 'pending',
    requestHash: request.requestHash,
  });
  const customErrorWrite = await writeOwnedJsonFile(customStatusPath, request.id, request.requestHash, {
    id: request.id,
    status: 'error',
    requestHash: request.requestHash,
    error: 'freshness failed',
  });
  assert.equal(customErrorWrite.outputPath, customStatusPath);
  assert.equal(JSON.parse(await readFile(customStatusPath, 'utf8')).error, 'freshness failed');

  assert.deepEqual(
    assessProofValidity({ breakpoints: [{ file: 'src/app.ts', line: 12 }] }, { reason: 'breakpoint', matchedBreakpoint: true }),
    {
      stopProofValid: true,
      variableInspectionValid: false,
      proofValid: false,
      missingLocals: [],
      missingWatches: [],
      watchErrors: {},
      capturedLocals: [],
      capturedWatches: [],
      reason: 'no locals or watches were requested, so this is breakpoint-only proof',
    },
  );
  assert.equal(
    assessProofValidity(
      { locals: ['value'], watches: ['value + 1'] },
      { reason: 'breakpoint', matchedBreakpoint: true, locals: {}, watches: { 'value + 1': '15' } },
    ).proofValid,
    false,
  );
  assert.equal(
    assessProofValidity(
      { locals: ['value'], watches: ['missing.attr'] },
      { reason: 'breakpoint', matchedBreakpoint: true, locals: { value: '14' }, watches: { 'missing.attr': '<error: nope>' } },
    ).proofValid,
    false,
  );
  assert.equal(
    assessProofValidity(
      { locals: ['value'], watches: ['value + 1'] },
      { reason: 'breakpoint', matchedBreakpoint: true, locals: { value: '14' }, watches: { 'value + 1': '15' } },
    ).proofValid,
    true,
  );
  assert.equal(
    assessProofValidity(
      { locals: ['value'] },
      {
        reason: 'breakpoint',
        matchedBreakpoint: false,
        breakpointEvidence: [
          {
            requested: { file: 'src/app.py', line: 1 },
            actual: { file: 'src/app.py', line: 2, function: 'main' },
            relocated: true,
            accepted: true,
            reason: 'actual stopped frame is an adapter-relocated executable line inside the requested current symbol range',
          },
        ],
        locals: { value: '14' },
      },
    ).proofValid,
    true,
  );
  assert.deepEqual(
    assessSessionControlValidity(
      { action: 'inspect', sessionId: 'session-1', locals: ['value'] },
      3,
      { sessionId: 'session-1', stopSequence: 3, reason: 'inspect', locals: { value: '14' } },
    ),
    {
      sessionProofValid: true,
      variableInspectionValid: true,
      proofValid: true,
      sameSession: true,
      stopSequenceCurrent: true,
      stopSequenceAdvanced: false,
      missingLocals: [],
      missingWatches: [],
      watchErrors: {},
      capturedLocals: ['value'],
      capturedWatches: [],
      reason: 'same session control action produced the expected paused state',
    },
  );
  assert.equal(
    assessSessionControlValidity(
      { action: 'stepOver', sessionId: 'session-1' },
      3,
      { sessionId: 'session-1', stopSequence: 4, reason: 'step' },
    ).proofValid,
    true,
  );
  assert.equal(
    assessSessionControlValidity(
      { action: 'stepIn', sessionId: 'session-1' },
      3,
      { sessionId: 'session-2', stopSequence: 4, reason: 'step' },
    ).proofValid,
    false,
  );

  console.log('debugger bridge protocol tests passed');
} finally {
  await rm(tempRoot, { recursive: true, force: true });
}
