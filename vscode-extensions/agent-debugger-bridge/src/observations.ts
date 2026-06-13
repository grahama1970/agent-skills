import * as fs from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';
import { resolveInsideWorkspace } from './manifest';
import { AgentDebuggerManifest, ObservationRecord, SessionState } from './types';

function nowIso(): string {
  return new Date().toISOString();
}

export async function appendObservation(
  workspace: vscode.WorkspaceFolder,
  manifest: AgentDebuggerManifest,
  type: string,
  data: Record<string, unknown>,
  source: ObservationRecord['source'] = 'bridge',
): Promise<void> {
  const observationPath = resolveInsideWorkspace(workspace, manifest.observations_path);
  await fs.mkdir(path.dirname(observationPath), { recursive: true });
  const record: ObservationRecord = {
    schema: 'agent_debugger_observation.v1',
    ts: nowIso(),
    type,
    task: manifest.task,
    source,
    data,
  };
  await fs.appendFile(observationPath, `${JSON.stringify(record)}\n`, 'utf8');
}

export async function writeSessionState(
  workspace: vscode.WorkspaceFolder,
  manifest: AgentDebuggerManifest,
  state: Omit<SessionState, 'schema' | 'updated_at' | 'task' | 'launch_config_name'>,
): Promise<void> {
  const statePath = resolveInsideWorkspace(workspace, manifest.session_state_path);
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  const record: SessionState = {
    schema: 'agent_debugger_session_state.v1',
    task: manifest.task,
    launch_config_name: manifest.launch_config_name,
    updated_at: nowIso(),
    ...state,
  };
  await fs.writeFile(statePath, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
}

export function observationSummaryPath(workspace: vscode.WorkspaceFolder, manifest: AgentDebuggerManifest): string {
  return resolveInsideWorkspace(workspace, manifest.observations_path);
}
