"""
Live provider integrations for pricing data.

Handles live API calls to Chutes, OpenRouter, and RunPod,
plus the main get_batch_cost_comparison() entry point.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

import httpx

from pricing_models import (
    BatchProviderPricing,
    ProviderPricing,
    PRICING_CACHE,
    CHUTES_AVAILABLE,
    ChutesClient,
    RUNPOD_AVAILABLE,
    RunPodCalculator,
)
from pricing_core import (
    find_cheapest_provider,
    estimate_batch_cost,
    format_cost_table,
    parse_pricing_from_dogpile,
    load_cached_pricing,
    save_cached_pricing,
)
from loguru import logger


async def fetch_openrouter_pricing(model_id: str) -> Optional[ProviderPricing]:
    """
    Fetch live pricing from OpenRouter API.

    Args:
        model_id: OpenRouter model ID (e.g., "deepseek/deepseek-v3.2")

    Returns:
        ProviderPricing or None if not found
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://openrouter.ai/api/v1/models/{model_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code != 200:
                return None

            data = response.json()
            pricing = data.get("pricing", {})

            return ProviderPricing(
                provider="openrouter",
                model_id=model_id,
                input_price_per_m=float(pricing.get("prompt", 0)) * 1_000_000,
                output_price_per_m=float(pricing.get("completion", 0)) * 1_000_000,
                context_window=data.get("context_length", 128000),
                notes="Live pricing from OpenRouter API",
            )
    except Exception:
        return None


async def fetch_chutes_pricing(model_id: str) -> Optional[ProviderPricing]:
    """
    Fetch live pricing from Chutes API (via ops-chutes).

    Args:
        model_id: Chutes model ID (e.g., "deepseek-ai/DeepSeek-V3.2-TEE")

    Returns:
        ProviderPricing or None if not found
    """
    api_key = os.environ.get("CHUTES_API_KEY", "")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.chutes.ai/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code != 200:
                return None

            models = response.json()
            for model in models:
                if model.get("id") == model_id:
                    pricing = model.get("pricing", {})
                    return ProviderPricing(
                        provider="chutes",
                        model_id=model_id,
                        input_price_per_m=float(pricing.get("prompt", 0)),
                        output_price_per_m=float(pricing.get("completion", 0)),
                        rate_limit_rps=6,  # Chutes limit
                        notes="Live pricing from Chutes API",
                    )
    except Exception:
        return None

    return None


def fetch_live_chutes_pricing(model_pattern: str = "") -> list[dict]:
    """
    Fetch live pricing from Chutes via /ops-chutes skill.

    Returns list of pricing dicts for matching models.
    """
    if not CHUTES_AVAILABLE:
        return []

    try:
        client = ChutesClient()
        models = client.list_models()

        results = []
        for m in models:
            model_id = m.get("id", "")
            if model_pattern.lower() in model_id.lower():
                pricing = m.get("pricing", {})
                input_price = float(pricing.get("prompt", 0))
                output_price = float(pricing.get("completion", 0))

                results.append({
                    "provider": "chutes",
                    "model_id": model_id,
                    "input_price_per_m": input_price,
                    "output_price_per_m": output_price,
                    "concurrent_connections": 6,
                    "tokens_per_sec": 180.0,
                    "source": "live_api",
                    "notes": "Live from Chutes API",
                })

        return results
    except Exception:
        return []


