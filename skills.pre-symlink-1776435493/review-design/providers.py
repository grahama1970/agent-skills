"""Provider dispatch for review-design skill.

Each provider function accepts (system_prompt, user_prompt, images) and returns
the LLM response text. The call_provider() dispatcher handles retries and
routing.
"""

import json
import subprocess
import time
from typing import Optional

from config import PROVIDERS


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
    """Call OpenAI CLI with vision support."""
    # Build messages with images
    content = []
    for name, uri in images:
        content.append({"type": "image_url", "image_url": {"url": uri}})
    content.append({"type": "text", "text": user_prompt})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    # Use the openai CLI or API
    cmd = [
        "openai", "api", "chat.completions.create",
        "--model", PROVIDERS["openai"].model,
        "--messages", json.dumps(messages),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"OpenAI CLI failed (rc={result.returncode}): {result.stderr}")

    # Parse response
    response = json.loads(result.stdout)
    return response["choices"][0]["message"]["content"]


def call_gemini(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
) -> str:
    """Call Gemini via httpx with API key from KDE Wallet (Pro Plan).

    Uses GEMINI_API_KEY from KDE Wallet "Embry OS" folder.
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

    # Use generativelanguage endpoint with API key from wallet as auth
    # (OAuth token from Gemini CLI has cloud-platform scope, not generative-language)
    api_key = subprocess.run(
        ["kwallet-query", "-r", "GEMINI_API_KEY", "-f", "Embry OS", "kdewallet"],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()

    if not api_key or api_key.startswith("Failed") or api_key.startswith("Error"):
        raise RuntimeError("GEMINI_API_KEY not found in KDE Wallet (Embry OS folder)")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, params={"key": api_key}, json=payload)

    if response.status_code != 200:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")

    result = response.json()

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response format: {result}") from e


def call_subagent(
    system_prompt: str,
    user_prompt: str,
    images: list[tuple[str, str]],
) -> str:
    """Call scillm API for vision review.

    Routes through the local scillm proxy on localhost:4001.
    Uses the configured model for vision (large context).
    """
    import httpx

    model = PROVIDERS["subagent"].model

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

    url = "http://localhost:4001/v1/chat/completions"

    with httpx.Client(timeout=600.0) as client:
        response = client.post(
            url,
            headers={"Authorization": "Bearer sk-dev-proxy-123"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                "max_tokens": 16384,
                "temperature": 0.7,
            },
        )

    if response.status_code != 200:
        raise RuntimeError(f"scillm error {response.status_code}: {response.text}")

    result = response.json()
    text = result["choices"][0]["message"]["content"]

    if not text:
        raise RuntimeError(f"scillm returned empty response: {result}")

    usage = result.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    print(f"    scillm: model={model}, tokens={total_tokens}")

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
    for attempt in range(max_retries):
        try:
            if provider == "claude":
                return call_claude(system_prompt, user_prompt, images, session_id)
            elif provider == "openai":
                return call_openai(system_prompt, user_prompt, images)
            elif provider == "gemini":
                return call_gemini(system_prompt, user_prompt, images)
            elif provider == "subagent":
                return call_subagent(system_prompt, user_prompt, images)
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
