import assert from 'node:assert/strict'
import { copyFile, mkdir, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { runCommand, sha256File } from './proofUtils'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(uiRoot, '..', '..', '..')
const watchRoot = path.resolve(repoRoot, 'skills/watch')

function argValue(name: string): string | null {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || null : null
}

function formatSrtTime(seconds: number): string {
  const whole = Math.floor(seconds)
  const millis = Math.round((seconds - whole) * 1000)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = whole % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(millis).padStart(3, '0')}`
}

async function requireCommand(command: string): Promise<void> {
  const result = await runCommand({
    command: 'bash',
    args: ['-lc', `command -v ${command}`],
    cwd: repoRoot,
  })
  assert.equal(result.exit_code, 0, `${command} is required for the live pyannote immutable sanity check`)
}

async function probeDuration(filePath: string): Promise<number> {
  const result = await runCommand({
    command: 'ffprobe',
    args: ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', filePath],
    cwd: repoRoot,
  })
  assert.equal(result.exit_code, 0, result.stderr || result.stdout)
  const duration = Number.parseFloat(result.stdout.trim())
  assert.ok(Number.isFinite(duration) && duration > 0, `invalid duration for ${filePath}: ${result.stdout}`)
  return duration
}

async function health(url: string): Promise<Record<string, unknown>> {
  const response = await fetch(url)
  assert.equal(response.status, 200, `pyannote health returned HTTP ${response.status}`)
  const payload = await response.json() as Record<string, unknown>
  assert.equal(payload.ok, true)
  assert.equal(payload.provider, 'pyannote')
  assert.equal(payload.model, 'pyannote/speaker-diarization-community-1')
  assert.equal(payload.model_loaded, true)
  if ((process.env.WATCH_PYANNOTE_REQUIRE_CUDA || 'true') !== 'false') {
    assert.equal(payload.device, 'cuda', `expected CUDA-backed pyannote service, got ${String(payload.device)}`)
  }
  return payload
}

async function makeFixture(root: string): Promise<{ video: string, captions: string, audio: string }> {
  const rawA = path.join(root, 'speaker-a.raw.wav')
  const rawB = path.join(root, 'speaker-b.raw.wav')
  const wavA = path.join(root, 'speaker-a.wav')
  const wavB = path.join(root, 'speaker-b.wav')
  const silence = path.join(root, 'silence.wav')
  const audioList = path.join(root, 'audio-list.txt')
  const audio = path.join(root, 'source-audio.wav')
  const video = path.join(root, 'source-video.mp4')
  const captions = path.join(root, 'captions.srt')

  for (const command of [
    {
      args: [
        '-v',
        'en-us+m1',
        '-s',
        '145',
        '-w',
        rawA,
        'This is speaker alpha. The watch diarization sanity check is running through a real video file.',
      ],
    },
    {
      args: [
        '-v',
        'en-us+f3',
        '-s',
        '155',
        '-w',
        rawB,
        'This is speaker beta. Anonymous speakers must stay evidence, and must not become character names.',
      ],
    },
  ]) {
    const result = await runCommand({ command: 'espeak-ng', args: command.args, cwd: root })
    assert.equal(result.exit_code, 0, result.stderr || result.stdout)
  }
  for (const [input, output] of [[rawA, wavA], [rawB, wavB]]) {
    const result = await runCommand({
      command: 'ffmpeg',
      args: ['-hide_banner', '-loglevel', 'error', '-y', '-i', input, '-ar', '16000', '-ac', '1', output],
      cwd: root,
    })
    assert.equal(result.exit_code, 0, result.stderr || result.stdout)
  }
  const silenceResult = await runCommand({
    command: 'ffmpeg',
    args: ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '0.8', silence],
    cwd: root,
  })
  assert.equal(silenceResult.exit_code, 0, silenceResult.stderr || silenceResult.stdout)

  await writeFile(audioList, [`file '${wavA}'`, `file '${silence}'`, `file '${wavB}'`, ''].join('\n'))
  const concatResult = await runCommand({
    command: 'ffmpeg',
    args: ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', audioList, '-c', 'copy', audio],
    cwd: root,
  })
  assert.equal(concatResult.exit_code, 0, concatResult.stderr || concatResult.stdout)

  const aDuration = await probeDuration(wavA)
  const audioDuration = await probeDuration(audio)
  const videoResult = await runCommand({
    command: 'ffmpeg',
    args: [
      '-hide_banner',
      '-loglevel',
      'error',
      '-y',
      '-f',
      'lavfi',
      '-i',
      `testsrc2=size=320x180:rate=24:duration=${audioDuration.toFixed(3)}`,
      '-i',
      audio,
      '-shortest',
      '-c:v',
      'libx264',
      '-preset',
      'ultrafast',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      video,
    ],
    cwd: root,
  })
  assert.equal(videoResult.exit_code, 0, videoResult.stderr || videoResult.stdout)

  const secondStart = aDuration + 0.8
  await writeFile(
    captions,
    [
      '1',
      `${formatSrtTime(0)} --> ${formatSrtTime(Math.min(aDuration + 0.2, secondStart - 0.1))}`,
      'This is speaker alpha. The watch diarization sanity check is running through a real video file.',
      '',
      '2',
      `${formatSrtTime(secondStart)} --> ${formatSrtTime(audioDuration)}`,
      'This is speaker beta. Anonymous speakers must stay evidence, and must not become character names.',
      '',
    ].join('\n'),
  )
  return { video, captions, audio }
}

async function main(): Promise<void> {
  await requireCommand('ffmpeg')
  await requireCommand('ffprobe')
  await requireCommand('espeak-ng')

  const healthUrl = process.env.WATCH_DIARIZATION_HEALTH_URL || 'http://127.0.0.1:9001/healthz'
  const serviceHealth = await health(healthUrl)

  const proofRoot = path.resolve(
    argValue('--proof-dir')
      || process.env.WATCH_PYANNOTE_PROOF_DIR
      || process.env.WATCH_PROOF_DIR
      || path.join(os.tmpdir(), 'watch-pyannote-immutable-live-proof'),
  )
  const proofDir = path.join(proofRoot, 'pyannote-immutable-e2e')
  await mkdir(proofDir, { recursive: true })
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'watch-pyannote-immutable-'))

  try {
    const fixture = await makeFixture(tempRoot)
    const sourceVideoProof = path.join(proofDir, 'source-video.mp4')
    const sourceCaptionsProof = path.join(proofDir, 'captions.srt')
    const sourceAudioProof = path.join(proofDir, 'source-audio.wav')
    await copyFile(fixture.video, sourceVideoProof)
    await copyFile(fixture.captions, sourceCaptionsProof)
    await copyFile(fixture.audio, sourceAudioProof)

    const outDir = path.join(tempRoot, 'watch-output')
    const mediaRoot = path.join(tempRoot, 'watch-media')
    const watchResult = await runCommand({
      command: 'bash',
      args: [
        path.join(watchRoot, 'run.sh'),
        fixture.video,
        '--subtitle',
        fixture.captions,
        '--no-whisper',
        '--diarization',
        'pyannote',
        '--require-diarization',
        '--num-speakers',
        '2',
        '--fps',
        '0.2',
        '--max-frames',
        '2',
        '--resolution',
        '320',
        '--out-dir',
        outDir,
      ],
      cwd: repoRoot,
      env: {
        ...process.env,
        WATCH_MEDIA_ROOT: mediaRoot,
        WATCH_DIARIZATION_TIMEOUT_SECONDS: process.env.WATCH_DIARIZATION_TIMEOUT_SECONDS || '900',
      },
    })
    assert.equal(watchResult.exit_code, 0, `${watchResult.stdout}\n${watchResult.stderr}`)

    const diarizationPath = path.join(outDir, 'diarization.json')
    const transcriptPath = path.join(outDir, 'transcript.json')
    const reportPath = path.join(outDir, 'report.json')
    const htmlPath = path.join(outDir, 'report.html')
    const markdownPath = path.join(outDir, 'report.md')
    const diarization = JSON.parse(await readFile(diarizationPath, 'utf-8'))
    const transcript = JSON.parse(await readFile(transcriptPath, 'utf-8'))
    const report = JSON.parse(await readFile(reportPath, 'utf-8'))
    const html = await readFile(htmlPath, 'utf-8')
    const markdown = await readFile(markdownPath, 'utf-8')

    assert.equal(diarization.schema, 'watch.diarization.v1')
    assert.equal(diarization.status, 'complete')
    assert.equal(diarization.provider, 'pyannote')
    assert.equal(diarization.model, 'pyannote/speaker-diarization-community-1')
    assert.equal(diarization.device, serviceHealth.device)
    assert.ok(diarization.speaker_count >= 2, `expected at least two speakers, got ${diarization.speaker_count}`)
    assert.ok(diarization.turns.length >= 2, 'regular diarization turns missing')
    assert.ok(diarization.exclusive_turns.length >= 2, 'exclusive diarization turns missing')
    assert.match(diarization.source_audio_sha256, /^sha256:[a-f0-9]{64}$/)

    assert.equal(transcript.speaker_attribution?.status, 'complete')
    assert.equal(transcript.speaker_attribution?.identity_boundary?.anonymous_speakers_are_identity, false)
    assert.equal(transcript.speaker_attribution?.identity_boundary?.promotion_allowed, false)
    assert.ok(transcript.segments.every((segment: any) => typeof segment.text === 'string' && !segment.text.includes('SPEAKER_')))
    assert.ok(transcript.segments.some((segment: any) => typeof segment.speaker === 'string' && segment.speaker.startsWith('SPEAKER_')))
    assert.ok(transcript.segments.every((segment: any) => typeof segment.speaker_status === 'string'))

    const rows = report.scene_elements || []
    assert.ok(rows.length >= 1, 'report scene rows missing')
    assert.ok(rows.some((row: any) => Array.isArray(row.speaker_ids) && row.speaker_ids.length > 0))
    assert.ok(rows.every((row: any) => row.diarization_source === 'pyannote/speaker-diarization-community-1' || !row.speaker_ids?.length))
    assert.ok(html.includes('SPEAKER_'), 'HTML report does not render speaker evidence')
    assert.ok(markdown.includes('SPEAKER_'), 'Markdown report does not render speaker evidence')
    assert.ok(!JSON.stringify({ diarization, transcript, rows }).match(/Marcus|Willie|actor_name|character_name/))

    const copiedDiarization = {
      schema: diarization.schema,
      status: diarization.status,
      provider: diarization.provider,
      model: diarization.model,
      library_version: diarization.library_version,
      device: diarization.device,
      source_audio_sha256: diarization.source_audio_sha256,
      analysis_range: diarization.analysis_range,
      duration_seconds: diarization.duration_seconds,
      speaker_count: diarization.speaker_count,
      speakers: diarization.speakers,
      turns: diarization.turns,
      exclusive_turns: diarization.exclusive_turns,
      elapsed_seconds: diarization.elapsed_seconds,
    }
    await writeFile(path.join(proofDir, 'pyannote-diarization.json'), `${JSON.stringify(copiedDiarization, null, 2)}\n`)

    const selectedRows = rows.map((row: any) => ({
      timecode: row.timecode,
      speaker_ids: row.speaker_ids || [],
      speaker_attribution_status: row.speaker_attribution_status || '',
      overlapping_speech: Boolean(row.overlapping_speech),
      diarization_source: row.diarization_source || '',
      diarization_artifact_path: row.diarization_artifact_path || '',
    }))
    await writeFile(path.join(proofDir, 'pyannote-report-speaker-rows.json'), `${JSON.stringify(selectedRows, null, 2)}\n`)

    const proofArtifacts = [
      'source-video.mp4',
      'source-audio.wav',
      'captions.srt',
      'pyannote-diarization.json',
      'pyannote-report-speaker-rows.json',
    ]
    const artifacts = []
    for (const artifact of proofArtifacts) {
      const artifactPath = path.join(proofDir, artifact)
      const info = await stat(artifactPath)
      artifacts.push({
        path: path.relative(proofDir, artifactPath),
        sha256: await sha256File(artifactPath),
        bytes: info.size,
      })
    }
    const summary = {
      schema: 'watch.pyannote_immutable_e2e_proof.v1',
      status: 'PASS',
      mocked: false,
      live: true,
      service: {
        provider: serviceHealth.provider,
        model: serviceHealth.model,
        device: serviceHealth.device,
        model_loaded: serviceHealth.model_loaded,
        model_load_count: serviceHealth.model_load_count,
      },
      watch_cli_exit_code: watchResult.exit_code,
      assertions: {
        live_cuda_pyannote_service: true,
        watch_cli_exercised_real_media: true,
        diarization_receipt_complete: true,
        regular_and_exclusive_turns_retained: true,
        transcript_speaker_attribution_written: true,
        report_scene_rows_include_speaker_evidence: true,
        anonymous_speakers_not_promoted_to_identity: true,
      },
      artifacts,
    }
    await writeFile(path.join(proofDir, 'pyannote-e2e-summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
  } finally {
    if ((process.env.WATCH_PYANNOTE_KEEP_TEMP || 'false') !== 'true') {
      await rm(tempRoot, { recursive: true, force: true })
    }
  }

  console.log('watchPyannoteImmutableLive smoke passed')
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
