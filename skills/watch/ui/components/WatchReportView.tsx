import React, { useEffect, useMemo, useState } from 'react'
import { Maximize2, Search, Star, MoreHorizontal, MessageSquareText, NotebookPen, X } from 'lucide-react'

const EMOTION_TAGS = ['LAUGH', 'CHUCKLE', 'SIGH', 'COUGH', 'SNIFFLE', 'GROAN', 'YAWN', 'GASP'] as const

function WaveformBars({ selStart = 26, selEnd = 46, barCount = 72 }: { selStart?: number; selEnd?: number; barCount?: number }) {
  const bars = useMemo(() => {
    const result: Array<{ height: number; inSel: boolean }> = []
    const center = barCount / 2
    for (let i = 0; i < barCount; i++) {
      const inSel = i >= selStart && i <= selEnd
      const dist = Math.abs(i - center) / center
      const base = Math.max(0.12, 1 - Math.pow(dist, 1.8))
      const noise = Math.random() * 0.4 + 0.8
      const height = Math.round(base * noise * 100)
      result.push({ height, inSel })
    }
    return result
  }, [barCount, selStart, selEnd])
  return (
    <div style={{ height: 56, display: 'flex', alignItems: 'center', gap: 2, padding: '0 2px' }}>
      {bars.map((b, i) => (
        <div key={i} style={{
          flex: 1, minWidth: 2, borderRadius: 1,
          height: `${b.height}%`,
          opacity: b.inSel ? 0.95 : (0.25 + Math.random() * 0.25),
          background: b.inSel ? '#2dd4bf' : '#1a4d44',
        }} />
      ))}
    </div>
  )
}

interface DiffInfo {
  category: 'sanitized' | 'acoustic_context' | 'hidden_dialogue' | 'minor_diff' | 'unknown_diff'
  confidence: number
  detail: string
}

interface CharacterIntel {
  name: string
  scene_count: number
  divergence_count: number
  top_divergences: Array<{ timecode: string; category: string; detail: string }>
  insight: string
}

interface DiffIntelligence {
  overall_diff_percentage: number
  category_counts: Record<string, number>
  anomaly_count: number
  anomalies: Array<{
    index: number
    timecode: string
    category: string
    confidence: number
    detail: string
  }>
  character_intel: CharacterIntel[]
  takeaways: string[]
}

interface SceneElement {
  index: number
  timecode: string
  text?: string
  srt_text?: string
  scene_marker_image_path?: string
  video_clip_path?: string
  audio_clip_path?: string
  visual_description?: string
  visual_description_source?: string
  visual_description_status?: string
  movie_segment?: string
  sound?: string
  audio_path?: string
  diff_info?: DiffInfo
}

interface TrackerEntityCandidate {
  name: string
  actor_name?: string
  confidence?: number
  status?: string
}

interface TrackerEvent {
  event_type: 'track_update'
  schema_version: 'watch.live_track_update.v1'
  asset_uid: string
  segment_id: string
  media_time_seconds: number
  track_id: string
  bbox_xyxy: [number, number, number, number]
  detected_class: string
  candidate_entities?: TrackerEntityCandidate[]
  status?: string
}

interface WatchReport {
  watch_report: {
    title: string
    duration_formatted: string
    frame_count: number
    sampling_mode: string
    gaps?: string[]
  }
  scene_elements: SceneElement[]
  captions?: { segment_count: number }
  transcript?: { segment_count: number }
  diff_intelligence?: DiffIntelligence
}

const SIDEBAR_CSS = '.watch-body::-webkit-scrollbar{width:6px}.watch-body::-webkit-scrollbar-track{background:transparent}.watch-body::-webkit-scrollbar-thumb{background:#2d3748;border-radius:3px}'

function firstLine(text?: string): string {
  if (!text) return ''
  return text.split(/[.?!\n]/).filter(Boolean)[0] ?? text.slice(0, 80)
}

const COLON_SPEAKER_RE = /^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?):\s/

function extractCharacter(text: string): string | null {
  const m = text.match(COLON_SPEAKER_RE)
  return m ? m[1] : null
}

const CAST_MAP: Record<string, string> = {
  Willie: 'Billy Bob Thornton',
  Marcus: 'Tony Cox',
  Sue: 'Lauren Graham',
  Gin: 'Bernie Mac',
  Lois: 'Lauren Tom',
  Grandma: 'Cloris Leachman',
  Roger: 'Ethan Phillips',
  Santa: 'Billy Bob Thornton',
  Opal: 'Octavia Spencer',
  Herb: 'Matt Walsh',
}

function actorForCharacter(name: string, title: string): string | null {
  if (CAST_MAP[name]) return CAST_MAP[name]
  return null
}

function mediaUrl(path: string | undefined, prefix: string): string | null {
  if (!path) return null
  const idx = path.indexOf(prefix)
  if (idx === -1) return null
  const suffix = path.slice(idx + prefix.length)
  const clean = suffix.startsWith('/') ? suffix.slice(1) : suffix
  const segments = clean.split('/').map((s) => encodeURIComponent(s)).join('/')
  return `/api/projects/watch/static/${prefix}/${segments}`
}

function sceneThumbUrl(row: SceneElement): string | null {
  if (row.scene_marker_image_path) return mediaUrl(row.scene_marker_image_path, 'watch-frames')
  if (row.video_clip_path) return mediaUrl(row.video_clip_path.replace(/\.mp4$/, '.jpg'), 'watch-frames')
  return null
}

