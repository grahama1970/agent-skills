#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';

const DEFAULT_EXTENSION_DIR = '/home/graham/.pi/agent/extensions/lazy-report-shame-shame-shame';
const DEFAULT_SOURCES = [
  process.env.SHAME_WORD_WAV || '',
  '/tmp/lrsss-explicit-embry-ref-single-shame.wav',
  '/tmp/lrsss-chatterbox-lower-female-shame-single.wav',
].filter(Boolean);

function usage(exitCode = 0) {
  console.log(`Usage:
  install-shame-audio.mjs status [--extension-dir DIR]
  install-shame-audio.mjs install [--source FILE] [--extension-dir DIR] [--max-duration-sec N] [--min-duration-sec N] [--min-active-duration-sec N]

Installs one short Chatterbox word: "shame". No bell, no three-part shame loop.`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const opts = {
    command: argv[0] || 'status',
    source: '',
    extensionDir: DEFAULT_EXTENSION_DIR,
    maxDurationSec: 2.5,
    minDurationSec: 0.9,
    minActiveDurationSec: 0.45,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') usage(0);
    if (arg === '--source') opts.source = argv[++i] || '';
    else if (arg === '--extension-dir') opts.extensionDir = argv[++i] || '';
    else if (arg === '--max-duration-sec') opts.maxDurationSec = Number(argv[++i] || '2.5');
    else if (arg === '--min-duration-sec') opts.minDurationSec = Number(argv[++i] || '0.9');
    else if (arg === '--min-active-duration-sec') opts.minActiveDurationSec = Number(argv[++i] || '0.45');
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!['status', 'install'].includes(opts.command)) throw new Error(`unknown command: ${opts.command}`);
  if (!Number.isFinite(opts.maxDurationSec) || opts.maxDurationSec <= 0) throw new Error('max duration must be positive');
  if (!Number.isFinite(opts.minDurationSec) || opts.minDurationSec <= 0) throw new Error('min duration must be positive');
  if (!Number.isFinite(opts.minActiveDurationSec) || opts.minActiveDurationSec <= 0) throw new Error('min active duration must be positive');
  if (opts.minDurationSec > opts.maxDurationSec) throw new Error('min duration must not exceed max duration');
  return opts;
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function wavPcmStats(path, sampleRate, channels) {
  const buf = readFileSync(path);
  if (buf.length < 44 || buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') {
    return {};
  }
  let offset = 12;
  let dataStart = -1;
  let dataSize = 0;
  while (offset + 8 <= buf.length) {
    const id = buf.toString('ascii', offset, offset + 4);
    const size = buf.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (id === 'data') {
      dataStart = start;
      dataSize = Math.min(size, buf.length - start);
      break;
    }
    offset = start + size + (size % 2);
  }
  if (dataStart < 0 || dataSize < 2) return {};
  const sampleCount = Math.floor(dataSize / 2);
  const threshold = 100;
  let peak = 0;
  let firstActive = -1;
  let lastActive = -1;
  for (let i = 0; i < sampleCount; i += 1) {
    const abs = Math.abs(buf.readInt16LE(dataStart + i * 2));
    if (abs > peak) peak = abs;
    if (abs >= threshold) {
      const frame = Math.floor(i / Math.max(1, channels || 1));
      if (firstActive < 0) firstActive = frame;
      lastActive = frame;
    }
  }
  const activeFrames = firstActive >= 0 ? lastActive - firstActive + 1 : 0;
  return {
    pcm_peak: peak,
    active_duration_sec: sampleRate ? activeFrames / sampleRate : null,
    active_threshold_pcm16: threshold,
  };
}

function probe(path) {
  if (!existsSync(path)) return { exists: false, path };
  const result = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'stream=codec_name,sample_rate,channels,duration,bits_per_sample', '-of', 'json', path], { encoding: 'utf8', timeout: 5000 });
  let parsed = {};
  try { parsed = JSON.parse(result.stdout || '{}'); } catch {}
  const stream = parsed.streams?.[0] || {};
  const sampleRate = stream.sample_rate ? Number(stream.sample_rate) : null;
  const channels = stream.channels ? Number(stream.channels) : null;
  return {
    exists: true,
    path,
    sha256: sha256(path),
    codec_name: stream.codec_name || null,
    sample_rate: stream.sample_rate || null,
    channels: stream.channels || null,
    bits_per_sample: stream.bits_per_sample || null,
    duration_sec: stream.duration ? Number(stream.duration) : null,
    ...wavPcmStats(path, sampleRate, channels),
  };
}

function policyFailures(probed, opts) {
  const failures = [];
  if (!probed.exists) failures.push(`source does not exist: ${probed.path}`);
  if (probed.exists && probed.duration_sec === null) failures.push(`could not read source duration with ffprobe: ${probed.path}`);
  if (probed.duration_sec !== null && probed.duration_sec > opts.maxDurationSec) failures.push(`source is ${probed.duration_sec}s; expected <= ${opts.maxDurationSec}s, not a bell/loop`);
  if (probed.duration_sec !== null && probed.duration_sec < opts.minDurationSec) failures.push(`source is ${probed.duration_sec}s; expected >= ${opts.minDurationSec}s so it is not a sped-up/header-mismatched word`);
  if (probed.active_duration_sec !== undefined && probed.active_duration_sec !== null && probed.active_duration_sec < opts.minActiveDurationSec) {
    failures.push(`active speech is ${probed.active_duration_sec}s; expected >= ${opts.minActiveDurationSec}s`);
  }
  return failures;
}

function selectSource(opts) {
  if (opts.source) {
    const sourceProbe = probe(opts.source);
    const failures = policyFailures(sourceProbe, opts);
    if (failures.length) throw new Error(failures.join('; '));
    return { source: opts.source, sourceProbe };
  }
  const attempts = [];
  for (const source of DEFAULT_SOURCES) {
    const sourceProbe = probe(source);
    const failures = policyFailures(sourceProbe, opts);
    if (!failures.length) return { source, sourceProbe };
    attempts.push(`${source}: ${failures.join(', ')}`);
  }
  throw new Error(`no valid Chatterbox shame word source found. Set --source or SHAME_WORD_WAV. Attempts: ${attempts.join(' | ')}`);
}

try {
  const opts = parseArgs(process.argv.slice(2));
  const target = join(opts.extensionDir, 'shame.wav');
  if (opts.command === 'status') {
    console.log(JSON.stringify({ ok: true, installed: probe(target) }, null, 2));
    process.exit(0);
  }
  const { source, sourceProbe } = selectSource(opts);
  mkdirSync(opts.extensionDir, { recursive: true });
  copyFileSync(source, target);
  const installed = probe(target);
  const installedFailures = policyFailures(installed, opts);
  if (installedFailures.length) throw new Error(`installed audio failed policy: ${installedFailures.join('; ')}`);
  const receipt = {
    schema: 'lazy_report_shame.audio_install.v1',
    installed_at: new Date().toISOString(),
    source: sourceProbe,
    installed,
    policy: {
      phrase: 'shame',
      count: 1,
      bell: false,
      max_duration_sec: opts.maxDurationSec,
      min_duration_sec: opts.minDurationSec,
      min_active_duration_sec: opts.minActiveDurationSec,
    },
  };
  writeFileSync(join(opts.extensionDir, 'shame-audio-receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({ ok: true, receipt: join(opts.extensionDir, 'shame-audio-receipt.json'), installed }, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
