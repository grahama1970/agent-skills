import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as vscode from 'vscode';
import {
  AsyncKeyedQueue,
  assertExpectedStopSequence,
  type BridgeBreakpoint,
  type BridgeAuthority,
  type BridgeArtifactLocations,
  type BridgeBreakpointEvidence,
  type BridgeRequest,
  type BridgeSessionEvent,
  type BridgeSessionState,
  type BridgeSessionStatus,
  type BridgeSourceSymbolRange,
  assertWorkspacePath,
  assessProofValidity,
  assessSessionControlValidity,
  canonicalRequestHash,
  claimRequestId,
  enforceFreshRequest,
  invalidRequestStatusPath,
  isRequestAlreadyClaimed,
  resolveWorkspacePath as resolveContainedWorkspacePath,
  resolveArtifactPath,
  runtimeArtifactRoot,
  clampExpandLimits,
  classifyWatchExpression,
  redactSecretLikeValue,
  truncateDisplayValue,
  type ExpandLimits,
  sha256,
  usesSharedRequestOwner,
  validateRequest,
  verifyPendingStatus,
  withFreshRequestMetadata,
  writeOwnedJsonFile,
  writeJsonFile,
} from './protocol';

type StoppedState = {
  sessionId: string;
  sessionName: string;
  stopSequence: number;
  reason: string;
  threadId: number;
  frame?: unknown;
  stackFrames?: unknown[];
  matchedBreakpoint?: boolean;
  adapterBreakpointVerification?: string;
  breakpointEvidence?: BridgeBreakpointEvidence[];
  scopes?: unknown[];
  locals?: Record<string, string>;
  watches?: Record<string, string>;
  expanded?: Record<string, unknown>;
  auditedRiskyWatches?: Array<{ expression: string; reason: string }>;
  terminated?: boolean;
  error?: string;
};

type PendingCapture = {
  request: BridgeRequest;
  outputPath: string;
  resolve: (state: StoppedState) => void;
  timer: NodeJS.Timeout;
};

const channel = vscode.window.createOutputChannel('Debugger Bridge');
const pendingBySession = new Map<string, PendingCapture>();
const processedRequestIds = new Set<string>();
const processedRequestHashes = new Map<string, string>();
const activeSessions = new Map<string, vscode.DebugSession>();
const sessionStates = new Map<string, BridgeSessionState>();
const sessionEvents = new Map<string, BridgeSessionEvent[]>();
const requestFileMtimes = new Map<string, number>();
// #1433 breakpoint ownership: the bridge tracks exactly the breakpoints it
// created so it can (a) clear its own stale breakpoints on restart without
// touching the human's, and (b) treat run-to breakpoints as temporary. A
// human breakpoint is any SourceBreakpoint NOT in `ownedBreakpoints`, and the
// bridge must never remove one.
const ownedBreakpoints = new Set<vscode.SourceBreakpoint>();
const temporaryBreakpoints = new Set<vscode.SourceBreakpoint>();
const bridgeQueue = new AsyncKeyedQueue();

function removeOwnedBreakpoints(options: { temporaryOnly?: boolean } = {}) {
  const live = new Set(
    vscode.debug.breakpoints.filter(
      (breakpoint): breakpoint is vscode.SourceBreakpoint => breakpoint instanceof vscode.SourceBreakpoint,
    ),
  );
  const toRemove = [...ownedBreakpoints].filter(
    (breakpoint) => (!options.temporaryOnly || temporaryBreakpoints.has(breakpoint)) && live.has(breakpoint),
  );
  if (toRemove.length > 0) {
    vscode.debug.removeBreakpoints(toRemove);
  }
  for (const breakpoint of toRemove) {
    ownedBreakpoints.delete(breakpoint);
    temporaryBreakpoints.delete(breakpoint);
  }
  // Drop any owned references VS Code no longer knows about (e.g. removed by the
  // human) so the registry cannot leak or resurrect stale entries.
  for (const breakpoint of [...ownedBreakpoints]) {
    if (!live.has(breakpoint)) {
      ownedBreakpoints.delete(breakpoint);
      temporaryBreakpoints.delete(breakpoint);
    }
  }
  return toRemove.map((breakpoint) => ({
    file: breakpoint.location.uri.fsPath,
    line: breakpoint.location.range.start.line + 1,
  }));
}
let watcher: vscode.FileSystemWatcher | undefined;
let extensionHostKind: BridgeAuthority['extensionHostKind'] = 'unknown';

export function activate(context: vscode.ExtensionContext) {
  channel.appendLine('Debugger Bridge activated.');
  extensionHostKind = context.extension.extensionKind === vscode.ExtensionKind.Workspace
    ? 'workspace'
    : context.extension.extensionKind === vscode.ExtensionKind.UI
      ? 'ui'
      : 'unknown';

  context.subscriptions.push(channel);
  context.subscriptions.push(
    vscode.commands.registerCommand('debuggerBridge.processRequestFile', async () => {
      await processWorkspaceRequestFile();
    }),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('debuggerBridge.startLaunchConfig', async () => {
      const launchConfigName = await vscode.window.showInputBox({
        prompt: 'Launch configuration name',
        value: 'Debug with $debugger',
      });
      if (!launchConfigName) {
        return;
      }
      const request = withFreshRequestMetadata({ action: 'start', launchConfigName });
      await processBridgeRequest(request, request.requestHash);
    }),
  );
  context.subscriptions.push(
    vscode.debug.registerDebugAdapterTrackerFactory('*', {
      createDebugAdapterTracker(session) {
        return {
          onDidSendMessage(message) {
            void handleDebugAdapterMessage(session, message);
          },
        };
      },
    }),
  );
  context.subscriptions.push(
    vscode.debug.onDidStartDebugSession((session) => {
      activeSessions.set(session.id, session);
      upsertSessionState(session, undefined, 'running', {
        selectedThreadId: undefined,
        selectedFrameId: undefined,
      });
    }),
  );
  context.subscriptions.push(
    vscode.debug.onDidTerminateDebugSession((session) => {
      upsertSessionState(session, undefined, 'terminated');
      activeSessions.delete(session.id);
    }),
  );

  setupWorkspaceWatcher(context);
}

export function deactivate() {
  watcher?.dispose();
}

function setupWorkspaceWatcher(context: vscode.ExtensionContext) {
  watcher?.dispose();
  watcher = vscode.workspace.createFileSystemWatcher('**/.vscode/debugger-bridge/request.json');
  context.subscriptions.push(watcher);
  watcher.onDidCreate((uri) => void processRequestUri(uri), null, context.subscriptions);
  watcher.onDidChange((uri) => void processRequestUri(uri), null, context.subscriptions);
  const poller = setInterval(() => void pollWorkspaceRequestFiles(), 1000);
  context.subscriptions.push({ dispose: () => clearInterval(poller) });
}

