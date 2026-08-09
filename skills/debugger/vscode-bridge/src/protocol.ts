import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';

export type BridgeBreakpoint = {
  file: string;
  line: number;
};

export type BridgeAuthority = {
  uiKind: string;
  remoteName: string | null;
  extensionHostKind: 'ui' | 'workspace' | 'unknown';
  workspaceUriScheme: string;
  workspaceUriAuthority: string;
  workspacePath: string;
};

export type BridgeArtifactLocations = {
  requestPath?: string;
  statusPath?: string;
  sessionEventsPath?: string;
};

export type BridgeSourceSymbolRange = {
  file: string;
  sourceSha256: string;
  kind: 'function' | 'class' | 'module';
  name: string;
  startLine: number;
  endLine: number;
};

export type BridgeBreakpointEvidence = {
  requested: BridgeBreakpoint;
  vscodeBreakpoint?: BridgeBreakpoint & {
    enabled?: boolean;
  };
  adapter?: {
    verification: 'verified' | 'unverified' | 'unavailable';
    resolved?: BridgeBreakpoint;
    message?: string;
  };
  actual?: {
    file?: string;
    line?: number;
    function?: string;
  };
  sourceSymbolRange?: BridgeSourceSymbolRange;
  relocated: boolean;
  accepted: boolean;
  reason: string;
};

export type BridgeAction =
  | 'start'
  | 'restart'
  | 'process'
  | 'inspect'
  | 'stepOver'
  | 'stepIn'
  | 'stepOut'
  | 'continue'
  | 'pause'
  | 'runTo'
  | 'addBreakpoints'
  | 'removeBreakpoints'
  | 'selectFrame'
  | 'selectThread'
  | 'terminate';

export type BridgeRequest = {
  id?: string;
  action?: BridgeAction;
  workspace?: string;
  launchConfigName?: string;
  breakpoints?: BridgeBreakpoint[];
  removeBreakpoints?: BridgeBreakpoint[];
  runTo?: BridgeBreakpoint;
  locals?: string[];
  watches?: string[];
  allowWatchEval?: boolean;
  output?: string;
  stopTimeoutMs?: number;
  replaceBreakpoints?: boolean;
  saveBeforeStart?: boolean;
  createdAt?: string;
  requestHash?: string;
  maxRequestAgeMs?: number;
  sessionId?: string;
  expectedStopSequence?: number;
  threadId?: number;
  frameId?: number;
  stackDepth?: number;
  expectedRemoteName?: string;
  expectedWorkspaceUriScheme?: string;
  expectedWorkspaceUriAuthority?: string;
  expectedExtensionHostKind?: 'ui' | 'workspace';
};

export type BridgeStoppedState = {
  sessionId?: string;
  stopSequence?: number;
  reason?: string;
  threadId?: number;
  matchedBreakpoint?: boolean;
  error?: string;
  frame?: unknown;
  stackFrames?: unknown[];
  breakpointEvidence?: BridgeBreakpointEvidence[];
  scopes?: unknown[];
  locals?: Record<string, string>;
  watches?: Record<string, string>;
};

export type BridgeSessionStatus = 'starting' | 'running' | 'paused' | 'terminated' | 'failed';

export type BridgeSessionState = {
  schema: 'debugger.session.v1';
  bridgeSessionId: string;
  vscodeSessionId: string;
  vscodeSessionType: string;
  vscodeSessionName: string;
  workspace: string;
  authority?: BridgeAuthority;
  artifactLocations?: BridgeArtifactLocations;
  runtime?: Record<string, unknown>;
  status: BridgeSessionStatus;
  stopSequence: number;
  selectedThreadId?: number;
  selectedFrameId?: number;
  requestedBreakpoints: BridgeBreakpoint[];
  verifiedBreakpoints: BridgeBreakpoint[];
  lastCommandId?: string;
  lastRequestHash?: string;
  updatedAt: string;
  eventLogRef?: string;
};

export type BridgeSessionEvent = {
  schema: 'debugger.session_event.v1';
  sequence: number;
  sessionId: string;
  status: BridgeSessionStatus;
  action?: BridgeAction;
  requestId?: string;
  requestHash?: string;
  threadId?: number;
  frameId?: number;
  reason?: string;
  adapterEvent?: string;
  adapterCommand?: string;
  authority?: BridgeAuthority;
  createdAt: string;
};

