"""Blind adversarial tests for Task 15: Performance benchmarks."""
import sys
import os
import json
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBenchmarkOutput:
    def test_benchmarks_json_exists(self):
        """benchmarks.json must exist after benchmark run."""
        bench_path = os.path.join(SKILL_DIR, "benchmarks.json")
        assert os.path.exists(bench_path), (
            f"benchmarks.json not found at {bench_path}. "
            f"Run bench_performance.py first."
        )

    def test_benchmarks_valid_json(self):
        bench_path = os.path.join(SKILL_DIR, "benchmarks.json")
        if not os.path.exists(bench_path):
            pytest.skip("benchmarks.json not yet created")
        with open(bench_path) as f:
            data = json.load(f)
        assert isinstance(data, (dict, list)), "benchmarks.json must be valid JSON object/array"

    def test_has_timing_data(self):
        bench_path = os.path.join(SKILL_DIR, "benchmarks.json")
        if not os.path.exists(bench_path):
            pytest.skip("benchmarks.json not yet created")
        with open(bench_path) as f:
            data = json.load(f)

        # Should have timing entries
        if isinstance(data, dict):
            # Check for timing-related keys
            all_text = json.dumps(data).lower()
            assert any(k in all_text for k in ["time", "duration", "elapsed", "seconds", "ms"]), \
                "benchmarks.json must contain timing data"
        elif isinstance(data, list):
            assert len(data) > 0, "benchmarks.json list must not be empty"

    def test_has_native_timings(self):
        bench_path = os.path.join(SKILL_DIR, "benchmarks.json")
        if not os.path.exists(bench_path):
            pytest.skip("benchmarks.json not yet created")
        with open(bench_path) as f:
            data = json.load(f)

        all_text = json.dumps(data).lower()
        assert "native" in all_text or "extract_tables" in all_text, \
            "benchmarks.json should have native backend timings"

    def test_has_memory_data(self):
        bench_path = os.path.join(SKILL_DIR, "benchmarks.json")
        if not os.path.exists(bench_path):
            pytest.skip("benchmarks.json not yet created")
        with open(bench_path) as f:
            data = json.load(f)

        all_text = json.dumps(data).lower()
        assert any(k in all_text for k in ["memory", "rss", "peak_mem", "mem"]), \
            "benchmarks.json should have memory usage data"
