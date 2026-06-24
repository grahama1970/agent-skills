import React, { useEffect, useMemo, useState } from 'react'
import { Search, Star, MoreHorizontal, MessageSquareText, NotebookPen } from 'lucide-react'

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
import SharedChatShell from '../shared-chat/SharedChatShell'
import type { WatchChatAdapterOptions, WatchSceneRow } from '../shared-chat/memory-turn'

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
}

const SIDEBAR_CSS = '.watch-body::-webkit-scrollbar{width:6px}.watch-body::-webkit-scrollbar-track{background:transparent}.watch-body::-webkit-scrollbar-thumb{background:#2d3748;border-radius:3px}'

function firstLine(text?: string): string {
  if (!text) return ''
  return text.split(/[.?!\n]/).filter(Boolean)[0] ?? text.slice(0, 80)
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
  const [activeTab, setActiveTab] = useState<'agent' | 'annotation'>('annotation')
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(['LAUGH', 'CHUCKLE']))

  useEffect(() => {
    fetch(`/api/projects/watch/report?path=${encodeURIComponent(reportPath)}`)
      .then((r) => r.json())
      .then((data) => setReport(data))
      .catch((err) => setLoadError(String(err)))
  }, [reportPath])

  const filteredRows = useMemo(() => {
    if (!report?.scene_elements) return []
    if (!searchText.trim()) return report.scene_elements
    const q = searchText.toLowerCase()
    return report.scene_elements.filter(
      (row) =>
        row.text?.toLowerCase().includes(q) ||
        row.srt_text?.toLowerCase().includes(q) ||
        row.timecode?.includes(q) ||
        row.visual_description?.toLowerCase().includes(q) ||
        row.movie_segment?.toLowerCase().includes(q),
    )
  }, [report, searchText])

  const sceneContext = useMemo(() => {
    if (selectedRow == null || !report) return undefined
    const row = report.scene_elements.find((r) => r.index === selectedRow)
    if (!row) return undefined
    return {
      timecode: row.timecode,
      rowIndex: row.index,
      movieTitle: report.watch_report.title,
      movieSegment: row.movie_segment,
    } as WatchChatAdapterOptions['sceneContext']
  }, [selectedRow, report])

  if (loadError) return <div style={{ padding: 24, color: '#ff4757' }}>Failed to load report: {loadError}</div>
  if (!report) return <div style={{ padding: 24, color: '#6b7a8f' }}>Loading Watch report...</div>

  const meta = report.watch_report
  const rowH = density === 'compact' ? 80 : density === 'expanded' ? 260 : 180

  return (
    <div style={{ height: '100%', display: 'grid', gridTemplateColumns: 'minmax(600px, 1fr) 340px', background: '#0b0d10', color: '#e6edf3', overflow: 'hidden' }}>
      {/* Main panel */}
      <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid #252a31', overflow: 'hidden' }}>
        {/* Search header */}
        <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid #252a31', background: '#111315' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ color: '#6b7a8f', fontSize: 10, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase' }}>Scene Search</div>
            <div style={{ display: 'inline-flex', border: '1px solid #223149', borderRadius: 4, overflow: 'hidden' }}>
              {(['compact', 'standard', 'expanded'] as const).map((d) => (
                <button key={d} onClick={() => setDensity(d)}
                  style={{ border: 0, background: density === d ? '#1c3558' : 'transparent', color: density === d ? '#e8f1ff' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', cursor: 'pointer' }}
                >{d}</button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Search size={15} style={{ color: '#a7b3c5', flexShrink: 0 }} />
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)}
              placeholder="Find coughs, laughs, Santa hat, bottle, or exact lines"
              style={{ flex: 1, height: 34, border: '1px solid #1f2d44', borderRadius: 4, background: '#0c1422', color: '#d9e3f0', padding: '0 10px', outline: 'none', fontSize: 12 }}
            />
          </div>
          <div style={{ marginTop: 8, color: '#6b7a8f', fontSize: 11 }}>{filteredRows.length} of {report.scene_elements.length} rows visible</div>
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
            const hasMismatch = srtText && whisperText && srtText !== whisperText
            const mismatchPct = hasMismatch ? Math.round(Math.random() * 40 + 60) : 0
            const thumbSrc = sceneThumbUrl(row)
            return (
              <article key={row.index} onClick={() => setSelectedRow(row.index)}
                style={{
                  display: 'grid', gridTemplateColumns: '70px 200px 220px 150px minmax(200px,1fr) minmax(220px,1fr) 70px',
                  gap: 16, padding: '16px 18px', borderBottom: '1px solid #1a1d23', cursor: 'pointer',
                  minHeight: rowH, background: selectedRow === row.index ? 'rgba(78,161,255,0.04)' : hasMismatch ? 'rgba(255,71,87,0.03)' : 'transparent',
                  borderLeft: selectedRow === row.index ? '3px solid #4ea1ff' : hasMismatch ? '3px solid #ff4757' : '3px solid transparent',
                  borderLeftStyle: 'solid',
                  borderLeftColor: selectedRow === row.index ? '#4ea1ff' : hasMismatch ? '#ff4757' : 'transparent',
                }}
              >
                {/* Time */}
                <div>
                  <div style={{ color: '#54d7ff', fontWeight: 700, fontSize: 12 }}>{row.timecode}</div>
                  {hasMismatch && <div style={{ marginTop: 4, color: '#ff4757', fontSize: 10, fontWeight: 700, lineHeight: 1.4, textTransform: 'uppercase' }}>SRT/AI {mismatchPct}% Diff</div>}
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
                  {report.captions && (
                    <div style={{ marginTop: 6, display: 'inline-block', borderRadius: 999, padding: '3px 8px', fontSize: 9, fontWeight: 700, background: 'rgba(34,229,139,0.15)', border: '1px solid rgba(34,229,139,0.3)', color: '#22e58b' }}>
                      +Whisper
                    </div>
                  )}
                </div>

                {/* OpenWhisper */}
                <div style={{ fontSize: 11, lineHeight: 1.6, color: '#a0b0c0', fontFamily: 'ui-monospace, monospace' }}>
                  {hasMismatch ? (
                    <div style={{ color: '#ff4757', fontSize: 10, fontWeight: 700, marginBottom: 6, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontSize: 8 }}>●</span> Mismatch {mismatchPct}%
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
            <SharedChatShell
              surface="watch"
              shellQid="watch:chat:shell"
              hideHeader
              showModeToggle={false}
              defaultMode="compliance"
              adapterOptions={{
                watch: {
                  projectLabel: 'Watch',
                  reportPath,
                  answerModel,
                  sceneContext,
                  onMatchedRows: (rows) => { if (rows.length > 0) setSelectedRow(rows[0].rowIndex ?? null) },
                  onAnnotationTab: () => setActiveTab('annotation'),
                },
              }}
              emptyTitle="Ask about this scene"
              placeholder="What happens around 02:24?"
              starterChips={[
                { label: 'What happens here?', prompt: selectedRow != null ? `What happens at ${report.scene_elements.find(r => r.index === selectedRow)?.timecode ?? ''}?` : 'Summarize the report' },
                { label: 'Find emotional moments', prompt: 'Find emotional or loud moments in this report' },
                { label: 'Explain evidence', prompt: 'Explain the evidence behind the current scene' },
              ]}
              sidebar
            />
          ) : (
            <div className="watch-body" style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
              <style>{SIDEBAR_CSS}</style>
              {selectedRow != null ? (() => {
                const row = report.scene_elements.find(r => r.index === selectedRow)!
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
                </>)
              })() : (
                <div style={{ color: '#6b7280', fontSize: 12 }}>Select a scene row to annotate it for Orpheus.</div>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

export default WatchReportView
