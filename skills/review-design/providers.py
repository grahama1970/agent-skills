"""Provider dispatch for review-design skill.

Each provider function accepts (system_prompt, user_prompt, images) and returns
the LLM response text. The call_provider() dispatcher handles retries and
routing.
"""

import json
import os
import subprocess
import time
from typing import Optional

from config import PROVIDERS, normalize_provider

SCILLM_BASE_URL = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")
SCILLM_API_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")
SCILLM_CALLER = "review-design"
SCILLM_TIMEOUT_SEC = int(os.environ.get("REVIEW_DESIGN_SCILLM_TIMEOUT_SEC", "120"))


def _load_gemini_api_key() -> tuple[str, str]:
    """Load a Gemini API key without logging secret material."""
    for env_name in (
        "GEMINI_API_KEY_PAID",
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_FREE2",
        "GEMINI_API_KEY_FREE",
    ):
        value = os.environ.get(env_name, "").strip().strip('"').strip("'")
        if value:
            return value, env_name

    # Legacy workstation setup stores the key in KDE Wallet.
    result = subprocess.run(
        ["kwallet-query", "-r", "GEMINI_API_KEY", "-f", "Embry OS", "kdewallet"],
        capture_output=True, text=True, timeout=5,
    )
    api_key = result.stdout.strip()
    if api_key and not api_key.startswith(("Failed", "Error")):
        return api_key, "KDE Wallet Embry OS/GEMINI_API_KEY"

    raise RuntimeError(
        "Gemini API key not found. Set GEMINI_API_KEY_PAID, GEMINI_API_KEY, "
        "GEMINI_API_KEY_FREE2, or GEMINI_API_KEY, or update KDE Wallet "
        "Embry OS/GEMINI_API_KEY."
    )


def call_claude(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
    session_id: Optional[str] = None,
) -> str:
    """Call Claude via Anthropic SDK with multimodal content blocks.

    Uses the SDK directly — NOT claude --print, which can't handle
    base64 images due to stdin length limits.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package required for Claude provider. "
            "Install with: pip install anthropic"
        )

    # OAuth is the default auth method. Falls back to ANTHROPIC_API_KEY if set.
    client = anthropic.Anthropic()

    # Build multimodal content blocks
    content = []
    for name, uri in images:
        if uri.startswith("data:"):
            header, b64_data = uri.split(",", 1)
            media_type = header.split(":")[1].split(";")[0]
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            })
            content.append({"type": "text", "text": f"[Image: {name}]"})

    content.append({"type": "text", "text": user_prompt})

    message = client.messages.create(
        model=PROVIDERS["claude"].model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
    )

    return message.content[0].text


def call_openai(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
) -> str:
    """Call OpenAI SDK with vision support.

    Do not pass base64 screenshots through the CLI argv. Large screenshots can
    exceed the OS argument-size limit; the SDK sends the payload in-process.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package required for OpenAI provider. "
            "Install with: uv sync --project /home/graham/workspace/experiments/agent-skills/skills/review-design"
        )

    content = []
    for name, uri in images:
        content.append({"type": "image_url", "image_url": {"url": uri}})
        content.append({"type": "text", "text": f"[Image: {name}]"})
    content.append({"type": "text", "text": user_prompt})

    client = OpenAI()
    response = client.chat.completions.create(
        model=PROVIDERS["openai"].model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        max_tokens=8192,
        temperature=0.7,
    )
    message = response.choices[0].message.content
    if not message:
        raise RuntimeError(f"OpenAI returned empty response: {response}")
    return message


def call_gemini(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
) -> str:
    """Call Gemini via httpx with an API key from env or KDE Wallet.

    Hits generativelanguage.googleapis.com.
    1M+ context window handles 30+ screenshots easily.
    No SDK — just httpx.
    """
    import httpx

    model = PROVIDERS["gemini"].model

    # Build content parts
    parts = []
    for name, uri in images:
        if uri.startswith("data:"):
            header, b64_data = uri.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": b64_data,
                }
            })
            parts.append({"text": f"[Image: {name}]"})

    parts.append({"text": user_prompt})

    payload = {
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 16384,
        },
    }

    api_key, key_source = _load_gemini_api_key()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, params={"key": api_key}, json=payload)

    if response.status_code != 200:
        error_message = response.text
        error_status = None
        try:
            error = response.json().get("error", {})
            error_message = error.get("message", error_message)
            error_status = error.get("status")
        except json.JSONDecodeError:
            pass

        if "reported as leaked" in error_message:
            raise RuntimeError(
                f"Gemini API key from {key_source} was reported as leaked/disabled. "
                "Create a new AI Studio key and update that source."
            )

        if error_status == "NOT_FOUND" and "no longer available" in error_message:
            raise RuntimeError(
                f"Gemini model {model} is no longer available for this key. "
                "Update review-design's Gemini model in config.py."
            )

        raise RuntimeError(
            f"Gemini API error {response.status_code}"
            f"{f' ({error_status})' if error_status else ''}: {error_message}"
        )

    result = response.json()

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response format: {result}") from e


