#!/usr/bin/env python3
"""Context7 API client for documentation lookup.

Usage:
    python context7.py search arangodb "bm25 search"
    python context7.py context /arangodb/arangodb "bm25 arangosearch"
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

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

app = typer.Typer(help="Context7 API - Library documentation lookup")


def get_api_key() -> str:
    """Get API key from environment or .env file."""
    key = os.getenv("CONTEXT7_API_KEY")
    if key:
        return key

    # Try to load from .env
    env_paths = [".env", "../.env", "../../.env", "../../../.env"]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("CONTEXT7_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"\'')

    raise ValueError("CONTEXT7_API_KEY not found in environment or .env")


def _search_libs(library_name: str, query: str, limit: int = 5) -> dict:
    """Search Context7 for libraries matching a name and query."""
    api_key = get_api_key()

    params = urllib.parse.urlencode({
        "libraryName": library_name,
        "query": query,
    })
    url = f"https://context7.com/api/v2/libs/search?{params}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])[:limit]
            return {
                "library_name": library_name,
                "query": query,
                "count": len(results),
                "results": results,
            }
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _get_context(library_id: str, query: str, tokens: int = 5000) -> str:
    """Get documentation context for a library and query."""
    api_key = get_api_key()

    params = urllib.parse.urlencode({
        "libraryId": library_id,
        "query": query,
        "tokens": tokens,
    })
    url = f"https://context7.com/api/v2/context?{params}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/plain",
    })

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


@app.command()
def search(
    library_name: str = typer.Argument(..., help="Library name (e.g., 'arangodb', 'lean4', 'react')"),
    query: str = typer.Argument(..., help="Search query for documentation"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results to return"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON"),
):
    """Search for libraries and documentation topics.

    Examples:
        python context7.py search arangodb "bm25 search"
        python context7.py search react "useEffect hooks"
        python context7.py search lean4 "induction tactics"
    """
    result = _search_libs(library_name, query, limit)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Found {result['count']} results for '{library_name}' + '{query}':")
            for r in result.get("results", []):
                print(f"  - {r.get('libraryId', 'unknown')}: {r.get('title', 'untitled')}")


@app.command()
def context(
    library_id: str = typer.Argument(..., help="Library ID from search (e.g., '/arangodb/arangodb')"),
    query: str = typer.Argument(..., help="Natural language query"),
    tokens: int = typer.Option(5000, "--tokens", "-t", help="Max tokens to return"),
):
    """Get documentation context for a specific library.

    First use 'search' to find the library_id, then use 'context' to get docs.

    Examples:
        python context7.py context /arangodb/arangodb "bm25 arangosearch"
        python context7.py context /facebook/react "useCallback memoization"
    """
    result = _get_context(library_id, query, tokens)
    print(result)


@app.command()
def find(
    topic: str = typer.Argument(..., help="Topic to search for across all libraries"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
):
    """Find documentation across popular libraries for a topic.

    Convenience command that searches common libraries.

    Examples:
        python context7.py find "binary search"
        python context7.py find "graph traversal"
    """
    # Search a few common libraries
    libraries = ["python", "typescript", "react", "nodejs"]
    all_results = []

    for lib in libraries:
        result = _search_libs(lib, topic, limit=3)
        if "results" in result:
            for r in result["results"]:
                r["searched_library"] = lib
                all_results.append(r)

    output = {
        "topic": topic,
        "count": len(all_results),
        "results": all_results[:limit],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    app()