async function pollWorkspaceRequestFiles() {
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const requestUri = vscode.Uri.joinPath(folder.uri, '.vscode', 'debugger-bridge', 'request.json');
    try {
      const stat = await vscode.workspace.fs.stat(requestUri);
      const priorMtime = requestFileMtimes.get(requestUri.fsPath);
      if (priorMtime === stat.mtime) {
        continue;
      }
      requestFileMtimes.set(requestUri.fsPath, stat.mtime);
      await processRequestUri(requestUri);
    } catch (error) {
      if ((error as { code?: string }).code === 'FileNotFound' || (error as { code?: string }).code === 'ENOENT') {
        continue;
      }
      channel.appendLine(`Debugger bridge request poll failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

async function processWorkspaceRequestFile(options: { missingOk?: boolean } = {}) {
  const folder = firstWorkspaceFolder();
  if (!folder) {
    throw new Error('No VS Code workspace folder is open.');
  }
  const requestUri = vscode.Uri.joinPath(folder.uri, '.vscode', 'debugger-bridge', 'request.json');
  try {
    await processRequestUri(requestUri);
  } catch (error) {
    if (!options.missingOk) {
      throw error;
    }
  }
}

async function processRequestUri(uri: vscode.Uri) {
  let raw = '';
  let parsedRequest: BridgeRequest | undefined;
  let parsedHash: string | undefined;
  try {
    const bytes = await vscode.workspace.fs.readFile(uri);
    raw = Buffer.from(bytes).toString('utf8');
    parsedRequest = JSON.parse(raw) as BridgeRequest;
    parsedHash = canonicalRequestHash(parsedRequest);
    await processBridgeRequest(parsedRequest, parsedHash, true, uri.fsPath);
  } catch (error) {
    const statusPath = requestErrorStatusPath(uri.fsPath, parsedRequest);
    const errorStatus = {
      id: parsedRequest?.id,
      status: 'error',
      proofValid: false,
      error: error instanceof Error ? error.message : String(error),
      requestHash: parsedHash ?? (raw ? sha256(raw) : undefined),
      updatedAt: new Date().toISOString(),
    };
    if (typeof parsedRequest?.id === 'string' && typeof parsedRequest?.requestHash === 'string') {
      await writeOwnedStatus(statusPath, parsedRequest.id, parsedRequest.requestHash, errorStatus, true);
    } else {
      await writeStatus(invalidRequestStatusPath(statusPath), errorStatus);
    }
    throw error;
  }
}

function requestErrorStatusPath(requestFilePath: string, request?: BridgeRequest) {
  const bridgeDir = path.dirname(requestFilePath);
  const sharedStatusPath = path.join(bridgeDir, 'status.json');
  if (!request || typeof request.output !== 'string') {
    return sharedStatusPath;
  }
  const workspacePath =
    typeof request.workspace === 'string'
      ? request.workspace
      : path.dirname(path.dirname(path.dirname(requestFilePath)));
  try {
    const { resolved, location } = resolveArtifactPath(workspacePath, request.output, 'output');
    if (location === 'runtime') {
      return resolved;
    }
    // #1440: an error status must never land at an arbitrary workspace path --
    // that would create a bridge-authored file the repo could stage. Workspace
    // outputs only get the error if they are inside the bridge dir itself;
    // anything else routes to the shared bridge status.
    const relativeToBridge = path.relative(bridgeDir, resolved);
    if (!relativeToBridge.startsWith('..') && !path.isAbsolute(relativeToBridge)) {
      return resolved;
    }
    channel.appendLine(
      `Debugger bridge routed an error status away from unprotected workspace path ${request.output} (#1440).`,
    );
    return invalidRequestStatusPath(sharedStatusPath);
  } catch (error) {
    channel.appendLine(`Debugger bridge could not resolve request output for error status: ${String(error)}`);
    return invalidRequestStatusPath(sharedStatusPath);
  }
}

async function processBridgeRequest(
  request: BridgeRequest,
  computedRequestHash?: string,
  requirePendingStatus = false,
  requestPath?: string,
) {
  validateRequest(request);
  if (!vscode.workspace.isTrusted) {
    throw new Error('Debugger bridge refuses to run in an untrusted VS Code workspace.');
  }
  const requestId = request.id as string;
  const requestHash = request.requestHash as string;
  const folder = resolveWorkspaceFolder(request.workspace);
  const outputPath = await resolveRuntimeOutputPath(folder, request);
  const authority = buildBridgeAuthority(folder);
  validateBridgeAuthority(request, authority);
  const artifactLocations: BridgeArtifactLocations = {
    requestPath,
    statusPath: outputPath,
  };
  if (requestHash !== computedRequestHash) {
    throw new Error('Debugger bridge requestHash does not match canonical request content.');
  }
  await bridgeQueue.run('vscode-debugger-session', () =>
    processBridgeRequestForOutput(request, requestId, requestHash, folder, outputPath, requirePendingStatus, authority, artifactLocations),
  );
}

async function processBridgeRequestForOutput(
  request: BridgeRequest,
  requestId: string,
  requestHash: string,
  folder: vscode.WorkspaceFolder,
  outputPath: string,
  requirePendingStatus: boolean,
  authority: BridgeAuthority,
  artifactLocations: BridgeArtifactLocations,
) {
  if (processedRequestIds.has(requestId)) {
    if (processedRequestHashes.get(requestId) === requestHash) {
      channel.appendLine(`Ignoring duplicate debugger bridge request already in progress or processed: ${requestId}`);
      return;
    }
    throw new Error(`Duplicate debugger bridge request id rejected with different requestHash: ${requestId}`);
  }
  if (await isRequestAlreadyClaimed(outputPath, requestId, requestHash)) {
    channel.appendLine(`Ignoring duplicate debugger bridge request already claimed: ${requestId}`);
    return;
  }
  enforceFreshRequest(request);
  if (requirePendingStatus) {
    await verifyPendingStatus(outputPath, request);
  }
  const claimed = await claimRequestId(outputPath, requestId, requestHash);
  if (!claimed) {
    channel.appendLine(`Ignoring duplicate debugger bridge request claimed concurrently: ${requestId}`);
    return;
  }
  processedRequestIds.add(requestId);
  processedRequestHashes.set(requestId, requestHash);
  const action = request.action ?? 'start';
  const statusBase = {
    id: request.id,
    requestHash,
    proofValid: false,
    authority,
    artifactLocations,
  };
  if (isSessionControlAction(action)) {
    await processSessionControlRequest(request, requestId, requestHash, folder, outputPath, statusBase, requirePendingStatus);
    return;
  }
  if (action === 'addBreakpoints') {
    await prepareSourceFiles(folder, request);
    const addedBreakpoints = await replaceRequestedBreakpoints(folder, request);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'breakpoints-added',
      addedBreakpoints,
      adapterBreakpointVerification: 'unavailable-vscode-api',
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }

  if (action !== 'start' && action !== 'restart' && action !== 'process') {
    throw new Error(`Unsupported debugger bridge action: ${action}`);
  }

  await writeOwnedStatus(outputPath, requestId, requestHash, {
    ...statusBase,
    status: 'starting',
    launchConfigName: request.launchConfigName,
    breakpoints: request.breakpoints ?? [],
    updatedAt: new Date().toISOString(),
  }, requirePendingStatus);

  await prepareSourceFiles(folder, request);
  const addedBreakpoints = await replaceRequestedBreakpoints(folder, request);
  if (action === 'restart') {
    await stopActiveDebugSession();
  }
  const correlationToken = `${requestId}:${requestHash.slice(0, 16)}`;
  const correlatedConfig = resolveLaunchConfiguration(folder, request.launchConfigName, correlationToken);
  const stopped = waitForStoppedState(request, outputPath, { correlationToken });
  const ok = await vscode.debug.startDebugging(
    folder,
    correlatedConfig ?? request.launchConfigName ?? 'Debug with $debugger',
  );
  if (!ok) {
    throw new Error(`VS Code refused to start debug configuration: ${request.launchConfigName ?? 'Debug with $debugger'}`);
  }

  await writeOwnedStatus(outputPath, requestId, requestHash, {
    ...statusBase,
    status: 'running',
    launchConfigName: request.launchConfigName,
    addedBreakpoints,
    updatedAt: new Date().toISOString(),
  }, requirePendingStatus);

  try {
    const stoppedState = await stopped;
    const proofAssessment = assessProofValidity(request, stoppedState);
    const sessionState = sessionStates.get(stoppedState.sessionId);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: proofAssessment.proofValid ? 'stopped' : 'stopped-not-proof',
      proofValid: proofAssessment.proofValid,
      proofAssessment,
      launchConfigName: request.launchConfigName,
      addedBreakpoints,
      stoppedState,
      sessionState,
      eventLog: stoppedState.sessionId ? sessionEvents.get(stoppedState.sessionId) ?? [] : [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
  } catch (error) {
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'error',
      launchConfigName: request.launchConfigName,
      addedBreakpoints,
      error: error instanceof Error ? error.message : String(error),
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    throw error;
  }
}

function isSessionControlAction(action: string) {
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

async function processSessionControlRequest(
  request: BridgeRequest,
  requestId: string,
  requestHash: string,
  folder: vscode.WorkspaceFolder,
  outputPath: string,
  statusBase: {
    id: string | undefined;
    requestHash: string;
    proofValid: boolean;
    authority: BridgeAuthority;
    artifactLocations: BridgeArtifactLocations;
  },
  requirePendingStatus: boolean,
) {
  const session = sessionForRequest(request);
  const currentState = currentSessionState(session, request);
  assertExpectedStopSequence(currentState, request);
  const threadId = request.threadId ?? currentState.selectedThreadId;

  if (request.action === 'inspect') {
    if (threadId === undefined) {
      throw new Error('Debugger bridge inspect requires selected or requested threadId.');
    }
    const stoppedState = await captureStoppedState(
      session,
      threadId,
      'inspect',
      request,
      request.frameId ?? currentState.selectedFrameId,
    );
    stoppedState.stopSequence = currentState.stopSequence;
    const sessionProofAssessment = assessSessionControlValidity(request, currentState.stopSequence, stoppedState);
    const sessionState = upsertSessionState(session, request, 'paused', {
      selectedThreadId: threadId,
      selectedFrameId: frameIdFromState(stoppedState) ?? currentState.selectedFrameId,
    }, { preserveStopSequence: true });
    await writeSessionEvents(folder, session.id);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'inspected',
      proofValid: sessionProofAssessment.proofValid,
      stoppedState,
      sessionState,
      sessionProofAssessment,
      eventLog: sessionEvents.get(session.id) ?? [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }

  if (request.action === 'selectThread' || request.action === 'selectFrame') {
    const sessionState = upsertSessionState(session, request, currentState.status, {
      selectedThreadId: request.threadId ?? currentState.selectedThreadId,
      selectedFrameId: request.frameId ?? currentState.selectedFrameId,
    });
    await writeSessionEvents(folder, session.id);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'selected',
      sessionState,
      eventLog: sessionEvents.get(session.id) ?? [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }

  if (request.action === 'removeBreakpoints') {
    const removedBreakpoints = removeRequestedBreakpoints(folder, request.removeBreakpoints ?? request.breakpoints ?? []);
    const sessionState = upsertSessionState(session, request, currentState.status);
    await writeSessionEvents(folder, session.id);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'breakpoints-removed',
      removedBreakpoints,
      sessionState,
      eventLog: sessionEvents.get(session.id) ?? [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }

  if (request.action === 'terminate') {
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'terminating',
      sessionState: upsertSessionState(session, request, 'running'),
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    await vscode.debug.stopDebugging(session);
    const sessionState = upsertSessionState(session, request, 'terminated');
    await writeSessionEvents(folder, session.id);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'terminated',
      sessionState,
      eventLog: sessionEvents.get(session.id) ?? [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }

  await prepareSourceFiles(folder, request);
  let addedBreakpoints: unknown[] = [];
  if (request.action === 'runTo' && request.runTo) {
    addedBreakpoints = await addRequestedBreakpoints(folder, [request.runTo], { temporary: true });
  } else if ((request.breakpoints?.length ?? 0) > 0) {
    addedBreakpoints = await replaceRequestedBreakpoints(folder, request);
  }

  const stopped = request.action === 'pause'
    ? waitForStoppedState(request, outputPath, { sessionId: session.id })
    : request.action === 'continue' || request.action === 'stepOver' || request.action === 'stepIn' || request.action === 'stepOut' || request.action === 'runTo'
      ? waitForStoppedState(request, outputPath, { sessionId: session.id })
      : undefined;
  await writeOwnedStatus(outputPath, requestId, requestHash, {
    ...statusBase,
    status: request.action === 'pause' ? 'pausing' : 'running',
    sessionState: upsertSessionState(session, request, 'running'),
    addedBreakpoints,
    updatedAt: new Date().toISOString(),
  }, requirePendingStatus);

  if (request.action === 'pause') {
    await sendThreadRequest(session, 'pause', threadId);
  } else if (request.action === 'continue' || request.action === 'runTo') {
    await sendThreadRequest(session, 'continue', threadId);
  } else if (request.action === 'stepOver') {
    await sendThreadRequest(session, 'next', threadId);
  } else if (request.action === 'stepIn') {
    await sendThreadRequest(session, 'stepIn', threadId);
  } else if (request.action === 'stepOut') {
    await sendThreadRequest(session, 'stepOut', threadId);
  }

  if (!stopped) {
    return;
  }
  const stoppedState = await stopped;
  if (request.action === 'runTo') {
    // A run-to breakpoint is temporary: remove it on the terminal path so it
    // does not linger as a surprise stop later (#1433). Proof for run-to is
    // matched against the run-to destination, not request.breakpoints.
    removeOwnedBreakpoints({ temporaryOnly: true });
  }
  if (stoppedState.terminated) {
    // The program ran to completion instead of hitting another stop. That is a
    // valid terminal outcome, distinct from a timeout (#1432).
    const sessionState = upsertSessionState(session, request, 'terminated');
    await writeSessionEvents(folder, session.id);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'terminated',
      sessionState,
      eventLog: sessionEvents.get(session.id) ?? [],
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    return;
  }
  const sessionProofAssessment = assessSessionControlValidity(request, currentState.stopSequence, stoppedState);
  const sessionState = sessionStates.get(session.id);
  await writeSessionEvents(folder, session.id);
  await writeOwnedStatus(outputPath, requestId, requestHash, {
    ...statusBase,
    status: sessionProofAssessment.proofValid ? 'stopped' : 'stopped-not-proof',
    proofValid: sessionProofAssessment.proofValid,
    sessionProofAssessment,
    addedBreakpoints,
    stoppedState,
    sessionState,
    eventLog: sessionEvents.get(session.id) ?? [],
    updatedAt: new Date().toISOString(),
  }, requirePendingStatus);
}

function sessionForRequest(request: BridgeRequest) {
  const session = activeSessions.get(request.sessionId ?? '') ?? (
    vscode.debug.activeDebugSession?.id === request.sessionId ? vscode.debug.activeDebugSession : undefined
  );
  if (!session) {
    throw new Error(`Debugger bridge sessionId is not active: ${request.sessionId}`);
  }
  return session;
}

function currentSessionState(session: vscode.DebugSession, request: BridgeRequest) {
  const state = sessionStates.get(session.id);
  if (!state) {
    throw new Error(`Debugger bridge has no session state for sessionId: ${request.sessionId}`);
  }
  return state;
}

async function sendThreadRequest(session: vscode.DebugSession, command: string, threadId?: number) {
  if (threadId === undefined) {
    throw new Error(`Debugger bridge ${command} requires selected or requested threadId.`);
  }
  await session.customRequest(command, { threadId });
}

function removeRequestedBreakpoints(folder: vscode.WorkspaceFolder, breakpoints: BridgeBreakpoint[]) {
  const targets = new Set(
    breakpoints.map((breakpoint) => `${resolveBreakpointPath(folder, breakpoint)}:${breakpoint.line}`),
  );
  const staleBreakpoints = vscode.debug.breakpoints.filter((breakpoint): breakpoint is vscode.SourceBreakpoint => {
    if (!(breakpoint instanceof vscode.SourceBreakpoint)) {
      return false;
    }
    // Only remove breakpoints the bridge owns: a human breakpoint at the same
    // file:line must survive an agent removeBreakpoints request (#1433).
    if (!ownedBreakpoints.has(breakpoint)) {
      return false;
    }
    return targets.has(`${breakpoint.location.uri.fsPath}:${breakpoint.location.range.start.line + 1}`);
  });
  if (staleBreakpoints.length > 0) {
    vscode.debug.removeBreakpoints(staleBreakpoints);
    for (const breakpoint of staleBreakpoints) {
      ownedBreakpoints.delete(breakpoint);
      temporaryBreakpoints.delete(breakpoint);
    }
  }
  return staleBreakpoints.map((breakpoint) => ({
    file: breakpoint.location.uri.fsPath,
    line: breakpoint.location.range.start.line + 1,
  }));
}

function upsertSessionState(
  session: vscode.DebugSession,
  request: BridgeRequest | undefined,
  status: BridgeSessionStatus,
  patch: Partial<
    Pick<
      BridgeSessionState,
      'runtime' | 'selectedThreadId' | 'selectedFrameId' | 'requestedBreakpoints' | 'verifiedBreakpoints'
    >
  > = {},
  options: { preserveStopSequence?: boolean } = {},
) {
  const prior = sessionStates.get(session.id);
  const isStopped = status === 'paused';
  const stopSequence = isStopped && !options.preserveStopSequence ? (prior?.stopSequence ?? 0) + 1 : (prior?.stopSequence ?? 0);
  const state: BridgeSessionState = {
    schema: 'debugger.session.v1',
    bridgeSessionId: `vscode:${session.id}`,
    vscodeSessionId: session.id,
    vscodeSessionType: session.type,
    vscodeSessionName: session.name,
    workspace: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '',
    authority: bridgeAuthorityForCurrentWorkspace(),
    artifactLocations: {
      sessionEventsPath: path.join(
        runtimeArtifactRoot(vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? ''),
        `session-events.${safeSessionId(session.id)}.json`,
      ),
    },
    runtime: patch.runtime ?? prior?.runtime,
    status,
    stopSequence,
    selectedThreadId: patch.selectedThreadId ?? prior?.selectedThreadId,
    selectedFrameId: patch.selectedFrameId ?? prior?.selectedFrameId,
    requestedBreakpoints: patch.requestedBreakpoints ?? prior?.requestedBreakpoints ?? request?.breakpoints ?? [],
    verifiedBreakpoints: patch.verifiedBreakpoints ?? prior?.verifiedBreakpoints ?? [],
    lastCommandId: request?.id ?? prior?.lastCommandId,
    lastRequestHash: request?.requestHash ?? prior?.lastRequestHash,
    updatedAt: new Date().toISOString(),
    eventLogRef: `.vscode/debugger-bridge/session-events.${safeSessionId(session.id)}.json`,
  };
  sessionStates.set(session.id, state);
  recordSessionEvent(state, request, status);
  return state;
}

function recordSessionEvent(state: BridgeSessionState, request: BridgeRequest | undefined, status: BridgeSessionStatus) {
  const events = sessionEvents.get(state.vscodeSessionId) ?? [];
  events.push({
    schema: 'debugger.session_event.v1',
    sequence: events.length + 1,
    sessionId: state.vscodeSessionId,
    status,
    // Origin is a claim we can defend: an event carrying a request is an agent
    // action; without one it is external to the bridge. We never fabricate
    // 'human_ui' -- an adapter stop and a human UI action are indistinguishable
    // from a stopped event, so both record 'unknown_external' (#1435).
    origin: request ? 'agent_request' : 'unknown_external',
    action: request?.action,
    requestId: request?.id,
    requestHash: request?.requestHash,
    threadId: state.selectedThreadId,
    frameId: state.selectedFrameId,
    authority: state.authority,
    createdAt: state.updatedAt,
  });
  sessionEvents.set(state.vscodeSessionId, events);
}

async function writeSessionEvents(folder: vscode.WorkspaceFolder, sessionId: string) {
  const events = sessionEvents.get(sessionId) ?? [];
  // Session events carry paused runtime detail: keep them out of the worktree (#1440).
  const eventPath = path.join(
    runtimeArtifactRoot(folder.uri.fsPath),
    `session-events.${safeSessionId(sessionId)}.json`,
  );
  await writeJsonFile(eventPath, events);
}

function safeSessionId(value: string) {
  return value.replace(/[^a-zA-Z0-9_.-]/g, '_');
}

function bridgeAuthorityForCurrentWorkspace() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    return undefined;
  }
  return buildBridgeAuthority(folder);
}

function buildBridgeAuthority(folder: vscode.WorkspaceFolder): BridgeAuthority {
  return {
    uiKind: vscode.UIKind[vscode.env.uiKind] ?? String(vscode.env.uiKind),
    remoteName: vscode.env.remoteName ?? null,
    extensionHostKind,
    workspaceUriScheme: folder.uri.scheme,
    workspaceUriAuthority: folder.uri.authority,
    workspacePath: folder.uri.fsPath,
  };
}

function validateBridgeAuthority(request: BridgeRequest, authority: BridgeAuthority) {
  const mismatches: string[] = [];
  if (request.expectedRemoteName !== undefined && request.expectedRemoteName !== (authority.remoteName ?? '')) {
    mismatches.push(`remoteName expected ${request.expectedRemoteName || '<local>'} got ${authority.remoteName ?? '<local>'}`);
  }
  if (
    request.expectedWorkspaceUriScheme !== undefined &&
    request.expectedWorkspaceUriScheme !== authority.workspaceUriScheme
  ) {
    mismatches.push(
      `workspaceUriScheme expected ${request.expectedWorkspaceUriScheme} got ${authority.workspaceUriScheme}`,
    );
  }
  if (
    request.expectedWorkspaceUriAuthority !== undefined &&
    request.expectedWorkspaceUriAuthority !== authority.workspaceUriAuthority
  ) {
    mismatches.push(
      `workspaceUriAuthority expected ${request.expectedWorkspaceUriAuthority || '<none>'} got ${
        authority.workspaceUriAuthority || '<none>'
      }`,
    );
  }
  if (
    request.expectedExtensionHostKind !== undefined &&
    request.expectedExtensionHostKind !== authority.extensionHostKind
  ) {
    mismatches.push(
      `extensionHostKind expected ${request.expectedExtensionHostKind} got ${authority.extensionHostKind}`,
    );
  }
  if (mismatches.length > 0) {
    throw new Error(
      `debugger_bridge_authority_mismatch: ${mismatches.join('; ')}. Install/update the bridge in the active workspace extension host and rerun the request from that workspace.`,
    );
  }
}

function frameIdFromState(state: StoppedState) {
  const frameId = (state.frame as { id?: unknown } | undefined)?.id;
  return typeof frameId === 'number' ? frameId : undefined;
}

async function prepareSourceFiles(folder: vscode.WorkspaceFolder, request: BridgeRequest) {
  if (request.saveBeforeStart === false) {
    return;
  }
  const requestedFiles = new Set((request.breakpoints ?? []).map((breakpoint) => resolveBreakpointPath(folder, breakpoint)));
  for (const document of vscode.workspace.textDocuments) {
    if (requestedFiles.has(document.uri.fsPath) && document.isDirty) {
      await document.save();
    }
  }
}

async function stopActiveDebugSession() {
  // Stop EVERY live debug session, not just the active one. A restart that left
  // only the "active" session alive let prior paused/zombie sessions pile up
  // until the adapter stopped binding new breakpoints (observed: a walkthrough
  // that restarts repeatedly degraded after ~10 sessions). We wait until all
  // tracked sessions have actually terminated before returning.
  const sessions = new Set<vscode.DebugSession>();
  if (vscode.debug.activeDebugSession) {
    sessions.add(vscode.debug.activeDebugSession);
  }
  for (const session of activeSessions.values()) {
    sessions.add(session);
  }
  if (sessions.size === 0) {
    return;
  }
  const remaining = new Set([...sessions].map((session) => session.id));
  await new Promise<void>((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      subscription.dispose();
      resolve();
    };
    const timer = setTimeout(finish, 8000);
    const subscription = vscode.debug.onDidTerminateDebugSession((terminated) => {
      remaining.delete(terminated.id);
      if (remaining.size === 0) {
        finish();
      }
    });
    // stopDebugging() with no argument stops all sessions; also stop each tracked
    // session explicitly in case some are not the current root.
    void Promise.all([
      vscode.debug.stopDebugging(),
      ...[...sessions].map((session) => Promise.resolve(vscode.debug.stopDebugging(session)).catch(() => undefined)),
    ]).then(() => undefined, () => finish());
  });
}

async function replaceRequestedBreakpoints(folder: vscode.WorkspaceFolder, request: BridgeRequest) {
  const breakpoints = request.breakpoints ?? [];
  if (request.replaceBreakpoints !== false) {
    // Clear every breakpoint THIS bridge owns, in any file -- otherwise a
    // breakpoint left in another file by a prior request is hit before the
    // requested line (#1433). Human breakpoints are not in the owned set and
    // are deliberately preserved across restart / run-to / cleanup.
    removeOwnedBreakpoints();
  }
  return addRequestedBreakpoints(folder, breakpoints);
}

async function addRequestedBreakpoints(
  folder: vscode.WorkspaceFolder,
  breakpoints: BridgeBreakpoint[],
  options: { temporary?: boolean } = {},
) {
  const sourceBreakpoints = breakpoints.map((breakpoint) => {
    const filePath = resolveBreakpointPath(folder, breakpoint);
    const location = new vscode.Location(vscode.Uri.file(filePath), new vscode.Position(breakpoint.line - 1, 0));
    return new vscode.SourceBreakpoint(location, true);
  });
  if (sourceBreakpoints.length > 0) {
    vscode.debug.addBreakpoints(sourceBreakpoints);
    for (const breakpoint of sourceBreakpoints) {
      ownedBreakpoints.add(breakpoint);
      if (options.temporary) {
        temporaryBreakpoints.add(breakpoint);
      }
    }
  }
  return sourceBreakpoints.map((breakpoint) => ({
    file: breakpoint.location.uri.fsPath,
    line: breakpoint.location.range.start.line + 1,
    enabled: breakpoint.enabled,
    adapterVerification: 'unavailable-vscode-api',
  }));
}

function resolveBreakpointPath(folder: vscode.WorkspaceFolder, breakpoint: BridgeBreakpoint) {
  const resolved = path.isAbsolute(breakpoint.file) ? breakpoint.file : path.join(folder.uri.fsPath, breakpoint.file);
  return assertWorkspacePath(folder.uri.fsPath, resolved, 'breakpoint');
}

function resolveLaunchConfiguration(
  folder: vscode.WorkspaceFolder,
  name: string | undefined,
  correlationToken: string,
): vscode.DebugConfiguration | undefined {
  const configs = vscode.workspace
    .getConfiguration('launch', folder.uri)
    .get<Array<Record<string, unknown>>>('configurations') ?? [];
  const match = configs.find((candidate) => candidate.name === name);
  if (!match) {
    return undefined;
  }
  // Clone and stamp a per-operation correlation token into the configuration.
  // VS Code copies extra configuration fields onto DebugSession.configuration,
  // so onDidStartDebugSession can recognize exactly the session this launch
  // produced and reject any unrelated or compound session (#1431).
  return { ...match, __bridgeCorrelationToken: correlationToken } as unknown as vscode.DebugConfiguration;
}

function sessionCorrelationToken(session: vscode.DebugSession): string | undefined {
  return (session.configuration as { __bridgeCorrelationToken?: string } | undefined)?.__bridgeCorrelationToken;
}

function waitForStoppedState(
  request: BridgeRequest,
  outputPath: string,
  options: { bindActiveSession?: boolean; sessionId?: string; correlationToken?: string } = {},
): Promise<StoppedState> {
  const timeoutMs = request.stopTimeoutMs ?? 30000;
  // A run action (continue / run-to / step) can end in the program exiting
  // rather than hitting another stop; that clean termination is a valid typed
  // outcome, not a timeout (#1432).
  const terminationIsOutcome = request.action === 'continue'
    || request.action === 'runTo'
    || request.action === 'stepOver'
    || request.action === 'stepIn'
    || request.action === 'stepOut';
  return new Promise((resolve, reject) => {
    let settled = false;
    let startSubscription: vscode.Disposable | undefined;
    let terminateSubscription: vscode.Disposable | undefined;
    const cleanup = () => {
      clearTimeout(timer);
      startSubscription?.dispose();
      terminateSubscription?.dispose();
      for (const [sessionId, pending] of pendingBySession.entries()) {
        if (pending === pendingCapture) {
          pendingBySession.delete(sessionId);
        }
      }
    };
    // Settle exactly once: whichever of stop / termination / timeout happens
    // first wins, and every listener and timer is torn down on that path.
    const settleResolve = (state: StoppedState) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(state);
    };
    const timer = setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(new Error(`Timed out waiting ${timeoutMs}ms for a debug adapter stopped event.`));
    }, timeoutMs);

    const pendingCapture: PendingCapture = {
      request,
      outputPath,
      resolve: settleResolve,
      timer,
    };

    const active = options.sessionId
      ? activeSessions.get(options.sessionId)
      : options.bindActiveSession
        ? vscode.debug.activeDebugSession
        : undefined;
    if (active) {
      pendingBySession.set(active.id, pendingCapture);
    }

    startSubscription = vscode.debug.onDidStartDebugSession((session) => {
      // With a correlation token, only the session THIS launch produced may be
      // bound; an unrelated or compound/child session that starts during the
      // wait cannot consume this pending stop (#1431).
      if (options.correlationToken !== undefined && sessionCorrelationToken(session) !== options.correlationToken) {
        return;
      }
      pendingBySession.set(session.id, pendingCapture);
      if (options.sessionId || options.bindActiveSession || options.correlationToken !== undefined) {
        startSubscription?.dispose();
      }
    });

    terminateSubscription = vscode.debug.onDidTerminateDebugSession((session) => {
      const boundToThisWait = pendingBySession.get(session.id) === pendingCapture
        || (options.sessionId !== undefined && session.id === options.sessionId);
      if (!boundToThisWait || !terminationIsOutcome) {
        return;
      }
      settleResolve({
        sessionId: session.id,
        sessionName: session.name,
        stopSequence: sessionStates.get(session.id)?.stopSequence ?? 0,
        reason: 'terminated',
        terminated: true,
        threadId: -1,
      });
    });

    if (active) {
      startSubscription.dispose();
    }
  });
}

async function ingestExternalStop(
  session: vscode.DebugSession,
  body: { reason?: string; threadId?: number },
) {
  const threadId = body.threadId;
  if (typeof threadId !== 'number') {
    return;
  }
  try {
    const stackTrace = await session.customRequest('stackTrace', { threadId, startFrame: 0, levels: 1 });
    const frame = stackTrace?.stackFrames?.[0];
    upsertSessionState(session, undefined, 'paused', {
      selectedThreadId: threadId,
      selectedFrameId: typeof frame?.id === 'number' ? frame.id : undefined,
    });
    const folder = firstWorkspaceFolder();
    if (folder) {
      await writeSessionEvents(folder, session.id);
    }
  } catch (error) {
    channel.appendLine(
      `Debugger bridge external stop capture failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

async function handleDebugAdapterMessage(session: vscode.DebugSession, message: unknown) {
  if (isDebugAdapterEvent(message, 'process')) {
    const prior = sessionStates.get(session.id);
    upsertSessionState(session, undefined, prior?.status ?? 'running', {
      runtime: sanitizeRuntimeIdentity((message as { body?: unknown }).body),
    }, { preserveStopSequence: true });
    return;
  }

  if (!isDebugAdapterEvent(message, 'stopped')) {
    return;
  }
  const pending = pendingBySession.get(session.id);
  if (!pending) {
    // #1435: a stop with no pending bridge capture is an external action -- the
    // human pressed Step Over / Continue, or hit a manually-created breakpoint.
    // Advance the shared session state so a later `inspect` sees the new frame
    // and any agent command carrying the pre-action stop sequence is fenced as
    // stale -- without continuing execution.
    void ingestExternalStop(session, message.body as { reason?: string; threadId?: number });
    return;
  }
  clearPendingCapture(pending);
  clearTimeout(pending.timer);

  const body = message.body as { reason?: string; threadId?: number };
  const threadId = body.threadId;
  if (typeof threadId !== 'number') {
    pending.resolve({
      sessionId: session.id,
      sessionName: session.name,
      stopSequence: sessionStates.get(session.id)?.stopSequence ?? 0,
      reason: body.reason ?? 'stopped',
      threadId: -1,
      error: 'Stopped event did not include a numeric threadId.',
    });
    return;
  }

  try {
    const state = await captureStoppedState(session, threadId, body.reason ?? 'stopped', pending.request);
    const sessionState = upsertSessionState(session, pending.request, 'paused', {
      selectedThreadId: threadId,
      selectedFrameId: frameIdFromState(state),
      requestedBreakpoints: pending.request.breakpoints ?? [],
      verifiedBreakpoints: state.matchedBreakpoint ? pending.request.breakpoints ?? [] : [],
    });
    state.stopSequence = sessionState.stopSequence;
    if (expectsBreakpointStop(pending.request) && state.reason !== 'breakpoint') {
      state.error = `Stopped for ${state.reason}, not breakpoint. This is not debugger proof.`;
    } else if (expectsBreakpointStop(pending.request) && !state.matchedBreakpoint) {
      state.error = 'Stopped frame did not match a requested breakpoint. This is not debugger proof.';
    }
    pending.resolve(state);
  } catch (error) {
    pending.resolve({
      sessionId: session.id,
      sessionName: session.name,
      stopSequence: sessionStates.get(session.id)?.stopSequence ?? 0,
      reason: body.reason ?? 'stopped',
      threadId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

function sanitizeRuntimeIdentity(body: unknown): Record<string, unknown> {
  if (!body || typeof body !== 'object') {
    return {};
  }
  const source = body as Record<string, unknown>;
  const runtime: Record<string, unknown> = {};
  for (const key of ['name', 'systemProcessId', 'isLocalProcess', 'startMethod', 'pointerSize']) {
    if (source[key] !== undefined) {
      runtime[key] = source[key];
    }
  }
  return runtime;
}

function clearPendingCapture(pendingCapture: PendingCapture) {
  for (const [sessionId, pending] of pendingBySession.entries()) {
    if (pending === pendingCapture) {
      pendingBySession.delete(sessionId);
    }
  }
}

async function captureStoppedState(
  session: vscode.DebugSession,
  threadId: number,
  reason: string,
  request: BridgeRequest,
  requestedFrameId?: number,
): Promise<StoppedState> {
  const stackTrace = await session.customRequest('stackTrace', { threadId, startFrame: 0, levels: request.stackDepth ?? 1 });
  const stackFrames = stackTrace?.stackFrames ?? [];
  const frame = requestedFrameId
    ? stackFrames.find((candidate: { id?: unknown }) => candidate.id === requestedFrameId) ?? stackFrames[0]
    : stackFrames[0];
  const state: StoppedState = {
    sessionId: session.id,
    sessionName: session.name,
    stopSequence: sessionStates.get(session.id)?.stopSequence ?? 0,
    reason,
    threadId,
    frame,
    stackFrames,
    adapterBreakpointVerification: 'unavailable-vscode-api',
    locals: {},
    watches: {},
  };
  state.breakpointEvidence = await breakpointEvidenceForFrame(frame, request);
  state.matchedBreakpoint = state.breakpointEvidence.some((evidence) => evidence.accepted);

  if (!frame?.id) {
    state.error = 'No stack frame was available at the stopped breakpoint.';
    return state;
  }

  const scopesResponse = await session.customRequest('scopes', { frameId: frame.id });
  const scopes = scopesResponse?.scopes ?? [];
  state.scopes = scopes;
  const localsScope = scopes.find((scope: { name?: string }) => scope.name?.toLowerCase() === 'locals') ?? scopes[0];
  if (localsScope?.variablesReference) {
    const variablesResponse = await session.customRequest('variables', {
      variablesReference: localsScope.variablesReference,
    });
    const variables = variablesResponse?.variables ?? [];
    // Allowlisted flat capture (unchanged contract), now redacted + truncated.
    for (const variable of variables) {
      if (request.locals?.includes(variable.name)) {
        const truncated = truncateDisplayValue(String(variable.value ?? ''));
        const redacted = redactSecretLikeValue(variable.name, truncated.value);
        state.locals![variable.name] = redacted.value;
      }
    }
    // #1438: explicit bounded typed expansion of requested locals only.
    const expandRequests = Array.isArray(request.expand) ? request.expand : [];
    if (expandRequests.length > 0) {
      state.expanded = {};
      for (const spec of expandRequests) {
        const name = typeof spec === 'string' ? spec : String((spec as { name?: unknown })?.name ?? '');
        if (!name) {
          continue;
        }
        const limits = clampExpandLimits(typeof spec === 'object' && spec !== null ? (spec as Partial<ExpandLimits>) : undefined);
        const target = variables.find((variable: { name?: string }) => variable.name === name);
        if (!target) {
          // A missing target invalidates only THIS inspection; nothing is fabricated.
          state.expanded[name] = { error: 'no such local in the paused frame', limits };
          continue;
        }
        const budget = { bytes: 0 };
        state.expanded[name] = await expandVariableBounded(session, target, limits, 0, new Set(), budget);
      }
    }
  }

  // #1438: watches are FAIL-CLOSED. Nothing evaluates unless allowWatchEval;
  // risky-classified expressions additionally require allowRiskyWatches and are
  // recorded in an audit list on the persisted state.
  const riskyAudit: Array<{ expression: string; reason: string }> = [];
  for (const expression of request.watches ?? []) {
    if (request.allowWatchEval !== true) {
      state.watches![expression] = '<blocked: watch evaluation disabled (allowWatchEval=false)>';
      continue;
    }
    const classified = classifyWatchExpression(expression);
    if (classified.risk === 'risky' && request.allowRiskyWatches !== true) {
      state.watches![expression] = `<blocked: side-effect risk — ${classified.reason}>`;
      continue;
    }
    if (classified.risk === 'risky') {
      riskyAudit.push({ expression, reason: classified.reason });
    }
    try {
      const evaluated = await session.customRequest('evaluate', {
        expression,
        frameId: frame.id,
        context: 'watch',
      });
      const truncated = truncateDisplayValue(String(evaluated?.result ?? ''));
      state.watches![expression] = redactSecretLikeValue(expression, truncated.value).value;
    } catch (error) {
      state.watches![expression] = `<error: ${error instanceof Error ? error.message : String(error)}>`;
    }
  }
  if (riskyAudit.length > 0) {
    state.auditedRiskyWatches = riskyAudit;
  }

  return state;
}

type ExpandedNode = {
  value?: string;
  type?: string;
  variablesReference?: number;
  namedVariables?: number;
  indexedVariables?: number;
  truncated?: true;
  originalLength?: number;
  redacted?: true;
  cycle?: true;
  childrenTruncatedAt?: number;
  budgetExhausted?: true;
  error?: string;
  limits?: { depth: number; maxChildren: number; maxBytes: number };
  children?: Record<string, ExpandedNode>;
};

// Walk one variable's children through DAP `variables` requests with hard
// bounds: depth, per-level child count, and a total byte budget. Repeated
// variablesReference values mark a cycle and terminate deterministically.
async function expandVariableBounded(
  session: vscode.DebugSession,
  variable: { name?: string; value?: unknown; type?: string; variablesReference?: number; namedVariables?: number; indexedVariables?: number },
  limits: { depth: number; maxChildren: number; maxBytes: number },
  depth: number,
  seenReferences: Set<number>,
  budget: { bytes: number },
): Promise<ExpandedNode> {
  const name = String(variable.name ?? '');
  const rawValue = String(variable.value ?? '');
  const truncated = truncateDisplayValue(rawValue);
  const redacted = redactSecretLikeValue(name, truncated.value);
  const node: ExpandedNode = { value: redacted.value, type: variable.type };
  if (truncated.truncated) {
    node.truncated = true;
    node.originalLength = truncated.originalLength;
  }
  if (redacted.redacted) {
    node.redacted = true;
  }
  if (depth === 0) {
    node.limits = limits;
  }
  const reference = typeof variable.variablesReference === 'number' ? variable.variablesReference : 0;
  if (reference > 0) {
    node.variablesReference = reference;
    if (typeof variable.namedVariables === 'number') node.namedVariables = variable.namedVariables;
    if (typeof variable.indexedVariables === 'number') node.indexedVariables = variable.indexedVariables;
  }
  budget.bytes += node.value?.length ?? 0;
  if (reference <= 0 || depth >= limits.depth) {
    return node;
  }
  if (seenReferences.has(reference)) {
    node.cycle = true;
    return node;
  }
  if (budget.bytes >= limits.maxBytes) {
    node.budgetExhausted = true;
    return node;
  }
  seenReferences.add(reference);
  try {
    const response = await session.customRequest('variables', { variablesReference: reference });
    const children = (response?.variables ?? []) as Array<{ name?: string }>;
    node.children = {};
    let taken = 0;
    for (const child of children) {
      const childName = String(child.name ?? '');
      // debugpy grouping/introspection pseudo-children burn the budget without
      // informing anyone; expansion targets USER state.
      if (/^(special variables|function variables|class variables|protected variables|len\(\))$/.test(childName) ||
          /^__.*__$/.test(childName)) {
        continue;
      }
      if (taken >= limits.maxChildren || budget.bytes >= limits.maxBytes) {
        node.childrenTruncatedAt = taken;
        if (budget.bytes >= limits.maxBytes) node.budgetExhausted = true;
        break;
      }
      node.children[String(child.name ?? `#${taken}`)] = await expandVariableBounded(
        session, child, limits, depth + 1, seenReferences, budget,
      );
      taken += 1;
    }
  } catch (error) {
    // A failed expansion invalidates only this subtree; no values are invented.
    node.error = `expansion failed: ${error instanceof Error ? error.message : String(error)}`;
  }
  return node;
}