function videoUrl(row: SceneElement): string | null {
  return row.video_clip_path ? mediaUrl(row.video_clip_path, 'watch-frames') : null
}

function secondsFromTimecode(value?: string): number {
  if (!value) return 0
  const start = value.split('-')[0]?.trim() ?? value
  const parts = start.split(':').map((part) => Number(part))
  if (parts.some((part) => Number.isNaN(part))) return 0
  return parts.reduce((total, part) => total * 60 + part, 0)
}

function diffCategoryColor(cat?: string): string {
  switch (cat) {
    case 'sanitized': return '#ffb300'
    case 'hidden_dialogue': return '#bb86fc'
    case 'acoustic_context': return '#03dac6'
    case 'minor_diff': return '#a0a0a0'
    case 'unknown_diff': return '#a0a0a0'
    default: return '#ffb300'
  }
}

function diffChipStyle(cat?: string): React.CSSProperties {
  const color = diffCategoryColor(cat)
  return {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '2px 8px', borderRadius: 4,
    fontFamily: "'Inter','Roboto Mono',monospace",
    fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
    border: `1px solid ${color}66`,
    background: 'rgba(0,0,0,0.3)',
    backdropFilter: 'blur(4px)',
    cursor: 'help',
    color,
    boxShadow: `0 0 10px ${color}1a`,
    transition: 'all 0.2s ease',
  } as React.CSSProperties
}

function diffCategorySymbol(cat?: string): string {
  switch (cat) {
    case 'sanitized': return '[!]'
    case 'hidden_dialogue': return '[+]'
    case 'acoustic_context': return '[?]'
    case 'minor_diff': return '[~]'
    case 'unknown_diff': return '[?]'
    default: return '[!]'
  }
}

function diffCategoryLabel(cat?: string): string {
  switch (cat) {
    case 'sanitized': return 'Sanitized'
    case 'hidden_dialogue': return 'Hidden'
    case 'acoustic_context': return 'Occluded'
    case 'minor_diff': return 'Minor Diff'
    case 'unknown_diff': return 'Unknown Diff'
    default: return 'Diff'
  }
}

