import { useEffect, useRef, useState } from 'react'
import { Clapperboard, Video, Square, Download } from 'lucide-react'
import { useRegisterAction } from '../hooks'
import { Button } from './ui/button'

/** Native capture permission stays with the human; no auto-picked screen/mic. */
export function RehearsalControls({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  const [mic, setMic] = useState(false)
  const [status, setStatus] = useState('idle')
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const tracks = useRef<MediaStreamTrack[]>([])
  const audio = useRef<AudioContext | null>(null)
  useRegisterAction('deck:rehearse', { app: 'pitchdeck', action: 'DECK_REHEARSE', label: 'Rehearsal view', description: 'Hide editing tools and private speaker notes' })
  useRegisterAction('deck:record:start', { app: 'pitchdeck', action: 'DECK_RECORD_START', label: 'Record', description: 'Ask the human to choose a capture source and optional microphone' })
  useRegisterAction('deck:record:stop', { app: 'pitchdeck', action: 'DECK_RECORD_STOP', label: 'Stop recording', description: 'Finish capture and make the video available for playback/download' })
  useRegisterAction('deck:record:mic', { app: 'pitchdeck', action: 'DECK_RECORD_MIC', label: 'Include microphone', description: 'Request microphone permission only when recording starts' })
  useRegisterAction('deck:record:download', { app: 'pitchdeck', action: 'DECK_RECORD_DOWNLOAD', label: 'Save recording', description: 'Download the captured WebM' })
  const cleanup = () => { tracks.current.forEach(t => t.stop()); tracks.current = []; void audio.current?.close(); audio.current = null }
  useEffect(() => () => { recorder.current?.state === 'recording' && recorder.current.stop(); cleanup() }, [])
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  const start = async () => {
    setStatus('permission'); setMessage('Choose the deck + VS Code display/window. Exclude private notes and unrelated windows.')
    try {
      if (!navigator.mediaDevices?.getDisplayMedia || !window.MediaRecorder) throw new Error('Screen recording requires a supported browser on localhost or HTTPS')
      const screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
      tracks.current = screen.getTracks()
      if (mic) {
        const voice = await navigator.mediaDevices.getUserMedia({ audio: true })
        tracks.current.push(...voice.getTracks())
        audio.current = new AudioContext()
        const mix = audio.current.createMediaStreamDestination()
        if (screen.getAudioTracks().length) audio.current.createMediaStreamSource(new MediaStream(screen.getAudioTracks())).connect(mix)
        audio.current.createMediaStreamSource(voice).connect(mix)
        screen.getAudioTracks().forEach(t => screen.removeTrack(t))
        mix.stream.getAudioTracks().forEach(t => { screen.addTrack(t); tracks.current.push(t) })
      }
      const chunks: BlobPart[] = []
      const capture = new MediaRecorder(screen)
      recorder.current = capture
      capture.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }
      capture.onstop = () => {
        cleanup()
        const blob = new Blob(chunks, { type: capture.mimeType })
        if (blob.size) { setUrl(URL.createObjectURL(blob)); setStatus('recorded'); setMessage(`${blob.size} bytes captured. Play back to verify both panes and audio before sharing.`) }
        else { setStatus('error'); setMessage('No video bytes captured') }
      }
      capture.onerror = () => { cleanup(); setStatus('error'); setMessage('Browser recording failed') }
      screen.getVideoTracks()[0].addEventListener('ended', () => { if (capture.state === 'recording') capture.stop() }, { once: true })
      capture.start(1000)
      setStatus('recording'); setMessage(`Capturing ${screen.getVideoTracks()[0].label}; ${screen.getAudioTracks().length ? 'audio track present' : 'no audio'}.`)
    } catch (error) { cleanup(); setStatus('error'); setMessage(String(error)) }
  }
  return <div className="flex max-w-full flex-wrap items-center gap-2 text-sm">
    <Button title="Toggle clean rehearsal view" data-qid="deck:rehearse" data-qs-action="DECK_REHEARSE" variant="ghost" aria-pressed={active} onClick={onToggle}><Clapperboard size={16} aria-hidden /> {active ? 'Exit rehearsal' : 'Rehearse'}</Button>
    {active ? <>
      <label className="flex items-center gap-1"><input type="checkbox" title="Include microphone audio" data-qid="deck:record:mic" data-qs-action="DECK_RECORD_MIC" checked={mic} disabled={['permission','recording'].includes(status)} onChange={e => setMic(e.target.checked)} /> Microphone</label>
      {status === 'recording' ? <Button title="Stop recording" data-qid="deck:record:stop" data-qs-action="DECK_RECORD_STOP" variant="destructive" onClick={() => recorder.current?.stop()}><Square size={16} aria-hidden /> Stop</Button>
        : <Button title="Choose screen or window and start recording" data-qid="deck:record:start" data-qs-action="DECK_RECORD_START" disabled={status === 'permission'} onClick={() => void start()}><Video size={16} aria-hidden /> Record</Button>}
      <span role="status" className="max-w-full break-words text-xs text-slate-400">{message || 'Ready to request capture permission; no recording yet.'}</span>
      {url ? <details className="w-full"><summary>Review recording</summary><video src={url} controls className="max-h-64 max-w-full" aria-label="Captured rehearsal playback" /><a href={url} download="pitchdeck-rehearsal.webm" title="Save recording" data-qid="deck:record:download" data-qs-action="DECK_RECORD_DOWNLOAD" className="inline-flex gap-1"><Download size={16} aria-hidden /> Save WebM</a></details> : null}
    </> : null}
  </div>
}
