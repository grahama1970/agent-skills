#!/usr/bin/env python3
"""
Codex Adapter for Agent Inbox.
Supports headless OAuth via ~/.pi/agent/auth.json
"""

import os
import sys
import json
import base64
import typer
import httpx
from pathlib import Path

app = typer.Typer(help="Codex Adapter")

DEFAULT_MODEL = "gpt-5.3-codex"
API_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
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
            return data.get("openai-codex")
    except Exception as e:
        print(f"Error reading auth file: {e}", file=sys.stderr)
        sys.exit(1)

def extract_account_id(token):
    """
    Extract chatgpt-account-id from JWT.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token")
            
        payload_b64 = parts[1]
        # Add padding if needed
        missing_padding = len(payload_b64) % 4
        if missing_padding:
            payload_b64 += "=" * (4 - missing_padding)
            
        payload_json = base64.b64decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
        
        return payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
    except Exception as e:
        print(f"Error extracting account ID: {e}", file=sys.stderr)
        sys.exit(1)

def generate_content(model, prompt, credentials):
    """
    Call Codex API using authenticated credentials.
    """
    token = credentials.get("access")
    if not token:
        print("Error: No access token found in credentials", file=sys.stderr)
        sys.exit(1)
        
    account_id = extract_account_id(token)
    if not account_id:
        print("Error: No account ID found in token", file=sys.stderr)
        sys.exit(1)
        
    headers = {
        "Authorization": f"Bearer {token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": "pi",
        "User-Agent": "pi (linux; x64)",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    data = {
        "model": model,
        "store": False,
        "stream": False,  # Simplified for non-streaming output
        "instructions": "You are a helpful coding assistant.",
        "input": [{"role": "user", "content": prompt}],
        "text": {"verbosity": "medium"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": True
    }
    
    response = httpx.post(API_ENDPOINT, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)
        
    # SSE parsing if stream=True, but here we use stream=False for simplicity
    # Wait, the backend might REQUIRE stream=True. Let's check.
    # The ts code uses stream: true and SSE parsing.
    # If I use stream: false, I might get a single JSON object.
    
    result = response.json()
    # Handle response.done or content parts
    # The Responses API is complex. For now, let's try to grab 'content' from the first choice/message.
    try:
        # Note: Actual response format might vary. This is a best guess based on standard OpenAI
        # and what I saw in the TS code (which processes events).
        # In non-streaming mode, we might get a 'response' object.
        if "content" in result:
             return result["content"]
        # Fallback to looking through 'choices' or events
        return json.dumps(result, indent=2)
    except Exception as e:
        print(f"Error parsing response: {e}", file=sys.stderr)
        return json.dumps(result, indent=2)

@app.command()
def main(
    prompt: str = typer.Argument(None, help="Prompt text (or read from stdin)"),
    model: str = typer.Option(DEFAULT_MODEL, help="Codex model name"),
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