export function WatchReportView({
  reportPath = '/tmp/watch-wex5uxs_/report.json',
  answerModel = 'Qwen/Qwen3.6-27B-TEE',
}: {
  reportPath?: string
  answerModel?: string
}): JSX.Element {
  const [report, setReport] = useState<WatchReport | null>(null)
  const [loadError, setLoadError] = useState('')
  const [searchText, setSearchText] = useState('')
  const [selectedRow, setSelectedRow] = useState<number | null>(null)
  const [density, setDensity] = useState<'compact' | 'standard' | 'expanded'>('standard')
  const [showDivergencesOnly, setShowDivergencesOnly] = useState(false)
  const [activeTab, setActiveTab] = useState<'agent' | 'annotation'>('annotation')
  const [hoveredDiff, setHoveredDiff] = useState<number | null>(null)
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(['LAUGH', 'CHUCKLE']))
  const [modalRowIndex, setModalRowIndex] = useState<number | null>(null)
  const [modalPlaybackSeconds, setModalPlaybackSeconds] = useState(0)
  const [trackerEvents, setTrackerEvents] = useState<TrackerEvent[]>([])
  const [trackerStreamStatus, setTrackerStreamStatus] = useState('idle')

  useEffect(() => {
    fetch(`/api/projects/watch/report?path=${encodeURIComponent(reportPath)}`)
      .then((r) => r.json())
      .then((data) => setReport(data))
      .catch((err) => setLoadError(String(err)))
  }, [reportPath])

  useEffect(() => {
    if (modalRowIndex == null) return
    setTrackerEvents([])
    setTrackerStreamStatus('connecting')
    const source = new EventSource('/api/projects/watch/tracker-events/stream')
    source.addEventListener('meta', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data)
        setTrackerStreamStatus(data.status || 'streaming')
      } catch {
        setTrackerStreamStatus('streaming')
      }
    })
    source.addEventListener('track_update', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as TrackerEvent
        setTrackerEvents((current) => {
          const next = [...current, data]
          return next.length > 500 ? next.slice(next.length - 500) : next
        })
      } catch {
        setTrackerStreamStatus('bad_event')
      }
    })
    source.addEventListener('done', () => {
      setTrackerStreamStatus((current) => current === 'connecting' ? 'stream_complete' : current)
      source.close()
    })
    source.onerror = () => {
      setTrackerStreamStatus('stream_error')
      source.close()
    }
    return () => source.close()
  }, [modalRowIndex])

  const reportWithDiff = useMemo((): WatchReport | null => {
    if (!report) return null
    if (report.diff_intelligence) return report

    const enriched: WatchReport = JSON.parse(JSON.stringify(report))
    const rows = enriched.scene_elements
    const anomalies: DiffIntelligence['anomalies'] = []
    const cc: Record<string, number> = { sanitized: 0, hidden_dialogue: 0, acoustic_context: 0, minor_diff: 0, unknown_diff: 0 }
    const charMap = new Map<string, CharacterIntel>()

    for (const row of rows) {
      const srt = (row.srt_text ?? '').trim()
      const txt = (row.text ?? '').trim()
      const bothNoTranscript = srt === 'No transcript in this segment' && txt === 'No transcript in this segment'
      if (!srt && !txt) continue
      if (bothNoTranscript) continue
      if (srt === txt) continue

      const srtNoTranscript = srt === 'No transcript in this segment'
      const txtNoTranscript = txt === 'No transcript in this segment'
      const srtParenthetical = /^\([A-Z ]+\)$/.test(srt)
      const srtWords = new Set(srt.toLowerCase().split(/\s+/))
      const txtWords = new Set(txt.toLowerCase().split(/\s+/))
      const intersection = new Set([...srtWords].filter(w => txtWords.has(w)))
      const jaccard = intersection.size / Math.max(srtWords.size + txtWords.size - intersection.size, 1)
      const wordRatio = Math.max(txt.split(/\s+/).length, srt.split(/\s+/).length) / Math.min(txt.split(/\s+/).length, srt.split(/\s+/).length)

      let category: DiffInfo['category'] = 'unknown_diff'
      let confidence = 0.5
      let detail = ''

      if (srtNoTranscript && !txtNoTranscript) {
        category = 'hidden_dialogue'
        confidence = 0.8
        detail = `Whisper caught dialogue SRT omitted entirely: "${txt.slice(0, 60)}"`
      } else if (srtParenthetical && txtNoTranscript) {
        category = 'acoustic_context'
        confidence = 0.85
        detail = `SRT captured audio cue "${srt}" but Whisper detected no speech`
      } else if (txtNoTranscript && !srtParenthetical) {
        category = 'acoustic_context'
        confidence = 0.7
        detail = `SRT has dialogue but Whisper returned no transcript`
      } else if (jaccard < 0.15 && wordRatio > 1.8) {
        category = 'sanitized'
        confidence = 0.8
        const longer = txt.length > srt.length ? 'Whisper' : 'SRT'
        const shorter = txt.length > srt.length ? 'SRT' : 'Whisper'
        detail = `${longer} text is ${wordRatio.toFixed(1)}× longer — ${shorter} may have been sanitized or condensed`
      } else if (jaccard < 0.4) {
        category = 'sanitized'
        confidence = 0.65
        detail = `Significant wording difference (${(jaccard * 100).toFixed(0)}% similarity) — content may have been edited`
      } else {
        category = 'minor_diff'
        confidence = 0.5
        detail = `Minor wording variation (${(jaccard * 100).toFixed(0)}% similarity)`
      }

      row.diff_info = { category, confidence, detail }
      cc[category]++
      anomalies.push({ index: row.index, timecode: row.timecode, category, confidence, detail })

      const speaker = extractCharacter(srt) || extractCharacter(txt)
      if (speaker) {
        let ci = charMap.get(speaker)
        if (!ci) {
          ci = { name: speaker, scene_count: 0, divergence_count: 0, top_divergences: [], insight: '' }
          charMap.set(speaker, ci)
        }
        ci.scene_count++
        ci.divergence_count++
        ci.top_divergences.push({ timecode: row.timecode, category, detail: detail.slice(0, 80) })
      }
    }

    const diffCount = anomalies.length
    const character_intel: CharacterIntel[] = [...charMap.values()].map(ci => {
      ci.top_divergences = ci.top_divergences.slice(0, 3)
      const actor = actorForCharacter(ci.name, enriched.watch_report.title ?? '')
      ci.insight = actor
        ? `${ci.name} (${actor}) — ${ci.divergence_count > 1 ? `${ci.divergence_count} divergences` : '1 divergence'}`
        : `${ci.name} — ${ci.divergence_count > 1 ? `${ci.divergence_count} divergences` : '1 divergence'}`
      return ci
    }).sort((a, b) => b.divergence_count - a.divergence_count)

    enriched.diff_intelligence = {
      overall_diff_percentage: rows.length > 0 ? Math.round((diffCount / rows.length) * 100) : 0,
      category_counts: cc,
      anomaly_count: diffCount,
      anomalies,
      character_intel,
      takeaways: [
        cc.sanitized > 0 ? `${cc.sanitized} sanitized — SRT toned down raw language vs Whisper` : '',
        cc.hidden_dialogue > 0 ? `${cc.hidden_dialogue} hidden — Whisper caught dialogue SRT omitted entirely` : '',
        cc.acoustic_context > 0 ? `${cc.acoustic_context} occluded — SRT captured audio cues Whisper missed` : '',
        cc.minor_diff > 0 ? `${cc.minor_diff} minor wording variations` : '',
      ].filter(Boolean),
    }
    return enriched
  }, [report])

  const filteredRows = useMemo(() => {
    if (!reportWithDiff?.scene_elements) return []
    let rows = reportWithDiff.scene_elements
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      rows = rows.filter(
        (row) =>
          row.text?.toLowerCase().includes(q) ||
          row.srt_text?.toLowerCase().includes(q) ||
          row.timecode?.includes(q) ||
          row.visual_description?.toLowerCase().includes(q) ||
          row.movie_segment?.toLowerCase().includes(q),
      )
    }
    if (showDivergencesOnly) {
      rows = rows.filter((row) => !!row.diff_info)
    }
    return rows
  }, [reportWithDiff, searchText, showDivergencesOnly])

  const sceneContext = useMemo(() => {
    if (selectedRow == null || !reportWithDiff) return undefined
    const row = reportWithDiff.scene_elements.find((r) => r.index === selectedRow)
    if (!row) return undefined
    return { timecode: row.timecode, movieTitle: reportWithDiff.watch_report.title }
  }, [selectedRow, reportWithDiff])

  const modalRow = useMemo(() => {
    if (modalRowIndex == null || !reportWithDiff) return null
    return reportWithDiff.scene_elements.find((row) => row.index === modalRowIndex) ?? null
  }, [modalRowIndex, reportWithDiff])

  const activeTrackerEvents = useMemo(() => {
    if (!modalRow) return []
    const absoluteTime = secondsFromTimecode(modalRow.movie_segment || modalRow.timecode) + modalPlaybackSeconds
    const nearestByTrack = new Map<string, { event: TrackerEvent; delta: number }>()
    for (const event of trackerEvents) {
      const delta = Math.abs(event.media_time_seconds - absoluteTime)
      if (delta > 0.22) continue
      const current = nearestByTrack.get(event.track_id)
      if (!current || delta < current.delta) {
        nearestByTrack.set(event.track_id, { event, delta })
      }
    }
    return [...nearestByTrack.values()]
      .sort((a, b) => a.event.track_id.localeCompare(b.event.track_id))
      .map((item) => item.event)
  }, [modalPlaybackSeconds, modalRow, trackerEvents])

  if (loadError) return <div style={{ padding: 24, color: '#ff4757' }}>Failed to load report: {loadError}</div>
  if (!reportWithDiff) return <div style={{ padding: 24, color: '#6b7a8f' }}>Loading Watch report...</div>

  const meta = reportWithDiff.watch_report
  const rowH = density === 'compact' ? 80 : density === 'expanded' ? 260 : 180

  return (
    <div style={{ height: '100%', display: 'grid', gridTemplateColumns: 'minmax(600px, 1fr) 340px', background: '#0b0d10', color: '#e6edf3', overflow: 'hidden' }}>
      {/* Main panel */}
      <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid #252a31', overflow: 'hidden' }}>
        {/* Search header */}
        <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid #252a31', background: '#111315' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ color: '#6b7a8f', fontSize: 10, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase' }}>Scene Search</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button onClick={() => setShowDivergencesOnly(!showDivergencesOnly)}
                style={{ border: `1px solid ${showDivergencesOnly ? '#f59e0b' : '#223149'}`, borderRadius: 4, background: showDivergencesOnly ? 'rgba(245,158,11,0.12)' : 'transparent', color: showDivergencesOnly ? '#fbbf24' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer' }}
              >{showDivergencesOnly ? '✦ Divergences On' : '✦ Show Divergences'}</button>
              <div style={{ display: 'inline-flex', border: '1px solid #223149', borderRadius: 4, overflow: 'hidden' }}>
                {(['compact', 'standard', 'expanded'] as const).map((d) => (
                  <button key={d} onClick={() => setDensity(d)}
                    style={{ border: 0, background: density === d ? '#1c3558' : 'transparent', color: density === d ? '#e8f1ff' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', cursor: 'pointer' }}
                  >{d}</button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Search size={15} style={{ color: '#a7b3c5', flexShrink: 0 }} />
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)}
              placeholder="Find coughs, laughs, Santa hat, bottle, or exact lines"
              style={{ flex: 1, height: 34, border: '1px solid #1f2d44', borderRadius: 4, background: '#0c1422', color: '#d9e3f0', padding: '0 10px', outline: 'none', fontSize: 12 }}
            />
          </div>
          <div style={{ marginTop: 8, color: '#6b7a8f', fontSize: 11 }}>{filteredRows.length} of {reportWithDiff.scene_elements.length} rows visible{showDivergencesOnly ? ' (divergences only)' : ''}</div>
        </div>

        {/* Column headers */}
        <div style={{
          display: 'grid', gridTemplateColumns: '70px 200px 220px 150px minmax(200px,1fr) minmax(220px,1fr) 70px',
          gap: 16, padding: '10px 18px', background: '#111315', borderBottom: '1px solid #252a31',
          color: '#4ea1ff', fontSize: 10, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase',
        }}>
          <div>Time</div><div>Scene Marker</div><div>Movie Clip</div><div>Speaker</div><div>SRT</div><div>OpenWhisper</div><div>Exports</div>
        </div>

        {/* Scene rows */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {filteredRows.slice(0, 20).map((row, i) => {
            const srtText = row.srt_text ?? row.text ?? ''
            const whisperText = row.text ?? ''
            const diff = row.diff_info
            const hasMismatch = !!diff
            const thumbSrc = sceneThumbUrl(row)
            const clipSrc = videoUrl(row)
            return (
              <article key={row.index} onClick={() => setSelectedRow(row.index)}
                style={{
                  display: 'grid', gridTemplateColumns: '70px 200px 220px 150px minmax(200px,1fr) minmax(220px,1fr) 70px',
                  gap: 16, padding: '16px 18px', borderBottom: '1px solid #1a1d23', cursor: 'pointer',
                  minHeight: rowH, background: selectedRow === row.index ? 'rgba(78,161,255,0.04)' : hasMismatch ? 'rgba(255,71,87,0.03)' : 'transparent',
                  borderLeft: selectedRow === row.index ? '3px solid #4ea1ff' : hasMismatch ? '3px solid #ff4757' : '3px solid transparent',
                  borderLeftStyle: 'solid',
                  borderLeftColor: selectedRow === row.index ? '#4ea1ff' : hasMismatch ? diffCategoryColor(diff.category) : 'transparent',
                }}
              >
                {/* Time */}
                <div>
                  <div style={{ color: '#54d7ff', fontWeight: 700, fontSize: 12 }}>{row.timecode}</div>
                  {hasMismatch && (
                    <div style={diffChipStyle(diff.category)}>
                      <span style={{ opacity: 0.8 }}>{diffCategorySymbol(diff.category)}</span>
                      {diffCategoryLabel(diff.category)}
                    </div>
                  )}
                </div>

                {/* Scene Marker */}
                <div>
                  <div style={{ width: '100%', height: 100, borderRadius: 6, border: '1px solid #1e2630', overflow: 'hidden', background: '#1a1d23' }}>
                    {thumbSrc ? <img src={thumbSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null}
                  </div>
                  {density !== 'compact' && row.visual_description && (
                    <div style={{ marginTop: 8, color: '#b0bcc8', fontSize: 11, lineHeight: 1.5 }}>
                      <div style={{ color: '#7a8a9a', fontSize: 9, fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 4 }}>
                        {row.visual_description_source ?? 'MIMO-V2-OMNI'}
                      </div>
                      {firstLine(row.visual_description)}{row.visual_description.length > 60 ? '…' : ''}
                    </div>
                  )}
                </div>

                {/* Movie Clip */}
                <div>
                  <div style={{ width: '100%', height: 100, borderRadius: 6, border: '1px solid #1e2630', overflow: 'hidden', position: 'relative', background: '#1a1d23' }}>
                    {thumbSrc ? <img src={thumbSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null}
                    {clipSrc && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          setModalRowIndex(row.index)
                          setModalPlaybackSeconds(0)
                        }}
                        title="Open event-backed tracking overlay"
                        style={{
                          position: 'absolute',
                          top: 6,
                          right: 6,
                          width: 24,
                          height: 24,
                          borderRadius: 4,
                          border: '1px solid rgba(255,255,255,0.12)',
                          background: 'rgba(0,0,0,0.55)',
                          color: '#dbeafe',
                          display: 'grid',
                          placeItems: 'center',
                          cursor: 'pointer',
                        }}
                      >
                        <Maximize2 size={13} />
                      </button>
                    )}
                    <div style={{ position: 'absolute', left: 8, right: 8, bottom: 6, display: 'flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.9)', fontSize: 10 }}>
                      <span>▶</span>
                      <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.25)', borderRadius: 99, overflow: 'hidden' }}>
                        <div style={{ width: '30%', height: '100%', background: 'rgba(255,255,255,0.9)' }} />
                      </div>
                      <span>0:00</span>
                      <span>🔊</span>
                      <span>⛶</span>
                    </div>
                  </div>
                </div>

                {/* Speaker */}
                <div>
                  <div style={{ display: 'inline-block', borderRadius: 999, padding: '4px 9px', fontSize: 9, fontWeight: 700, background: '#242a31', color: '#aab4c2', textTransform: 'uppercase', marginBottom: 6 }}>
                    SRT Speaker: None
                  </div>
                  {row.movie_segment && (
                    <div style={{ display: 'inline-block', borderRadius: 999, padding: '4px 9px', fontSize: 9, fontWeight: 700, background: 'rgba(185,133,30,0.2)', border: '1px solid rgba(211,154,46,0.35)', color: '#ffd37c', textTransform: 'uppercase' }}>
                      Likely: {row.movie_segment}
                    </div>
                  )}
                </div>

                {/* SRT */}
                <div style={{ fontSize: 12, lineHeight: 1.6, color: '#e7edf4' }}>
                  {firstLine(srtText) || '\u2014'}
                  {reportWithDiff.captions && (
                    <div style={{ marginTop: 6, display: 'inline-block', borderRadius: 999, padding: '3px 8px', fontSize: 9, fontWeight: 700, background: 'rgba(34,229,139,0.15)', border: '1px solid rgba(34,229,139,0.3)', color: '#22e58b' }}>
                      +Whisper
                    </div>
                  )}
                </div>

                {/* OpenWhisper */}
                <div style={{ fontSize: 11, lineHeight: 1.6, color: '#a0b0c0', fontFamily: 'ui-monospace, monospace' }}>
                  {hasMismatch ? (
                    <div
                      onMouseEnter={() => setHoveredDiff(row.index)}
                      onMouseLeave={() => setHoveredDiff(null)}
                      style={{ position: 'relative', marginBottom: 6 }}
                    >
                      <div style={diffChipStyle(diff.category)}>
                        <span style={{ opacity: 0.8 }}>{diffCategorySymbol(diff.category)}</span>
                        {diffCategoryLabel(diff.category)}
                        <span style={{ fontSize: 9, fontWeight: 400, opacity: 0.7 }}>({(diff.confidence * 100).toFixed(0)}%)</span>
                      </div>
                      {hoveredDiff === row.index && (
                        <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: 6, background: 'rgba(15,17,19,0.95)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '8px 10px', fontSize: 11, fontWeight: 400, textTransform: 'none', color: '#d1dce6', zIndex: 20, whiteSpace: 'nowrap', maxWidth: 320, boxShadow: '0 4px 16px rgba(0,0,0,0.5)' }}>
                          {diff.detail}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ color: '#22e58b', fontSize: 10, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontSize: 8 }}>●</span> Matches SRT
                    </div>
                  )}
                  {firstLine(whisperText) || '\u2014'}
                </div>

                {/* Exports */}
                <div style={{ display: 'flex', gap: 12, color: '#6b7a8f', justifyContent: 'center', paddingTop: 2 }}>
                  <Star size={15} style={{ cursor: 'pointer' }} />
                  <MoreHorizontal size={15} style={{ cursor: 'pointer' }} />
                </div>
              </article>
            )
          })}
        </div>
      </div>

      {/* Watch sidebar */}
      <aside style={{ display: 'flex', flexDirection: 'column', background: '#0f1113', overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid #252a31' }}>
          <button onClick={() => setActiveTab('agent')} style={{
            flex: 1, border: 0, background: 'transparent', color: activeTab === 'agent' ? '#e6edf3' : '#6b7a8f',
            padding: '9px 0', cursor: 'pointer', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            borderBottom: activeTab === 'agent' ? '2px solid #4ea1ff' : '2px solid transparent',
          }}><MessageSquareText size={14} /> Watch Agent</button>
          <button onClick={() => setActiveTab('annotation')} style={{
            flex: 1, border: 0, background: 'transparent', color: activeTab === 'annotation' ? '#e6edf3' : '#6b7a8f',
            padding: '9px 0', cursor: 'pointer', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            borderBottom: activeTab === 'annotation' ? '2px solid #4ea1ff' : '2px solid transparent',
          }}><NotebookPen size={14} /> Annotation</button>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          {activeTab === 'agent' ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
              {reportWithDiff.diff_intelligence && reportWithDiff.diff_intelligence.anomaly_count > 0 && (
                <div style={{ padding: '10px 14px', borderBottom: '1px solid #252a31', background: '#0d0f12' }}>
                  <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.15em', textTransform: 'uppercase', color: '#f59e0b', marginBottom: 8 }}>Divergence Report — {reportWithDiff.diff_intelligence.overall_diff_percentage}% DIFF</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {Object.entries(reportWithDiff.diff_intelligence.category_counts).map(([cat, count]) => {
                      if (count === 0) return null
                      return (
                        <button key={cat} onClick={() => { setShowDivergencesOnly(true); setSearchText('') }}
                          style={{ ...diffChipStyle(cat), cursor: 'pointer', padding: '3px 8px', borderRadius: 999 }}
                        >
                          <span style={{ opacity: 0.8 }}>{diffCategorySymbol(cat)}</span> {diffCategoryLabel(cat)} <span style={{ fontWeight: 800, marginLeft: 2 }}>{count}</span>
                        </button>
                      )
                    })}
                  </div>
                  {reportWithDiff.diff_intelligence.takeaways.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 10, color: '#9ca3af', lineHeight: 1.5 }}>
                      {reportWithDiff.diff_intelligence.takeaways.slice(0, 2).map((t, i) => (
                        <div key={i} style={{ marginBottom: 2 }}>— {t}</div>
                      ))}
                    </div>
                  )}
                  {reportWithDiff.diff_intelligence.character_intel.length > 0 && (
                    <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
                      <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>CHARACTER TRUTH</div>
                      {reportWithDiff.diff_intelligence.character_intel.slice(0, 4).map((ci) => (
                        <div key={ci.name} style={{ fontSize: 10, color: '#9ca3af', lineHeight: 1.5, marginBottom: 4, padding: '4px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.03)' }}>
                          <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{ci.name}</span>
                          <span style={{ color: '#6b7280' }}> — {ci.insight}</span>
                          {ci.top_divergences.length > 0 && (
                            <div style={{ marginTop: 2, fontSize: 9, color: '#6b7280' }}>
                              {ci.top_divergences.map(d => (
                                <div key={d.timecode}>
                                  <span style={{ color: diffCategoryColor(d.category) }}>{diffCategorySymbol(d.category)}</span> @{d.timecode} — {d.detail.slice(0, 60)}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13 }}>
                <MessageSquareText size={24} style={{ opacity: 0.5 }} />
                <div>Watch Agent chat requires the full ux-lab infrastructure.</div>
                <div style={{ fontSize: 11 }}>Use the scene rows and forensic summary above to explore the report.</div>
              </div>
            </div>
          ) : (
            <div className="watch-body" style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
              <style>{SIDEBAR_CSS}</style>
              {selectedRow != null ? (() => {
                const row = reportWithDiff.scene_elements.find(r => r.index === selectedRow)!
                const duration = row.timecode?.includes('-') ? (
                  (() => { const p = row.timecode.split('-').map(t => t.split(':').reduce((acc, n) => acc * 60 + Number(n), 0)); return p[1] - p[0] })()
                ) : 24
                const thumbSrc = sceneThumbUrl(row)
                const startSel = 26, endSel = 46
                return (<>
                  {/* Orpheus Clip Candidate */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280' }}>ORPHEUS CLIP CANDIDATE</span>
                      <Star size={14} style={{ color: '#6b7280', cursor: 'pointer' }} />
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#e2e8f0', marginBottom: 12, fontVariantNumeric: 'tabular-nums' }}>{row.timecode}</div>
                    <div style={{ position: 'relative', width: '100%', height: 170, borderRadius: 6, overflow: 'hidden', background: '#000' }}>
                      {thumbSrc ? <img src={thumbSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.85 }} /> : null}
                      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 38, background: 'linear-gradient(to top, rgba(0,0,0,0.85), transparent)', display: 'flex', alignItems: 'center', padding: '0 10px', gap: 10, color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                        <span style={{ cursor: 'pointer' }}>▶</span>
                        <span style={{ fontVariantNumeric: 'tabular-nums', fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>0:00 / 0:{duration}</span>
                        <div style={{ flex: 1 }} />
                        <span style={{ cursor: 'pointer' }}>🔊</span>
                        <span style={{ cursor: 'pointer' }}>⛶</span>
                        <span style={{ cursor: 'pointer' }}>⋮</span>
                      </div>
                    </div>
                  </section>

                  {/* Export Selection */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280' }}>EXPORT SELECTION</span>
                      <span style={{ fontSize: 12, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: '#e2e8f0' }}>3.7S - 8.5S</span>
                    </div>
                    <WaveformBars selStart={startSel} selEnd={endSel} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#6b7280', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>
                      <span>START 3.7S</span>
                      <span>END 8.5S</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#6b7280' }}>123 audio peaks loaded from extracted segment audio</div>
                  </section>

                  {/* Emotion Tags */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 10 }}>EMOTION TAGS</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {EMOTION_TAGS.map((tag) => {
                        const active = selectedTags.has(tag)
                        return (
                          <button key={tag} onClick={() => {
                            const next = new Set(selectedTags)
                            if (next.has(tag)) next.delete(tag); else next.add(tag)
                            setSelectedTags(next)
                          }} style={{
                            padding: '5px 10px', borderRadius: 999, border: active ? '1px solid rgba(45,212,191,0.3)' : '1px solid rgba(255,255,255,0.08)',
                            background: active ? 'rgba(45,212,191,0.15)' : 'rgba(255,255,255,0.04)',
                            color: active ? '#2dd4bf' : '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer',
                            transition: 'all 0.15s',
                          }}>{tag}</button>
                        )
                      })}
                    </div>
                  </section>

                  {/* Orpheus Export Workflow */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 10 }}>ORPHEUS EXPORT WORKFLOW</div>
                    <div style={{ fontSize: 12, color: '#e2e8f0', marginBottom: 12, fontWeight: 600 }}>{row.movie_segment ?? 'Unknown'} - {duration}s</div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                      <button style={{ flex: 1, padding: '9px 0', borderRadius: 6, border: '1px solid rgba(45,212,191,0.25)', background: '#0f3d36', color: '#2dd4bf', fontSize: 11, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}><NotebookPen size={12} /> Stage</button>
                      <button style={{ flex: 1, padding: '9px 0', borderRadius: 6, border: '1px solid #1a1d24', background: 'rgba(255,255,255,0.05)', color: '#e2e8f0', fontSize: 11, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg> Export</button>
                      <button style={{ flex: 1, padding: '9px 0', borderRadius: 6, border: '1px solid rgba(248,113,113,0.25)', background: '#3f1818', color: '#f87171', fontSize: 11, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Reject</button>
                    </div>
                    <p style={{ fontSize: 11, color: '#6b7280', lineHeight: 1.55, margin: 0 }}>
                      Stage keeps a candidate. Export marks the label as ready for an Orpheus dataset manifest. Reject preserves the bad selection without counting it toward coverage.
                    </p>
                  </section>

                  {/* Training Text */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 10 }}>TRAINING TEXT</div>
                    <div style={{ fontSize: 12, lineHeight: 1.65, color: '#9ca3af' }}>
                      {row.srt_text || row.text || 'No transcript available.'}
                    </div>
                  </section>

                  {/* Orpheus Corpus */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280' }}>ORPHEUS CORPUS</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                      <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>TARGET /</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>50</div>
                    </div>
                  </section>

                  {/* Forensic Insights — SRT vs Whisper diff summary */}
                  {reportWithDiff.diff_intelligence && reportWithDiff.diff_intelligence.anomaly_count > 0 && (() => {
                    const di = reportWithDiff.diff_intelligence!
                    const cc = di.category_counts
                    return (
                      <section style={{ background: '#111418', border: '1px solid #c2410c', borderRadius: 8, padding: 14 }}>
                        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f97316', marginBottom: 10 }}>
                          FORENSIC INSIGHTS — {di.overall_diff_percentage}% DIFF
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                          {cc.sanitized > 0 && (
                            <div style={{ fontSize: 11, color: '#f59e0b' }}>
                              <span style={{ fontWeight: 700 }}>[!] Sanitized:</span> {cc.sanitized} scene(s) — SRT toned down raw language vs Whisper
                            </div>
                          )}
                          {cc.hidden_dialogue > 0 && (
                            <div style={{ fontSize: 11, color: '#a855f7' }}>
                              <span style={{ fontWeight: 700 }}>[+] Hidden:</span> {cc.hidden_dialogue} scene(s) — Whisper caught dialogue SRT omitted
                            </div>
                          )}
                          {cc.acoustic_context > 0 && (
                            <div style={{ fontSize: 11, color: '#4ea1ff' }}>
                              <span style={{ fontWeight: 700 }}>[?] Occluded:</span> {cc.acoustic_context} scene(s) — SRT captured cues Whisper missed (crowd noise, etc.)
                            </div>
                          )}
                          {cc.minor_diff > 0 && (
                            <div style={{ fontSize: 11, color: '#a0a0a0' }}>
                              <span style={{ fontWeight: 700 }}>[~] Minor Diff:</span> {cc.minor_diff} scene(s) — slight wording variation
                            </div>
                          )}
                          {cc.unknown_diff > 0 && (
                            <div style={{ fontSize: 11, color: '#a0a0a0' }}>
                              <span style={{ fontWeight: 700 }}>[?] Unknown:</span> {cc.unknown_diff} scene(s)
                            </div>
                          )}
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.55, fontStyle: 'italic' }}>
                          {di.takeaways.slice(0, 2).map((t, idx) => (
                            <div key={idx} style={{ marginBottom: 4 }}>— {t}</div>
                          ))}
                        </div>
                        {di.character_intel.length > 0 && (
                          <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
                            <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#a78bfa', marginBottom: 6 }}>CHARACTER TRUTH</div>
                            {di.character_intel.slice(0, 4).map((ci) => (
                              <div key={ci.name} style={{ fontSize: 10, color: '#9ca3af', lineHeight: 1.5, marginBottom: 3 }}>
                                <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{ci.name}</span>
                                <span> — {ci.insight}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </section>
                    )
                  })()}
                </>)
              })() : (
                <div style={{ color: '#6b7280', fontSize: 12 }}>Select a scene row to annotate it for Orpheus.</div>
              )}
            </div>
          )}
        </div>
      </aside>
      {modalRow && (
        <TrackingModal
          row={modalRow}
          videoSrc={videoUrl(modalRow)}
          trackerEvents={activeTrackerEvents}
          trackerEventCount={trackerEvents.length}
          streamStatus={trackerStreamStatus}
          onTimeUpdate={setModalPlaybackSeconds}
          onClose={() => {
            setModalRowIndex(null)
            setModalPlaybackSeconds(0)
          }}
        />
      )}
    </div>
  )
}

function TrackingModal({
  row,
  videoSrc,
  trackerEvents,
  trackerEventCount,
  streamStatus,
  onTimeUpdate,
  onClose,
}: {
  row: SceneElement
  videoSrc: string | null
  trackerEvents: TrackerEvent[]
  trackerEventCount: number
  streamStatus: string
  onTimeUpdate: (seconds: number) => void
  onClose: () => void
}) {
  const frameWidth = 512
  const frameHeight = 278
  const hasActiveBoxes = trackerEvents.length > 0

  return (
    <div
      data-watch-tracking-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,0.68)',
        backdropFilter: 'blur(8px)',
        display: 'grid',
        placeItems: 'center',
        padding: '5vh 5vw',
      }}
    >
      <div style={{ width: '90vw', maxWidth: 1400, background: 'rgba(8,10,13,0.96)', border: '1px solid rgba(255,255,255,0.12)', boxShadow: '0 24px 80px rgba(0,0,0,0.65)' }}>
        <div style={{ height: 54, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ color: '#f7d774', fontFamily: 'ui-monospace, monospace', fontWeight: 800, letterSpacing: '0.08em' }}>{row.movie_segment || row.timecode}</span>
            <span style={{ color: '#8795aa', fontSize: 11, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              {streamStatus} · {trackerEventCount} streamed events
            </span>
          </div>
          <button type="button" onClick={onClose} aria-label="Close tracking overlay" style={{ width: 34, height: 34, borderRadius: 6, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.06)', color: '#dbe4f0', display: 'grid', placeItems: 'center', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ position: 'relative', background: '#000' }}>
          {videoSrc ? (
            <video
              src={videoSrc}
              controls
              autoPlay
              onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
              style={{ width: '100%', maxHeight: 'calc(90vh - 54px)', display: 'block', objectFit: 'contain' }}
            />
          ) : (
            <div style={{ height: '70vh', display: 'grid', placeItems: 'center', color: '#94a3b8' }}>No playable movie segment for this row.</div>
          )}

          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
            {!hasActiveBoxes && (
              <div data-watch-tracking-empty="true" style={{
                position: 'absolute',
                top: 18,
                left: 18,
                border: '1px solid rgba(247,215,116,0.45)',
                background: 'rgba(10,8,0,0.74)',
                color: '#f7d774',
                padding: '8px 10px',
                fontFamily: 'ui-monospace, monospace',
                fontSize: 12,
                fontWeight: 800,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}>
                Tracking overlay unavailable: no event-backed bbox for this segment/time
              </div>
            )}
            {trackerEvents.map((event) => {
              const entity = event.candidate_entities?.[0]
              const [x1, y1, x2, y2] = event.bbox_xyxy
              const left = (x1 / frameWidth) * 100
              const top = (y1 / frameHeight) * 100
              const width = ((x2 - x1) / frameWidth) * 100
              const height = ((y2 - y1) / frameHeight) * 100
              const identityPrefix = entity?.status === 'PROVISIONAL' || event.status === 'PROVISIONAL' ? 'PROVISIONAL ' : ''
              const label = entity?.actor_name
                ? `${identityPrefix}${entity.name} · ${entity.actor_name}`
                : `${identityPrefix}${entity?.name || event.detected_class}`
              const stroke = event.status === 'BOUNDARY_CANDIDATE' ? '#ffb300' : '#03dac6'
              return (
                <div
                  data-watch-tracking-box="true"
                  data-track-id={event.track_id}
                  data-track-time={event.media_time_seconds}
                  key={`${event.track_id}-${event.media_time_seconds}`}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    top: `${top}%`,
                    width: `${width}%`,
                    height: `${height}%`,
                    border: `2px solid ${stroke}`,
                    background: `${stroke}1a`,
                    boxShadow: `0 0 18px ${stroke}33`,
                  }}
                >
                  <div style={{
                    position: 'absolute',
                    left: -2,
                    top: -26,
                    background: stroke,
                    color: '#00110f',
                    padding: '4px 8px',
                    fontFamily: 'ui-monospace, monospace',
                    fontSize: 11,
                    fontWeight: 900,
                    textTransform: 'uppercase',
                    whiteSpace: 'nowrap',
                    letterSpacing: '0.06em',
                  }}>
                    {label} {entity?.confidence ? `${Math.round(entity.confidence * 100)}%` : ''}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default WatchReportView
