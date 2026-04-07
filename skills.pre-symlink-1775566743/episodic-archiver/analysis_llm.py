"""LLM interface and session assessment for episodic archiver analysis."""

import json
import os
import sys
from typing import Any, Dict, List
from loguru import logger

# ---------------------------------------------------------------------------
# Shadow gateway: route through /assistant validate() cascade
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("EPISODIC_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        _assistant_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assistant")
        if _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False


def get_embedding(text: str) -> list:
    """Get embedding from service, fallback to graph_memory."""
    import httpx as _httpx
    service_url = os.getenv("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602")
    try:
        resp = _httpx.post(f"{service_url}/embed", json={"text": text}, timeout=10)
        if resp.status_code == 200:
            return resp.json()["vector"]
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    from graph_memory.embeddings import encode_texts
    return encode_texts([text])[0]


def _get_llm_config() -> dict:
    """Get scillm configuration from environment."""
    return {
        "model": os.getenv("CHUTES_MODEL_ID") or os.getenv("CHUTES_TEXT_MODEL", "sonar-medium"),
        "api_base": os.getenv("SCILLM_API_BASE", "http://localhost:4001"),
        "api_key": os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123"),
    }


async def _llm_completion(prompt: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
    """Single LLM completion via scillm, with /assistant gateway cascade."""
    # --- Gateway path: try cheaper tiers first ---
    if _gateway_available and json_mode:
        try:
            gw_result = _gw_validate(
                input_data={"turns": prompt[:2000], "session_id": "episodic"},
                task="episodic-session-scorer",
            )
            if gw_result and gw_result.result:
                import json as _json
                return _json.dumps(gw_result.result)
        except Exception as e:
            logger.debug("gateway episodic analysis failed, falling through to scillm: {}", e)

    # --- Direct scillm path (fallback) ---
    from scillm import acompletion

    cfg = _get_llm_config()
    if not cfg["api_key"]:
        return "{}" if json_mode else ""

    kwargs = dict(
        model=cfg["model"],
        api_base=cfg["api_base"],
        api_key=cfg["api_key"],
        custom_llm_provider="openai",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
        timeout=60,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = await acompletion(**kwargs)
    return resp.choices[0].message.content


async def _llm_batch(requests: list, concurrency: int = 4) -> list:
    """Batch LLM completions via scillm, with /assistant gateway cascade."""
    # --- Gateway path: route each request through cascade ---
    if _gateway_available:
        results = []
        for i, req in enumerate(requests):
            try:
                content = ""
                msgs = req.get("messages", [])
                for m in msgs:
                    if m.get("role") == "user":
                        content = m.get("content", "")[:2000]
                        break
                gw_result = _gw_validate(
                    input_data={"turns": content, "session_id": f"batch_{i}"},
                    task="episodic-session-scorer",
                )
                if gw_result and gw_result.result:
                    results.append({"index": req.get("index", i), "ok": True, "content": json.dumps(gw_result.result)})
                    continue
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
            # Mark as needing direct path
            results.append({"index": req.get("index", i), "ok": False, "error": "gateway_skip", "_req": req})

        # Fall through to scillm for any that failed gateway
        needs_direct = [r for r in results if r.get("error") == "gateway_skip"]
        if not needs_direct:
            return results

    # --- Direct scillm path (fallback) ---
    from scillm import batch_acompletions_iter

    cfg = _get_llm_config()
    if not cfg["api_key"]:
        return [{"index": r.get("index", i), "ok": False, "error": "no api key"} for i, r in enumerate(requests)]

    results = []
    async for res in batch_acompletions_iter(
        requests,
        api_base=cfg["api_base"],
        api_key=cfg["api_key"],
        custom_llm_provider="openai",
        concurrency=concurrency,
        timeout=60,
        wall_time_s=300,
        response_format={"type": "json_object"},
        retry_invalid_json=1,
    ):
        results.append(res)
    return results


def _format_turns_for_llm(turns: list, max_chars: int = 12000) -> str:
    """Format turns for LLM analysis, truncating to stay within limits."""
    lines = []
    total = 0
    for t in turns:
        role = t.get("type", t.get("role", "unknown"))
        body = t.get("body", t.get("content", t.get("message", "")))
        if not body:
            continue
        line = f"[{role}] {body[:500]}"
        if total + len(line) > max_chars:
            lines.append(f"... ({len(turns) - len(lines)} more turns truncated)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


async def assess_session(turns: list, session_id: str) -> dict:
    """LLM-powered session assessment via scillm."""
    formatted = _format_turns_for_llm(turns)

    prompt = f"""You are a Session Analyst. Analyze this agent conversation transcript.

Return JSON:
{{
  "problems_addressed": ["list of problems the session tackled"],
  "solutions_found": ["list of verified solutions"],
  "unresolved": ["problems attempted but not solved"],
  "incompetent_handling": ["things done poorly or incorrectly"],
  "key_learnings": ["novel insights worth storing"],
  "quality_score": 0.0,
  "resolution_status": "resolved",
  "dogpile_candidates": ["specific technical gaps worth researching"]
}}

Rules:
- quality_score: 0.0-1.0 overall session quality
- resolution_status: "resolved" | "partial" | "unresolved" | "abandoned"
- Be honest about incompetent_handling - identify genuine failures
- dogpile_candidates: only include specific technical gaps that research would help with

Session ID: {session_id}
Transcript ({len(turns)} turns):
{formatted}"""

    try:
        raw = await _llm_completion(prompt, max_tokens=2048, json_mode=True)
        return json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        return {
            "problems_addressed": [],
            "solutions_found": [],
            "unresolved": [],
            "incompetent_handling": [],
            "key_learnings": [],
            "quality_score": 0.0,
            "resolution_status": "unknown",
            "dogpile_candidates": [],
            "_error": str(e),
        }


async def profile_user_from_session(turns: list, session_id: str, user_id: str = "unknown") -> dict:
    """Extract user behavioral profile from a session transcript via LLM.

    Returns a structured profile for incremental merge into user_priors.
    """
    formatted = _format_turns_for_llm(turns)

    prompt = f"""You are a User Behavior Analyst. Analyze this conversation to extract the user's behavioral profile.

Return JSON:
{{
  "communication_style": "technical|casual|formal|mixed",
  "expertise_domains": ["list of domains the user demonstrates knowledge in"],
  "expertise_level": "beginner|intermediate|advanced|expert",
  "response_preferences": {{
    "verbosity": "concise|balanced|detailed",
    "format": "code-first|explanation-first|mixed",
    "examples": true
  }},
  "frustration_triggers": ["patterns that frustrated the user"],
  "satisfaction_signals": ["patterns the user responded positively to"],
  "bridge_affinities": {{
    "Precision": 0.0,
    "Resilience": 0.0,
    "Fragility": 0.0,
    "Corruption": 0.0,
    "Loyalty": 0.0,
    "Stealth": 0.0
  }}
}}

Rules:
- communication_style: dominant style in this session
- expertise_domains: only include domains clearly demonstrated (not just mentioned)
- expertise_level: based on the depth and correctness of user's technical statements
- response_preferences: infer from how the user reacts to different response styles
- frustration_triggers: empty list if no frustration observed
- satisfaction_signals: empty list if no satisfaction observed
- bridge_affinities: 0.0-1.0 score for each Federated Taxonomy bridge based on session content focus
  - Precision: accuracy, correctness, formal verification
  - Resilience: recovery, robustness, self-healing
  - Fragility: vulnerability analysis, failure modes
  - Corruption: data integrity, trust, adversarial behavior
  - Loyalty: consistency, reliability, long-term patterns
  - Stealth: security, privacy, detection avoidance

User ID: {user_id}
Session ID: {session_id}
Transcript ({len(turns)} turns):
{formatted}"""

    try:
        raw = await _llm_completion(prompt, max_tokens=1024, json_mode=True)
        profile = json.loads(raw)
        # Ensure required fields exist
        profile.setdefault("communication_style", "mixed")
        profile.setdefault("expertise_domains", [])
        profile.setdefault("expertise_level", "intermediate")
        profile.setdefault("response_preferences", {
            "verbosity": "balanced", "format": "mixed", "examples": True
        })
        profile.setdefault("frustration_triggers", [])
        profile.setdefault("satisfaction_signals", [])
        profile.setdefault("bridge_affinities", {})
        return profile
    except (json.JSONDecodeError, Exception) as e:
        return {
            "communication_style": "mixed",
            "expertise_domains": [],
            "expertise_level": "intermediate",
            "response_preferences": {"verbosity": "balanced", "format": "mixed", "examples": True},
            "frustration_triggers": [],
            "satisfaction_signals": [],
            "bridge_affinities": {},
            "_error": str(e),
        }
