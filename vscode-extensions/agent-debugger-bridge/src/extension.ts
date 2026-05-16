import * as fs from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';
import { loadManifestFromPath, findLatestManifest, getWorkspaceFolder, resolveInsideWorkspace } from './manifest';
import { appendObservation, writeSessionState } from './observations';
import { AgentDebuggerManifest, DebugCommand, ManifestBreakpoint } from './types';
import { MockDebugAdapter } from './mockDebugAdapter';

class AgentDebuggerBridge {
  private readonly workspace: vscode.WorkspaceFolder;
  private manifest?: AgentDebuggerManifest;
  private managedSession?: vscode.DebugSession;
  private readonly agentBreakpoints = new Set<vscode.Breakpoint>();
  private currentThreadId?: number;
  private currentFrameId?: number;
  private commandOffset = 0;

  constructor(context: vscode.ExtensionContext) {
    this.workspace = getWorkspaceFolder();
    context.subscriptions.push(
      vscode.debug.onDidStartDebugSession((session) => this.onSessionStarted(session)),
      vscode.debug.onDidTerminateDebugSession((session) => this.onSessionTerminated(session)),
      vscode.debug.onDidChangeBreakpoints((event) => this.onBreakpointsChanged(event)),
      vscode.debug.registerDebugAdapterTrackerFactory('*', {
        createDebugAdapterTracker: (session) => ({
          onDidSendMessage: (message) => this.onAdapterMessage(session, message),
        }),
      }),
    );
  }