def get_chutes_quota() -> dict:
    """Get current Chutes quota usage via /ops-chutes skill."""
    if not CHUTES_AVAILABLE:
        return {"available": False, "reason": "ChutesClient not available"}

    try:
        client = ChutesClient()
        quota_data = client.get_quota()

        used = quota_data.get("used", 0)
        quota = quota_data.get("quota", 0)
        remaining = quota - used if quota > 0 else 0
        pct_used = (used / quota * 100) if quota > 0 else 0

        return {
            "available": True,
            "used": used,
            "quota": quota,
            "remaining": remaining,
            "pct_used": round(pct_used, 1),
            "can_run_batch": remaining > 0,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_chutes_model_status(model_id: str) -> str:
    """Check model status via /ops-chutes skill."""
    if not CHUTES_AVAILABLE:
        return "UNKNOWN"
    try:
        client = ChutesClient()
        return client.get_model_status(model_id)
    except Exception:
        return "UNKNOWN"


def get_chutes_balance() -> dict:
    """Get current Chutes account balance via /ops-chutes skill."""
    if not CHUTES_AVAILABLE:
        return {"available": False, "reason": "ChutesClient not available"}
    try:
        client = ChutesClient()
        user_info = client.get_user_info()
        return {"available": True, "balance": user_info.get("balance", 0)}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_runpod_cost_estimates(
    model_size: str,
    total_tokens: int,
    limit: int = 3,
) -> list[dict]:
    """Get RunPod cost estimates via /ops-runpod skill."""
    if not RUNPOD_AVAILABLE:
        hours = total_tokens / 150.0 / 3600
        return [{
            "provider": "runpod",
            "model_id": "self-hosted-8xA100",
            "total_cost": round(hours * 15.0, 2),
            "estimated_hours": round(hours, 2),
            "hourly_rate": 15.0,
            "tokens_per_sec": 150,
            "input_price_per_m": 0,
            "output_price_per_m": 0,
            "source": "static_estimate",
            "notes": "Static estimate (~$15/hr 8x A100)",
        }]

    try:
        calc = RunPodCalculator()
        comparison = calc.compare_providers(model_size, total_tokens, include_local=False)

        results = []
        for key, info in list(comparison.items())[:limit]:
            if info.get("provider") != "runpod":
                continue
            processing_seconds = info.get("processing_time_seconds", 0)
            processing_hours = info.get("processing_time_hours", 0)
            results.append({
                "provider": "runpod",
                "model_id": info.get("instance_type", key),
                "total_cost": info.get("total_cost", 0),
                "estimated_hours": processing_hours,
                "hourly_rate": info.get("total_cost", 0) / max(processing_hours, 0.01),
                "tokens_per_sec": total_tokens / max(processing_seconds, 1),
                "input_price_per_m": 0,
                "output_price_per_m": 0,
                "source": "ops_runpod",
                "notes": f"RunPod {info.get('instance_type', '')}",
            })

        return results if results else get_runpod_cost_estimates.__wrapped__(model_size, total_tokens, limit)
    except Exception as e:
        hours = total_tokens / 150.0 / 3600
        return [{
            "provider": "runpod",
            "model_id": "self-hosted-8xA100",
            "total_cost": round(hours * 15.0, 2),
            "estimated_hours": round(hours, 2),
            "hourly_rate": 15.0,
            "tokens_per_sec": 150,
            "input_price_per_m": 0,
            "output_price_per_m": 0,
            "source": "static_fallback",
            "notes": f"Fallback: {e}",
        }]


def get_runpod_cost_estimate(model_size: str, total_tokens: int) -> dict:
    """Get cheapest RunPod cost estimate."""
    estimates = get_runpod_cost_estimates(model_size, total_tokens, limit=1)
    return estimates[0] if estimates else {"provider": "runpod", "error": "No estimates available"}


async def research_pricing_with_dogpile(
    model_name: str,
    batch_tokens: int = 90_000_000,
    refresh: bool = False,
) -> list[dict]:
    """Use /dogpile skill to research current pricing for a model."""
    if not refresh:
        cached = load_cached_pricing()
        if model_name.lower() in [k.lower() for k in cached.keys()]:
            return cached.get(model_name, [])

    query = f"{model_name} API pricing 2026 per million tokens Chutes OpenRouter DeepSeek"

    dogpile_path = Path.home() / ".claude/skills/dogpile/run.sh"
    if not dogpile_path.exists():
        dogpile_path = Path(__file__).resolve().parent.parent / "dogpile" / "run.sh"

    if not dogpile_path.exists():
        return find_cheapest_provider(model_name, batch_tokens // 2, batch_tokens // 2)

    try:
        result = subprocess.run(
            [str(dogpile_path), "search", query, "--no-tui"],
            capture_output=True, text=True, timeout=120, cwd=dogpile_path.parent,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0:
            parsed = parse_pricing_from_dogpile(result.stdout)
            if parsed:
                estimates = []
                for p in parsed:
                    if p.get("input_price_per_m") and p.get("output_price_per_m"):
                        input_tokens = batch_tokens // 2
                        output_tokens = batch_tokens // 2
                        input_cost = (input_tokens / 1_000_000) * p["input_price_per_m"]
                        output_cost = (output_tokens / 1_000_000) * p["output_price_per_m"]
                        estimates.append({
                            "provider": p["provider"],
                            "model_id": model_name,
                            "input_price_per_m": p["input_price_per_m"],
                            "output_price_per_m": p["output_price_per_m"],
                            "input_cost": round(input_cost, 2),
                            "output_cost": round(output_cost, 2),
                            "total_cost": round(input_cost + output_cost, 2),
                            "source": "dogpile",
                            "notes": p.get("raw_line", ""),
                        })

                cached = load_cached_pricing()
                cached[model_name] = estimates
                save_cached_pricing(cached)

                estimates.sort(key=lambda x: x["total_cost"])
                return estimates
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    return find_cheapest_provider(model_name, batch_tokens // 2, batch_tokens // 2)


async def find_cheapest_for_model(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    use_dogpile: bool = False,
) -> dict:
    """Find the cheapest provider for a specific model."""
    total_tokens = input_tokens + output_tokens

    if use_dogpile:
        estimates = await research_pricing_with_dogpile(model_name, total_tokens)
    else:
        estimates = find_cheapest_provider(model_name, input_tokens, output_tokens)

    if not estimates:
        return {"found": False, "error": f"No pricing found for model: {model_name}"}

    cheapest = estimates[0]
    return {
        "found": True,
        "cheapest": cheapest,
        "all_providers": estimates,
        "table": format_cost_table(estimates),
        "savings_vs_second": (
            round(estimates[1]["total_cost"] - cheapest["total_cost"], 2)
            if len(estimates) > 1 else 0
        ),
    }


async def get_batch_cost_comparison(
    model_pattern: str,
    num_requests: int,
    avg_input_tokens: int,
    avg_output_tokens: int,
    model_size: str = "180B",
    include_runpod: bool = True,
    use_live_pricing: bool = True,
    check_quota: bool = True,
    check_model_status: bool = False,
) -> dict:
    """
    Get comprehensive batch cost comparison across all providers.

    This is the main entry point for prompt-lab's --with-cost feature.
    """
    input_tokens = num_requests * avg_input_tokens
    output_tokens = num_requests * avg_output_tokens
    total_tokens = input_tokens + output_tokens

    estimates = []
    quota_info = None
    model_status_info = {}

    if check_quota and CHUTES_AVAILABLE:
        quota_info = get_chutes_quota()

    if use_live_pricing:
        chutes_pricing = fetch_live_chutes_pricing(model_pattern)
        for p in chutes_pricing:
            input_cost = (input_tokens / 1_000_000) * p["input_price_per_m"]
            output_cost = (output_tokens / 1_000_000) * p["output_price_per_m"]
            concurrent = p.get("concurrent_connections", 6)
            effective_throughput = p["tokens_per_sec"] * concurrent
            time_hours = output_tokens / effective_throughput / 3600

            if check_model_status:
                status = get_chutes_model_status(p["model_id"])
                model_status_info[p["model_id"]] = status

            estimates.append({
                "provider": "chutes",
                "model_id": p["model_id"],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_price_per_m": p["input_price_per_m"],
                "output_price_per_m": p["output_price_per_m"],
                "input_cost": round(input_cost, 2),
                "output_cost": round(output_cost, 2),
                "total_cost": round(input_cost + output_cost, 2),
                "estimated_hours": round(time_hours, 2),
                "concurrent_connections": concurrent,
                "tokens_per_sec_total": round(effective_throughput, 0),
                "source": p["source"],
                "notes": f"{p['notes']} ({concurrent} conn)",
                "model_status": model_status_info.get(p["model_id"]) if check_model_status else None,
            })

    if not estimates:
        static_estimates = find_cheapest_provider(model_pattern, input_tokens, output_tokens)
        estimates.extend(static_estimates)

    if include_runpod:
        runpod_estimates = get_runpod_cost_estimates(model_size, total_tokens, limit=2)
        for runpod_est in runpod_estimates:
            if "error" not in runpod_est:
                runpod_est["input_tokens"] = input_tokens
                runpod_est["output_tokens"] = output_tokens
                runpod_est["input_cost"] = 0
                runpod_est["output_cost"] = 0
                estimates.append(runpod_est)

    estimates.sort(key=lambda x: x.get("total_cost", float("inf")))

    if not estimates:
        return {
            "found": False,
            "error": f"No pricing found for model pattern: {model_pattern}",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    cheapest = estimates[0]

    table_lines = [
        f"Batch: {num_requests:,} requests x ({avg_input_tokens} in + {avg_output_tokens} out) = {total_tokens:,} tokens",
        f"       ({input_tokens:,} input + {output_tokens:,} output)",
        "",
        "Provider         | Model                      | In $/M  | Out $/M | Total    | Time   | Notes",
        "-----------------|----------------------------|---------|---------|----------|--------|------",
    ]

    for e in estimates:
        provider = e["provider"][:15].ljust(15)
        model = e.get("model_id", "")[:26].ljust(26)
        in_price = f"${e.get('input_price_per_m', 0):.2f}".rjust(7)
        out_price = f"${e.get('output_price_per_m', 0):.2f}".rjust(7)
        cost = f"${e['total_cost']:.2f}".rjust(8)
        time_str = f"{e.get('estimated_hours', 0):.1f}h".rjust(6)
        notes = (e.get("notes", "") or "")[:25]
        table_lines.append(f"{provider} | {model} | {in_price} | {out_price} | {cost} | {time_str} | {notes}")

    result = {
        "found": True,
        "num_requests": num_requests,
        "avg_input_tokens": avg_input_tokens,
        "avg_output_tokens": avg_output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimates": estimates,
        "cheapest": cheapest,
        "table": "\n".join(table_lines),
        "savings_vs_second": (
            round(estimates[1]["total_cost"] - cheapest["total_cost"], 2)
            if len(estimates) > 1 else 0
        ),
    }

    if quota_info:
        result["quota"] = quota_info
        if quota_info.get("available") and quota_info.get("pct_used", 0) > 80:
            result["quota_warning"] = f"Chutes quota {quota_info['pct_used']:.1f}% used"

    if model_status_info:
        result["model_status"] = model_status_info
        cheapest_model = cheapest.get("model_id", "")
        if cheapest_model in model_status_info and model_status_info[cheapest_model] != "HOT":
            result["model_warning"] = f"Cheapest model {cheapest_model} is {model_status_info[cheapest_model]}"

    return result
