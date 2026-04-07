"""
Shared Typer app and Rich console for llm-eval-lab CLI.

All CLI sub-modules import app and console from here.
"""
import sys
from pathlib import Path

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Also ensure prompt-lab is importable for shared modules
PROMPT_LAB_DIR = ROOT.parent / "prompt-lab"
if str(PROMPT_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(PROMPT_LAB_DIR))

try:
    import typer
    from rich.console import Console
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "rich", "-q"])
    import typer
    from rich.console import Console

app = typer.Typer(help="LLM Eval Lab: Model evaluation, comparison, and cost analysis")
console = Console()