async function breakpointEvidenceForFrame(frame: unknown, request: BridgeRequest): Promise<BridgeBreakpointEvidence[]> {
  const breakpoints = request.breakpoints ?? [];
  if (breakpoints.length === 0) {
    return [];
  }
  const line = (frame as { line?: unknown }).line;
  const sourcePath = (frame as { source?: { path?: unknown } }).source?.path;
  const functionName = (frame as { name?: unknown }).name;
  const actual = {
    file: typeof sourcePath === 'string' ? path.resolve(sourcePath) : undefined,
    line: typeof line === 'number' ? line : undefined,
    function: typeof functionName === 'string' ? functionName : undefined,
  };
  return Promise.all(breakpoints.map(async (breakpoint) => breakpointEvidence(breakpoint, request, actual)));
}

async function breakpointEvidence(
  breakpoint: BridgeBreakpoint,
  request: BridgeRequest,
  actual: { file?: string; line?: number; function?: string },
): Promise<BridgeBreakpointEvidence> {
  const normalizedBreakpointPath = path.resolve(
    request.workspace && !path.isAbsolute(breakpoint.file)
      ? path.join(request.workspace, breakpoint.file)
      : breakpoint.file,
  );
  const vscodeBreakpoint = vscode.debug.breakpoints.find((candidate): candidate is vscode.SourceBreakpoint => (
    candidate instanceof vscode.SourceBreakpoint &&
    path.resolve(candidate.location.uri.fsPath) === normalizedBreakpointPath &&
    candidate.location.range.start.line + 1 === breakpoint.line
  ));
  const evidence: BridgeBreakpointEvidence = {
    requested: { file: normalizedBreakpointPath, line: breakpoint.line },
    vscodeBreakpoint: vscodeBreakpoint
      ? {
          file: vscodeBreakpoint.location.uri.fsPath,
          line: vscodeBreakpoint.location.range.start.line + 1,
          enabled: vscodeBreakpoint.enabled,
        }
      : undefined,
    adapter: {
      verification: 'unavailable',
      message: 'VS Code extension API does not expose adapter setBreakpoints response for API-added breakpoints.',
    },
    actual,
    relocated: actual.line !== undefined && breakpoint.line !== actual.line,
    accepted: false,
    reason: 'actual stopped frame did not match requested source file',
  };
  if (actual.file === undefined || actual.line === undefined) {
    evidence.reason = 'actual stopped frame has no source path or line';
    return evidence;
  }
  if (path.resolve(actual.file) !== normalizedBreakpointPath) {
    return evidence;
  }
  if (actual.line === breakpoint.line) {
    evidence.accepted = true;
    evidence.reason = 'actual stopped frame matched requested breakpoint line';
    return evidence;
  }
  const symbolRange = await sourceSymbolRangeForLine(normalizedBreakpointPath, breakpoint.line);
  evidence.sourceSymbolRange = symbolRange;
  if (
    symbolRange &&
    actual.line >= symbolRange.startLine &&
    actual.line <= symbolRange.endLine &&
    (actual.function === undefined || symbolRange.name === '<module>' || actual.function === symbolRange.name)
  ) {
    evidence.accepted = true;
    evidence.reason = 'actual stopped frame is an adapter-relocated executable line inside the requested current symbol range';
    return evidence;
  }
  evidence.reason = 'actual stopped frame is outside the requested current symbol range';
  return evidence;
}