export type ProofAssessment = {
  stopProofValid: boolean;
  variableInspectionValid: boolean;
  proofValid: boolean;
  missingLocals: string[];
  missingWatches: string[];
  watchErrors: Record<string, string>;
  capturedLocals: string[];
  capturedWatches: string[];
  reason: string;
};

export type SessionControlAssessment = {
  sessionProofValid: boolean;
  variableInspectionValid: boolean;
  proofValid: boolean;
  sameSession: boolean;
  stopSequenceCurrent: boolean;
  stopSequenceAdvanced: boolean;
  missingLocals: string[];
  missingWatches: string[];
  watchErrors: Record<string, string>;
  capturedLocals: string[];
  capturedWatches: string[];
  reason: string;
};

export type StatusOwner = {
  id?: unknown;
  requestHash?: unknown;
};

export type OwnedStatusWriteDecision = {
  outputPath: string;
  superseded: boolean;
};

export type OwnedStatusWriteResult = OwnedStatusWriteDecision & {
  owner?: StatusOwner;
};

export class AsyncKeyedQueue {
  private readonly tails = new Map<string, Promise<void>>();

  async run<T>(key: string, task: () => Promise<T>): Promise<T> {
    const previous = this.tails.get(key) ?? Promise.resolve();
    let releaseCurrent: () => void = () => undefined;
    const current = new Promise<void>((resolve) => {
      releaseCurrent = resolve;
    });
    const tail = previous.catch(() => undefined).then(() => current);
    this.tails.set(key, tail);

    await previous.catch(() => undefined);
    try {
      return await task();
    } finally {
      releaseCurrent();
      if (this.tails.get(key) === tail) {
        this.tails.delete(key);
      }
    }
  }
}

export function decideOwnedStatusWritePath(
  filePath: string,
  requestId: string,
  requestHash: string,
  currentOwner?: StatusOwner,
): OwnedStatusWriteDecision {
  if (currentOwner && (currentOwner.id !== requestId || currentOwner.requestHash !== requestHash)) {
    return {
      outputPath: path.join(path.dirname(filePath), `status.${safeFileName(requestId)}.superseded.json`),
      superseded: true,
    };
  }
  return { outputPath: filePath, superseded: false };
}

export function invalidRequestStatusPath(statusPath: string, timestamp = new Date()) {
  const stamp = timestamp.toISOString().replace(/[^0-9TZ]/g, '');
  return path.join(path.dirname(statusPath), `status.invalid-request.${stamp}.json`);
}

export function usesSharedRequestOwner(filePath: string) {
  return path.basename(filePath) === 'status.json';
}

