#!/usr/bin/env python3
"""3-Tier Inference Router for task-specific GPTs.

Tier 0: Heuristic (regex, JSON schema, deterministic rules)  → microseconds, free
Tier 1: Small GPT (GGUF via llama-cpp / HF transformers)     → ~200ms, free
Tier 2: SciLLM (scillm quick_completion via Chutes)          → ~2-5s, ~$0.12/1K

Usage:
    python router.py route '{"question": "test?"}' --task qra-assessor
    python router.py batch --task qra-assessor --input items.jsonl
    python router.py metrics --task qra-assessor
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec

app = typer.Typer(add_completion=False)


@dataclass
class TierResult:
    """Result from a single tier of the routing cascade."""
    tier: int               # 0, 1, or 2
    source: str             # "heuristic", "local_gpt", "scillm"
    result: Any
    confidence: float
    latency_ms: float
    cached: bool = False


@dataclass
class RouterConfig:
    """Configuration for the inference router."""
    task_name: str
    confidence_threshold: float = 0.85
    enable_cache: bool = True
    cache_ttl_hours: int = 24
    tier0_fn: Optional[Callable] = None     # Custom heuristic
    model_path: Optional[Path] = None
    scillm_timeout: int = 30
    scope: Optional[str] = None             # Persona memory scope for context injection
    scope_context: Optional[str] = None     # Pre-fetched memory context (system prompt prefix)


class RouterMetrics:
    """Accumulated metrics for router performance."""

    def __init__(self):
        self.tier_counts: Counter = Counter()
        self.total_latency_ms: float = 0.0
        self.total_requests: int = 0
        self.cache_hits: int = 0
        self.confidence_bins: List[int] = [0] * 10  # 10 bins: [0.0-0.1, 0.1-0.2, ...]

    def record(self, result: TierResult) -> None:
        """Record a routing result."""
        self.tier_counts[result.tier] += 1
        self.total_latency_ms += result.latency_ms
        self.total_requests += 1
        if result.cached:
            self.cache_hits += 1
        bin_idx = min(9, int(result.confidence * 10))
        self.confidence_bins[bin_idx] += 1

    @property
    def escalation_rate(self) -> float:
        """Fraction of requests that went to tier 2."""
        if self.total_requests == 0:
            return 0.0
        return self.tier_counts[2] / self.total_requests

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of requests served from cache."""
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests

    def summary(self) -> dict:
        """JSON-serializable summary."""
        return {
            "total_requests": self.total_requests,
            "tier_counts": dict(self.tier_counts),
            "avg_latency_ms": (
                self.total_latency_ms / self.total_requests
                if self.total_requests > 0 else 0.0
            ),
            "escalation_rate": round(self.escalation_rate, 4),
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "confidence_histogram": self.confidence_bins,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def persist(self, path: Path) -> None:
        """Persist metrics summary to JSON file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w") as f:
                json.dump(self.summary(), f, indent=2)
            logger.info(f"Metrics persisted to {path}")
        except Exception as e:
            logger.warning(f"Failed to persist metrics: {e}")


class Router:
    """3-tier inference router with caching and metrics."""

    def __init__(self, config: RouterConfig):
        self.config = config
        self._cache: Dict[str, TierResult] = {}
        self._cache_expiry: Dict[str, float] = {}
        self._metrics = RouterMetrics()
        self._spec = None

    @property
    def spec(self):
        if self._spec is None:
            self._spec = load_task_spec(self.config.task_name)
        return self._spec

    @property
    def metrics(self) -> RouterMetrics:
        return self._metrics

    def route(self, input_data: dict) -> TierResult:
        """Route single input through tier cascade."""
        start = time.time()

        # 1. Check cache (with TTL enforcement)
        if self.config.enable_cache:
            cache_key = self._cache_key(input_data)
            if cache_key in self._cache:
                exp = self._cache_expiry.get(cache_key)
                if exp is not None and time.time() > exp:
                    self._cache.pop(cache_key, None)
                    self._cache_expiry.pop(cache_key, None)
                else:
                    cached = self._cache[cache_key]
                    result = TierResult(
                        tier=cached.tier,
                        source=cached.source,
                        result=cached.result,
                        confidence=cached.confidence,
                        latency_ms=(time.time() - start) * 1000,
                        cached=True,
                    )
                    self._metrics.record(result)
                    return result

        # 2. Try tier 0 (heuristic)
        tier0_result = self._tier0(input_data)
        if tier0_result is not None:
            tier0_result.latency_ms = (time.time() - start) * 1000
            self._store_cache(input_data, tier0_result)
            self._metrics.record(tier0_result)
            return tier0_result

        # 3. Try tier 1 (local GPT)
        tier1_result = self._tier1(input_data)
        if tier1_result.confidence >= self.config.confidence_threshold:
            tier1_result.latency_ms = (time.time() - start) * 1000
            self._store_cache(input_data, tier1_result)
            self._metrics.record(tier1_result)
            return tier1_result

        # 4. Escalate to tier 2 (scillm)
        logger.debug(
            f"Confidence {tier1_result.confidence:.3f} < "
            f"{self.config.confidence_threshold:.3f}, escalating to scillm"
        )
        try:
            tier2_result = self._tier2(input_data)
            tier2_result.latency_ms = (time.time() - start) * 1000
            self._store_cache(input_data, tier2_result)
            self._metrics.record(tier2_result)
            return tier2_result
        except Exception as e:
            logger.debug(f"scillm escalation failed: {e}, returning tier 1 result")
            tier1_result.latency_ms = (time.time() - start) * 1000
            self._metrics.record(tier1_result)
            return tier1_result

    def route_batch(self, inputs: list[dict]) -> list[TierResult]:
        """Batch routing — minimize API calls by grouping tier-2 escalations."""
        results: list[Optional[TierResult]] = [None] * len(inputs)
        needs_tier2: list[tuple[int, dict]] = []

        # Route all through tier 0 + tier 1
        for i, inp in enumerate(inputs):
            start = time.time()

            # Check cache
            if self.config.enable_cache:
                cache_key = self._cache_key(inp)
                if cache_key in self._cache:
                    cached = self._cache[cache_key]
                    results[i] = TierResult(
                        tier=cached.tier, source=cached.source,
                        result=cached.result, confidence=cached.confidence,
                        latency_ms=(time.time() - start) * 1000, cached=True,
                    )
                    self._metrics.record(results[i])
                    continue

            # Tier 0
            tier0_result = self._tier0(inp)
            if tier0_result is not None:
                tier0_result.latency_ms = (time.time() - start) * 1000
                self._store_cache(inp, tier0_result)
                self._metrics.record(tier0_result)
                results[i] = tier0_result
                continue

            # Tier 1
            tier1_result = self._tier1(inp)
            if tier1_result.confidence >= self.config.confidence_threshold:
                tier1_result.latency_ms = (time.time() - start) * 1000
                self._store_cache(inp, tier1_result)
                self._metrics.record(tier1_result)
                results[i] = tier1_result
            else:
                needs_tier2.append((i, inp))
                results[i] = tier1_result  # Placeholder

        # Batch-escalate to tier 2
        if needs_tier2:
            logger.info(f"Escalating {len(needs_tier2)}/{len(inputs)} items to scillm")
            for idx, inp in needs_tier2:
                start = time.time()
                try:
                    tier2_result = self._tier2(inp)
                    tier2_result.latency_ms = (time.time() - start) * 1000
                    self._store_cache(inp, tier2_result)
                    self._metrics.record(tier2_result)
                    results[idx] = tier2_result
                except Exception as e:
                    logger.warning(f"scillm failed for item {idx}: {e}")
                    # Keep tier 1 result already in results[idx]
                    self._metrics.record(results[idx])

        return results

    def _cache_key(self, input_data: dict) -> str:
        """SHA1 of canonical JSON."""
        canonical = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(canonical.encode()).hexdigest()

    def _store_cache(self, input_data: dict, result: TierResult) -> None:
        """Store result in cache with TTL."""
        if not self.config.enable_cache:
            return
        key = self._cache_key(input_data)
        self._cache[key] = result
        self._cache_expiry[key] = time.time() + (self.config.cache_ttl_hours * 3600)

    def _tier0(self, input_data: dict) -> Optional[TierResult]:
        """Custom heuristic if config.tier0_fn provided."""
        if self.config.tier0_fn is None:
            return None
        try:
            result = self.config.tier0_fn(input_data)
            if result is not None:
                return TierResult(
                    tier=0, source="heuristic",
                    result=result, confidence=1.0, latency_ms=0.0,
                )
        except Exception as e:
            logger.debug(f"Tier 0 heuristic failed: {e}")
        return None

    def _tier1(self, input_data: dict) -> TierResult:
        """Local GPT inference via infer.py. Prefers Ollama (GPU-loaded), falls back to GGUF/HF."""
        input_text = (
            json.dumps(input_data, ensure_ascii=False)
            if isinstance(input_data, dict) else str(input_data)
        )

        try:
            # Prefer Ollama — model stays loaded in VRAM, fastest path
            from infer import infer_ollama
            local_result = infer_ollama(self.config.task_name, input_text)
            return TierResult(
                tier=1, source="local_gpt_ollama",
                result=local_result.get("output", {}),
                confidence=local_result.get("confidence", 0.0),
                latency_ms=local_result.get("latency_ms", 0.0),
            )
        except Exception as ollama_err:
            logger.debug(f"Ollama inference failed: {ollama_err}, trying GGUF/HF fallback")

        try:
            from infer import infer_gguf, infer_hf
            try:
                local_result = infer_gguf(
                    self.config.task_name, input_text, self.config.model_path,
                )
            except FileNotFoundError:
                local_result = infer_hf(
                    self.config.task_name, input_text, self.config.model_path,
                )

            return TierResult(
                tier=1, source="local_gpt",
                result=local_result.get("output", {}),
                confidence=local_result.get("confidence", 0.0),
                latency_ms=local_result.get("latency_ms", 0.0),
            )
        except Exception as e:
            logger.debug(f"Local GPT failed: {e}, returning low-confidence stub")
            return TierResult(
                tier=1, source="local_gpt",
                result={}, confidence=0.0, latency_ms=0.0,
            )

    def _tier2(self, input_data: dict) -> TierResult:
        """scillm escalation."""
        spec = self.spec
        input_text = (
            json.dumps(input_data, ensure_ascii=False)
            if isinstance(input_data, dict) else str(input_data)
        )

        prompt_parts = []
        # Inject memory scope context as system prompt prefix
        if self.config.scope_context:
            prompt_parts.append(self.config.scope_context)
        if spec.system_prompt:
            prompt_parts.append(spec.system_prompt)
        prompt_parts.append(f"\nInput:\n{input_text}")
        if spec.output_schema:
            prompt_parts.append(
                f"\nRespond with JSON matching this schema:\n"
                f"{json.dumps(spec.output_schema, indent=2)}"
            )
        prompt = "\n".join(prompt_parts)

        scillm_dir = Path(__file__).resolve().parents[2] / "scillm"
        sys.path.insert(0, str(scillm_dir))
        from batch import quick_completion

        start = time.time()
        result_text = quick_completion(
            prompt=prompt,
            json_mode=True,
            timeout=self.config.scillm_timeout,
        )
        latency = (time.time() - start) * 1000

        try:
            result = json.loads(result_text)
        except (json.JSONDecodeError, TypeError):
            result = {"raw": result_text}

        return TierResult(
            tier=2, source="scillm",
            result=result, confidence=1.0,  # Tier 2 is authoritative
            latency_ms=latency,
        )


# --- Factory functions ---

def qra_assess_router(**overrides) -> Router:
    """Router for QRA assessment (confidence_threshold=0.85)."""
    defaults = {"task_name": "qra-assessor", "confidence_threshold": 0.85}
    defaults.update(overrides)
    return Router(RouterConfig(**defaults))


def edge_score_router(**overrides) -> Router:
    """Router for edge scoring (confidence_threshold=0.90)."""
    defaults = {"task_name": "edge-scorer", "confidence_threshold": 0.90}
    defaults.update(overrides)
    return Router(RouterConfig(**defaults))


def monitor_router(**overrides) -> Router:
    """Router for monitor-* skills (confidence_threshold=0.80, lenient)."""
    defaults = {"task_name": "session-analyzer", "confidence_threshold": 0.80}
    defaults.update(overrides)
    return Router(RouterConfig(**defaults))


# --- CLI ---

@app.command("route")
def route_cmd(
    input_text: str = typer.Argument(..., help="Input text or JSON"),
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    threshold: float = typer.Option(0.85, "--threshold"),
    model_path: Optional[Path] = typer.Option(None, "--model"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable caching"),
):
    """Route input through 3-tier cascade."""
    try:
        input_data = json.loads(input_text)
    except json.JSONDecodeError:
        input_data = {"text": input_text}

    config = RouterConfig(
        task_name=task,
        confidence_threshold=threshold,
        model_path=model_path,
        enable_cache=not no_cache,
    )
    router = Router(config)
    result = router.route(input_data)

    output = {
        "tier": result.tier,
        "source": result.source,
        "result": result.result,
        "confidence": result.confidence,
        "latency_ms": round(result.latency_ms, 2),
        "cached": result.cached,
    }
    print(json.dumps(output, indent=2, default=str))


@app.command("batch")
def batch_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    input_file: Path = typer.Option(..., "--input", "-i", help="JSONL input"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o"),
    threshold: float = typer.Option(0.85, "--threshold"),
):
    """Batch route inputs through 3-tier cascade."""
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(code=1)

    inputs = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                inputs.append(json.loads(line))

    config = RouterConfig(task_name=task, confidence_threshold=threshold)
    router = Router(config)
    results = router.route_batch(inputs)

    output_data = []
    for inp, res in zip(inputs, results):
        output_data.append({
            "input": inp,
            "tier": res.tier,
            "source": res.source,
            "result": res.result,
            "confidence": res.confidence,
            "latency_ms": round(res.latency_ms, 2),
            "cached": res.cached,
        })

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            for item in output_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"Batch results saved to {output_file}")
    else:
        for item in output_data:
            print(json.dumps(item, default=str))

    # Persist + print metrics summary
    metrics_path = Path("..") / "data" / task / "router_metrics.json"
    router.metrics.persist(metrics_path)
    print(json.dumps(router.metrics.summary(), indent=2))


@app.command("metrics")
def metrics_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
):
    """Show router metrics (placeholder — requires active router instance)."""
    logger.info(f"Metrics for task '{task}' — use route/batch commands to accumulate metrics")
    print(json.dumps(RouterMetrics().summary(), indent=2))


if __name__ == "__main__":
    app()