async function sourceSymbolRangeForLine(filePath: string, oneBasedLine: number): Promise<BridgeSourceSymbolRange | undefined> {
  let content: string;
  try {
    content = await fs.readFile(filePath, 'utf8');
  } catch {
    return undefined;
  }
  const lines = content.split(/\r?\n/);
  const index = oneBasedLine - 1;
  const sourceLine = lines[index] ?? '';
  const match = /^(\s*)(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)/.exec(sourceLine);
  const sourceSha256 = `sha256:${crypto.createHash('sha256').update(content, 'utf8').digest('hex')}`;
  if (!match) {
    return {
      file: filePath,
      sourceSha256,
      kind: 'module',
      name: '<module>',
      startLine: oneBasedLine,
      endLine: oneBasedLine,
    };
  }
  const declarationIndent = match[1].length;
  let endLine = lines.length;
  for (let i = index + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.trim() === '' || line.trimStart().startsWith('#')) {
      continue;
    }
    const indent = line.length - line.trimStart().length;
    if (indent <= declarationIndent) {
      endLine = i;
      break;
    }
  }
  return {
    file: filePath,
    sourceSha256,
    kind: sourceLine.trimStart().startsWith('class ') ? 'class' : 'function',
    name: match[2],
    startLine: oneBasedLine,
    endLine,
  };
}

