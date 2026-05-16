import * as fs from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';
import { AgentDebuggerManifest, ManifestBreakpoint } from './types';

export function getWorkspaceFolder(): vscode.WorkspaceFolder {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    throw new Error('Agent Debugger requires an open VS Code workspace folder.');
  }
  return folders[0];
}

export function resolveInsideWorkspace(workspace: vscode.WorkspaceFolder, relativePath: string): string {
  if (path.isAbsolute(relativePath)) {
    throw new Error(`Manifest path must be workspace-relative, got absolute path: ${relativePath}`);
  }
  const root = workspace.uri.fsPath;
  const resolved = path.resolve(root, relativePath);
  const relative = path.relative(root, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Manifest path escapes workspace: ${relativePath}`);
  }
  return resolved;
}

function assertString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`debug_manifest.json field '${field}' must be a non-empty string.`);
  }
  return value;
}

function assertBreakpoint(value: unknown, index: number): ManifestBreakpoint {
  if (!value || typeof value !== 'object') {
    throw new Error(`breakpoints[${index}] must be an object.`);
  }
  const item = value as Record<string, unknown>;
  const file = assertString(item.file, `breakpoints[${index}].file`);
  const line = item.line;
  if (typeof line !== 'number' || !Number.isInteger(line) || line < 1) {
    throw new Error(`breakpoints[${index}].line must be an integer >= 1.`);
  }
  const expressionsRaw = item.expressions;
  const expressions = Array.isArray(expressionsRaw)
    ? expressionsRaw.map((expr, exprIndex) => assertString(expr, `breakpoints[${index}].expressions[${exprIndex}]`))
    : [];
  return {
    file,
    line,
    expressions,
    reason: typeof item.reason === 'string' ? item.reason : undefined,
    stop: typeof item.stop === 'boolean' ? item.stop : true,
    source: item.source === 'human' || item.source === 'bridge' ? item.source : 'agent',
    logMessage: typeof item.logMessage === 'string' ? item.logMessage : undefined,
    condition: typeof item.condition === 'string' ? item.condition : undefined,
  };
}

export async function loadManifestFromPath(
  workspace: vscode.WorkspaceFolder,
  manifestPath: string,
): Promise<AgentDebuggerManifest> {
  const resolvedManifestPath = path.isAbsolute(manifestPath)
    ? manifestPath
    : resolveInsideWorkspace(workspace, manifestPath);
  const root = workspace.uri.fsPath;
  const relative = path.relative(root, resolvedManifestPath);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Manifest file must be inside workspace: ${manifestPath}`);
  }

  const raw = await fs.readFile(resolvedManifestPath, 'utf8');
  const parsed = JSON.parse(raw) as Record<string, unknown>;
  const schema = parsed.schema;
  if (schema !== 'agent_debugger_manifest.v1' && schema !== 'human_debug_manifest.v1') {
    throw new Error(`Unsupported manifest schema: ${String(schema)}`);
  }
  const language = parsed.language;
  if (language !== 'python') {
    throw new Error(`agent-debugger v1 supports only language='python', got ${String(language)}.`);
  }
  const breakpointsRaw = parsed.breakpoints;
  if (!Array.isArray(breakpointsRaw)) {
    throw new Error("debug_manifest.json field 'breakpoints' must be a list.");
  }

  const manifest: AgentDebuggerManifest = {
    schema,
    version: typeof parsed.version === 'number' ? parsed.version : 1,
    language,
    task: assertString(parsed.task, 'task'),
    launch_config_name: assertString(parsed.launch_config_name, 'launch_config_name'),
    harness: assertString(parsed.harness, 'harness'),
    target: typeof parsed.target === 'string' ? parsed.target : undefined,
    target_args: Array.isArray(parsed.target_args) ? parsed.target_args.map((arg, index) => assertString(arg, `target_args[${index}]`)) : [],
    breakpoints: breakpointsRaw.map(assertBreakpoint),
    commands_path: assertString(parsed.commands_path, 'commands_path'),
    observations_path: assertString(parsed.observations_path, 'observations_path'),
    session_state_path: assertString(parsed.session_state_path, 'session_state_path'),
    generated_at: typeof parsed.generated_at === 'string' ? parsed.generated_at : undefined,
    lifecycle: parsed.lifecycle && typeof parsed.lifecycle === 'object' ? parsed.lifecycle as AgentDebuggerManifest['lifecycle'] : undefined,
  };

  resolveInsideWorkspace(workspace, manifest.harness);
  resolveInsideWorkspace(workspace, manifest.commands_path);
  resolveInsideWorkspace(workspace, manifest.observations_path);
  resolveInsideWorkspace(workspace, manifest.session_state_path);
  for (const breakpoint of manifest.breakpoints) {
    resolveInsideWorkspace(workspace, breakpoint.file);
  }
  return manifest;
}

export async function findLatestManifest(workspace: vscode.WorkspaceFolder): Promise<string | undefined> {
  const files = await vscode.workspace.findFiles(new vscode.RelativePattern(workspace, '.plan-iterate/**/debug/debug_manifest.json'));
  if (files.length === 0) {
    return undefined;
  }
  const withStats = await Promise.all(files.map(async (uri) => {
    const stat = await fs.stat(uri.fsPath);
    return { uri, mtime: stat.mtimeMs };
  }));
  withStats.sort((a, b) => b.mtime - a.mtime);
  return path.relative(workspace.uri.fsPath, withStats[0].uri.fsPath);
}
