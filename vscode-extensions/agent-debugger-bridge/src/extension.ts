import * as fs from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';
import { appendObservation, writeSessionState } from './observations';
import { findLatestManifest, getWorkspaceFolder, loadManifestFromPath, resolveInsideWorkspace } from './manifest';
import { AgentDebuggerManifest, DebugCommand, ManifestBreakpoint } from './types';

class AgentDebuggerBridge {
  private workspace: vscode.WorkspaceFolder;
  private manifest?: AgentDebuggerManifest;
  private managedSession?: vscode.DebugSession;
  private agentBreakpoints = new Set<vscode.Breakpoint>();
  private currentThreadId?: number;
  private currentFrameId?: number;
  private commandOffset = 0;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.workspace = getWorkspaceFolder();
    context.subscriptions.push(
      vscode.debug.onDidStartDebugSession((session) => this.onDidStartDebugSession(session)),
      vscode.debug.onDidTerminateDebugSession((session) => this.onDidTerminateDebugSession(session)),
      vscode.debug.onDidChangeBreakpoints((event) => this.onDidChangeBreakpoints(event)),
      vscode.debug.registerDebugAdapterTrackerFactory('*', {
        createDebugAdapterTracker: (session) => ({
          onDidSendMessage: (message) => this.onDebugAdapterMessage(session, message),
        }),
      }),
    );
  }

  registerCommands(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand('agentDebugger.loadManifest', async (manifestPath?: string) => this.loadManifest(manifestPath)),
      vscode.commands.registerCommand('agentDebugger.setBreakpoints', async () => this.setBreakpoints()),
      vscode.commands.registerCommand('agentDebugger.start', async () => this.start()),
      vscode.commands.registerCommand('agentDebugger.runCurrentManifest', async (manifestPath?: string) => {
        await this.loadManifest(manifestPath);
        await this.setBreakpoints();
        await this.start();
      }),
      vscode.commands.registerCommand('agentDebugger.stop', async () => this.stop()),
      vscode.commands.registerCommand('agentDebugger.replay', async () => this.replay()),
      vscode.commands.registerCommand('agentDebugger.continue', async () => this.sendThreadRequest('continue')),
      vscode.commands.registerCommand('agentDebugger.stepOver', async () => this.sendThreadRequest('next')),
      vscode.commands.registerCommand('agentDebugger.stepIn', async () => this.sendThreadRequest('stepIn')),
      vscode.commands.registerCommand('agentDebugger.stepOut', async () => this.sendThreadRequest('stepOut')),
      vscode.commands.registerCommand('agentDebugger.pause', async () => this.sendThreadRequest('pause')),
      vscode.commands.registerCommand('agentDebugger.processCommandQueue', async () => this.processCommandQueue()),
    ];
  }

  private async loadManifest(manifestPath?: string): Promise<void> {
    let selectedPath = manifestPath;
    if (!selectedPath) {
      selectedPath = await findLatestManifest(this.workspace);
    }
    if (!selectedPath) {
      const selection = await vscode.window.showOpenDialog({
        title: 'Select agent-debugger debug_manifest.json',
        canSelectFiles: true,
        canSelectFolders: false,
        canSelectMany: false,
        filters: { JSON: ['json'] },
      });
      selectedPath = selection?.[0]?.fsPath;
    }
    if (!selectedPath) {
      throw new Error('No debug_manifest.json selected or discovered.');
    }

    this.manifest = await loadManifestFromPath(this.workspace, selectedPath);
    this.commandOffset = 0;
    await appendObservation(this.workspace, this.manifest, 'manifest_loaded', {
      task: this.manifest.task,
      launch_config_name: this.manifest.launch_config_name,
      breakpoint_count: this.manifest.breakpoints.length,
    });
    await writeSessionState(this.workspace, this.manifest, { status: 'manifest_loaded' });
    vscode.window.showInformationMessage(`Agent Debugger manifest loaded: ${this.manifest.task}`);
  }

  private async setBreakpoints(): Promise<void> {
    const manifest = this.requireManifest();
    if (this.agentBreakpoints.size > 0) {
      vscode.debug.removeBreakpoints([...this.agentBreakpoints]);
      this.agentBreakpoints.clear();
    }

    const newBreakpoints: vscode.Breakpoint[] = manifest.breakpoints.map((spec) => this.toSourceBreakpoint(spec));
    for (const breakpoint of newBreakpoints) {
      this.agentBreakpoints.add(breakpoint);
    }
    vscode.debug.addBreakpoints(newBreakpoints);
    await appendObservation(this.workspace, manifest, 'agent_breakpoints_set', {
      count: newBreakpoints.length,
      breakpoints: manifest.breakpoints.map((bp) => ({ file: bp.file, line: bp.line, expressions: bp.expressions ?? [] })),
    });
    await writeSessionState(this.workspace, manifest, { status: 'breakpoints_set' });
  }

  private async start(): Promise<void> {
    const manifest = this.requireManifest();
    const started = await vscode.debug.startDebugging(this.workspace, manifest.launch_config_name);
    await appendObservation(this.workspace, manifest, 'debug_start_requested', {
      launch_config_name: manifest.launch_config_name,
      started,
    });
    if (!started) {
      await writeSessionState(this.workspace, manifest, {
        status: 'error',
        message: `VS Code did not start launch configuration '${manifest.launch_config_name}'.`,
      });
      throw new Error(`Failed to start launch configuration: ${manifest.launch_config_name}`);
    }
  }

  private async stop(): Promise<void> {
    const manifest = this.requireManifest();
    if (!this.managedSession) {
      await appendObservation(this.workspace, manifest, 'stop_skipped_no_managed_session', {});
      return;
    }
    await vscode.debug.stopDebugging(this.managedSession);
    await appendObservation(this.workspace, manifest, 'stop_requested', { session_name: this.managedSession.name });
  }

  private async replay(): Promise<void> {
    const manifest = this.requireManifest();
    await appendObservation(this.workspace, manifest, 'replay_requested', {
      semantics: 'stop_and_restart_same_launch_config',
    });
    if (this.managedSession) {
      await vscode.debug.stopDebugging(this.managedSession);
      await this.wait(250);
    }
    await this.start();
  }

  private async processCommandQueue(): Promise<void> {
    const manifest = this.requireManifest();
    const commandPath = resolveInsideWorkspace(this.workspace, manifest.commands_path);
    let content: string;
    try {
      content = await fs.readFile(commandPath, 'utf8');
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'command_queue_missing', { command_path: manifest.commands_path });
      return;
    }
    const fresh = content.slice(this.commandOffset);
    this.commandOffset = content.length;
    const lines = fresh.split(/\r?\n/).filter((line) => line.trim().length > 0);
    for (const line of lines) {
      let command: DebugCommand;
      try {
        command = JSON.parse(line) as DebugCommand;
      } catch (error) {
        await appendObservation(this.workspace, manifest, 'command_parse_error', { line, error: String(error) });
        continue;
      }
      await this.executeQueuedCommand(command);
    }
  }

  private async executeQueuedCommand(command: DebugCommand): Promise<void> {
    const manifest = this.requireManifest();
    await appendObservation(this.workspace, manifest, 'command_received', { command });
    switch (command.type) {
      case 'load_manifest':
        await this.loadManifest(command.manifest_path);
        return;
      case 'set_breakpoints':
        await this.setBreakpoints();
        return;
      case 'start':
        await this.start();
        return;
      case 'stop':
        await this.stop();
        return;
      case 'replay':
        await this.replay();
        return;
      case 'continue':
        await this.sendThreadRequest('continue');
        return;
      case 'step_over':
        await this.sendThreadRequest('next');
        return;
      case 'step_in':
        await this.sendThreadRequest('stepIn');
        return;
      case 'step_out':
        await this.sendThreadRequest('stepOut');
        return;
      case 'pause':
        await this.sendThreadRequest('pause');
        return;
      case 'evaluate':
        if (!command.expression) {
          await appendObservation(this.workspace, manifest, 'evaluate_command_missing_expression', { command });
          return;
        }
        await this.evaluateExpression(command.expression);
        return;
      default: {
        const neverCommand: never = command.type;
        await appendObservation(this.workspace, manifest, 'unsupported_command', { command_type: neverCommand });
      }
    }
  }

  private async sendThreadRequest(command: 'continue' | 'next' | 'stepIn' | 'stepOut' | 'pause'): Promise<void> {
    const manifest = this.requireManifest();
    const session = this.requireManagedSession();
    const threadId = await this.getThreadId(session);
    try {
      const response = await session.customRequest(command, { threadId });
      await appendObservation(this.workspace, manifest, 'debug_control_request', { command, threadId, response });
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'debug_control_request_failed', { command, threadId, error: String(error) });
    }
  }

  private async evaluateExpression(expression: string): Promise<void> {
    const manifest = this.requireManifest();
    const session = this.requireManagedSession();
    if (!this.currentFrameId) {
      await appendObservation(this.workspace, manifest, 'evaluate_skipped_no_paused_frame', { expression });
      return;
    }
    try {
      const response = await session.customRequest('evaluate', {
        expression,
        frameId: this.currentFrameId,
        context: 'watch',
      });
      await appendObservation(this.workspace, manifest, 'expression_evaluated', { expression, response });
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'expression_evaluation_failed', { expression, error: String(error) });
    }
  }

  private async onDidStartDebugSession(session: vscode.DebugSession): Promise<void> {
    if (!this.manifest || session.name !== this.manifest.launch_config_name) {
      return;
    }
    this.managedSession = session;
    this.currentThreadId = undefined;
    this.currentFrameId = undefined;
    await appendObservation(this.workspace, this.manifest, 'debug_session_started', {
      session_id: session.id,
      session_name: session.name,
      session_type: session.type,
    }, 'debugger');
    await writeSessionState(this.workspace, this.manifest, {
      status: 'running',
      active_session_name: session.name,
    });
  }

  private async onDidTerminateDebugSession(session: vscode.DebugSession): Promise<void> {
    if (!this.manifest || session.id !== this.managedSession?.id) {
      return;
    }
    await appendObservation(this.workspace, this.manifest, 'debug_session_terminated', {
      session_id: session.id,
      session_name: session.name,
    }, 'debugger');
    await writeSessionState(this.workspace, this.manifest, { status: 'stopped' });
    this.managedSession = undefined;
    this.currentThreadId = undefined;
    this.currentFrameId = undefined;
  }

  private async onDidChangeBreakpoints(event: vscode.BreakpointsChangeEvent): Promise<void> {
    if (!this.manifest) {
      return;
    }
    const humanAdded = event.added.filter((breakpoint) => !this.agentBreakpoints.has(breakpoint)).map((bp) => this.describeBreakpoint(bp));
    const removed = event.removed.map((bp) => this.describeBreakpoint(bp));
    if (humanAdded.length > 0) {
      await appendObservation(this.workspace, this.manifest, 'human_breakpoints_added', { breakpoints: humanAdded }, 'human');
    }
    if (removed.length > 0) {
      await appendObservation(this.workspace, this.manifest, 'breakpoints_removed', { breakpoints: removed });
    }
  }

  private async onDebugAdapterMessage(session: vscode.DebugSession, message: unknown): Promise<void> {
    if (!this.manifest || session.id !== this.managedSession?.id) {
      return;
    }
    const event = message as { type?: string; event?: string; body?: Record<string, unknown> };
    if (event.type !== 'event' || event.event !== 'stopped') {
      return;
    }
    const threadId = typeof event.body?.threadId === 'number' ? event.body.threadId : await this.getThreadId(session);
    this.currentThreadId = threadId;
    await this.captureStoppedState(session, threadId, event.body ?? {});
  }

  private async captureStoppedState(session: vscode.DebugSession, threadId: number, eventBody: Record<string, unknown>): Promise<void> {
    const manifest = this.requireManifest();
    try {
      const stackTrace = await session.customRequest('stackTrace', { threadId, startFrame: 0, levels: 1 });
      const frame = stackTrace?.stackFrames?.[0];
      if (!frame) {
        await appendObservation(this.workspace, manifest, 'breakpoint_stopped_no_frame', { threadId, eventBody }, 'debugger');
        return;
      }
      this.currentFrameId = frame.id;
      const sourcePath = typeof frame.source?.path === 'string' ? frame.source.path : undefined;
      const relativePath = sourcePath ? path.relative(this.workspace.uri.fsPath, sourcePath).replace(/\\/g, '/') : undefined;
      const line = typeof frame.line === 'number' ? frame.line : undefined;
      const matchingBreakpoint = manifest.breakpoints.find((bp) => bp.line === line && relativePath && path.normalize(bp.file) === path.normalize(relativePath));
      const expressions = matchingBreakpoint?.expressions ?? [];
      const evaluated: Record<string, unknown> = {};
      for (const expression of expressions) {
        try {
          const response = await session.customRequest('evaluate', {
            expression,
            frameId: frame.id,
            context: 'watch',
          });
          evaluated[expression] = response?.result ?? response;
        } catch (error) {
          evaluated[expression] = { error: String(error) };
        }
      }
      await appendObservation(this.workspace, manifest, 'breakpoint_hit', {
        threadId,
        frameId: frame.id,
        file: relativePath ?? sourcePath ?? null,
        line,
        name: frame.name,
        eventBody,
        reason: matchingBreakpoint?.reason ?? null,
        expressions: evaluated,
      }, 'debugger');
      await writeSessionState(this.workspace, manifest, {
        status: 'paused',
        active_session_name: session.name,
        current_file: relativePath ?? sourcePath,
        current_line: line,
        current_thread_id: threadId,
      });
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'breakpoint_capture_failed', { threadId, error: String(error) }, 'debugger');
    }
  }

  private async getThreadId(session: vscode.DebugSession): Promise<number> {
    if (this.currentThreadId) {
      return this.currentThreadId;
    }
    const threadsResponse = await session.customRequest('threads');
    const threadId = threadsResponse?.threads?.[0]?.id;
    if (typeof threadId !== 'number') {
      throw new Error('Debug adapter did not return a thread id.');
    }
    this.currentThreadId = threadId;
    return threadId;
  }

  private toSourceBreakpoint(spec: ManifestBreakpoint): vscode.SourceBreakpoint {
    const absolute = resolveInsideWorkspace(this.workspace, spec.file);
    const location = new vscode.Location(vscode.Uri.file(absolute), new vscode.Position(spec.line - 1, 0));
    return new vscode.SourceBreakpoint(location, spec.stop !== false, spec.condition, undefined, spec.logMessage);
  }

  private describeBreakpoint(breakpoint: vscode.Breakpoint): Record<string, unknown> {
    if (breakpoint instanceof vscode.SourceBreakpoint) {
      return {
        type: 'source',
        file: path.relative(this.workspace.uri.fsPath, breakpoint.location.uri.fsPath).replace(/\\/g, '/'),
        line: breakpoint.location.range.start.line + 1,
        enabled: breakpoint.enabled,
        condition: breakpoint.condition,
        logMessage: breakpoint.logMessage,
      };
    }
    return { type: 'unknown', enabled: breakpoint.enabled };
  }

  private requireManifest(): AgentDebuggerManifest {
    if (!this.manifest) {
      throw new Error('No agent-debugger manifest loaded. Run Agent Debugger: Load Manifest first.');
    }
    return this.manifest;
  }

  private requireManagedSession(): vscode.DebugSession {
    if (!this.managedSession) {
      throw new Error('No managed debug session is active.');
    }
    return this.managedSession;
  }

  private async wait(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const bridge = new AgentDebuggerBridge(context);
  context.subscriptions.push(...bridge.registerCommands());
}

export function deactivate(): void {
  // VS Code disposes subscriptions from the extension context.
}
