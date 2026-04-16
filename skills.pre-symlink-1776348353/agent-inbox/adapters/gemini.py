#!/usr/bin/env python3
"""
Gemini Adapter for Agent Inbox.
Supports headless OAuth via Application Default Credentials (ADC) or Service Account.
"""

import os
import sys
import json
import typer
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account
import httpx

app = typer.Typer(help="Gemini Adapter")

DEFAULT_MODEL = "gemini-1.5-pro-latest"
API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def get_credentials(service_account_file=None):
    """
    Get credentials from Service Account file or ADC.
    """
    if service_account_file:
        return service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    
    # Fallback to ADC
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return creds

def generate_content(model, prompt, credentials):
    """
    Call Gemini API using authenticated credentials.
    """
    # Refresh credentials if needed
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    
    url = API_ENDPOINT.format(model=model)
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096
        }
    }
    
    response = httpx.post(url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)
        
    result = response.json()
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return text
    except (KeyError, IndexError):
        print(f"Unexpected response format: {json.dumps(result, indent=2)}", file=sys.stderr)
        sys.exit(1)

@app.command()
def main(
    prompt: str = typer.Argument(None, help="Prompt text (or read from stdin)"),
    model: str = typer.Option(DEFAULT_MODEL, help="Gemini model name"),
    service_account: str = typer.Option(None, help="Path to service account JSON"),
):
    if not prompt:
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    try:
        creds = get_credentials(service_account)
        output = generate_content(model, prompt, creds)
        print(output)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    app()
