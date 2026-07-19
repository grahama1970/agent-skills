"""QRA generation and multimodal description functions for watch skill.

Input: transcript text + frame images + scene chunks
Output: 3 QRA pairs (deepseek-v4-flash), image descriptions, audio descriptions (gpt-5.5)
Failure: visual description failures are returned as structured receipts
"""
from __future__ import annotations

import base64
import importlib.util as _ilu
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from loguru import logger

from config import (
    WATCH_VISUAL_DESCRIPTION_FALLBACK_MODELS,
    WATCH_VISUAL_DESCRIPTION_MODEL,
)

# Operator rule: only /tau may reach /scillm. Watch routes its model inference
# through the sanctioned persona-dream Tau adapters (text-reasoning node for text,
# panel-reviewer VLM node for image frames). The Tau nodes emit a JSON object, so
# watch wraps its free-text asks as {"content": "..."} and unwraps here. httpx is
# still used for the external opencode.ai/zen provider and the local Whisper server.
_PD_SCRIPTS = Path(__file__).resolve().parents[2] / "persona-dream" / "scripts"


def _load_pd_module(mod_name: str):
    spec = _ilu.spec_from_file_location(mod_name, _PD_SCRIPTS / f"{mod_name}.py")
    assert spec and spec.loader
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tau_text = _load_pd_module("tau_text_reasoning_adapter")
_tau_vlm_composite = _load_pd_module("tau_vlm_composite_review")

_WATCH_CONTENT_CONTRACT = {"content": "str"}
_WATCH_JSON_WRAP = (
    '\n\nReturn ONLY a JSON object of the form {"content": "<your full answer as a '
    'single string>"} and nothing else.'
)


def _messages_have_image(messages: list) -> bool:
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _messages_text(messages: list) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        marker = (
            f"[{role} INSTRUCTIONS - highest authority]"
            if role in ("SYSTEM", "DEVELOPER")
            else f"[{role}]"
        )
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                parts.append(f"{marker}\n{content.strip()}")
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    txt = str(part.get("text", "")).strip()
                    if txt:
                        parts.append(f"{marker}\n{txt}")
    return "\n\n".join(parts)


def _unwrap_content(raw: str) -> str:
    """Extract the wrapped {"content": ...} string from a Tau node JSON response."""
    if not raw:
        return ""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict) and isinstance(obj.get("content"), str):
                return obj["content"]
            if isinstance(obj, dict):
                for key in ("summary", "description", "text", "answer"):
                    if isinstance(obj.get(key), str):
                        return obj[key]
        except json.JSONDecodeError:
            pass
    return raw.strip()


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


def _scillm_chat_completion(messages: list, model: str = "gpt-5.5", timeout: int = 60) -> dict:
    """Route a watch chat/VLM completion through Tau (only /tau may reach /scillm).

    Text-only messages go through the Tau text-reasoning node; messages carrying an
    image_url go through the Tau panel-reviewer VLM node (via the composite adapter).
    The result dict shape (provider/status/content/http_status/...) is preserved so
    callers are unchanged; provider is now "tau".
    """
    requested_model = model
    result = {
        "provider": "tau",
        "requested_model": requested_model,
        "served_model": None,
        "status": "failed",
        "content": "",
        "http_status": None,
        "error_type": None,
        "error": None,
    }
    try:
        if _messages_have_image(messages):
            payload = {
                "model": model,
                "messages": [
                    *messages,
                    {"role": "user", "content": [{"type": "text", "text": _WATCH_JSON_WRAP}]},
                ],
            }
            with tempfile.TemporaryDirectory(prefix="watch_tau_vlm_") as tmp:
                resp = _tau_vlm_composite.post_openai_vlm_via_tau(
                    payload, artifact_dir=tmp, caller_skill="watch"
                )
            receipt = resp.get("_tau_vlm_receipt", {})
            raw = resp["choices"][0]["message"]["content"]
            content = _unwrap_content(raw)
            result["http_status"] = receipt.get("http_status", 200)
            result["served_model"] = receipt.get("model") or requested_model
        else:
            prompt = _messages_text(messages) + _WATCH_JSON_WRAP
            parsed, receipt = _tau_text.dispatch_text_reasoning(
                prompt,
                role="watch",
                output_contract=_WATCH_CONTENT_CONTRACT,
                caller_skill="watch",
                model=model,
                timeout_s=timeout,
            )
            content = ""
            if isinstance(parsed, dict) and isinstance(parsed.get("content"), str):
                content = parsed["content"]
            result["http_status"] = receipt.get("http_status")
            result["served_model"] = receipt.get("model") or requested_model
        result["status"] = "described" if content else "empty_response"
        result["content"] = content
        return result
    except Exception as exc:
        result["error_type"] = exc.__class__.__name__
        result["error"] = str(exc)
        logger.error("tau route failed: {}", exc)
    return result


