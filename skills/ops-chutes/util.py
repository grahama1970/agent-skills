"""util - ops-chutes.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import httpx
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from loguru import logger

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

INFERENCE_API_BASE = "https://llm.chutes.ai"
MANAGEMENT_API_BASE = "https://api.chutes.ai"

class ChutesClient:
    def __init__(self, token: Optional[str] = None):
        # Support both naming conventions for robustness
        self.token = token or os.environ.get("CHUTES_API_TOKEN") or os.environ.get("CHUTES_API_KEY")
        if not self.token:
            raise ValueError("CHUTES_API_TOKEN or CHUTES_API_KEY not found in environment")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OpsChutes/1.0"
        }
        self.timeout = 30.0

    def get_quota(self, chute_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get quota usage for a specific chute or global usage if chute_id is None.
        Endpoint: GET /users/me/quota_usage/{chute_id|me}
        """
        target = chute_id if chute_id else "me"
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/users/me/quota_usage/{target}")
                resp.raise_for_status()
                data = resp.json()
                
                # Strict Validation
                if "used" not in data or "quota" not in data:
                    raise RuntimeError(f"API response missing 'used' or 'quota' fields for {target}: {data}")
                
                return data
            except httpx.HTTPStatusError as e:
                msg = f"Quota check failed for {target}: {e.response.status_code} {e.response.text}"
                raise RuntimeError(msg)
            except Exception as e:
                raise RuntimeError(f"Error fetching quota for {target}: {e}")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user info, including balance.
        Strictly validates the presence of 'balance'.
        """
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/users/me")
                resp.raise_for_status()
                data = resp.json()
                
                if "balance" not in data:
                    raise RuntimeError(f"API response missing 'balance' field: {data}")
                
                return data
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"User info failed: {e.response.status_code} {e.response.text}")
            except Exception as e:
                raise RuntimeError(f"Error fetching user info: {e}")

    def list_chutes(self) -> List[Dict[str, Any]]:
        """
        List all accessible chutes.
        No longer silently swallows auth errors.
        """
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/chutes")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Failed to list chutes: {e.response.status_code} {e.response.text}")
            except Exception as e:
                raise RuntimeError(f"Error listing chutes: {e}")

    def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models via the Inference API.
        """
        with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/v1/models")
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
            except Exception as e:
                raise RuntimeError(f"Failed to list models: {e}")

    def get_model_status(self, model_id: str) -> str:
        """
        Determine if a model is HOT, COLD, or DOWN.
        - HOT: Responding to inference /ping
        - COLD: Present in /v1/models but maybe not responding yet (or management status != running)
        - DOWN: Not responding and/or not in list
        """
        # 1. Check Inference ping for HOT status
        if self.check_sanity(model=model_id):
            return "HOT"

        # 2. Check model list for existence (COLD)
        try:
            models = self.list_models()
            if any(m.get("id") == model_id for m in models):
                return "COLD"
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

        return "DOWN"
    
    def check_sanity(self, model: str = "Qwen/Qwen2.5-72B-Instruct") -> bool:
        """Run a real inference check."""
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
                "max_tokens": 5,
                "temperature": 0.1
            }
            with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
                resp = client.post("/v1/chat/completions", json=payload)
                return resp.status_code == 200
        except Exception:
            return False

    def get_day_reset_time(self) -> datetime:
        """Get the NEXT 7PM ET reset time (UTC-aware)."""
        eastern = ZoneInfo("America/New_York")
        now_est = datetime.now(tz=eastern)
        reset_target = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        if now_est >= reset_target:
            reset_target = reset_target + timedelta(days=1)
        return reset_target.astimezone(timezone.utc)

    def list_inference_models(self) -> list:
        """List all models via the Inference API with TEE/pricing metadata."""
        with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/v1/models")
                resp.raise_for_status()
                return resp.json().get("data", [])
            except Exception as e:
                raise RuntimeError(f"Failed to list inference models: {e}")

    def get_chute_details(self, chute_id: str) -> Dict[str, Any]:
        """Get full details for a specific chute (public or owned)."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get(f"/chutes/{chute_id}")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Failed to get chute {chute_id}: {e.response.status_code}")
            except Exception as e:
                raise RuntimeError(f"Error fetching chute {chute_id}: {e}")

    def timed_ping(self, model: str, max_tokens: int = 5) -> Optional[float]:
        """
        Send a minimal inference request and return response time in seconds.
        Returns None if the request fails.
        """
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Say OK"}],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        try:
            with httpx.Client(base_url=INFERENCE_API_BASE, headers=self.headers, timeout=60.0) as client:
                start = time.monotonic()
                resp = client.post("/v1/chat/completions", json=payload)
                elapsed = time.monotonic() - start
                if resp.status_code == 200:
                    return elapsed
                return None
        except Exception:
            return None

    def find_family(self, model_id: str, all_models: Optional[list] = None) -> List[Dict[str, Any]]:
        """
        Find all models in the same family as model_id.
        Returns list of models sorted by name, including the input model.
        E.g. for 'deepseek-ai/DeepSeek-V3.1-TEE' returns all DeepSeek-V3* variants.
        """
        import re

        if all_models is None:
            all_models = self.list_inference_models()

        org = model_id.split('/')[0]
        # Strip TEE suffix and version qualifiers to get core family
        base = re.sub(r'-TEE$', '', model_id)
        base_name = base.split('/')[-1]
        # Strip version suffixes: .1, .2, -0528, -Speciale, -Terminus, -FP8, -Instruct-2507
        core = re.sub(r'[-.](\d+|Speciale|Terminus|FP8|Instruct|Thinking)(-\d{4})?$', '', base_name)
        # Further strip if still has minor version
        core = re.sub(r'\.\d+$', '', core)
        # core should now be like "DeepSeek-V3" or "DeepSeek-R1" or "Qwen3-235B-A22B"

        family = []
        for m in all_models:
            if not m["id"].startswith(org + '/'):
                continue
            m_name = m["id"].split('/')[-1]
            m_stripped = re.sub(r'-TEE$', '', m_name)
            m_core = re.sub(r'[-.](\d+|Speciale|Terminus|FP8|Instruct|Thinking)(-\d{4})?$', '', m_stripped)
            m_core = re.sub(r'\.\d+$', '', m_core)
            if m_core == core:
                family.append(m)

        family.sort(key=lambda m: m["id"])
        return family

    def find_non_tee_variant(self, tee_model_id: str, all_models: Optional[list] = None) -> Optional[Dict[str, Any]]:
        """
        Given a TEE model ID (e.g. 'deepseek-ai/DeepSeek-V3.1-TEE'),
        find the best non-TEE alternative from the same org/family.
        """
        import re

        if all_models is None:
            all_models = self.list_inference_models()

        # Strip -TEE suffix to get the base name
        base = re.sub(r'-TEE$', '', tee_model_id)
        org = tee_model_id.split('/')[0]

        # Exact match (base name without -TEE)
        for m in all_models:
            if m["id"] == base and not m.get("confidential_compute"):
                return m

        # Progressive stripping: try removing version suffixes
        # e.g. DeepSeek-V3.1 -> DeepSeek-V3, DeepSeek-R1-0528 -> DeepSeek-R1
        strip_patterns = [
            r'-\d{4}$',           # date suffixes: -0528, -0324, -2507
            r'\.\d+$',            # minor versions: .1, .2
            r'-Terminus$',        # variant names
            r'-Speciale$',
            r'-FP8$',
            r'-Instruct(-\d{4})?$',
        ]
        candidate_bases = [base]
        current = base
        for pat in strip_patterns:
            stripped = re.sub(pat, '', current)
            if stripped != current:
                candidate_bases.append(stripped)
                current = stripped

        for cb in candidate_bases:
            for m in all_models:
                if m["id"] == cb and not m.get("confidential_compute"):
                    return m

        # Family match: same org, core model name prefix, non-TEE
        # Extract core family: "deepseek-ai/DeepSeek-V3.1-TEE" -> "deepseek-v3"
        base_name = base.split('/')[-1].lower()
        # Normalize: remove dots, keep first meaningful segments
        core = re.sub(r'[.\d]+-?', lambda x: x.group().replace('.', '-'), base_name)
        core_parts = re.split(r'[-_]', core)
        # Use first 2 significant parts as family
        family_key = '-'.join(p for p in core_parts[:2] if p)

        candidates = []
        for m in all_models:
            if m.get("confidential_compute"):
                continue
            if not m["id"].startswith(org + '/'):
                continue
            m_name = m["id"].split('/')[-1].lower()
            m_core = re.sub(r'[.\d]+-?', lambda x: x.group().replace('.', '-'), m_name)
            m_parts = re.split(r'[-_]', m_core)
            m_family = '-'.join(p for p in m_parts[:2] if p)
            if m_family == family_key:
                candidates.append(m)

        if candidates:
            # Prefer the one with shortest name (simplest variant)
            candidates.sort(key=lambda m: len(m["id"]))
            return candidates[0]

        return None

    def get_usage_history(self, limit: int = 100) -> list:
        """
        Fetch hourly usage history from /users/me/usage, paginated.
        Returns list of hourly buckets: {bucket, amount, count, input_tokens, output_tokens}.
        """
        all_items: list = []
        page = 0
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            while True:
                try:
                    resp = client.get(f"/users/me/usage?page={page}&limit={limit}")
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("items", [])
                    if not items:
                        break
                    all_items.extend(items)
                    total = data.get("total", 0)
                    if len(all_items) >= total:
                        break
                    page += 1
                except httpx.HTTPStatusError as e:
                    raise RuntimeError(f"Usage history failed: {e.response.status_code} {e.response.text}")
                except Exception as e:
                    raise RuntimeError(f"Error fetching usage history: {e}")
        return all_items

    def get_gpu_pricing(self) -> Dict[str, Any]:
        """Fetch GPU pricing from /pricing endpoint."""
        with httpx.Client(base_url=MANAGEMENT_API_BASE, headers=self.headers, timeout=self.timeout) as client:
            try:
                resp = client.get("/pricing")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                raise RuntimeError(f"Failed to fetch pricing: {e}")

    def close(self):
        return