def _scillm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SCILLM_API_KEY}",
        "X-Caller-Skill": SCILLM_CALLER,
        "Content-Type": "application/json",
    }


def check_scillm_health() -> None:
    """Fail fast with an actionable error if the scillm proxy is unavailable."""
    import httpx

    try:
        response = httpx.get(f"{SCILLM_BASE_URL}/health", timeout=2.0)
    except httpx.ConnectError as e:
        raise RuntimeError(
            "scillm proxy is not running. Start it with: "
            "docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d"
        ) from e
    except httpx.TimeoutException as e:
        raise RuntimeError(f"scillm proxy health check timed out at {SCILLM_BASE_URL}/health") from e

    if response.status_code != 200:
        raise RuntimeError(f"scillm proxy unhealthy: {response.status_code}: {response.text}")


def call_scillm(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
    provider: str = "scillm",
) -> str:
    """Call scillm API for vision review.

    Routes through the local scillm proxy using the public VLM model alias.
    scillm owns VLM fallback, provider retries, auth injection, and logging.
    """
    import httpx

    canonical_provider = normalize_provider(provider)
    model = os.environ.get("REVIEW_DESIGN_SCILLM_MODEL", PROVIDERS[canonical_provider].model)

    # Build multimodal content blocks (OpenAI-compatible format)
    content = []
    for name, uri in images:
        if uri.startswith("data:"):
            content.append({
                "type": "image_url",
                "image_url": {"url": uri},
            })
            content.append({"type": "text", "text": f"[Image: {name}]"})

    content.append({"type": "text", "text": user_prompt})

    check_scillm_health()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": 0.7,
        "stream": True,
        "stream_progress_events": True,
        "stream_heartbeat_s": 5,
        "timeout": SCILLM_TIMEOUT_SEC,
    }

    chunks: list[str] = []
    served_model = model
    print(f"    scillm: streaming request model={model}, images={len(images)}, timeout={SCILLM_TIMEOUT_SEC}s")

    timeout = httpx.Timeout(
        connect=5.0,
        read=SCILLM_TIMEOUT_SEC + 15.0,
        write=30.0,
        pool=5.0,
    )
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            f"{SCILLM_BASE_URL}/v1/chat/completions",
            headers=_scillm_headers(),
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                details = body
                try:
                    error_payload = json.loads(body)
                    error_obj = error_payload.get("error", error_payload)
                    project_agent_message = error_obj.get("project_agent_message")
                    provider_error_code = error_obj.get("provider_error_code") or error_obj.get("type")
                    if project_agent_message:
                        details = f"{project_agent_message} ({body})"
                    if provider_error_code:
                        details = f"{provider_error_code}: {details}"
                except json.JSONDecodeError:
                    pass
                raise RuntimeError(f"scillm error {response.status_code}: {details}")

            for line in response.iter_lines():
                if not line or line.startswith(":") or line.startswith("event:"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if event.get("model"):
                    served_model = event["model"]
                choices = event.get("choices") or []
                if not choices:
                    if event.get("event") in {"heartbeat", "started"}:
                        print(f"    scillm: {event.get('event')}")
                    continue
                delta = choices[0].get("delta") or {}
                content_delta = delta.get("content")
                if content_delta:
                    chunks.append(content_delta)
                    if len(chunks) == 1 or len("".join(chunks)) % 2000 < len(content_delta):
                        print(f"    scillm: streamed {len(''.join(chunks))} chars")

    text = "".join(chunks)
    if not text:
        raise RuntimeError("scillm returned empty streaming response")

    print(f"    scillm: requested={model}, served={served_model}, chars={len(text)}")
    return text


def call_provider(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
    session_id: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """Call the specified provider with vision support and retry on rate limit."""
    provider = normalize_provider(provider)
    for attempt in range(max_retries):
        try:
            if provider == "claude":
                return call_claude(system_prompt, user_prompt, images, session_id)
            elif provider == "openai":
                return call_openai(system_prompt, user_prompt, images)
            elif provider == "gemini":
                return call_gemini(system_prompt, user_prompt, images)
            elif provider == "scillm":
                return call_scillm(system_prompt, user_prompt, images, provider)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except RuntimeError as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = 60 * (attempt + 1)  # 60s, 120s, 180s
                print(f"    Rate limited. Waiting {wait_time}s before retry {attempt + 2}/{max_retries}...")
                time.sleep(wait_time)
            else:
                raise

    raise RuntimeError(f"Rate limit exceeded after {max_retries} retries")
