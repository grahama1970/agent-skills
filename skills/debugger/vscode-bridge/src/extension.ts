import * as path from 'node:path';
import * as vscode from 'vscode';
import {
  AsyncKeyedQueue,
  type BridgeBreakpoint,
  type BridgeRequest,
  assertWorkspacePath,
  assessProofValidity,
  canonicalRequestHash,
  claimRequestId,
  decideOwnedStatusWritePath,
  enforceFreshRequest,
  invalidRequestStatusPath,
  isRequestAlreadyClaimed,
  resolveWorkspacePath as resolveContainedWorkspacePath,
  sha256,
  usesSharedRequestOwner,
  validateRequest,
  verifyPendingStatus,
  withFreshRequestMetadata,
  writeJsonFile,
} from './protocol';

type StoppedState = {
  sessionId: string;
  sessionName: string;
  reason: string;
  threadId: number;
  frame?: unknown;
  matchedBreakpoint?: boolean;
  adapterBreakpointVerification?: string;
  scopes?: unknown[];
  locals?: Record<string, string>;
  watches?: Record<string, string>;
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
const bridgeQueue = new AsyncKeyedQueue();
let watcher: vscode.FileSystemWatcher | undefined;

export function activate(context: vscode.ExtensionContext) {
  channel.appendLine('Debugger Bridge activated.');

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
    await processBridgeRequest(parsedRequest, parsedHash, true);
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
    return resolveContainedWorkspacePath(workspacePath, request.output, 'output');
  } catch (error) {
    channel.appendLine(`Debugger bridge could not resolve request output for error status: ${String(error)}`);
    return invalidRequestStatusPath(sharedStatusPath);
  }
}

async function processBridgeRequest(request: BridgeRequest, computedRequestHash?: string, requirePendingStatus = false) {
  validateRequest(request);
  if (!vscode.workspace.isTrusted) {
    throw new Error('Debugger bridge refuses to run in an untrusted VS Code workspace.');
  }
  const requestId = request.id as string;
  const requestHash = request.requestHash as string;
  const folder = resolveWorkspaceFolder(request.workspace);
  const outputPath = resolveWorkspacePath(folder, request.output ?? '.vscode/debugger-bridge/status.json');
  if (requestHash !== computedRequestHash) {
    throw new Error('Debugger bridge requestHash does not match canonical request content.');
  }
  await bridgeQueue.run('vscode-debugger-session', () =>
    processBridgeRequestForOutput(request, requestId, requestHash, folder, outputPath, requirePendingStatus),
  );
}

async function processBridgeRequestForOutput(
  request: BridgeRequest,
  requestId: string,
  requestHash: string,
  folder: vscode.WorkspaceFolder,
  outputPath: string,
  requirePendingStatus: boolean,
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
  };
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

  if (action === 'continue') {
    await prepareSourceFiles(folder, request);
    const addedBreakpoints = await replaceRequestedBreakpoints(folder, request);
    const session = vscode.debug.activeDebugSession;
    if (!session) {
      throw new Error('No active VS Code debug session is available to continue.');
    }
    const stopped = waitForStoppedState(request, outputPath, { bindActiveSession: true });
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: 'continuing',
      launchConfigName: request.launchConfigName,
      addedBreakpoints,
      sessionId: session.id,
      updatedAt: new Date().toISOString(),
    }, requirePendingStatus);
    await vscode.commands.executeCommand('workbench.action.debug.continue');
    const stoppedState = await stopped;
    const proofAssessment = assessProofValidity(request, stoppedState);
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: proofAssessment.proofValid ? 'stopped' : 'stopped-not-proof',
      proofValid: proofAssessment.proofValid,
      proofAssessment,
      launchConfigName: request.launchConfigName,
      addedBreakpoints,
      stoppedState,
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
  const stopped = waitForStoppedState(request, outputPath, { bindActiveSession: false });
  const ok = await vscode.debug.startDebugging(folder, request.launchConfigName ?? 'Debug with $debugger');
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
    await writeOwnedStatus(outputPath, requestId, requestHash, {
      ...statusBase,
      status: proofAssessment.proofValid ? 'stopped' : 'stopped-not-proof',
      proofValid: proofAssessment.proofValid,
      proofAssessment,
      launchConfigName: request.launchConfigName,
      addedBreakpoints,
      stoppedState,
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
  const session = vscode.debug.activeDebugSession;
  if (!session) {
    return;
  }
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, 5000);
    const subscription = vscode.debug.onDidTerminateDebugSession((terminated) => {
      if (terminated.id === session.id) {
        clearTimeout(timer);
        subscription.dispose();
        resolve();
      }
    });
    void vscode.debug.stopDebugging(session).then(
      () => undefined,
      () => {
        clearTimeout(timer);
        subscription.dispose();
        resolve();
      },
    );
  });
}

async function replaceRequestedBreakpoints(folder: vscode.WorkspaceFolder, request: BridgeRequest) {
  const breakpoints = request.breakpoints ?? [];
  if (request.replaceBreakpoints !== false) {
    const requestedFiles = new Set(breakpoints.map((breakpoint) => resolveBreakpointPath(folder, breakpoint)));
    const staleBreakpoints = vscode.debug.breakpoints.filter(
      (breakpoint): breakpoint is vscode.SourceBreakpoint =>
        breakpoint instanceof vscode.SourceBreakpoint && requestedFiles.has(breakpoint.location.uri.fsPath),
    );
    if (staleBreakpoints.length > 0) {
      vscode.debug.removeBreakpoints(staleBreakpoints);
    }
  }
  return addRequestedBreakpoints(folder, breakpoints);
}

