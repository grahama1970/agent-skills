"""PySide6 QObject bridge for voice-lab QML editor.

Exposes alignment data, waveform peaks, recording controls, I/O markers,
mic level monitoring, countdown timer, and phase state to QML.
Follows the horus-overlay bridge pattern.
"""
from __future__ import annotations

import struct
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QTimer,
    Property,
    Qt,
    Signal,
    Slot,
)


class SegmentModel(QAbstractListModel):
    """Exposes alignment segments to QML as a list model."""

    IndexRole = Qt.UserRole + 1
    StartMsRole = Qt.UserRole + 2
    EndMsRole = Qt.UserRole + 3
    TextRole = Qt.UserRole + 4
    SimilarityRole = Qt.UserRole + 5
    GrahamPathRole = Qt.UserRole + 6
    OriginalPathRole = Qt.UserRole + 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []

    def roleNames(self):
        return {
            self.IndexRole: b"segIndex",
            self.StartMsRole: b"startMs",
            self.EndMsRole: b"endMs",
            self.TextRole: b"text",
            self.SimilarityRole: b"similarity",
            self.GrahamPathRole: b"grahamPath",
            self.OriginalPathRole: b"originalPath",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._segments)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._segments):
            return None
        seg = self._segments[index.row()]
        if role == self.IndexRole:
            return seg.index
        if role == self.StartMsRole:
            return seg.start_ms
        if role == self.EndMsRole:
            return seg.end_ms
        if role == self.TextRole:
            return seg.text
        if role == self.SimilarityRole:
            return seg.similarity
        if role == self.GrahamPathRole:
            return seg.graham_segment or ""
        if role == self.OriginalPathRole:
            return seg.original_segment or ""
        return None

    def load_segments(self, segments):
        """Replace all segments (triggers full model reset)."""
        self.beginResetModel()
        self._segments = segments
        self.endResetModel()

    def update_segment(self, row: int, start_ms: int, end_ms: int):
        """Update timing bounds for a single segment."""
        if 0 <= row < len(self._segments):
            self._segments[row].start_ms = start_ms
            self._segments[row].end_ms = end_ms
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    @property
    def segments(self):
        return self._segments


