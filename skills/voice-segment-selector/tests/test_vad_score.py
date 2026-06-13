import numpy as np

from lib.score import score_clip
from lib.vad import detect_speech_spans, merge_intervals


def test_merge_intervals():
    merged = merge_intervals([(0.0, 1.0), (1.2, 2.0), (5.0, 6.0)], 0.45)
    assert merged == [(0.0, 2.0), (5.0, 6.0)]


def test_detect_speech_spans_on_tone():
    sr = 16000
    y = np.zeros(sr * 10, dtype=np.float32)
    y[sr * 2 : sr * 8] = 0.2 * np.sin(2 * np.pi * 180 * np.arange(sr * 6) / sr)
    spans = detect_speech_spans(y, sr, min_clip_sec=3.0, max_clip_sec=8.0, top_db=35)
    assert isinstance(spans, list)


def test_score_clip_positive():
    sr = 16000
    t = np.arange(sr * 5) / sr
    y = (0.08 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    score, metrics = score_clip(y, sr)
    assert score > 0.2
    assert "speech_ratio" in metrics