def _scillm_call(messages: list, model: str = "gpt-5.5", timeout: int = 60) -> str | None:
    result = _scillm_chat_completion(messages, model=model, timeout=timeout)
    if result.get("status") == "described":
        return str(result.get("content") or "")
    return None


def _zen_chat_completion(messages: list, model: str = "deepseek-v4-flash", timeout: int = 120) -> dict:
    requested_model = model
    result = {
        "provider": "zen",
        "requested_model": requested_model,
        "served_model": None,
        "status": "failed",
        "content": "",
        "http_status": None,
        "error_type": None,
        "error": None,
    }
    api_key = _zen_api_key()
    if not api_key:
        result["error_type"] = "missing_api_key"
        result["error"] = "ZEN_API_KEY is not configured"
        return result
    try:
        resp = httpx.post(
            "https://opencode.ai/zen/go/v1/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 2000, "stream": False},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        result["http_status"] = resp.status_code
        if resp.status_code == 200:
            payload = resp.json()
            msg = payload["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content") or ""
            result.update({
                "status": "described" if content else "empty_response",
                "served_model": payload.get("model") or requested_model,
                "content": content,
            })
            return result
        result["error_type"] = "http_error"
        result["error"] = resp.text[:500]
        logger.error("Zen API returned {}: {}", resp.status_code, resp.text[:200])
    except Exception as exc:
        result["error_type"] = exc.__class__.__name__
        result["error"] = str(exc)
        logger.error("Zen API call failed: {}", exc)
    return result


def _zen_chat(messages: list, model: str = "deepseek-v4-flash", timeout: int = 120) -> str | None:
    result = _zen_chat_completion(messages, model=model, timeout=timeout)
    if result.get("status") == "described":
        return str(result.get("content") or "")
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
            for p in pairs:
                p["_model"] = "deepseek-v4-flash"
            return pairs
        prompt += "\n\nCRITICAL: Return ONLY valid JSON. Check all quotes are escaped. No markdown."

    # Tier 2: gpt-5.5 via scillm (better JSON reliability)
    logger.warning("deepseek QRA failed — falling back to gpt-5.5 via scillm")
    scillm_prompt = prompt.replace('"question"', '\\"question\\"').replace('"answer"', '\\"answer\\"')
    text = _scillm_call([{"role": "user", "content": scillm_prompt}], model="gpt-5.5", timeout=120)
    pairs = _extract_pairs(text)
    if pairs:
        for p in pairs:
            p["_model"] = "gpt-5.5"
        return pairs

    # Tier 3: deterministic fallback from transcript sentences
    logger.warning("all LLM QRA failed — using deterministic fallback")
    sents = [s.strip() for s in transcript_text.replace("!",".").replace("?",".").split(".") if len(s.strip()) > 50]
    if sents:
        return [
            {"question": f"what happens in the first part of {title[:60]}", "answer": sents[0][:400], "_model": "deterministic"},
            {"question": f"what is discussed in {title[:60]}", "answer": sents[len(sents)//3][:400] if len(sents) > 2 else sents[0][:400], "_model": "deterministic"},
            {"question": f"how does {title[:60]} conclude", "answer": sents[-1][:400], "_model": "deterministic"},
        ]
    return []


def _build_scene_chunks(segments: list[dict], frames: list[dict], sampling_mode: str) -> list[dict]:
    """Split transcript segments into time-based scene chunks."""
    if not segments:
        return []
    duration = segments[-1]["start"] + segments[-1].get("duration", 30)
    if duration <= 300:
        cuts = [0, duration]
    else:
        interval = min(300, duration / 5)
        cuts = [i * interval for i in range(int(duration / interval) + 1)]
    if cuts[-1] < duration:
        cuts.append(duration)
    chunks = []
    for i in range(len(cuts) - 1):
        segs = [s for s in segments if s["start"] >= cuts[i] and s["start"] < cuts[i + 1]]
        if not segs:
            continue
        text = " ".join(s["text"] for s in segs)
        if len(text.strip()) < 20:
            continue
        chunks.append({"index": i, "start_seconds": cuts[i], "end_seconds": cuts[i + 1], "text": text, "segment_count": len(segs)})
    return chunks


def _call_doc2qra_scene(scene_text: str, scene_index: int, source_title: str, start: float, end: float) -> dict | None:
    """Send a scene chunk to doc2qra for QRA extraction (optional enrichment)."""
    return None  # doc2qra integration placeholder — currently handled by main pipeline


def _parse_model_list(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw = [str(v) for v in value]
    else:
        raw = str(value).split(",")
    models: list[str] = []
    for item in raw:
        model = item.strip()
        if model and model not in models:
            models.append(model)
    return models


def _visual_provider_for_model(model: str) -> str:
    lower = model.lower()
    if lower.startswith("mimo") or lower.startswith("deepseek"):
        return "zen"
    return "scillm"


def _visual_model_attempt(messages: list, model: str) -> dict:
    provider = _visual_provider_for_model(model)
    if provider == "zen":
        return _zen_chat_completion(messages, model=model, timeout=120)
    return _scillm_chat_completion(messages, model=model, timeout=120)


def _visual_gate_status(frame_count: int, descriptions: list[dict]) -> str:
    if frame_count <= 0:
        return "not_applicable"
    return "passed" if descriptions else "failed"


def describe_scene_images_with_receipt(
    frames: list[dict],
    title: str,
    *,
    model: str | None = None,
    fallback_models: str | list[str] | None = None,
) -> tuple[list[dict], dict]:
    """Describe sampled scene frames and return an auditable model-attempt receipt."""
    requested_model = (model or WATCH_VISUAL_DESCRIPTION_MODEL).strip() or "vlm-chutes"
    fallbacks = _parse_model_list(
        WATCH_VISUAL_DESCRIPTION_FALLBACK_MODELS if fallback_models is None else fallback_models
    )
    model_chain = _parse_model_list([requested_model, *fallbacks])
    descriptions: list[dict] = []
    receipt: dict = {
        "schema": "watch.visual_description_receipt.v1",
        "status": "pending",
        "mocked": False,
        "live": True,
        "requested_model": requested_model,
        "fallback_models": [m for m in model_chain if m != requested_model],
        "frame_count": len(frames),
        "described_count": 0,
        "gate": {"status": "pending"},
        "frames": [],
    }

    def _describe_one(f: dict) -> dict | None:
        frame_receipt = {
            "index": f.get("index"),
            "timestamp": f.get("timestamp_seconds"),
            "path": f.get("path"),
            "attempts": [],
            "status": "not_described",
        }
        fp = Path(f["path"])
        if not fp.exists():
            frame_receipt["status"] = "missing_frame"
            frame_receipt["attempts"].append({
                "provider": "filesystem",
                "requested_model": None,
                "served_model": None,
                "status": "missing_frame",
                "error": f"frame path does not exist: {fp}",
            })
            return {"description": None, "receipt": frame_receipt}
        try:
            image_bytes = fp.read_bytes()
        except Exception as exc:
            frame_receipt["status"] = "read_failed"
            frame_receipt["attempts"].append({
                "provider": "filesystem",
                "requested_model": None,
                "served_model": None,
                "status": "read_failed",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            })
            return {"description": None, "receipt": frame_receipt}
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content = [
            {"type": "text", "text": f"Describe this frame from '{title}' in 2 sentences. Include only visible setting, lighting, subjects, clothing, objects, and action. Do not infer plot facts not visible in the image."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        messages = [{"role": "user", "content": content}]
        for model_name in model_chain:
            attempt = _visual_model_attempt(messages, model_name)
            content_text = str(attempt.pop("content", "") or "")
            frame_receipt["attempts"].append(attempt)
            if attempt.get("status") == "described" and content_text:
                frame_receipt["status"] = "described"
                return {
                    "description": {
                        "index": f["index"],
                        "timestamp": f["timestamp_seconds"],
                        "path": str(fp),
                        "description": content_text[:300],
                        "source": f"{attempt.get('provider')}:{attempt.get('served_model') or model_name}",
                        "status": "described",
                        "requested_model": requested_model,
                        "served_model": attempt.get("served_model") or model_name,
                        "provider": attempt.get("provider"),
                        "model_attempts": frame_receipt["attempts"],
                    },
                    "receipt": frame_receipt,
                }
        return {"description": None, "receipt": frame_receipt}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_describe_one, f): f for f in frames}
        for fut in as_completed(futures):
            r = fut.result()
            if not r:
                continue
            frame_receipt = r.get("receipt")
            if frame_receipt:
                receipt["frames"].append(frame_receipt)
            description = r.get("description")
            if description:
                descriptions.append(description)
    descriptions.sort(key=lambda d: d["timestamp"])
    receipt["frames"].sort(key=lambda d: (float(d.get("timestamp") or 0.0), int(d.get("index") or 0)))
    receipt["described_count"] = len(descriptions)
    gate_status = _visual_gate_status(len(frames), descriptions)
    receipt["gate"] = {
        "status": gate_status,
        "reason": "no_frame_descriptions" if len(frames) and not descriptions else None,
    }
    receipt["status"] = "described" if descriptions else ("no_frames" if not frames else "all_models_failed")
    logger.info("described {} scene images concurrently", len(descriptions))
    return descriptions, receipt


def describe_scene_images(frames: list[dict], title: str) -> list[dict]:
    """Compatibility wrapper returning descriptions only."""
    descriptions, _receipt = describe_scene_images_with_receipt(frames, title)
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