export function validateRequest(request: BridgeRequest) {
  const actions = new Set<BridgeAction | undefined>([
    'start',
    'restart',
    'process',
    'inspect',
    'stepOver',
    'stepIn',
    'stepOut',
    'continue',
    'pause',
    'runTo',
    'addBreakpoints',
    'removeBreakpoints',
    'selectFrame',
    'selectThread',
    'terminate',
    undefined,
  ]);
  if (!actions.has(request.action)) {
    throw new Error(`Unsupported debugger bridge action: ${String(request.action)}`);
  }
  if (typeof request.id !== 'string' || request.id.length < 8) {
    throw new Error('Debugger bridge request id must be a non-empty unique string.');
  }
  if (typeof request.requestHash !== 'string' || !/^[0-9a-f]{64}$/i.test(request.requestHash)) {
    throw new Error('Debugger bridge requestHash must be a sha256 hex string.');
  }
  if (request.createdAt !== undefined && Number.isNaN(Date.parse(request.createdAt))) {
    throw new Error(`Debugger bridge request createdAt is invalid: ${request.createdAt}`);
  }
  if (request.stopTimeoutMs !== undefined && (request.stopTimeoutMs < 100 || request.stopTimeoutMs > 300000)) {
    throw new Error('Debugger bridge stopTimeoutMs must be between 100 and 300000.');
  }
  if (
    request.maxRequestAgeMs !== undefined &&
    (!Number.isInteger(request.maxRequestAgeMs) || request.maxRequestAgeMs < 100 || request.maxRequestAgeMs > 300000)
  ) {
    throw new Error('Debugger bridge maxRequestAgeMs must be an integer between 100 and 300000.');
  }
  for (const breakpoint of request.breakpoints ?? []) {
    if (!breakpoint.file || !Number.isInteger(breakpoint.line) || breakpoint.line < 1) {
      throw new Error(`Invalid debugger bridge breakpoint: ${JSON.stringify(breakpoint)}`);
    }
  }
  for (const breakpoint of request.removeBreakpoints ?? []) {
    if (!breakpoint.file || !Number.isInteger(breakpoint.line) || breakpoint.line < 1) {
      throw new Error(`Invalid debugger bridge removeBreakpoints entry: ${JSON.stringify(breakpoint)}`);
    }
  }
  if (request.runTo !== undefined && (!request.runTo.file || !Number.isInteger(request.runTo.line) || request.runTo.line < 1)) {
    throw new Error(`Invalid debugger bridge runTo breakpoint: ${JSON.stringify(request.runTo)}`);
  }
  if (request.locals !== undefined && !Array.isArray(request.locals)) {
    throw new Error('Debugger bridge locals must be an array.');
  }
  if (request.watches !== undefined && !Array.isArray(request.watches)) {
    throw new Error('Debugger bridge watches must be an array.');
  }
  if ((request.watches?.length ?? 0) > 0 && request.allowWatchEval !== true) {
    throw new Error('Debugger bridge watch evaluation requires allowWatchEval: true.');
  }
  if (request.expectedRemoteName !== undefined && typeof request.expectedRemoteName !== 'string') {
    throw new Error('Debugger bridge expectedRemoteName must be a string.');
  }
  if (request.expectedWorkspaceUriScheme !== undefined && typeof request.expectedWorkspaceUriScheme !== 'string') {
    throw new Error('Debugger bridge expectedWorkspaceUriScheme must be a string.');
  }
  if (request.expectedWorkspaceUriAuthority !== undefined && typeof request.expectedWorkspaceUriAuthority !== 'string') {
    throw new Error('Debugger bridge expectedWorkspaceUriAuthority must be a string.');
  }
  if (
    request.expectedExtensionHostKind !== undefined &&
    request.expectedExtensionHostKind !== 'ui' &&
    request.expectedExtensionHostKind !== 'workspace'
  ) {
    throw new Error('Debugger bridge expectedExtensionHostKind must be "ui" or "workspace".');
  }
  validateSessionControlRequest(request);
}

export function requiresBoundSession(action: BridgeAction | undefined) {
  return (
    action === 'inspect' ||
    action === 'stepOver' ||
    action === 'stepIn' ||
    action === 'stepOut' ||
    action === 'continue' ||
    action === 'pause' ||
    action === 'runTo' ||
    action === 'removeBreakpoints' ||
    action === 'selectFrame' ||
    action === 'selectThread' ||
    action === 'terminate'
  );
}

export function validateSessionControlRequest(request: BridgeRequest) {
  if (!requiresBoundSession(request.action)) {
    return;
  }
  if (typeof request.sessionId !== 'string' || request.sessionId.length === 0) {
    throw new Error(`Debugger bridge ${request.action} requires sessionId.`);
  }
  if (!Number.isInteger(request.expectedStopSequence) || (request.expectedStopSequence as number) < 0) {
    throw new Error(`Debugger bridge ${request.action} requires non-negative integer expectedStopSequence.`);
  }
  if (request.threadId !== undefined && (!Number.isInteger(request.threadId) || request.threadId < 0)) {
    throw new Error('Debugger bridge threadId must be a non-negative integer.');
  }
  if (request.frameId !== undefined && (!Number.isInteger(request.frameId) || request.frameId < 0)) {
    throw new Error('Debugger bridge frameId must be a non-negative integer.');
  }
  if (request.stackDepth !== undefined && (!Number.isInteger(request.stackDepth) || request.stackDepth < 1 || request.stackDepth > 50)) {
    throw new Error('Debugger bridge stackDepth must be an integer between 1 and 50.');
  }
}

