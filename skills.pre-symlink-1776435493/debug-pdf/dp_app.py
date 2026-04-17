"""
Shared Typer app and logger for debug-pdf CLI.

All CLI sub-modules import app from here.
"""
import typer
from loguru import logger

app = typer.Typer(help="Debug PDF - Failure-to-fixture automation")
