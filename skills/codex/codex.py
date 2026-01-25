#!/usr/bin/env python3
import json
import subprocess
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

def run_codex(
    prompt: str,
    model: str = "gpt-5.2-codex",
    reasoning: str = "high",
    sandbox: str = "workspace-write",
    json_mode: bool = False,
    output_schema: Optional[Path] = None,
) -> str:
    """Run a codex exec command."""
    cmd = [
        "codex", "exec",
        "--model", model,
        "-c", f"reasoning_effort=\"{reasoning}\"",
        "-s", sandbox,
        "--full-auto",
        "--skip-git-repo-check"
    ]
    
    if json_mode:
        cmd.append("--json")
    
    if output_schema and output_schema.exists():
        cmd.extend(["--output-schema", str(output_schema)])
        
    # Use - to read from stdin
    cmd.append("-")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=prompt)
        
        if process.returncode != 0:
            return f"Error: {stderr}"
        
        return stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def main():
    parser = argparse.ArgumentParser(description="Codex Skill - gpt-5.2 High Reasoning Bridge")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Reason command
    reason_parser = subparsers.add_parser("reason", help="Generic reasoning")
    reason_parser.add_argument("prompt", help="Reasoning prompt")
    reason_parser.add_argument("--model", default="gpt-5.2-codex")
    reason_parser.add_argument("--reasoning", default="high", choices=["low", "medium", "high"])
    
    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Structured extraction")
    extract_parser.add_argument("prompt", help="Extraction prompt")
    extract_parser.add_argument("--schema", type=Path, help="Path to JSON Schema file")
    extract_parser.add_argument("--model", default="gpt-5.2-codex", help="Codex model to use")
    extract_parser.add_argument("--reasoning", default="high", choices=["low", "medium", "high"], help="Reasoning effort level")
    
    args = parser.parse_args()
    
    if args.command == "reason":
        print(run_codex(args.prompt, model=args.model, reasoning=args.reasoning))
    elif args.command == "extract":
        print(run_codex(args.prompt, model=args.model, reasoning=args.reasoning, output_schema=args.schema))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
