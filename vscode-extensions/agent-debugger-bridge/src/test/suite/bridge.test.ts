import * as assert from 'assert';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';

interface JsonRecord {
  type?: string;
  data?: Record<string, unknown>;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function readJsonl(file: string): Promise<JsonRecord[]> {
  try {
    const raw = await fs.readFile(file, 'utf8');
    return raw
      .split(/\r?\n/)
      .filter((line) => line.trim().length > 0)
      .map((line) => JSON.parse(line) as JsonRecord);
  } catch (error) {
    return [];
  }
}

async function waitForRecord(file: string, predicate: (record: JsonRecord) => boolean, timeoutMs = 12000): Promise<JsonRecord> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const records = await readJsonl(file);
    const found = records.find(predicate);
    if (found) {
      return found;
    }
    await wait(100);
  }
  const records = await readJsonl(file);
  throw new Error(`Timed out waiting for observation. Current records: ${JSON.stringify(records, null, 2)}`);
}

async function writeJson(file: string, value: unknown): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

suite('Agent Debugger Bridge e2e', () => {
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspace) {
    throw new Error('Test workspace was not opened.');
  }

  const targetPath = path.join(workspace, 'target.py');
  const debugDir = path.join(workspace, '.plan-iterate', 'bridge-e2e', 'debug');
  const manifestPath = path.join(debugDir, 'debug_manifest.json');
  const observationsPath = path.join(debugDir, 'debug_observations.jsonl');
  const commandsPath = path.join(debugDir, 'debug_commands.jsonl');
  const statePath = path.join(debugDir, 'debug_session_state.json');

  setup(async () => {
    await fs.rm(path.join(workspace, '.plan-iterate'), { recursive: true, force: true });
    await fs.rm(path.join(workspace, '.vscode'), { recursive: true, force: true });
    vscode.debug.removeBreakpoints(vscode.debug.breakpoints);

    const lines = [
      'items = [1, 2, 3]',
      'value = 42',
      'payload = {}',
      'print(value)',
    ];
    await fs.writeFile(targetPath, `${lines.join('\n')}\n`, 'utf8');

    await writeJson(path.join(workspace, '.vscode', 'launch.json'), {
      version: '0.2.0',
      configurations: [
        {
          name: 'Agent Debugger: bridge-e2e',
          type: 'agent-debugger-mock',
          request: 'launch',
          program: '${workspaceFolder}/target.py',
        },
      ],
    });
    await writeJson(manifestPath, {
      schema: 'agent_debugger_manifest.v1',
      version: 1,
      language: 'python',
      task: 'bridge-e2e',
      launch_config_name: 'Agent Debugger: bridge-e2e',
      harness: 'target.py',
      breakpoints: [
        {
          file: 'target.py',
          line: 2,
          reason: 'Inspect value and item count at the suspected line.',
          expressions: ['value', 'len(items)', 'payload.get("key")'],
          source: 'agent',
          stop: true,
        },
      ],
      commands_path: '.plan-iterate/bridge-e2e/debug/debug_commands.jsonl',
      observations_path: '.plan-iterate/bridge-e2e/debug/debug_observations.jsonl',
      session_state_path: '.plan-iterate/bridge-e2e/debug/debug_session_state.json',
      lifecycle: {
        replay_semantics: 'stop_and_restart_same_launch_config',
        managed_session_only: true,
      },
    });
    await fs.writeFile(observationsPath, '', 'utf8');
    await fs.writeFile(commandsPath, '', 'utf8');
    await writeJson(statePath, { schema: 'agent_debugger_session_state.v1', status: 'not_started' });
  });

  teardown(async () => {
    await vscode.commands.executeCommand('agentDebugger.stop');
    await wait(200);
    vscode.debug.removeBreakpoints(vscode.debug.breakpoints);
  });

  test('loads manifest, sets breakpoints, starts managed session, and captures expressions', async () => {
    await vscode.commands.executeCommand('agentDebugger.runCurrentManifest', manifestPath);

    const hit = await waitForRecord(observationsPath, (record) => record.type === 'breakpoint_hit');
    assert.strictEqual(hit.data?.file, 'target.py');
    assert.strictEqual(hit.data?.line, 2);
    assert.deepStrictEqual(hit.data?.expressions, {
      value: '42',
      'len(items)': '3',
      'payload.get("key")': 'None',
    });

    const state = JSON.parse(await fs.readFile(statePath, 'utf8')) as Record<string, unknown>;
    assert.strictEqual(state.status, 'paused');
    assert.strictEqual(state.current_file, 'target.py');
    assert.strictEqual(state.current_line, 2);
  });

  test('records human-set breakpoints after manifest load', async () => {
    await vscode.commands.executeCommand('agentDebugger.loadManifest', manifestPath);
    const humanBreakpoint = new vscode.SourceBreakpoint(
      new vscode.Location(vscode.Uri.file(targetPath), new vscode.Position(3, 0)),
      true,
    );
    vscode.debug.addBreakpoints([humanBreakpoint]);

    const record = await waitForRecord(observationsPath, (item) => item.type === 'human_breakpoints_added');
    const breakpoints = record.data?.breakpoints as Array<Record<string, unknown>>;
    assert.strictEqual(breakpoints[0].file, 'target.py');
    assert.strictEqual(breakpoints[0].line, 4);
  });

  test('processes queued evaluate and continue commands while paused', async () => {
    await vscode.commands.executeCommand('agentDebugger.runCurrentManifest', manifestPath);
    await waitForRecord(observationsPath, (record) => record.type === 'breakpoint_hit');

    await fs.appendFile(commandsPath, `${JSON.stringify({ type: 'evaluate', expression: 'items', source: 'agent' })}\n`, 'utf8');
    await vscode.commands.executeCommand('agentDebugger.processCommandQueue');
    const evaluated = await waitForRecord(observationsPath, (record) => record.type === 'expression_evaluated');
    assert.strictEqual((evaluated.data?.response as Record<string, unknown>)?.result, '[1, 2, 3]');

    await fs.appendFile(commandsPath, `${JSON.stringify({ type: 'continue', source: 'agent' })}\n`, 'utf8');
    await vscode.commands.executeCommand('agentDebugger.processCommandQueue');
    await waitForRecord(observationsPath, (record) => record.type === 'debug_session_terminated');
  });

  test('replay means stop and restart the same launch configuration', async () => {
    await vscode.commands.executeCommand('agentDebugger.runCurrentManifest', manifestPath);
    await waitForRecord(observationsPath, (record) => record.type === 'breakpoint_hit');

    await vscode.commands.executeCommand('agentDebugger.replay');
    await waitForRecord(observationsPath, (record) => record.type === 'replay_requested');

    const records = await readJsonl(observationsPath);
    const startRequests = records.filter((record) => record.type === 'debug_start_requested');
    assert.ok(startRequests.length >= 2, `expected at least two starts, got ${startRequests.length}`);
  });
});
