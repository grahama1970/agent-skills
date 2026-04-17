#!/usr/bin/env python3
"""
CLI for /create-persona skill.

Assembles all CLI command groups from split modules.
"""

from .cli_app import app

# Import all command modules to register their commands with the app
import importlib
from . import cli_core  # noqa: F401 -- create, list, show, update, delete
from . import cli_relationships  # noqa: F401 -- relate, export, import
from . import cli_batch  # noqa: F401 -- batch
from . import cli_quality  # noqa: F401 -- diagnose, validate, improve, simulacrum, audit
from . import cli_advanced  # noqa: F401 -- bdi, bridges, route
from . import cli_voice  # noqa: F401 -- voice train/status/synthesize/list
from . import cli_personaplex  # noqa: F401 -- personaplex status/extract-prompts/config/test-register/setup


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