function frameMatchesRequestedBreakpoint(frame: unknown, request: BridgeRequest) {
  if (!frame || typeof frame !== 'object') {
    return false;
  }
  const line = (frame as { line?: unknown }).line;
  const sourcePath = (frame as { source?: { path?: unknown } }).source?.path;
  if (typeof line !== 'number' || typeof sourcePath !== 'string') {
    return false;
  }
  const normalizedFramePath = path.resolve(sourcePath);
  return (request.breakpoints ?? []).some((breakpoint) => {
    const normalizedBreakpointPath = path.resolve(
      request.workspace && !path.isAbsolute(breakpoint.file)
        ? path.join(request.workspace, breakpoint.file)
        : breakpoint.file,
    );
    return normalizedBreakpointPath === normalizedFramePath && breakpoint.line === line;
  });
}

function expectsBreakpointStop(request: BridgeRequest) {
  const action = request.action ?? 'start';
  return action === 'start' || action === 'restart' || action === 'process' || action === 'continue' || action === 'runTo';
}

function isDebugAdapterEvent(message: unknown, eventName: string): message is { type: 'event'; event: string; body?: unknown } {
  return (
    typeof message === 'object' &&
    message !== null &&
    (message as { type?: unknown }).type === 'event' &&
    (message as { event?: unknown }).event === eventName
  );
}