class VoiceLabBridge(QObject):
    """Main bridge between Python voice-lab backend and QML editor UI."""

    # -- Signals --
    recordingStarted = Signal()
    recordingStopped = Signal()
    recordingError = Signal(str)  # emitted with error message
    peaksUpdated = Signal()
    alignmentSaved = Signal()
    srtTextChanged = Signal()
    isRecordingChanged = Signal()
    refPeaksChanged = Signal()
    recPeaksChanged = Signal()
    audioDurationChanged = Signal()
    refAudioPathChanged = Signal()
    recAudioPathChanged = Signal()
    takeCountChanged = Signal()
    takeListChanged = Signal()
    playbackRequested = Signal()  # QML should start MediaPlayer

    # Video editor signals
    inPointMsChanged = Signal()
    outPointMsChanged = Signal()
    micLevelChanged = Signal()
    countdownValueChanged = Signal()
    phaseChanged = Signal()
    countdownFinished = Signal()

    # Content browser signals
    videoSourceChanged = Signal()
    videoSourceTypeChanged = Signal()
    videoTitleChanged = Signal()

    _VALID_PHASES = ("browse", "set_io", "record", "review")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segment_model = SegmentModel(self)
        self._ref_peaks: list[float] = []
        self._rec_peaks: list[float] = []
        self._audio_duration: float = 0.0
        self._ref_audio_path: str = ""
        self._rec_audio_path: str = ""
        self._is_recording: bool = False
        self._srt_text: str = ""
        self._rec_process: Optional[subprocess.Popen] = None
        self._rec_stderr_thread: Optional[threading.Thread] = None
        self._rec_stderr_output: str = ""
        self._output_dir: Optional[Path] = None
        self._srt_path: Optional[Path] = None
        self._take_count: int = 0
        self._take_list: list[dict] = []  # [{"path": str, "label": str}, ...]

        # Video editor state
        self._in_point_ms: int = -1
        self._out_point_ms: int = -1
        self._mic_level: float = 0.0
        self._countdown_value: int = -1  # -1=inactive, 3/2/1/0
        self._phase: str = "browse"

        # Content browser state
        self._video_source: str = ""        # URL or file path
        self._video_source_type: str = ""   # "youtube" or "local"
        self._video_title: str = ""

        # Mic monitor
        self._mic_monitor_proc: Optional[subprocess.Popen] = None
        self._mic_monitor_thread: Optional[threading.Thread] = None
        self._mic_monitor_running: bool = False
        self._mic_source: Optional[QObject] = None  # gui_bridge for shared mic

        # Countdown timer
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)

    # -- Properties --

    @Property(QObject, constant=True)
    def segmentModel(self):
        return self._segment_model

    @Property("QVariantList", notify=refPeaksChanged)
    def refPeaks(self):
        return self._ref_peaks

    @Property("QVariantList", notify=recPeaksChanged)
    def recPeaks(self):
        return self._rec_peaks

    @Property(float, notify=audioDurationChanged)
    def audioDuration(self):
        return self._audio_duration

    @Property(str, notify=refAudioPathChanged)
    def refAudioPath(self):
        return self._ref_audio_path

    @Property(str, notify=recAudioPathChanged)
    def recAudioPath(self):
        return self._rec_audio_path

    @Property(bool, notify=isRecordingChanged)
    def isRecording(self):
        return self._is_recording

    @Property(str, notify=srtTextChanged)
    def srtText(self):
        return self._srt_text

    @Property(int, notify=takeCountChanged)
    def takeCount(self):
        return self._take_count

    @Property("QVariantList", notify=takeListChanged)
    def takeList(self):
        return [t["label"] for t in self._take_list]

    @Property(int, notify=inPointMsChanged)
    def inPointMs(self):
        return self._in_point_ms

    @Property(int, notify=outPointMsChanged)
    def outPointMs(self):
        return self._out_point_ms

    @Property(float, notify=micLevelChanged)
    def micLevel(self):
        return self._mic_level

    @Property(int, notify=countdownValueChanged)
    def countdownValue(self):
        return self._countdown_value

    @Property(str, notify=phaseChanged)
    def phase(self):
        return self._phase

    @Property(str, notify=videoSourceChanged)
    def videoSource(self):
        return self._video_source

    @Property(str, notify=videoSourceTypeChanged)
    def videoSourceType(self):
        return self._video_source_type

    @Property(str, notify=videoTitleChanged)
    def videoTitle(self):
        return self._video_title

    # -- Slots --

    @Slot(str, str)
    def loadSession(self, ref_audio: str, srt_path: str, output_dir: str = ""):
        """Load reference audio and SRT, compute peaks, populate segment model.

        Args:
            output_dir: Override output directory for takes. If empty, uses
                        ref_audio's parent directory.
        """
        from alignment import AlignedSegment, parse_srt
        from waveform import load_audio, resample_for_display

        ref_path = Path(ref_audio).resolve()
        self._srt_path = Path(srt_path)
        self._ref_audio_path = str(ref_path)
        self.refAudioPathChanged.emit()

        # Load audio and compute peaks
        audio, sr = load_audio(ref_path)
        self._audio_duration = len(audio) / sr
        self.audioDurationChanged.emit()

        mins, maxs = resample_for_display(audio, width=2000)
        # Interleave min/max for QML consumption
        self._ref_peaks = []
        for mn, mx in zip(mins, maxs):
            self._ref_peaks.append(float(mn))
            self._ref_peaks.append(float(mx))
        self.refPeaksChanged.emit()

        # Parse SRT and populate segment model
        segments_raw = parse_srt(self._srt_path)
        segments = [
            AlignedSegment(
                index=s.index,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text,
            )
            for s in segments_raw
        ]
        self._segment_model.load_segments(segments)

        # Set output dir — prefer explicit override, fallback to ref audio parent
        if output_dir:
            self._output_dir = Path(output_dir)
        else:
            self._output_dir = ref_path.parent
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Scan for existing takes in the output dir
        self._take_list = []
        existing = sorted(self._output_dir.glob("graham_take*.wav"))
        for p in existing:
            self._take_list.append({"path": str(p), "label": p.stem})
        if existing:
            self._take_count = len(existing)
            self.takeCountChanged.emit()
        self.takeListChanged.emit()

        logger.info(
            f"Loaded session: {ref_path.name}, "
            f"{len(segments)} segments, {self._audio_duration:.1f}s, "
            f"{len(existing)} existing takes in {self._output_dir}"
        )

        # Start mic level monitor
        self._start_mic_monitor()

    # -- I/O Point Slots --

    @Slot(int)
    def setInPoint(self, ms: int):
        """Set the in-point marker in milliseconds."""
        self._in_point_ms = ms
        self.inPointMsChanged.emit()
        logger.info(f"In-point set: {ms}ms ({ms/1000:.1f}s)")

    @Slot(int)
    def setOutPoint(self, ms: int):
        """Set the out-point marker in milliseconds."""
        self._out_point_ms = ms
        self.outPointMsChanged.emit()
        logger.info(f"Out-point set: {ms}ms ({ms/1000:.1f}s)")

    @Slot()
    def clearIOPoints(self):
        """Clear both I/O point markers."""
        self._in_point_ms = -1
        self._out_point_ms = -1
        self.inPointMsChanged.emit()
        self.outPointMsChanged.emit()
        logger.info("I/O points cleared")

    # -- Phase Slots --

    @Slot(str)
    def setPhase(self, phase: str):
        """Set the current workflow phase."""
        if phase not in self._VALID_PHASES:
            logger.warning(f"Invalid phase: {phase}")
            return
        self._phase = phase
        self.phaseChanged.emit()
        logger.info(f"Phase: {phase}")

    # -- Video Source Slots --

    @Slot(str, str, str)
    def setVideoSource(self, source: str, source_type: str, title: str):
        """Set video source. source_type: 'youtube' or 'local'."""
        self._video_source = source
        self._video_source_type = source_type
        self._video_title = title
        self.videoSourceChanged.emit()
        self.videoSourceTypeChanged.emit()
        self.videoTitleChanged.emit()
        logger.info(f"Video source: {source_type} — {title} ({source[:80]})")

    # -- Countdown Slots --

    @Slot()
    def startCountdown(self):
        """Start 3-2-1 countdown. Emits countdownFinished at 0."""
        self._countdown_value = 3
        self.countdownValueChanged.emit()
        self._countdown_timer.start()

    @Slot(int)
    def loadTake(self, index: int):
        """Load a previous take's waveform into the recording track."""
        if index < 0 or index >= len(self._take_list):
            return
        take_path = Path(self._take_list[index]["path"])
        if not take_path.exists():
            logger.warning(f"Take file missing: {take_path}")
            return

        from waveform import load_audio, resample_for_display

        audio, sr = load_audio(take_path)
        mins, maxs = resample_for_display(audio, width=2000)
        self._rec_peaks = []
        for mn, mx in zip(mins, maxs):
            self._rec_peaks.append(float(mn))
            self._rec_peaks.append(float(mx))
        self._rec_audio_path = str(take_path)
        self.recAudioPathChanged.emit()
        self.recPeaksChanged.emit()
        logger.info(f"Loaded take: {take_path.name} ({len(audio)/sr:.1f}s)")

    def _countdown_tick(self):
        """Handle countdown timer tick."""
        self._countdown_value -= 1
        self.countdownValueChanged.emit()
        if self._countdown_value <= 0:
            self._countdown_timer.stop()
            self._countdown_value = -1
            self.countdownValueChanged.emit()
            self.countdownFinished.emit()

    # -- Mic Level Monitor --

    def set_mic_source(self, gui_bridge: QObject) -> None:
        """Read mic level from gui_bridge instead of spawning own pw-record.

        When running in unified app mode, gui_bridge owns the single pw-record
        process. This avoids duplicate mic readers.
        """
        self._mic_source = gui_bridge
        gui_bridge.micLevelChanged.connect(self._on_shared_mic_level)
        logger.info("Editor mic source: shared from gui_bridge")

    def _on_shared_mic_level(self) -> None:
        """Forward mic level from gui_bridge."""
        if self._mic_source:
            self._mic_level = self._mic_source.micLevel
            self.micLevelChanged.emit()

    def _start_mic_monitor(self):
        """Start background mic level monitoring via pw-record stdout.

        If set_mic_source() was called, skip — we read from gui_bridge instead.
        """
        if self._mic_source is not None:
            logger.info("Mic monitor skipped: using shared source from gui_bridge")
            return
        if self._mic_monitor_running:
            return
        self._mic_monitor_running = True
        self._mic_monitor_thread = threading.Thread(
            target=self._mic_monitor_loop, daemon=True
        )
        self._mic_monitor_thread.start()

    def _mic_monitor_loop(self):
        """Read raw audio from pw-record stdout and compute RMS at ~30Hz."""
        try:
            self._mic_monitor_proc = subprocess.Popen(
                [
                    "pw-record",
                    "--target", "61",  # Jabra mic
                    "--rate", "48000",
                    "--channels", "1",
                    "--format", "s16",
                    "-",  # stdout
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("pw-record not found, mic monitor disabled")
            self._mic_monitor_running = False
            return

        CHUNK_BYTES = 3200  # 1600 samples * 2 bytes = ~33ms at 48kHz
        proc = self._mic_monitor_proc
        while self._mic_monitor_running and proc and proc.poll() is None:
            try:
                data = proc.stdout.read(CHUNK_BYTES)
                if not data:
                    break
                # Unpack s16le samples and compute RMS
                n_samples = len(data) // 2
                if n_samples == 0:
                    continue
                samples = struct.unpack(f"<{n_samples}h", data[:n_samples * 2])
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                # Normalize to 0.0-1.0 (s16 max = 32768)
                level = min(1.0, rms / 32768.0 * 4.0)  # *4 for visual boost
                self._mic_level = level
                self.micLevelChanged.emit()
            except Exception:
                break

        self._mic_monitor_running = False

    def _stop_mic_monitor(self):
        """Stop the mic level monitor."""
        self._mic_monitor_running = False
        if self._mic_monitor_proc and self._mic_monitor_proc.poll() is None:
            self._mic_monitor_proc.terminate()
            self._mic_monitor_proc = None

    def _stderr_reader(self, proc: subprocess.Popen):
        """Read stderr from pw-record in a background thread."""
        try:
            stderr_data = proc.stderr.read() if proc.stderr else b""
            self._rec_stderr_output = stderr_data.decode("utf-8", errors="replace")
        except Exception:
            self._rec_stderr_output = ""

    @Slot()
    def startRecording(self):
        """Start recording via PipeWire. Use recordAndPlay() for synchronized operation."""
        if self._is_recording:
            return

        # Timestamped filename to avoid overwriting previous takes
        self._take_count += 1
        self.takeCountChanged.emit()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_path = self._output_dir / f"graham_take{self._take_count:02d}_{timestamp}.wav"
        self._rec_audio_path = str(rec_path)
        self.recAudioPathChanged.emit()

        try:
            self._rec_stderr_output = ""
            self._rec_process = subprocess.Popen(
                [
                    "pw-record",
                    "--rate", "48000",
                    "--channels", "1",
                    "--format", "s16",
                    str(rec_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Read stderr in background thread so it doesn't block
            self._rec_stderr_thread = threading.Thread(
                target=self._stderr_reader,
                args=(self._rec_process,),
                daemon=True,
            )
            self._rec_stderr_thread.start()

            self._is_recording = True
            self.isRecordingChanged.emit()
            self.recordingStarted.emit()
            logger.info(f"Recording started: {rec_path} (take {self._take_count})")
        except FileNotFoundError:
            msg = "pw-record not found — is PipeWire installed?"
            logger.error(msg)
            self.recordingError.emit(msg)

    @Slot()
    def recordAndPlay(self):
        """Start recording AND request playback simultaneously.

        This ensures Graham's recording is time-aligned with the reference.
        QML connects playbackRequested to refPlayer.play().
        If an in-point is set, QML should seek to it before playing.
        """
        self.startRecording()
        if self._is_recording:
            self.playbackRequested.emit()

    @Slot()
    def cycleTake(self):
        """Cycle to next take for loop recording.

        Terminates current pw-record, immediately starts a new one with
        incremented take count.  Does NOT compute peaks/similarity or emit
        recordingStopped — keeps isRecording True throughout so the UI and
        Timer don't flicker.
        """
        if not self._is_recording or not self._rec_process:
            return

        # Terminate current recording
        self._rec_process.terminate()
        self._rec_process.wait(timeout=2)
        logger.info(
            f"Take {self._take_count} saved (loop cycle): {self._rec_audio_path}"
        )

        # Add completed take to list
        completed_path = Path(self._rec_audio_path)
        if completed_path.exists() and completed_path.stat().st_size > 0:
            self._take_list.append({
                "path": self._rec_audio_path,
                "label": completed_path.stem,
            })
            self.takeListChanged.emit()

        # Start new take immediately
        self._take_count += 1
        self.takeCountChanged.emit()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_path = (
            self._output_dir
            / f"graham_take{self._take_count:02d}_{timestamp}.wav"
        )
        self._rec_audio_path = str(rec_path)
        self.recAudioPathChanged.emit()

        try:
            self._rec_stderr_output = ""
            self._rec_process = subprocess.Popen(
                [
                    "pw-record",
                    "--rate", "48000",
                    "--channels", "1",
                    "--format", "s16",
                    str(rec_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._rec_stderr_thread = threading.Thread(
                target=self._stderr_reader,
                args=(self._rec_process,),
                daemon=True,
            )
            self._rec_stderr_thread.start()
            logger.info(
                f"Recording started: {rec_path} "
                f"(take {self._take_count}, loop cycle)"
            )
        except FileNotFoundError:
            self._is_recording = False
            self.isRecordingChanged.emit()
            self.recordingError.emit("pw-record not found")

    @Slot()
    def stopRecording(self):
        """Stop recording and compute waveform peaks for the recording."""
        if not self._is_recording or not self._rec_process:
            return

        self._rec_process.terminate()
        self._rec_process.wait(timeout=5)
        self._rec_process = None
        self._is_recording = False
        self.isRecordingChanged.emit()
        self.recordingStopped.emit()

        # Wait for stderr thread to finish
        if self._rec_stderr_thread:
            self._rec_stderr_thread.join(timeout=2)
            self._rec_stderr_thread = None

        # Check for pw-record errors
        if self._rec_stderr_output.strip():
            logger.warning(f"pw-record stderr: {self._rec_stderr_output.strip()}")

        # Load recorded audio and compute peaks
        rec_path = Path(self._rec_audio_path)
        if rec_path.exists() and rec_path.stat().st_size > 0:
            from waveform import load_audio, resample_for_display

            audio, sr = load_audio(rec_path)
            mins, maxs = resample_for_display(audio, width=2000)
            self._rec_peaks = []
            for mn, mx in zip(mins, maxs):
                self._rec_peaks.append(float(mn))
                self._rec_peaks.append(float(mx))
            self.recPeaksChanged.emit()
            self.peaksUpdated.emit()
            logger.info(f"Recording stopped, {len(audio) / sr:.1f}s captured")

            # Add to take list
            self._take_list.append({
                "path": str(rec_path),
                "label": rec_path.stem,
            })
            self.takeListChanged.emit()

            # Auto-compute per-segment similarity
            self.computeSimilarity()
        else:
            msg = "Recording file empty or missing"
            if self._rec_stderr_output.strip():
                msg += f" — pw-record: {self._rec_stderr_output.strip()}"
            logger.error(msg)
            self.recordingError.emit(msg)

    @Slot(str)
    def saveAlignment(self, output_path: str):
        """Save current segment boundaries to alignment JSON."""
        from alignment import save_alignment

        out = (
            Path(output_path)
            if output_path
            else self._output_dir / "alignment.json"
        )
        save_alignment(self._segment_model.segments, out)
        self.alignmentSaved.emit()
        logger.info(f"Alignment saved: {out}")

    @Slot(int, int, int)
    def updateSegmentBounds(self, row: int, start_ms: int, end_ms: int):
        """Update segment boundaries with minimum gap constraint (100ms)."""
        MIN_GAP_MS = 100
        segs = self._segment_model.segments

        # Clamp start: must not go before previous segment's end + gap
        if row > 0:
            prev_end = segs[row - 1].end_ms
            start_ms = max(start_ms, prev_end + MIN_GAP_MS)

        # Clamp end: must not go past next segment's start - gap
        if row < len(segs) - 1:
            next_start = segs[row + 1].start_ms
            end_ms = min(end_ms, next_start - MIN_GAP_MS)

        # Enforce minimum segment length
        if end_ms - start_ms < MIN_GAP_MS:
            return

        self._segment_model.update_segment(row, start_ms, end_ms)

    @Slot(float, result=str)
    def getSrtTextAt(self, position_s: float) -> str:
        """Return SRT text for the segment at the given time position."""
        pos_ms = int(position_s * 1000)
        for seg in self._segment_model.segments:
            if seg.start_ms <= pos_ms <= seg.end_ms:
                self._srt_text = seg.text
                self.srtTextChanged.emit()
                return seg.text
        return ""

    # -- Segment accessor slots (for QML) --

    @Slot(int, result=int)
    def getSegmentStartMs(self, row: int) -> int:
        """Get start_ms for segment at row index."""
        segs = self._segment_model.segments
        if 0 <= row < len(segs):
            return segs[row].start_ms
        return -1

    @Slot(int, result=int)
    def getSegmentEndMs(self, row: int) -> int:
        """Get end_ms for segment at row index."""
        segs = self._segment_model.segments
        if 0 <= row < len(segs):
            return segs[row].end_ms
        return -1

    @Slot(int, result=str)
    def getSegmentText(self, row: int) -> str:
        """Get text for segment at row index."""
        segs = self._segment_model.segments
        if 0 <= row < len(segs):
            return segs[row].text
        return ""

    @Slot(int, result=float)
    def getSegmentSimilarity(self, row: int) -> float:
        """Get similarity score for segment at row index."""
        segs = self._segment_model.segments
        if 0 <= row < len(segs):
            return segs[row].similarity
        return 0.0

    @Slot(float, result=int)
    def findSegmentAt(self, position_ms: float) -> int:
        """Find segment index containing the given position in ms. Returns -1 if none."""
        pos = int(position_ms)
        for i, seg in enumerate(self._segment_model.segments):
            if seg.start_ms <= pos <= seg.end_ms:
                return i
        return -1

    @Slot()
    def computeSimilarity(self):
        """Compute per-segment MFCC similarity between reference and recording."""
        rec_path = Path(self._rec_audio_path) if self._rec_audio_path else None
        ref_path = Path(self._ref_audio_path) if self._ref_audio_path else None

        if not rec_path or not rec_path.exists() or not ref_path or not ref_path.exists():
            logger.warning("Cannot compute similarity: missing audio files")
            return

        from alignment import _compute_similarity, _ms_to_samples

        import numpy as np
        import soundfile as sf

        ref_audio, ref_sr = sf.read(str(ref_path), dtype="float32")
        rec_audio, rec_sr = sf.read(str(rec_path), dtype="float32")

        if ref_audio.ndim > 1:
            ref_audio = ref_audio.mean(axis=1)
        if rec_audio.ndim > 1:
            rec_audio = rec_audio.mean(axis=1)

        sr = min(ref_sr, rec_sr)

        for i, seg in enumerate(self._segment_model.segments):
            start_sample_ref = _ms_to_samples(seg.start_ms, ref_sr)
            end_sample_ref = _ms_to_samples(seg.end_ms, ref_sr)
            start_sample_rec = _ms_to_samples(seg.start_ms, rec_sr)
            end_sample_rec = _ms_to_samples(seg.end_ms, rec_sr)

            ref_seg = ref_audio[start_sample_ref:end_sample_ref]
            rec_seg = rec_audio[start_sample_rec:end_sample_rec]

            if len(ref_seg) > 0 and len(rec_seg) > 0:
                sim = _compute_similarity(ref_seg, rec_seg, sr)
                seg.similarity = sim
            else:
                seg.similarity = 0.0

        # Notify QML that model data changed
        first = self._segment_model.index(0)
        last = self._segment_model.index(len(self._segment_model.segments) - 1)
        self._segment_model.dataChanged.emit(first, last)
        logger.info("Per-segment MFCC similarity computed")
