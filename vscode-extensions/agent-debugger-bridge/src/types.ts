export type DebuggerLanguage = 'python';

export interface ManifestBreakpoint {
  file: string;
  line: number;
  reason?: string;
  expressions?: string[];
  stop?: boolean;
  source?: 'agent' | 'human' | 'bridge';
  logMessage?: string;
  condition?: string;
}

export interface AgentDebuggerManifest {
  schema: 'agent_debugger_manifest.v1' | 'human_debug_manifest.v1';
  version: number;
  language: DebuggerLanguage;
  task: string;
  launch_config_name: string;
  harness: string;
  target?: string;
  target_args?: string[];
  breakpoints: ManifestBreakpoint[];
  commands_path: string;
  observations_path: string;
  session_state_path: string;
  generated_at?: string;
  lifecycle?: {
    replay_semantics?: 'stop_and_restart_same_launch_config' | string;
    managed_session_only?: boolean;
  };
}

export interface ObservationRecord {
  schema: 'agent_debugger_observation.v1';
  ts: string;
  type: string;
  task?: string;
  source?: 'agent' | 'human' | 'bridge' | 'debugger';
  data: Record<string, unknown>;
}

export interface SessionState {
  schema: 'agent_debugger_session_state.v1';
  status: 'not_started' | 'manifest_loaded' | 'breakpoints_set' | 'running' | 'paused' | 'stopped' | 'error';
  task?: string;
  launch_config_name?: string;
  active_session_name?: string;
  current_file?: string;
  current_line?: number;
  current_thread_id?: number;
  updated_at: string;
  message?: string;
}

export interface DebugCommand {
  type:
    | 'load_manifest'
    | 'set_breakpoints'
    | 'start'
    | 'stop'
    | 'replay'
    | 'continue'
    | 'step_over'
    | 'step_in'
    | 'step_out'
    | 'pause'
    | 'evaluate';
  manifest_path?: string;
  expression?: string;
  source?: 'agent' | 'human';
  reason?: string;
}
