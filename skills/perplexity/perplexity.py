#!/usr/bin/env python3
"""Perplexity API client for research queries with web search.

Usage:
    python perplexity.py ask "What's new in Python 3.12?"
    python perplexity.py ask --model large "ArangoDB vs Neo4j"
    python perplexity.py research --json "Best Lean4 tactics"
"""
import os
import sys
import json
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any

SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env  # type: ignore
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv  # type: ignore
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

_load_env()

try:
    import typer
except ImportError:
    print("typer not installed. Run: pip install typer", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(help="Perplexity AI - Research with web search")

# Model mapping (updated Jan 2025)
# See: https://docs.perplexity.ai/getting-started/models
MODELS = {
    "small": "sonar",           # Fast, good for simple queries
    "large": "sonar-pro",       # Better quality, more thorough
    "huge": "sonar-reasoning",  # Best for complex analysis
}

API_URL = "https://api.perplexity.ai/chat/completions"


def get_api_key() -> str:
    """Get API key from environment or .env file."""
    key = os.getenv("PERPLEXITY_API_KEY")
    if key:
        return key

    # Try to load from .env
    env_paths = [".env", "../.env", "../../.env", "../../../.env"]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("PERPLEXITY_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')

    raise ValueError("PERPLEXITY_API_KEY not found in environment or .env")


def _research(
    question: str,
    model: str = "small",
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Research a question with web search, returning answer and citations."""
    api_key = get_api_key()
    model_id = MODELS.get(model, MODELS["small"])

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.2,
        "return_citations": True,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())

            answer = ""
            citations = []

            if "choices" in result and result["choices"]:
                choice = result["choices"][0]
                if "message" in choice:
                    answer = choice["message"].get("content", "")

            if "citations" in result:
                citations = result["citations"]

            return {
                "answer": answer,
                "citations": citations,
                "model": model_id,
                "usage": result.get("usage", {}),
            }

    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {e.reason}", "details": error_body}
    except Exception as e:
        return {"error": str(e)}


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask Perplexity"),
    model: str = typer.Option("small", "--model", "-m", help="Model size: small, large, huge"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
):
    """Ask a question and get a concise answer.

    Examples:
        python perplexity.py ask "What's new in Python 3.12?"
        python perplexity.py ask --model large "Compare Redis vs Memcached"
        python perplexity.py ask -m huge "Explain transformer attention"
    """
    if model not in MODELS:
        typer.echo(f"Unknown model: {model}. Choose from: {list(MODELS.keys())}", err=True)
        raise typer.Exit(1)

    result = _research(question, model, system)

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(1)

    typer.echo(result.get("answer", "No answer returned"))

    if result.get("citations"):
        typer.echo(f"\n[{len(result['citations'])} citations - use 'research' command for details]")


@app.command()
def research(
    question: str = typer.Argument(..., help="Question to research"),
    model: str = typer.Option("small", "--model", "-m", help="Model size: small, large, huge"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON with citations"),
):
    """Research a question with full citations.

    Returns structured JSON with answer, citations, and usage stats.

    Examples:
        python perplexity.py research "Best practices for ArangoDB indexes"
        python perplexity.py research --model large "State of LLM fine-tuning 2025"
    """
    if model not in MODELS:
        typer.echo(f"Unknown model: {model}. Choose from: {list(MODELS.keys())}", err=True)
        raise typer.Exit(1)

    result = _research(question, model, system)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            typer.echo(f"Error: {result['error']}", err=True)
            raise typer.Exit(1)

        typer.echo(result.get("answer", "No answer returned"))
        typer.echo("\nCitations:")
        for i, cite in enumerate(result.get("citations", []), 1):
            typer.echo(f"  [{i}] {cite}")


@app.command()
def models():
    """List available Perplexity models.

    Example:
        python perplexity.py models
    """
    print(json.dumps({
        "models": {k: {"id": v, "description": desc} for k, v, desc in [
            ("small", MODELS["small"], "Fast, good for simple queries"),
            ("large", MODELS["large"], "Better quality, more thorough"),
            ("huge", MODELS["huge"], "Best for complex analysis"),
        ]}
    }, indent=2))


if __name__ == "__main__":
    app()
