import * as vscode from 'vscode';

type ProtocolMessage = { seq: number; type: string };
type RequestMessage = ProtocolMessage & { type: 'request'; command: string; arguments?: Record<string, unknown> };
type ResponseMessage = ProtocolMessage & {
  type: 'response';
  request_seq: number;
  command: string;
  success: boolean;
  message?: string;
  body?: unknown;
};
type EventMessage = ProtocolMessage & { type: 'event'; event: string; body?: unknown };

export class MockDebugAdapter implements vscode.DebugAdapter {
  private readonly emitter = new vscode.EventEmitter<ProtocolMessage>();
  readonly onDidSendMessage = this.emitter.event;
  private seq = 1;
  private currentLine = 1;
  private sourcePath: string;

  constructor(program: string | undefined) {
    this.sourcePath = program ?? 'target.py';
  }

  handleMessage(message: ProtocolMessage): void {
    const request = message as RequestMessage;
    if (request.type !== 'request') {
      return;
    }
    switch (request.command) {
      case 'initialize':
        this.sendResponse(request, {
          supportsConfigurationDoneRequest: true,
          supportsEvaluateForHovers: true,
          supportsStepBack: false,
          supportsDataBreakpoints: false,
        });
        this.sendEvent('initialized', {});
        return;
      case 'launch':
        this.sourcePath = String(request.arguments?.program ?? this.sourcePath).replace('${workspaceFolder}', vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '');
        this.sendResponse(request);
        return;
      case 'setBreakpoints': {
        const source = request.arguments?.source as { path?: string } | undefined;
        const breakpoints = request.arguments?.breakpoints as Array<{ line?: number }> | undefined;
        this.sourcePath = source?.path ?? this.sourcePath;
        const requested = breakpoints ?? [];
        if (requested.length > 0 && requested[0].line) {
          this.currentLine = requested[0].line;
        }
        this.sendResponse(request, {
          breakpoints: requested.map((bp, index) => ({ id: index + 1, verified: true, line: bp.line })),
        });
        return;
      }
      case 'setExceptionBreakpoints':
      case 'configurationDone':
        this.sendResponse(request);
        if (request.command === 'configurationDone') {
          this.sendEvent('stopped', { reason: 'breakpoint', threadId: 1, allThreadsStopped: true });
        }
        return;
      case 'threads':
        this.sendResponse(request, { threads: [{ id: 1, name: 'mock-thread' }] });
        return;
      case 'stackTrace':
        this.sendResponse(request, {
          stackFrames: [{
            id: 1000,
            name: 'mock_main',
            source: { name: 'target.py', path: this.sourcePath },
            line: this.currentLine,
            column: 1,
          }],
          totalFrames: 1,
        });
        return;
      case 'evaluate': {
        const expression = String(request.arguments?.expression ?? '');
        this.sendResponse(request, {
          result: this.evaluate(expression),
          variablesReference: 0,
        });
        return;
      }
      case 'continue':
        this.sendResponse(request, { allThreadsContinued: true });
        this.sendEvent('terminated', {});
        return;
      case 'next':
      case 'stepIn':
      case 'stepOut':
      case 'pause':
        this.sendResponse(request);
        this.currentLine += 1;
        this.sendEvent('stopped', { reason: request.command, threadId: 1, allThreadsStopped: true });
        return;
      case 'disconnect':
        this.sendResponse(request);
        this.sendEvent('terminated', {});
        return;
      default:
        this.sendResponse(request, undefined, false, `Unsupported mock command: ${request.command}`);
    }
  }

  dispose(): void {
    this.emitter.dispose();
  }

  private evaluate(expression: string): string {
    const values: Record<string, string> = {
      value: '42',
      'payload.get("key")': 'None',
      'len(items)': '3',
      items: '[1, 2, 3]',
    };
    return values[expression] ?? `mock:${expression}`;
  }

  private sendResponse(request: RequestMessage, body?: unknown, success = true, message?: string): void {
    const response: ResponseMessage = {
      seq: this.seq++,
      type: 'response',
      request_seq: request.seq,
      command: request.command,
      success,
      message,
      body,
    };
    this.emitter.fire(response);
  }

  private sendEvent(event: string, body: unknown): void {
    const protocolEvent: EventMessage = {
      seq: this.seq++,
      type: 'event',
      event,
      body,
    };
    this.emitter.fire(protocolEvent);
  }
}