export function assertExpectedStopSequence(state: BridgeSessionState, request: BridgeRequest) {
  if (request.expectedStopSequence !== state.stopSequence) {
    throw new Error(
      `Debugger bridge stale ${request.action} rejected: expectedStopSequence ${request.expectedStopSequence} does not match current ${state.stopSequence}.`,
    );
  }
}

export function enforceFreshRequest(request: BridgeRequest, nowMs = Date.now()) {
  if (!request.createdAt) {
    throw new Error('Debugger bridge request must include createdAt to prevent stale replay.');
  }
  const maxAgeMs = request.maxRequestAgeMs ?? 120000;
  const ageMs = nowMs - Date.parse(request.createdAt);
  if (ageMs < -30000 || ageMs > maxAgeMs) {
    throw new Error(`Stale debugger bridge request rejected: age ${ageMs}ms exceeds ${maxAgeMs}ms.`);
  }
}

export function withFreshRequestMetadata(request: BridgeRequest): BridgeRequest {
  const prepared = {
    ...request,
    id: request.id ?? `debugger-${crypto.randomUUID()}`,
    createdAt: request.createdAt ?? new Date().toISOString(),
  };
  return {
    ...prepared,
    requestHash: request.requestHash ?? canonicalRequestHash(prepared),
  };
}

export async function verifyPendingStatus(outputPath: string, request: BridgeRequest) {
  const raw = await fs.readFile(outputPath, 'utf8');
  const status = JSON.parse(raw) as { id?: unknown; status?: unknown; requestHash?: unknown };
  if (status.status !== 'pending' || status.id !== request.id || status.requestHash !== request.requestHash) {
    throw new Error('Debugger bridge pending status does not match request id/hash.');
  }
}

export async function isRequestAlreadyClaimed(outputPath: string, requestId: string, requestHash: string) {
  const claimPath = requestClaimPath(outputPath, requestId);
  try {
    const raw = await fs.readFile(claimPath, 'utf8');
    const parsed = JSON.parse(raw) as { requestHash?: unknown };
    if (parsed.requestHash === requestHash) {
      return true;
    }
    throw new Error(`Duplicate debugger bridge request id has different requestHash: ${requestId}`);
  } catch (error) {
    if ((error as { code?: string }).code === 'ENOENT') {
      return false;
    }
    throw error;
  }
}

export async function claimRequestId(outputPath: string, requestId: string, requestHash: string) {
  const claimPath = requestClaimPath(outputPath, requestId);
  const bridgeDir = path.dirname(outputPath);
  await fs.mkdir(path.dirname(claimPath), { recursive: true });
  const handle = await fs.open(claimPath, 'wx').catch((error: { code?: string }) => {
    if (error.code === 'EEXIST') {
      return undefined;
    }
    throw error;
  });
  if (!handle) {
    if (await isRequestAlreadyClaimed(outputPath, requestId, requestHash)) {
      return false;
    }
    throw new Error(`Duplicate debugger bridge request id rejected from atomic claim: ${requestId}`);
  }
  await handle.writeFile(JSON.stringify({ id: requestId, requestHash, claimedAt: new Date().toISOString() }, null, 2) + '\n');
  await handle.close();

  const processedPath = path.join(bridgeDir, 'processed-ids.json');
  const processed = await readProcessedIds(processedPath);
  pruneProcessedIds(processed);
  processed[requestId] = Date.now();
  await writeJsonFile(processedPath, processed);
  return true;
}

export async function writeOwnedJsonFile(
  filePath: string,
  requestId: string,
  requestHash: string,
  body: unknown,
  readCurrentOwner?: () => Promise<StatusOwner | undefined>,
): Promise<OwnedStatusWriteResult> {
  return withStatusFileLock(filePath, async () => {
    const owner = (await readCurrentOwner?.()) ?? (await readStatusOwner(filePath));
    const decision = decideOwnedStatusWritePath(filePath, requestId, requestHash, owner);
    await writeJsonFile(decision.outputPath, body);
    return { ...decision, owner };
  });
}