async function addRequestedBreakpoints(folder: vscode.WorkspaceFolder, breakpoints: BridgeBreakpoint[]) {
  const sourceBreakpoints = breakpoints.map((breakpoint) => {
    const filePath = resolveBreakpointPath(folder, breakpoint);
    const location = new vscode.Location(vscode.Uri.file(filePath), new vscode.Position(breakpoint.line - 1, 0));
    return new vscode.SourceBreakpoint(location, true);
  });
  if (sourceBreakpoints.length > 0) {
    vscode.debug.addBreakpoints(sourceBreakpoints);
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

function waitForStoppedState(
  request: BridgeRequest,
  outputPath: string,
  options: { bindActiveSession?: boolean } = {},
): Promise<StoppedState> {
  const timeoutMs = request.stopTimeoutMs ?? 30000;
  return new Promise((resolve, reject) => {
    let startSubscription: vscode.Disposable | undefined;
    const timer = setTimeout(() => {
      for (const [sessionId, pending] of pendingBySession.entries()) {
        if (pending === pendingCapture) {
          pendingBySession.delete(sessionId);
        }
      }
      startSubscription?.dispose();
      reject(new Error(`Timed out waiting ${timeoutMs}ms for a debug adapter stopped event.`));
    }, timeoutMs);

    const pendingCapture: PendingCapture = {
      request,
      outputPath,
      resolve,
      timer,
    };

    const active = options.bindActiveSession ? vscode.debug.activeDebugSession : undefined;
    if (active) {
      pendingBySession.set(active.id, pendingCapture);
    }

    startSubscription = vscode.debug.onDidStartDebugSession((session) => {
      pendingBySession.set(session.id, pendingCapture);
      startSubscription?.dispose();
    });
    if (active) {
      startSubscription.dispose();
    }
  });
}

async function handleDebugAdapterMessage(session: vscode.DebugSession, message: unknown) {
  if (!isDebugAdapterEvent(message, 'stopped')) {
    return;
  }
  const pending = pendingBySession.get(session.id);
  if (!pending) {
    return;
  }
  pendingBySession.delete(session.id);
  clearTimeout(pending.timer);

  const body = message.body as { reason?: string; threadId?: number };
  const threadId = body.threadId;
  if (typeof threadId !== 'number') {
    pending.resolve({
      sessionId: session.id,
      sessionName: session.name,
      reason: body.reason ?? 'stopped',
      threadId: -1,
      error: 'Stopped event did not include a numeric threadId.',
    });
    return;
  }

  try {
    const state = await captureStoppedState(session, threadId, body.reason ?? 'stopped', pending.request);
    if (state.reason !== 'breakpoint') {
      state.error = `Stopped for ${state.reason}, not breakpoint. This is not debugger proof.`;
    } else if (!state.matchedBreakpoint) {
      state.error = 'Stopped frame did not match a requested breakpoint. This is not debugger proof.';
    }
    pending.resolve(state);
  } catch (error) {
    pending.resolve({
      sessionId: session.id,
      sessionName: session.name,
      reason: body.reason ?? 'stopped',
      threadId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function captureStoppedState(
  session: vscode.DebugSession,
  threadId: number,
  reason: string,
  request: BridgeRequest,
): Promise<StoppedState> {
  const stackTrace = await session.customRequest('stackTrace', { threadId, startFrame: 0, levels: 1 });
  const frame = stackTrace?.stackFrames?.[0];
  const state: StoppedState = {
    sessionId: session.id,
    sessionName: session.name,
    reason,
    threadId,
    frame,
    matchedBreakpoint: frameMatchesRequestedBreakpoint(frame, request),
    adapterBreakpointVerification: 'unavailable-vscode-api',
    locals: {},
    watches: {},
  };

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
    for (const variable of variables) {
      if (request.locals?.includes(variable.name)) {
        state.locals![variable.name] = variable.value;
      }
    }
  }

  for (const expression of request.watches ?? []) {
    try {
      const evaluated = await session.customRequest('evaluate', {
        expression,
        frameId: frame.id,
        context: 'watch',
      });
      state.watches![expression] = evaluated?.result ?? '';
    } catch (error) {
      state.watches![expression] = `<error: ${error instanceof Error ? error.message : String(error)}>`;
    }
  }

  return state;
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
  const currentRequestOwner =
    requireCurrentRequestOwner && usesSharedRequestOwner(filePath) ? await readCurrentRequestOwner(filePath) : undefined;
  const current = currentRequestOwner ?? (await readStatusOwner(filePath));
  const decision = decideOwnedStatusWritePath(filePath, requestId, requestHash, current);
  if (decision.superseded) {
    await writeJsonFile(decision.outputPath, body);
    const ownerId = current ? String(current.id) : '<missing>';
    channel.appendLine(
      `Archived debugger bridge status for superseded request ${requestId}; current status belongs to ${ownerId}.`,
    );
    return false;
  }
  await writeStatus(decision.outputPath, body);
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

async function readStatusOwner(filePath: string): Promise<{ id?: unknown; requestHash?: unknown } | undefined> {
  try {
    const raw = await vscode.workspace.fs.readFile(vscode.Uri.file(filePath));
    const parsed = JSON.parse(Buffer.from(raw).toString('utf8')) as { id?: unknown; requestHash?: unknown };
    return { id: parsed.id, requestHash: parsed.requestHash };
  } catch (error) {
    if ((error as { code?: string }).code === 'FileNotFound' || (error as { code?: string }).code === 'ENOENT') {
      return undefined;
    }
    throw error;
  }
}
