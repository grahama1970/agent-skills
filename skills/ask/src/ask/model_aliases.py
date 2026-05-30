"""Provider-family shorthand resolution for human `$ask` prompts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx


PROVIDER_ALIASES = {
    "oc": "opencode",
    "opencode": "opencode",
    "opencode-go": "opencode",
    "chutes": "chutes",
}

OPENCODE_FAMILIES = {
    "deepseek": "deepseek",
    "ds": "deepseek",
    "glm": "glm",
    "kimi": "kimi",
    "mimo": "mimo",
    "mini": "mimo",
    "minimax": "minimax",
    "qwen": "qwen",
}

CHUTES_FAMILIES = {
    "deepseek": "deepseek",
    "ds": "deepseek",
    "kimi": "kimi",
    "qwen": "qwen",
    "text": "text",
    "default": "text",
}

DEFAULT_PROVIDER_BY_FAMILY = {
    "deepseek": "opencode",
    "glm": "opencode",
    "kimi": "opencode",
    "mimo": "opencode",
    "minimax": "opencode",
    "qwen": "opencode",
}

OPENCODE_FALLBACK_MODELS = {
    "deepseek": "opencode-go/deepseek-v4-pro",
    "glm": "opencode-go/glm-5.1",
    "kimi": "opencode-go/kimi-k2.6",
    "mimo": "opencode-go/mimo-v2.5-pro",
    "minimax": "opencode-go/minimax-m2.7",
    "qwen": "opencode-go/qwen3.6-plus",
}

OPENCODE_PREFERENCES = {
    "deepseek": [
        "opencode-go/deepseek-v4-pro",
        "opencode-go/deepseek-v4-flash",
    ],
    "glm": [
        "opencode-go/glm-5.1",
        "opencode-go/glm-5",
    ],
    "kimi": [
        "opencode-go/kimi-k2.6",
        "opencode-go/kimi-k2.5",
    ],
    "mimo": [
        "opencode-go/mimo-v2.5-pro",
        "opencode-go/mimo-v2.5",
        "opencode-go/mimo-v2-pro",
        "opencode-go/mimo-v2-omni",
    ],
    "minimax": [
        "opencode-go/minimax-m2.7",
        "opencode-go/minimax-m2.5",
    ],
    "qwen": [
        "opencode-go/qwen3.6-plus",
        "opencode-go/qwen3.5-plus",
    ],
}

CHUTES_MODELS = {
    "deepseek": "chutes-deepseek",
    "kimi": "chutes-kimi",
    "qwen": "chutes-qwen",
    "text": "text",
}


@dataclass(frozen=True)
class ModelAliasRoute:
    """Resolved shorthand model route from the leading chat tokens."""

    provider_hint: str
    family: str
    resolved_model: str
    question_parts: list[str]
    raw_alias: str
    source: str
    oracle_backend: str = "scillm"
    input_capabilities: dict[str, bool] | None = None
    warning: str | None = None

    @property
    def question(self) -> str:
        return " ".join(self.question_parts).strip()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ParsedAlias:
    provider_hint: str
    family: str
    raw_family: str
    question_parts: list[str]
    raw_alias: str
    exact_model: str | None = None


def resolve_model_alias_route(
    question_parts: list[str],
    *,
    scillm_base_url: str,
    scillm_api_key: str,
    timeout: float = 30.0,
    required_input: str | None = None,
) -> ModelAliasRoute | None:
    """Resolve leading provider-family shorthand, if present."""

    # WebGPT shorthand: `$ask webgpt ...` routes to --oracle-backend webgpt.
    # This is a browser-driven oracle backed by the human's signed-in ChatGPT
    # tab via surf; the tab id is auto-resolved (or supplied via --webgpt-tab-id).
    # Accept both unquoted ($ask webgpt foo bar) and quoted ($ask "webgpt foo bar")
    # forms by splitting the first arg on whitespace before checking the alias.
    if question_parts:
        first_arg = question_parts[0]
        first_tokens = first_arg.split()
        first_clean = _clean_token(first_tokens[0]).lower() if first_tokens else ""
        if first_clean in {"webgpt", "chatgpt"}:
            tail_of_first = " ".join(first_tokens[1:]).strip()
            remaining = ([tail_of_first] if tail_of_first else []) + list(question_parts[1:])
            if not remaining:
                raise ValueError(f"{first_tokens[0]} requires a question after the model shorthand.")
            return ModelAliasRoute(
                provider_hint="webgpt",
                family="webgpt",
                resolved_model="webgpt",
                question_parts=remaining,
                raw_alias=first_tokens[0],
                source="webgpt-controlled-tab",
                oracle_backend="webgpt",
                input_capabilities={"text": True, "image": False, "pdf": False},
            )
        if first_clean in {"cursor-browser", "cursorbrowser", "cursor"} and len(first_tokens) >= 2 and first_tokens[1].lower() in {"webgpt", "chatgpt", "browser"}:
            # $ask cursor-browser webgpt ...
            tail = " ".join(first_tokens[2:]).strip()
            remaining = ([tail] if tail else []) + list(question_parts[1:])
            if not remaining:
                raise ValueError(f"{first_tokens[0]} {first_tokens[1]} requires a question after the model shorthand.")
            return ModelAliasRoute(
                provider_hint="cursor-browser",
                family="cursor-browser",
                resolved_model="cursor-browser",
                question_parts=remaining,
                raw_alias=f"{first_tokens[0]}-{first_tokens[1]}",
                source="cursor-browser-view",
                oracle_backend="cursor-browser",
                input_capabilities={"text": True, "image": False, "pdf": False},
            )
        if first_clean in {"cursor-browser", "cursorbrowser"} or (first_clean == "cursor" and len(first_tokens) >= 2 and first_tokens[1].lower() == "browser"):
            tail_of_first = " ".join(first_tokens[1:]).strip()
            if first_clean == "cursor" and first_tokens[1].lower() == "browser":
                tail_of_first = " ".join(first_tokens[2:]).strip()
            remaining = ([tail_of_first] if tail_of_first else []) + list(question_parts[1:])
            if not remaining:
                raise ValueError(f"{first_tokens[0]} requires a question after the model shorthand.")
            return ModelAliasRoute(
                provider_hint="cursor-browser",
                family="cursor-browser",
                resolved_model="cursor-browser",
                question_parts=remaining,
                raw_alias=first_tokens[0],
                source="cursor-browser-view",
                oracle_backend="cursor-browser",
                input_capabilities={"text": True, "image": False, "pdf": False},
            )
        browser_oracle_aliases = {
            "webgemini": ("webgemini", "webgemini", "webgemini-controlled-tab"),
            "gemini": ("webgemini", "webgemini", "webgemini-controlled-tab"),
            "webkimi": ("webkimi", "webkimi", "webkimi-controlled-tab"),
            "webperplexity": ("webperplexity", "webperplexity", "webperplexity-one-shot-cdp"),
            "perplexity": ("webperplexity", "webperplexity", "webperplexity-one-shot-cdp"),
        }
        if first_clean in browser_oracle_aliases:
            family, backend, source = browser_oracle_aliases[first_clean]
            tail_of_first = " ".join(first_tokens[1:]).strip()
            remaining = ([tail_of_first] if tail_of_first else []) + list(question_parts[1:])
            if not remaining:
                raise ValueError(f"{first_tokens[0]} requires a question after the model shorthand.")
            return ModelAliasRoute(
                provider_hint=backend,
                family=family,
                resolved_model=backend,
                question_parts=remaining,
                raw_alias=first_tokens[0],
                source=source,
                oracle_backend=backend,
                input_capabilities={"text": True, "image": False, "pdf": False},
            )

    parsed = _parse_model_alias(question_parts)
    if not parsed:
        return None
    if not parsed.question_parts:
        raise ValueError(f"{parsed.raw_alias} requires a question after the model shorthand.")

    if parsed.provider_hint == "opencode":
        models: list[dict[str, Any]] = []
        warning = None
        try:
            models = fetch_opencode_go_models(scillm_base_url, scillm_api_key, timeout=timeout)
        except httpx.HTTPError as exc:
            warning = f"OpenCode Go discovery failed; used fallback map: {type(exc).__name__}"
        resolved_model = select_opencode_model(parsed.family, models, required_input=required_input)
        return ModelAliasRoute(
            provider_hint=parsed.provider_hint,
            family=parsed.family,
            resolved_model=resolved_model,
            question_parts=parsed.question_parts,
            raw_alias=parsed.raw_alias,
            source="live-opencode-go-models" if models else "static-opencode-go-fallback",
            input_capabilities=opencode_model_input_capabilities(resolved_model, models),
            warning=warning,
        )

    resolved_model = resolve_chutes_model(parsed.family, exact_model=parsed.exact_model)
    return ModelAliasRoute(
        provider_hint=parsed.provider_hint,
        family=parsed.family,
        resolved_model=resolved_model,
        question_parts=parsed.question_parts,
        raw_alias=parsed.raw_alias,
        source="chutes-configured-alias",
        input_capabilities={"text": True, "image": False, "pdf": False},
    )


def fetch_opencode_go_models(
    scillm_base_url: str,
    scillm_api_key: str,
    *,
    timeout: float = 3.0,
) -> list[dict[str, Any]]:
    """Fetch current OpenCode Go models exposed by scillm."""

    response = httpx.get(
        f"{scillm_base_url.rstrip('/')}/v1/scillm/opencode-go/models",
        headers={"Authorization": f"Bearer {scillm_api_key}", "X-Caller-Skill": "ask"},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    models = data.get("models", [])
    if not isinstance(models, list):
        return []
    return [model for model in models if isinstance(model, dict)]


def select_opencode_model(
    family: str,
    models: list[dict[str, Any]],
    *,
    required_input: str | None = None,
) -> str:
    """Pick the best currently supported OpenCode Go model for a family."""

    normalized = OPENCODE_FAMILIES.get(family.lower(), family.lower())
    preference = OPENCODE_PREFERENCES.get(normalized)
    if not preference:
        raise ValueError(f"Unknown OpenCode Go model family '{family}'.")

    available: set[str] = set()
    for model in models:
        model_id = str(model.get("id") or model.get("name") or "")
        if not model_id:
            continue
        if model.get("supported") is False:
            continue
        if model.get("key_configured") is False:
            continue
        if required_input and not model_supports_input(model, required_input):
            continue
        available.add(model_id)

    for model_id in preference:
        if model_id in available:
            return model_id
    if required_input:
        raise ValueError(f"No configured OpenCode Go {family} model supports {required_input} input.")
    return OPENCODE_FALLBACK_MODELS[normalized]


def model_supports_input(model: dict[str, Any], input_kind: str) -> bool:
    """Return whether model metadata reports support for an input kind."""
    input_capabilities = model.get("input")
    if not isinstance(input_capabilities, dict):
        return input_kind == "text"
    return bool(input_capabilities.get(input_kind))


def opencode_model_input_capabilities(model_id: str, models: list[dict[str, Any]]) -> dict[str, bool]:
    """Return input capability metadata for a selected OpenCode Go model."""
    for model in models:
        candidate_id = str(model.get("id") or model.get("name") or "")
        if candidate_id != model_id:
            continue
        input_capabilities = model.get("input")
        if isinstance(input_capabilities, dict):
            return {
                "text": bool(input_capabilities.get("text")),
                "image": bool(input_capabilities.get("image")),
                "pdf": bool(input_capabilities.get("pdf")),
            }
    if "/kimi-" in model_id:
        return {"text": True, "image": True, "pdf": False}
    return {"text": True, "image": False, "pdf": False}


def resolve_chutes_model(family: str, *, exact_model: str | None = None) -> str:
    """Resolve Chutes shorthand to the configured scillm alias or exact model."""

    if exact_model:
        return exact_model
    normalized = CHUTES_FAMILIES.get(family.lower(), family.lower())
    try:
        return CHUTES_MODELS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown Chutes model family '{family}'.") from exc


def _parse_model_alias(question_parts: list[str]) -> _ParsedAlias | None:
    if not question_parts:
        return None

    first = _clean_token(question_parts[0])
    first_lower = first.lower()
    if "-" in first_lower:
        provider_token, family_token = first_lower.split("-", 1)
        provider = PROVIDER_ALIASES.get(provider_token)
        if provider:
            parsed = _family_for_provider(provider, family_token)
            if parsed:
                family, exact_model = parsed
                return _ParsedAlias(
                    provider_hint=provider,
                    family=family,
                    raw_family=family_token,
                    question_parts=question_parts[1:],
                    raw_alias=question_parts[0],
                    exact_model=exact_model,
                )

    provider = PROVIDER_ALIASES.get(first_lower)
    if provider and len(question_parts) >= 2:
        second = _clean_token(question_parts[1])
        parsed = _family_for_provider(provider, second)
        if parsed:
            family, exact_model = parsed
            return _ParsedAlias(
                provider_hint=provider,
                family=family,
                raw_family=second,
                question_parts=question_parts[2:],
                raw_alias=f"{question_parts[0]} {question_parts[1]}",
                exact_model=exact_model,
            )

    bare_family = OPENCODE_FAMILIES.get(first_lower)
    if bare_family and bare_family in DEFAULT_PROVIDER_BY_FAMILY:
        return _ParsedAlias(
            provider_hint=DEFAULT_PROVIDER_BY_FAMILY[bare_family],
            family=bare_family,
            raw_family=first,
            question_parts=question_parts[1:],
            raw_alias=question_parts[0],
        )
    return None


def _family_for_provider(provider: str, raw_family: str) -> tuple[str, str | None] | None:
    clean_family = _clean_token(raw_family)
    family_lower = clean_family.lower()
    if provider == "opencode":
        family = OPENCODE_FAMILIES.get(family_lower)
        return (family, None) if family else None
    if "/" in clean_family:
        family = clean_family.rsplit("/", 1)[-1].split("-", 1)[0].lower()
        return family, clean_family
    family = CHUTES_FAMILIES.get(family_lower)
    return (family, None) if family else None


def _clean_token(value: str) -> str:
    return value.strip().strip("`'\"")
