import path from 'node:path'
import { fileURLToPath } from 'node:url'

export type WatchServerConfig = {
  port: number
  reportPath: string
  framesDir: string
  memoryDaemonUrl: string
  yoloLabelDir: string
  detectorCandidatesDir: string
  trackerEventsPath: string
  trackerScriptPath: string
  trackerModelPath: string
  overlayPayloadPath: string
  retryMemorySyncOnStart: boolean
}

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const WATCH_SKILL_DIR = path.resolve(__dirname, '..', '..')

function envString(env: NodeJS.ProcessEnv, key: string, fallback: string): string {
  const value = env[key]
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function envPort(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const value = Number(env[key])
  return Number.isInteger(value) && value > 0 && value <= 65535 ? value : fallback
}

function envBoolean(env: NodeJS.ProcessEnv, key: string, fallback: boolean): boolean {
  const value = env[key]
  if (value == null || value === '') return fallback
  return /^(1|true|yes|on)$/i.test(value)
}

export function loadWatchServerConfig(env: NodeJS.ProcessEnv = process.env): WatchServerConfig {
  return {
    port: envPort(env, 'WATCH_API_PORT', 3003),
    reportPath: envString(env, 'WATCH_REPORT_PATH', '/tmp/watch-wex5uxs_/report.json'),
    framesDir: envString(env, 'WATCH_FRAMES_DIR', '/mnt/storage12tb/media/watch-frames'),
    memoryDaemonUrl: envString(env, 'MEMORY_DAEMON_URL', 'http://127.0.0.1:8601'),
    yoloLabelDir: envString(
      env,
      'WATCH_YOLO_LABEL_DIR',
      path.join(WATCH_SKILL_DIR, 'docs/architecture/generated/watch_yolo_track_labels'),
    ),
    detectorCandidatesDir: envString(
      env,
      'WATCH_DETECTOR_CANDIDATES_DIR',
      path.join(WATCH_SKILL_DIR, 'docs/architecture/generated'),
    ),
    trackerEventsPath: envString(
      env,
      'WATCH_TRACKER_EVENTS_PATH',
      path.join(
        WATCH_SKILL_DIR,
        'docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl',
      ),
    ),
    trackerScriptPath: envString(
      env,
      'WATCH_TRACKER_SCRIPT',
      path.join(WATCH_SKILL_DIR, 'scripts/track_yolo_bytetrack.py'),
    ),
    trackerModelPath: envString(env, 'WATCH_TRACKER_MODEL', path.join(WATCH_SKILL_DIR, 'yolo11n.pt')),
    overlayPayloadPath: envString(
      env,
      'WATCH_OVERLAY_PAYLOAD_PATH',
      path.join(
        WATCH_SKILL_DIR,
        'docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json',
      ),
    ),
    retryMemorySyncOnStart: envBoolean(env, 'WATCH_YOLO_SYNC_RETRY_ON_START', false),
  }
}

export const WATCH_SKILL_DIR_PATH = WATCH_SKILL_DIR
