#!/usr/bin/env python3
"""
assess.py - Programmatic project assessment tool
"""
import argparse
import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

# Initial categories as requested
CATEGORIES = {
    "aspirational": [],    # Planned but not implemented
    "brittle": [],         # Fragile code patterns
    "over_engineered": [], # Too complex for simple tasks
    "working_well": [],    # Solid, tested code
    "outstanding": []      # Exceptional quality
}

def scan_for_issues(root_path: Path) -> Dict[str, Any]:
    """
    Perform static analysis to categorize code features.
    This is a V1 implementation using heuristics.
    """
    report = {
        "project": root_path.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": "Automated assessment V2",
        "categories": {k: [] for k in CATEGORIES.keys()},
        "issues": []
    }

    # Exclusion patterns
    exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}

    for root, dirs, files in os.walk(root_path):
        # In-place modification of dirs to skip excluded ones
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        rel_root = str(Path(root).relative_to(root_path))
        if rel_root != ".":
            # Heuristic for Over-Engineered: Deeply nested directory structure
            if len(Path(rel_root).parts) > 5:
                report["categories"]["over_engineered"].append({
                    "feature": "Deep Nesting",
                    "location": rel_root,
                    "reason": f"Directory structure is {len(Path(rel_root).parts)} levels deep"
                })

        for file in files:
            file_path = Path(root) / file
            if file_path.suffix not in ['.py', '.ts', '.js', '.md', '.sh']:
                continue
                
            try:
                content = file_path.read_text(errors='ignore')
                rel_path = str(file_path.relative_to(root_path))
                
                # Heuristic for Working Well: Features with tests
                if file_path.suffix in ['.py', '.ts', '.js']:
                    test_file = None
                    if file_path.suffix == '.py':
                        test_file = file_path.parent / f"test_{file_path.name}"
                    else:
                        test_file = file_path.with_suffix(f".test{file_path.suffix}")
                    
                    if test_file.exists():
                        report["categories"]["working_well"].append({
                            "feature": file_path.stem,
                            "location": rel_path,
                            "status": "Has companion test file"
                        })

                # Check Aspirational (TODOs)
                todos = re.findall(r'TODO[:\s]+(.*)', content)
                for todo in todos:
                    report["categories"]["aspirational"].append({
                        "feature": "Pending Task",
                        "location": rel_path,
                        "reason": f"TODO: {todo.strip()}"
                    })

                # Check Brittle (FIXME, hardcoded secrets heuristic)
                fixmes = re.findall(r'FIXME[:\s]+(.*)', content)
                for fixme in fixmes:
                    report["categories"]["brittle"].append({
                        "feature": "Known Issue",
                        "location": rel_path,
                        "reason": f"FIXME: {fixme.strip()}"
                    })
                
                # Heuristic for Brittle: Hardcoded local paths
                local_path_match = re.search(r'/home/graham/[\w\-/.]+', content)
                if local_path_match:
                    report["categories"]["brittle"].append({
                        "feature": "Hardcoded Path",
                        "location": rel_path,
                        "reason": f"Found local user path: {local_path_match.group(0)}"
                    })
                
                # Heuristic for Brittle: Magic Numbers in critical paths
                if file_path.suffix in ['.py', '.ts'] and "config" in rel_path.lower():
                    if re.search(r'=\s*\d{5,}', content): # Numbers with 5+ digits
                        report["categories"]["brittle"].append({
                            "feature": "Magic Number",
                            "location": rel_path,
                            "reason": "Found large numeric constant in configuration"
                        })

                # Check for "pass" only bodies (Stub/Aspirational)
                if file_path.suffix == '.py':
                    if re.search(r'def\s+\w+\s*\(.*\):\s*\n\s*pass\s*$', content, re.MULTILINE):
                        report["categories"]["aspirational"].append({
                            "feature": "Stubbed Function",
                            "location": rel_path,
                            "reason": "Function body is only 'pass'"
                        })

            except Exception as e:
                report["issues"].append({
                    "type": "scan_error",
                    "severity": "low",
                    "description": f"Could not read {rel_path}: {e}"
                })

    # Outstanding: Features with high metadata density (SKILL.md)
    # Handled by naturally finding SKILL.md files in the project
    
    return report

def main():
    parser = argparse.ArgumentParser(description="Programmatic project assessment")
    parser.add_argument("command", choices=["run"], help="Command to execute")
    parser.add_argument("path", help="Path to project root")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--deep", action="store_true", help="Enable deep analysis (LLM)")
    parser.add_argument("--model", help="LLM model to use for deep analysis")

    args = parser.parse_args()
    
    project_path = Path(args.path).resolve()
    if not project_path.exists():
        print(f"Error: Path {project_path} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Assess-CLI: Analyzing {project_path}...", file=sys.stderr)
    report = scan_for_issues(project_path)
    
    # Placeholder for LLM integration
    if args.deep:
        print("Note: Deep analysis logic pending integration with Codex skill.", file=sys.stderr)

    # Output
    json_output = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(json_output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

if __name__ == "__main__":
    main()