async function withStatusFileLock<T>(filePath: string, task: () => Promise<T>): Promise<T> {
  const lockPath = `${filePath}.lock`;
  const deadline = Date.now() + 10_000;
  while (true) {
    try {
      await fs.mkdir(lockPath);
      break;
    } catch (error) {
      if ((error as { code?: string }).code !== 'EEXIST') {
        throw error;
      }
      if (Date.now() > deadline) {
        throw new Error(`Timed out waiting for debugger bridge status lock: ${lockPath}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
  try {
    return await task();
  } finally {
    await fs.rm(lockPath, { recursive: true, force: true });
  }
}

function requestClaimPath(outputPath: string, requestId: string) {
  return path.join(path.dirname(outputPath), 'processed-claims', `${safeFileName(requestId)}.json`);
}

export function assessProofValidity(request: BridgeRequest, stoppedState: BridgeStoppedState): ProofAssessment {
  const acceptedBreakpointEvidence =
    (stoppedState.breakpointEvidence ?? []).some((evidence) => evidence.accepted === true);
  const stopProofValid =
    stoppedState.reason === 'breakpoint' &&
    (stoppedState.matchedBreakpoint === true || acceptedBreakpointEvidence) &&
    stoppedState.error === undefined;
  const requestedLocals = request.locals ?? [];
  const requestedWatches = request.watches ?? [];
  const locals = stoppedState.locals ?? {};
  const watches = stoppedState.watches ?? {};
  const missingLocals = requestedLocals.filter((name) => locals[name] === undefined);
  const missingWatches = requestedWatches.filter((expression) => watches[expression] === undefined);
  const watchErrors = Object.fromEntries(
    requestedWatches
      .filter((expression) => typeof watches[expression] === 'string' && watches[expression].startsWith('<error:'))
      .map((expression) => [expression, watches[expression]]),
  );
  const capturedLocals = requestedLocals.filter((name) => locals[name] !== undefined);
  const capturedWatches = requestedWatches.filter(
    (expression) => watches[expression] !== undefined && watchErrors[expression] === undefined,
  );
  const requestedInspectionCount = requestedLocals.length + requestedWatches.length;
  const capturedInspectionCount = capturedLocals.length + capturedWatches.length;
  const variableInspectionValid =
    requestedInspectionCount > 0 &&
    capturedInspectionCount > 0 &&
    missingLocals.length === 0 &&
    missingWatches.length === 0 &&
    Object.keys(watchErrors).length === 0;
  const proofValid = stopProofValid && variableInspectionValid;
  let reason = 'matched breakpoint and inspected requested runtime state';
  if (!stopProofValid) {
    reason = stoppedState.error ?? 'stopped state did not match a requested breakpoint';
  } else if (requestedInspectionCount === 0) {
    reason = 'no locals or watches were requested, so this is breakpoint-only proof';
  } else if (missingLocals.length > 0 || missingWatches.length > 0) {
    reason = 'requested locals or watches were missing from captured runtime state';
  } else if (Object.keys(watchErrors).length > 0) {
    reason = 'one or more requested watch expressions failed';
  } else if (capturedInspectionCount === 0) {
    reason = 'no requested runtime state was captured';
  }
  return {
    stopProofValid,
    variableInspectionValid,
    proofValid,
    missingLocals,
    missingWatches,
    watchErrors,
    capturedLocals,
    capturedWatches,
    reason,
  };
}

export function assessSessionControlValidity(
  request: BridgeRequest,
  previousStopSequence: number,
  stoppedState: BridgeStoppedState,
): SessionControlAssessment {
  const requestedLocals = request.locals ?? [];
  const requestedWatches = request.watches ?? [];
  const locals = stoppedState.locals ?? {};
  const watches = stoppedState.watches ?? {};
  const missingLocals = requestedLocals.filter((name) => locals[name] === undefined);
  const missingWatches = requestedWatches.filter((expression) => watches[expression] === undefined);
  const watchErrors = Object.fromEntries(
    requestedWatches
      .filter((expression) => typeof watches[expression] === 'string' && watches[expression].startsWith('<error:'))
      .map((expression) => [expression, watches[expression]]),
  );
  const capturedLocals = requestedLocals.filter((name) => locals[name] !== undefined);
  const capturedWatches = requestedWatches.filter(
    (expression) => watches[expression] !== undefined && watchErrors[expression] === undefined,
  );
  const requestedInspectionCount = requestedLocals.length + requestedWatches.length;
  const capturedInspectionCount = capturedLocals.length + capturedWatches.length;
  const variableInspectionValid =
    requestedInspectionCount === 0 ||
    (
      capturedInspectionCount > 0 &&
      missingLocals.length === 0 &&
      missingWatches.length === 0 &&
      Object.keys(watchErrors).length === 0
    );
  const sameSession = request.sessionId === stoppedState.sessionId;
  const stopSequenceCurrent = request.action === 'inspect' && stoppedState.stopSequence === previousStopSequence;
  const stopSequenceAdvanced = request.action !== 'inspect' && (stoppedState.stopSequence ?? 0) > previousStopSequence;
  const sessionProofValid =
    sameSession &&
    stoppedState.error === undefined &&
    (stopSequenceCurrent || stopSequenceAdvanced);
  const proofValid = sessionProofValid && variableInspectionValid;

  let reason = 'same session control action produced the expected paused state';
  if (!sameSession) {
    reason = 'stopped state belongs to a different debug session';
  } else if (stoppedState.error !== undefined) {
    reason = stoppedState.error;
  } else if (!stopSequenceCurrent && !stopSequenceAdvanced) {
    reason = request.action === 'inspect'
      ? 'inspect changed or lost the expected stop sequence'
      : 'session control did not advance to a new stopped sequence';
  } else if (!variableInspectionValid) {
    reason = 'requested locals or watches were missing from captured runtime state';
  }

  return {
    sessionProofValid,
    variableInspectionValid,
    proofValid,
    sameSession,
    stopSequenceCurrent,
    stopSequenceAdvanced,
    missingLocals,
    missingWatches,
    watchErrors,
    capturedLocals,
    capturedWatches,
    reason,
  };
}

export function safeFileName(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]/g, '_');
}

async function readProcessedIds(processedPath: string): Promise<Record<string, number>> {
  try {
    const raw = await fs.readFile(processedPath, 'utf8');
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
    );
  } catch (error) {
    if ((error as { code?: string }).code === 'ENOENT') {
      return {};
    }
    throw error;
  }
}

function pruneProcessedIds(processed: Record<string, number>) {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  for (const [id, timestamp] of Object.entries(processed)) {
    if (timestamp < cutoff) {
      delete processed[id];
    }
  }
}

export function resolveWorkspacePath(workspacePath: string, filePath: string, label: string) {
  const resolved = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath);
  return assertWorkspacePath(workspacePath, resolved, label);
}

export function assertWorkspacePath(workspacePath: string, candidatePath: string, label: string) {
  const workspace = path.resolve(workspacePath);
  const resolved = path.resolve(candidatePath);
  const relative = path.relative(workspace, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Debugger bridge ${label} path must stay inside workspace: ${candidatePath}`);
  }
  return resolved;
}

export async function writeJsonFile(filePath: string, body: unknown) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = path.join(
    path.dirname(filePath),
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.${crypto.randomBytes(6).toString('hex')}.tmp`,
  );
  await fs.writeFile(tempPath, JSON.stringify(body, null, 2) + '\n', 'utf8');
  await fs.rename(tempPath, filePath);
}

export function sha256(value: string) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function canonicalRequestHash(request: BridgeRequest) {
  const { requestHash: _requestHash, ...payload } = request;
  return sha256(stableStringify(payload));
}

async function readStatusOwner(filePath: string): Promise<StatusOwner | undefined> {
  try {
    const raw = await fs.readFile(filePath, 'utf8');
    const parsed = JSON.parse(raw) as StatusOwner;
    return { id: parsed.id, requestHash: parsed.requestHash };
  } catch (error) {
    if ((error as { code?: string }).code === 'ENOENT') {
      return undefined;
    }
    throw error;
  }
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, entryValue]) => entryValue !== undefined)
      .sort(([left], [right]) => left.localeCompare(right));
    return `{${entries.map(([key, entryValue]) => `${JSON.stringify(key)}:${stableStringify(entryValue)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
