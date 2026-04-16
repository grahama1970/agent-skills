"""GeminiClient — Google Gemini API wrapper for ops-google skill."""
import json
import os
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

# Shared budget state file
USAGE_DIR = Path.home() / ".pi" / "ops-google"
USAGE_FILE = USAGE_DIR / "usage.json"
DEFAULT_MAX_DAILY = 5000


class GeminiClient:
    """Wrapper for Google Gemini API operations."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        self._genai = genai

    def list_models(self) -> list[dict]:
        """List available Gemini models with rate limits and capabilities."""
        models = []
        for m in self._genai.list_models():
            if "generateContent" not in (m.supported_generation_methods or []):
                continue
            models.append({
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description or "",
                "input_token_limit": m.input_token_limit,
                "output_token_limit": m.output_token_limit,
                "supported_methods": m.supported_generation_methods,
            })
        return models

    def model_health(self, model: str = "gemini-2.5-flash") -> dict:
        """Quick health check — send tiny prompt, measure latency."""
        try:
            gen_model = self._genai.GenerativeModel(model)
            start = time.monotonic()
            response = gen_model.generate_content(
                "Say OK",
                generation_config={"max_output_tokens": 5, "temperature": 0.1},
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            status = "OK" if elapsed_ms < 5000 else "SLOW"
            return {
                "status": status,
                "latency_ms": round(elapsed_ms),
                "model": model,
                "response": response.text[:50] if response.text else "",
            }
        except Exception as e:
            return {
                "status": "DOWN",
                "latency_ms": None,
                "model": model,
                "error": str(e),
            }

    def get_rate_limits(self, model: str = "gemini-2.5-flash") -> dict:
        """Get rate limit info for the model on current tier.

        Google doesn't expose per-key rate limits via API, so we return
        the documented Pro tier limits.
        """
        # Documented Google Pro tier limits (as of 2026-02)
        pro_limits = {
            "gemini-2.5-flash": {"rpm": 2000, "tpm": 4_000_000, "rpd": 10_000},
            "gemini-2.5-pro": {"rpm": 150, "tpm": 2_000_000, "rpd": 2_500},
            "gemini-2.0-flash": {"rpm": 2000, "tpm": 4_000_000, "rpd": 10_000},
            "gemini-2.0-flash-lite": {"rpm": 4000, "tpm": 4_000_000, "rpd": 14_400},
            "gemini-1.5-flash": {"rpm": 2000, "tpm": 4_000_000, "rpd": 10_000},
            "gemini-1.5-pro": {"rpm": 1000, "tpm": 4_000_000, "rpd": 10_000},
        }
        # Normalize model name (strip "models/" prefix if present)
        clean = model.replace("models/", "")
        limits = pro_limits.get(clean, {"rpm": "unknown", "tpm": "unknown", "rpd": "unknown"})
        return {"model": clean, "tier": "Google Pro", **limits}

    def get_budget_status(self) -> dict:
        """Read cross-process Gemini usage from shared state file."""
        return read_shared_usage()

    def sanity(self) -> dict:
        """Full health check: API key valid, model reachable, rate limits."""
        result = {"api_key": bool(self.api_key), "api_key_prefix": self.api_key[:8] + "..."}
        try:
            models = self.list_models()
            result["models_available"] = len(models)
            result["model_names"] = [m["name"] for m in models[:5]]
        except Exception as e:
            result["models_error"] = str(e)
            result["models_available"] = 0

        health = self.model_health()
        result["health"] = health

        budget = self.get_budget_status()
        result["budget"] = budget

        return result


# ---------------------------------------------------------------------------
# Shared cross-process budget tracking
# ---------------------------------------------------------------------------

def read_shared_usage() -> dict:
    """Read the shared usage counter. Returns default if file missing/corrupt."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    default = {"calls_today": 0, "date": today, "max_daily": DEFAULT_MAX_DAILY}

    if not USAGE_FILE.exists():
        return default

    try:
        with open(USAGE_FILE) as f:
            data = json.load(f)
        # Reset if date changed
        if data.get("date") != today:
            return default
        return data
    except (json.JSONDecodeError, OSError):
        return default


def increment_shared_usage() -> dict:
    """Atomically increment the shared Gemini call counter.

    Uses file locking (fcntl.flock) for cross-process safety.
    Returns the updated usage dict.
    """
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lock_path = USAGE_DIR / "usage.lock"

    try:
        with open(lock_path, "w") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                # Read current state
                if USAGE_FILE.exists():
                    with open(USAGE_FILE) as f:
                        data = json.load(f)
                    if data.get("date") != today:
                        data = {"calls_today": 0, "date": today,
                                "max_daily": data.get("max_daily", DEFAULT_MAX_DAILY)}
                else:
                    data = {"calls_today": 0, "date": today, "max_daily": DEFAULT_MAX_DAILY}

                data["calls_today"] += 1
                data["last_call"] = datetime.now(timezone.utc).isoformat()

                # Write atomically
                tmp = USAGE_FILE.with_suffix(".tmp")
                with open(tmp, "w") as f:
                    json.dump(data, f)
                tmp.rename(USAGE_FILE)

                return data
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except OSError as e:
        logger.warning("Failed to update shared Gemini usage: {}", e)
        return {"calls_today": -1, "date": today, "max_daily": DEFAULT_MAX_DAILY, "error": str(e)}


def update_max_daily(new_max: int) -> dict:
    """Update the max_daily limit in the shared state file."""
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = USAGE_DIR / "usage.lock"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            if USAGE_FILE.exists():
                with open(USAGE_FILE) as f:
                    data = json.load(f)
                if data.get("date") != today:
                    data = {"calls_today": 0, "date": today, "max_daily": new_max}
                else:
                    data["max_daily"] = new_max
            else:
                data = {"calls_today": 0, "date": today, "max_daily": new_max}

            tmp = USAGE_FILE.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(data, f)
            tmp.rename(USAGE_FILE)
            return data
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def shared_budget_ok() -> bool:
    """Check if the shared cross-process budget allows another call."""
    usage = read_shared_usage()
    max_daily = usage.get("max_daily", DEFAULT_MAX_DAILY)
    if max_daily <= 0:
        return False
    return usage.get("calls_today", 0) < max_daily
