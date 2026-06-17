"""QRA generation and multimodal description functions for watch skill.

Input: transcript text + frame images + scene chunks
Output: 3 QRA pairs (deepseek-v4-flash), image descriptions (mimo-v2-omni), audio descriptions (gpt-5.5)
Failure: returns empty list on API error (calling code handles fallback)
"""
from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from loguru import logger


def _zen_api_key() -> str:
    k = os.environ.get("ZEN_API_KEY", "")
    if not k:
        zshrc = Path.home() / ".zshrc"
        if zshrc.exists():
            for line in zshrc.read_text().splitlines():
                m = re.search(r'ZEN_API_KEY="([^"]+)"', line)
                if m:
                    k = m.group(1)
                    break
    return k


def _scillm_call(messages: list, model: str = "gpt-5.5", timeout: int = 60) -> str | None:
    try:
        resp = httpx.post(
            "http://localhost:4001/v1/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 500, "stream": False},
            headers={"Authorization": "Bearer sk-dev-proxy-123", "X-Caller-Skill": "watch"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning_content") or ""
    except Exception as exc:
        logger.error("scillm call failed: {}", exc)
    return None


def _zen_chat(messages: list, model: str = "deepseek-v4-flash", timeout: int = 120) -> str | None:
    api_key = _zen_api_key()
    if not api_key:
        return None
    try:
        resp = httpx.post(
            "https://opencode.ai/zen/go/v1/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 2000, "stream": False},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning_content") or ""
        logger.error("Zen API returned {}: {}", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Zen API call failed: {}", exc)
    return None


def generate_qras(transcript_text: str, title: str, uploader: str | None = None) -> list[dict]:
    """Generate 3 QRA pairs from transcript.

    Tries: deepseek-v4-flash (Zen) → gpt-5.5 (scillm) → deterministic fallback.
    """
    if not transcript_text or len(transcript_text.strip()) < 50:
        return []
    creator = uploader or "unknown"
    truncated = transcript_text[:8000]
    prompt = (
        f'Video: "{title}" by {creator}\n\n'
        + f"Transcript excerpt ({len(truncated)} chars):\n{truncated}\n\n"
        + "Generate exactly 3 question-answer pairs about this video. "
        + "Return ONLY valid JSON array, one pair per line, no other text:\n"
        + '{"question":"specific question","answer":"2-4 sentence answer"}\n'
        + '{"question":"another specific question","answer":"2-4 sentence answer"}\n'
        + '{"question":"a third specific question","answer":"2-4 sentence answer"}'
    )

    def _extract_pairs(text: str) -> list[dict] | None:
        """Try to extract QRA pairs from LLM response text."""
        if not text:
            return None
        text = text.replace("```json", "").replace("```", "").strip()
        import re as _re
        try:
            if text.startswith("["):
                pairs = json.loads(text)
            else:
                lines = [l.strip() for l in text.split("\n") if l.strip().startswith("{")]
                pairs = json.loads(f"[{','.join(lines)}]")
            if not isinstance(pairs, list):
                pairs = [pairs]
            valid = [p for p in pairs if len(p.get("answer", "")) >= 30]
            return valid[:3] if valid else None
        except Exception:
            return None

    # Tier 1: deepseek-v4-flash via Zen API
    for attempt in range(2):
        text = _zen_chat([{"role": "user", "content": prompt}], timeout=120)
        pairs = _extract_pairs(text)
        if pairs:
            return pairs
        prompt += "\n\nCRITICAL: Return ONLY valid JSON. Check all quotes are escaped. No markdown."

    # Tier 2: gpt-5.5 via scillm (better JSON reliability)
    logger.warning("deepseek QRA failed — falling back to gpt-5.5 via scillm")
    scillm_prompt = prompt.replace('"question"', '\\"question\\"').replace('"answer"', '\\"answer\\"')
    text = _scillm_call([{"role": "user", "content": scillm_prompt}], model="gpt-5.5", timeout=120)
    pairs = _extract_pairs(text)
    if pairs:
        return pairs

    # Tier 3: deterministic fallback from transcript sentences
    logger.warning("all LLM QRA failed — using deterministic fallback")
    sents = [s.strip() for s in transcript_text.replace("!",".").replace("?",".").split(".") if len(s.strip()) > 50]
    if sents:
        return [
            {"question": f"what happens in the first part of {title[:60]}", "answer": sents[0][:400]},
            {"question": f"what is discussed in {title[:60]}", "answer": sents[len(sents)//3][:400] if len(sents) > 2 else sents[0][:400]},
            {"question": f"how does {title[:60]} conclude", "answer": sents[-1][:400]},
        ]
    return []


def describe_scene_images(frames: list[dict], title: str) -> list[dict]:
    """Describe up to 5 scene frames via mimo-v2-omni, concurrent."""
    if not _zen_api_key():
        return []
    descriptions: list[dict] = []

    def _describe_one(f: dict) -> dict | None:
        fp = Path(f["path"])
        if not fp.exists():
            return None
        b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
        text = _zen_chat(
            [{"role": "user", "content": [
                {"type": "text", "text": f"Describe this frame from '{title}' in 2 sentences. Include setting, lighting, visible subjects, and action."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            model="mimo-v2-omni",
            timeout=120,
        )
        if text:
            return {"index": f["index"], "timestamp": f["timestamp_seconds"], "description": text[:300]}
        return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_describe_one, f): f for f in frames[:5]}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                descriptions.append(r)
    descriptions.sort(key=lambda d: d["timestamp"])
    logger.info("described {} scene images concurrently", len(descriptions))
    return descriptions


def describe_audio_tracks(scenes: list[dict], transcript_segments: list[dict], title: str) -> list[dict]:
    """Describe soundtrack per scene chunk via gpt-5.5, concurrent."""
    if not scenes or not transcript_segments:
        return []
    descriptions: list[dict] = []

    def _describe_one(s: dict) -> dict | None:
        start_sec = s.get("start_seconds", s.get("start", 0))
        end_sec = s.get("end_seconds", s.get("end", 0))
        segs = [sg for sg in transcript_segments if sg["start"] >= start_sec and sg["start"] <= end_sec]
        if not segs:
            return None
        text = " ".join(sg["text"] for sg in segs)
        result = _scillm_call([{"role": "user", "content":
            f"Describe the audio/soundtrack for this scene from '{title}' ({start_sec:.0f}-{end_sec:.0f}s). "
            + f"Based on this transcript, describe the mood, music, sound effects, and dialogue delivery: {text[:1000]}"}])
        if result:
            return {"start": start_sec, "end": end_sec, "description": result[:300]}
        return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_describe_one, s): s for s in scenes[:5]}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                descriptions.append(r)
    descriptions.sort(key=lambda d: d["start"])
    logger.info("described {} audio tracks concurrently", len(descriptions))
    return descriptions
