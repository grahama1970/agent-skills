"""Pytest controls for fresh bounded sampling and independent temporary evidence storage."""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(override=False)
def pytest_addoption(parser):
    parser.addoption("--samples", action="store", type=int, default=128,
                     help="Number of fresh random Unicode edit probes per test.")


@pytest.fixture
def samples(request):
    value = request.config.getoption("--samples")
    if not 50 <= value <= 5000:
        pytest.fail("Fresh sampling must be between 50 and 5000 probes.")
    return value


@pytest.fixture
def evidence_dir(tmp_path):
    base = os.environ.get("AI_DETECTION_TEST_ARTIFACTS")
    location = Path(base) if base else tmp_path / "evidence"
    location.mkdir(parents=True, exist_ok=True)
    return location