function firstWorkspaceFolder() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    throw new Error('No VS Code workspace folder is open.');
  }
  return folder;
}

function resolveWorkspaceFolder(workspacePath?: string) {
  if (!workspacePath) {
    return firstWorkspaceFolder();
  }
  const resolved = path.resolve(workspacePath);
  const folder = vscode.workspace.workspaceFolders?.find((candidate) => candidate.uri.fsPath === resolved);
  if (!folder) {
    throw new Error(`Workspace folder is not open in VS Code: ${resolved}`);
  }
  return folder;
}

function resolveWorkspacePath(folder: vscode.WorkspaceFolder, filePath: string) {
  return resolveContainedWorkspacePath(folder.uri.fsPath, filePath, 'output');
}

// #1440: runtime-value-bearing status defaults OUTSIDE the git worktree, under
// $XDG_RUNTIME_DIR/agent-skills-debugger/<workspace-hash>/. An explicit
// request.output inside the workspace is "workspace-local mode" and is refused
// unless that path is git-ignored (cannot be accidentally staged) or the request
// carries an audited allowWorkspaceArtifacts override.
async function resolveRuntimeOutputPath(
  folder: vscode.WorkspaceFolder,
  request: Record<string, unknown>,
): Promise<string> {
  const requested = typeof request.output === 'string' ? request.output : undefined;
  if (!requested) {
    return path.join(runtimeArtifactRoot(folder.uri.fsPath), 'status.json');
  }
  const { resolved, location } = resolveArtifactPath(folder.uri.fsPath, requested, 'output');
  if (location === 'workspace' && request.allowWorkspaceArtifacts !== true) {
    const ignored = await isGitIgnored(folder.uri.fsPath, resolved);
    if (!ignored) {
      throw new Error(
        `Debugger bridge refuses workspace-local artifacts at ${requested}: the path is not ` +
        `git-ignored, so paused runtime values could be staged/committed. Use the default ` +
        `runtime-dir storage, git-ignore the path, or set allowWorkspaceArtifacts: true (audited).`,
      );
    }
  }
  return resolved;
}

