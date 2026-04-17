#!/usr/bin/env python3
"""
Claude (Anthropic) Adapter for Agent Inbox.
Supports headless OAuth via ~/.pi/agent/auth.json
"""

import os
import sys
import json
import typer
import httpx
from pathlib import Path

app = typer.Typer(help="Claude Adapter")

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
API_ENDPOINT = "https://api.anthropic.com/v1/messages"
AUTH_FILE = Path.home() / ".pi" / "agent" / "auth.json"

def get_credentials():
    """
    Get credentials from ~/.pi/agent/auth.json
    """
    if not AUTH_FILE.exists():
        print(f"Error: Auth file not found: {AUTH_FILE}", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
            return data.get("anthropic")
    except Exception as e:
        print(f"Error reading auth file: {e}", file=sys.stderr)
        sys.exit(1)

def generate_content(model, prompt, credentials):
    """
    Call Anthropic API using authenticated credentials.
    """
    token = credentials.get("access")
    if not token:
        print("Error: No access token found in credentials", file=sys.stderr)
        sys.exit(1)
        
    # Stealth mode headers as found in packages/ai/src/providers/anthropic.ts
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
        "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14,interleaved-thinking-2025-05-14",
        "user-agent": "claude-cli/2.1.2 (external, cli)",
        "x-app": "cli",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    data = {
        "model": model,
        "max_tokens": 4096,
        "system": "You are Claude Code, Anthropic's official CLI for Claude.",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    
    response = httpx.post(API_ENDPOINT, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)
        
    result = response.json()
    try:
        # Anthropic messages API returns a 'content' array
        text = result["content"][0]["text"]
        return text
    except (KeyError, IndexError):
        print(f"Unexpected response format: {json.dumps(result, indent=2)}", file=sys.stderr)
        sys.exit(1)

@app.command()
def main(
    prompt: str = typer.Argument(None, help="Prompt text (or read from stdin)"),
    model: str = typer.Option(DEFAULT_MODEL, help="Claude model name"),
):
    if not prompt:
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    creds = get_credentials()
    output = generate_content(model, prompt, creds)
    print(output)

if __name__ == "__main__":
    app()