  registerCommands(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand('agentDebugger.loadManifest', (manifestPath?: string) => this.loadManifest(manifestPath)),
      vscode.commands.registerCommand('agentDebugger.setBreakpoints', () => this.setBreakpoints()),
      vscode.commands.registerCommand('agentDebugger.start', () => this.start()),
      vscode.commands.registerCommand('agentDebugger.runCurrentManifest', async (manifestPath?: string) => {
        await this.loadManifest(manifestPath);
        await this.setBreakpoints();
        await this.start();
      }),
      vscode.commands.registerCommand('agentDebugger.stop', () => this.stop()),
      vscode.commands.registerCommand('agentDebugger.replay', () => this.replay()),
      vscode.commands.registerCommand('agentDebugger.continue', () => this.sendThreadRequest('continue')),
      vscode.commands.registerCommand('agentDebugger.stepOver', () => this.sendThreadRequest('next')),
      vscode.commands.registerCommand('agentDebugger.stepIn', () => this.sendThreadRequest('stepIn')),
      vscode.commands.registerCommand('agentDebugger.stepOut', () => this.sendThreadRequest('stepOut')),
      vscode.commands.registerCommand('agentDebugger.pause', () => this.sendThreadRequest('pause')),
      vscode.commands.registerCommand('agentDebugger.evaluate', async (expression?: string) => {
        const selected = expression ?? await vscode.window.showInputBox({
          title: 'Agent Debugger: Evaluate Expression',
          prompt: 'Expression to evaluate in the current paused stack frame',
        });
        if (selected) {
          await this.evaluateExpression(selected);
        }
      }),
      vscode.commands.registerCommand('agentDebugger.processCommandQueue', () => this.processCommandQueue()),
    ];
  }

  private async loadManifest(manifestPath?: string): Promise<void> {
    const selected = manifestPath ?? await findLatestManifest(this.workspace);
    if (!selected) {
      throw new Error('No .plan-iterate/**/debug/debug_manifest.json found. Pass a manifest path explicitly.');
    }
    this.manifest = await loadManifestFromPath(this.workspace, selected);
    this.commandOffset = 0;
    await appendObservation(this.workspace, this.manifest, 'manifest_loaded', {
      task: this.manifest.task,
      launch_config_name: this.manifest.launch_config_name,
      breakpoint_count: this.manifest.breakpoints.length,
    });
    await writeSessionState(this.workspace, this.manifest, { status: 'manifest_loaded' });
  }

  private async setBreakpoints(): Promise<void> {
    const manifest = this.requireManifest();
    if (this.agentBreakpoints.size > 0) {
      vscode.debug.removeBreakpoints([...this.agentBreakpoints]);
      this.agentBreakpoints.clear();
    }
    const breakpoints = manifest.breakpoints.map((spec) => this.toSourceBreakpoint(spec));
    for (const breakpoint of breakpoints) {
      this.agentBreakpoints.add(breakpoint);
    }
    vscode.debug.addBreakpoints(breakpoints);
    await appendObservation(this.workspace, manifest, 'agent_breakpoints_set', {
      count: breakpoints.length,
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
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    await this.start();
  }

  private async processCommandQueue(): Promise<void> {
    const manifest = this.requireManifest();
    const commandPath = resolveInsideWorkspace(this.workspace, manifest.commands_path);
    let content = '';
    try {
      content = await fs.readFile(commandPath, 'utf8');
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'command_queue_missing', { command_path: manifest.commands_path });
      return;
    }
    const fresh = content.slice(this.commandOffset);
    this.commandOffset = content.length;
    for (const line of fresh.split(/\r?\n/).filter((item) => item.trim().length > 0)) {
      try {
        await this.executeCommand(JSON.parse(line) as DebugCommand);
      } catch (error) {
        await appendObservation(this.workspace, manifest, 'command_failed', { line, error: String(error) });
      }
    }
  }

  private async executeCommand(command: DebugCommand): Promise<void> {
    const manifest = this.requireManifest();
    await appendObservation(this.workspace, manifest, 'command_received', { command });
    switch (command.type) {
      case 'load_manifest':
        await this.loadManifest(command.manifest_path);
        break;
      case 'set_breakpoints':
        await this.setBreakpoints();
        break;
      case 'start':
        await this.start();
        break;
      case 'stop':
        await this.stop();
        break;
      case 'replay':
        await this.replay();
        break;
      case 'continue':
        await this.sendThreadRequest('continue');
        break;
      case 'step_over':
        await this.sendThreadRequest('next');
        break;
      case 'step_in':
        await this.sendThreadRequest('stepIn');
        break;
      case 'step_out':
        await this.sendThreadRequest('stepOut');
        break;
      case 'pause':
        await this.sendThreadRequest('pause');
        break;
      case 'evaluate':
        await this.evaluateExpression(command.expression ?? '');
        break;
    }
  }

  private async sendThreadRequest(command: 'continue' | 'next' | 'stepIn' | 'stepOut' | 'pause'): Promise<void> {
    const manifest = this.requireManifest();
    const session = this.requireSession();
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
    const session = this.requireSession();
    if (!expression) {
      await appendObservation(this.workspace, manifest, 'evaluate_skipped_empty_expression', {});
      return;
    }
    if (!this.currentFrameId) {
      await appendObservation(this.workspace, manifest, 'evaluate_skipped_no_paused_frame', { expression });
      return;
    }
    try {
      const response = await session.customRequest('evaluate', { expression, frameId: this.currentFrameId, context: 'watch' });
      await appendObservation(this.workspace, manifest, 'expression_evaluated', { expression, response });
    } catch (error) {
      await appendObservation(this.workspace, manifest, 'expression_evaluation_failed', { expression, error: String(error) });
    }
  }

  private async onSessionStarted(session: vscode.DebugSession): Promise<void> {
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
    await writeSessionState(this.workspace, this.manifest, { status: 'running', active_session_name: session.name });
  }

  private async onSessionTerminated(session: vscode.DebugSession): Promise<void> {
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

  private async onBreakpointsChanged(event: vscode.BreakpointsChangeEvent): Promise<void> {
    if (!this.manifest) {
      return;
    }
    const humanAdded = event.added.filter((bp) => !this.agentBreakpoints.has(bp)).map((bp) => this.describeBreakpoint(bp));
    if (humanAdded.length > 0) {
      await appendObservation(this.workspace, this.manifest, 'human_breakpoints_added', { breakpoints: humanAdded }, 'human');
    }
    if (event.removed.length > 0) {
      await appendObservation(this.workspace, this.manifest, 'breakpoints_removed', {
        breakpoints: event.removed.map((bp) => this.describeBreakpoint(bp)),
      });
    }
  }

  private async onAdapterMessage(session: vscode.DebugSession, message: unknown): Promise<void> {
    if (!this.manifest || session.id !== this.managedSession?.id) {
      return;
    }
    const event = message as { type?: string; event?: string; body?: Record<string, unknown> };
    if (event.type !== 'event' || event.event !== 'stopped') {
      return;
    }
    const threadId = typeof event.body?.threadId === 'number' ? event.body.threadId : await this.getThreadId(session);
    this.currentThreadId = threadId;
    await this.captureStopped(session, threadId, event.body ?? {});
  }

  private async captureStopped(session: vscode.DebugSession, threadId: number, eventBody: Record<string, unknown>): Promise<void> {
    const manifest = this.requireManifest();
    try {
      const trace = await session.customRequest('stackTrace', { threadId, startFrame: 0, levels: 1 });
      const frame = trace?.stackFrames?.[0];
      if (!frame) {
        await appendObservation(this.workspace, manifest, 'breakpoint_stopped_no_frame', { threadId, eventBody }, 'debugger');
        return;
      }
      this.currentFrameId = frame.id;
      const sourcePath = typeof frame.source?.path === 'string' ? frame.source.path : undefined;
      const rel = sourcePath ? path.relative(this.workspace.uri.fsPath, sourcePath).replace(/\\/g, '/') : undefined;
      const line = typeof frame.line === 'number' ? frame.line : undefined;
      const matching = manifest.breakpoints.find((bp) => rel && path.normalize(bp.file) === path.normalize(rel) && bp.line === line);
      const expressions: Record<string, unknown> = {};
      for (const expression of matching?.expressions ?? []) {
        try {
          const response = await session.customRequest('evaluate', { expression, frameId: frame.id, context: 'watch' });
          expressions[expression] = response?.result ?? response;
        } catch (error) {
          expressions[expression] = { error: String(error) };
        }
      }
      await appendObservation(this.workspace, manifest, 'breakpoint_hit', {
        threadId,
        frameId: frame.id,
        file: rel ?? sourcePath ?? null,
        line,
        name: frame.name,
        reason: matching?.reason ?? null,
        eventBody,
        expressions,
      }, 'debugger');
      await writeSessionState(this.workspace, manifest, {
        status: 'paused',
        active_session_name: session.name,
        current_file: rel ?? sourcePath,
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
    const response = await session.customRequest('threads');
    const threadId = response?.threads?.[0]?.id;
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
      throw new Error('No agent-debugger manifest loaded.');
    }
    return this.manifest;
  }

  private requireSession(): vscode.DebugSession {
    if (!this.managedSession) {
      throw new Error('No managed debug session is active.');
    }
    return this.managedSession;
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const bridge = new AgentDebuggerBridge(context);
  context.subscriptions.push(...bridge.registerCommands());
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory('agent-debugger-mock', {
    createDebugAdapterDescriptor: (session) => {
      const program = String(session.configuration.program ?? 'target.py');
      return new vscode.DebugAdapterInlineImplementation(new MockDebugAdapter(program));
    },
  }));
}

export function deactivate(): void {
  // VS Code disposes subscriptions from the extension context.
}