async function isGitIgnored(workspacePath: string, candidate: string): Promise<boolean> {
  const { execFile } = await import('node:child_process');
  return await new Promise<boolean>((resolve) => {
    execFile(
      'git',
      ['-C', workspacePath, 'check-ignore', '-q', candidate],
      { timeout: 10_000 },
      (error) => resolve(error === null),
    );
  });
}

async function writeStatus(filePath: string, body: unknown) {
  await writeJsonFile(filePath, body);
  channel.appendLine(`Wrote debugger bridge status: ${filePath}`);
}

async function writeOwnedStatus(
  filePath: string,
  requestId: string,
  requestHash: string,
  body: unknown,
  requireCurrentRequestOwner: boolean,
) {
  const decision = await writeOwnedJsonFile(
    filePath,
    requestId,
    requestHash,
    body,
    requireCurrentRequestOwner && usesSharedRequestOwner(filePath) ? () => readCurrentRequestOwner(filePath) : undefined,
  );
  if (decision.superseded) {
    const ownerId = decision.owner ? String(decision.owner.id) : '<missing>';
    channel.appendLine(
      `Archived debugger bridge status for superseded request ${requestId}; current status belongs to ${ownerId}.`,
    );
    return false;
  }
  channel.appendLine(`Wrote debugger bridge status: ${decision.outputPath}`);
  return true;
}

async function readCurrentRequestOwner(statusPath: string): Promise<{ id?: unknown; requestHash?: unknown } | undefined> {
  try {
    const raw = await vscode.workspace.fs.readFile(vscode.Uri.file(path.join(path.dirname(statusPath), 'request.json')));
    const parsed = JSON.parse(Buffer.from(raw).toString('utf8')) as { id?: unknown; requestHash?: unknown };
    return { id: parsed.id, requestHash: parsed.requestHash };
  } catch (error) {
    if ((error as { code?: string }).code === 'FileNotFound' || (error as { code?: string }).code === 'ENOENT') {
      return undefined;
    }
    throw error;
  }
}
