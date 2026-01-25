#!/usr/bin/env python3
"""
Rate Limit Recovery Skill

Collects recent transcripts and logging information from agent platforms that were rate-limited mid-task.
Supports recovery from Codex, Claude Code, Pi, and Antigravity rate limits.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Constants for file size limits and performance
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size to read
MAX_LOG_LINES = 1000  # Maximum lines to read from log files
MAX_RECENT_FILES = 50  # Maximum recent files to track

class RateLimitRecovery:
    def __init__(self):
        self.home_dir = Path.home()
        self.pi_data_dir = self.home_dir / ".pi" / "rate-limit-recovery"
        self.pi_data_dir.mkdir(parents=True, exist_ok=True)
        self.recovery_data = {
            "timestamp": datetime.now().isoformat(),
            "platform": None,
            "session_id": None,
            "error_info": {},
            "session_context": {},
            "logs": {},
            "system_state": {},
            "recovery_summary": {}
        }
    
    def _safe_read_file(self, file_path: Path, max_lines: Optional[int] = None, max_chars: Optional[int] = None) -> str:
        """Safely read a file with size and line limits."""
        try:
            stat = file_path.stat()
            if stat.st_size > MAX_FILE_SIZE:
                return f"[File too large: {stat.st_size} bytes, max: {MAX_FILE_SIZE}]"
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if max_lines:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append("[... truncated due to line limit]")
                            break
                        lines.append(line.rstrip())
                    return '\n'.join(lines)
                elif max_chars:
                    content = f.read(max_chars)
                    if len(f.read(1)) > 0:  # Check if there's more content
                        content += "\n[... truncated due to size limit]"
                    return content
                else:
                    return f.read()
        except (OSError, UnicodeDecodeError, PermissionError) as e:
            return f"[Error reading file: {e}]"
    
    def _safe_read_json(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Safely read and parse JSON file with size limits."""
        try:
            stat = file_path.stat()
            if stat.st_size > MAX_FILE_SIZE:
                return {"error": f"File too large: {stat.st_size} bytes"}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, PermissionError) as e:
            return {"error": f"Failed to parse JSON: {e}"}
    
    def detect_platform(self) -> Optional[str]:
        """Auto-detect which agent platform was recently used."""
        platform_indicators = {
            "codex": [
                self.home_dir / ".codex",
                self.home_dir / ".codex" / "sessions",
                Path.cwd() / ".codex"
            ],
            "claude": [
                self.home_dir / ".claude",
                Path.cwd() / ".claude",
                self.home_dir / "Library" / "Application Support" / "Claude"
            ],
            "pi": [
                self.home_dir / ".pi",
                self.home_dir / ".pi" / "sessions",
                self.home_dir / ".pi" / "agent"
            ],
            "antigravity": [
                self.home_dir / ".antigravity",
                Path.cwd() / ".antigravity",
                self.home_dir / "Library" / "Application Support" / "Antigravity"
            ]
        }
        
        # Check for recent activity in platform directories
        for platform, paths in platform_indicators.items():
            for path in paths:
                if path.exists():
                    # Check for recent modifications
                    try:
                        stat = path.stat()
                        if datetime.now() - datetime.fromtimestamp(stat.st_mtime) < timedelta(hours=24):
                            return platform
                    except OSError:
                        continue
        
        # Check for rate limit errors in recent logs
        recent_logs = self._find_recent_logs()
        for log_file in recent_logs:
            content = self._safe_read_file(log_file, max_chars=10000)
            if "429" in content or "rate limit" in content.lower():
                # Try to identify platform from log path or content
                if "codex" in str(log_file).lower() or "codex" in content.lower():
                    return "codex"
                elif "claude" in str(log_file).lower() or "claude" in content.lower():
                    return "claude"
                elif "pi" in str(log_file).lower() or "pi" in content.lower():
                    return "pi"
                elif "antigravity" in str(log_file).lower() or "antigravity" in content.lower():
                    return "antigravity"
        
        return None
    
    def _find_recent_logs(self) -> List[Path]:
        """Find recently modified log files across common locations."""
        log_patterns = [
            "*.log",
            "*.jsonl",
            "*log*.txt",
            "*debug*",
            "*error*"
        ]
        
        search_dirs = [
            Path.cwd(),
            self.home_dir,
            self.home_dir / ".local" / "share",
            Path("/tmp") if os.path.exists("/tmp") else Path.cwd() / "tmp",
            self.home_dir / "Library" / "Logs" if os.name == "posix" and (self.home_dir / "Library").exists() else self.home_dir / ".cache"
        ]
        
        recent_logs = []
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
                
            for pattern in log_patterns:
                try:
                    for log_file in search_dir.rglob(pattern):
                        if log_file.is_file():
                            try:
                                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                                if mtime > cutoff_time:
                                    recent_logs.append(log_file)
                            except OSError:
                                continue
                except (OSError, PermissionError):
                    continue
        
        return recent_logs
    
    def recover_codex(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Recover from OpenAI Codex rate limiting."""
        recovery_data = {
            "platform": "codex",
            "session_data": {},
            "logs": {},
            "error_info": {}
        }
        
        # Codex session directories
        codex_paths = [
            self.home_dir / ".codex" / "sessions",
            Path.cwd() / ".codex" / "sessions",
            self.home_dir / ".codex"
        ]
        
        # Find recent sessions
        sessions = []
        for codex_path in codex_paths:
            if codex_path.exists():
                try:
                    # Look for session files
                    session_files = list(codex_path.glob("*.json")) + list(codex_path.glob("session*"))
                    for session_file in session_files:
                        try:
                            stat = session_file.stat()
                            if datetime.now() - datetime.fromtimestamp(stat.st_mtime) < timedelta(hours=2):
                                sessions.append(session_file)
                        except OSError:
                            continue
                except OSError:
                    continue
        
        # Read session data
        for session_file in sessions[:5]:  # Limit to 5 most recent
            session_data = self._safe_read_json(session_file)
            if "error" not in session_data:
                recovery_data["session_data"][str(session_file)] = session_data
        
        # Look for Codex logs
        log_paths = [
            self.home_dir / ".codex" / "logs",
            Path.cwd() / "codex.log",
            Path.cwd() / ".codex" / "debug.log"
        ]
        
        for log_path in log_paths:
            if log_path.exists() and log_path.is_file():
                logs_content = self._safe_read_file(log_path, max_lines=MAX_LOG_LINES)
                if not logs_content.startswith("[Error") and not logs_content.startswith("[File too large"):
                    recovery_data["logs"][str(log_path)] = logs_content.split('\n')
        
        # Check for rate limit errors
        recent_logs = self._find_recent_logs()
        for log_file in recent_logs:
            if "codex" in str(log_file).lower():
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if "429" in content or "rate limit" in content.lower():
                            # Extract error details
                            error_lines = [line for line in content.split('\n') if '429' in line or 'rate limit' in line.lower()]
                            recovery_data["error_info"][str(log_file)] = error_lines[-10:]  # Last 10 error lines
                except (OSError, UnicodeDecodeError):
                    continue
        
        return recovery_data
    
    def recover_claude(self, workspace_path: Optional[str] = None) -> Dict[str, Any]:
        """Recover from Claude Code rate limiting."""
        recovery_data = {
            "platform": "claude",
            "workspace_data": {},
            "claude_logs": {},
            "error_info": {}
        }
        
        # Claude workspace directories
        claude_paths = []
        if workspace_path:
            claude_paths.append(Path(workspace_path) / ".claude")
        
        claude_paths.extend([
            self.home_dir / ".claude",
            Path.cwd() / ".claude",
            self.home_dir / "Library" / "Application Support" / "Claude"
        ])
        
        # Find Claude data
        for claude_path in claude_paths:
            if claude_path.exists():
                try:
                    # Look for conversation history
                    conv_files = list(claude_path.glob("conversation*")) + list(claude_path.glob("history*"))
                    for conv_file in conv_files:
                        if conv_file.stat().st_mtime > (datetime.now() - timedelta(hours=2)).timestamp():
                            content = self._safe_read_file(conv_file, max_chars=5000)
                            if not content.startswith("[Error") and not content.startswith("[File too large"):
                                recovery_data["claude_logs"][str(conv_file)] = content
                    
                    # Look for context files
                    context_files = list(claude_path.glob("context*")) + list(claude_path.glob("*.json"))
                    for context_file in context_files:
                        context_data = self._safe_read_json(context_file)
                        if "error" not in context_data:
                            recovery_data["workspace_data"][str(context_file)] = context_data
                            
                except OSError:
                    continue
        
        # Check workspace for recent activity
        workspace = Path(workspace_path) if workspace_path else Path.cwd()
        if workspace.exists():
            try:
                # Find recently modified files
                recent_files = []
                # Common directories to exclude from scanning
                exclude_dirs = {
                    'node_modules', '.git', '__pycache__', '.venv', 'venv',
                    '.tox', 'build', 'dist', '.pytest_cache', '.mypy_cache',
                    '.coverage', 'htmlcov', '.eggs', '*.egg-info'
                }
                
                for file_path in workspace.rglob("*"):
                    if file_path.is_file():
                        # Skip excluded directories
                        if any(excluded in str(file_path) for excluded in exclude_dirs):
                            continue
                        try:
                            stat = file_path.stat()
                            if datetime.now() - datetime.fromtimestamp(stat.st_mtime) < timedelta(hours=2):
                                recent_files.append(str(file_path))
                        except OSError:
                            continue
                
                recovery_data["workspace_data"]["recent_files"] = recent_files[:20]  # Top 20
            except OSError:
                pass
        
        return recovery_data
    
    def recover_pi(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Recover from Pi rate limiting."""
        recovery_data = {
            "platform": "pi",
            "pi_sessions": {},
            "memory_data": {},
            "error_info": {}
        }
        
        # Pi directories
        pi_paths = [
            self.home_dir / ".pi",
            self.home_dir / ".pi" / "sessions",
            self.home_dir / ".pi" / "agent",
            Path.cwd() / ".pi"
        ]
        
        # Find Pi session files
        for pi_path in pi_paths:
            if pi_path.exists():
                try:
                    # Look for session files
                    session_files = list(pi_path.glob("session*")) + list(pi_path.glob("*.jsonl"))
                    for session_file in session_files:
                        try:
                            stat = session_file.stat()
                            if datetime.now() - datetime.fromtimestamp(stat.st_mtime) < timedelta(hours=2):
                                if session_file.suffix == '.jsonl':
                                    # Read JSONL files
                                    content = self._safe_read_file(session_file, max_lines=50)
                                    if not content.startswith("[Error") and not content.startswith("[File too large"):
                                        lines = content.split('\n')
                                        recovery_data["pi_sessions"][str(session_file)] = [json.loads(line) for line in lines if line.strip()]
                                else:
                                    # Read JSON files
                                    session_data = self._safe_read_json(session_file)
                                    if "error" not in session_data:
                                        recovery_data["pi_sessions"][str(session_file)] = session_data
                        except (OSError, json.JSONDecodeError):
                            continue
                except OSError:
                    continue
        
        # Check for episodic memory (if ArangoDB is available)
        try:
            # Try to connect to ArangoDB and get recent episodes
            result = subprocess.run([
                "curl", "-s", "-X", "GET",
                "http://localhost:8529/_db/_system/_api/cursor",
                "-H", "Content-Type: application/json",
                "-d", json.dumps({
                    "query": "FOR doc IN episodic_memory FILTER doc.timestamp >= @timestamp SORT doc.timestamp DESC LIMIT 10 RETURN doc",
                    "bindVars": {"timestamp": (datetime.now() - timedelta(hours=2)).isoformat()}
                })
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                arango_data = json.loads(result.stdout)
                if "result" in arango_data:
                    recovery_data["memory_data"]["episodic_memory"] = arango_data["result"]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass  # ArangoDB not available or no access
        
        return recovery_data
    
    def recover_antigravity(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Recover from Antigravity rate limiting."""
        recovery_data = {
            "platform": "antigravity",
            "antigravity_logs": {},
            "session_data": {},
            "error_info": {}
        }
        
        # Antigravity directories
        ag_paths = [
            self.home_dir / ".antigravity",
            Path.cwd() / ".antigravity",
            self.home_dir / "Library" / "Application Support" / "Antigravity"
        ]
        
        # Find Antigravity data
        for ag_path in ag_paths:
            if ag_path.exists():
                try:
                    # Look for log files
                    log_files = list(ag_path.glob("*.log")) + list(ag_path.glob("*log*"))
                    for log_file in log_files:
                        try:
                            stat = log_file.stat()
                            if datetime.now() - datetime.fromtimestamp(stat.st_mtime) < timedelta(hours=2):
                                logs_content = self._safe_read_file(log_file, max_lines=MAX_LOG_LINES)
                                if not logs_content.startswith("[Error") and not logs_content.startswith("[File too large"):
                                    recovery_data["antigravity_logs"][str(log_file)] = logs_content.split('\n')
                        except (OSError, UnicodeDecodeError):
                            continue
                    
                    # Look for session/task files
                    task_files = list(ag_path.glob("task*")) + list(ag_path.glob("session*"))
                    for task_file in task_files:
                        content = self._safe_read_file(task_file, max_chars=5000)
                        if not content.startswith("[Error") and not content.startswith("[File too large"):
                            recovery_data["session_data"][str(task_file)] = content
                            
                except OSError:
                    continue
        
        # Check for Google Cloud Code Assist logs
        gcloud_paths = [
            self.home_dir / ".config" / "gcloud" / "logs",
            Path.cwd() / "gcloud.log"
        ]
        
        for gcloud_path in gcloud_paths:
            if gcloud_path.exists() and gcloud_path.is_file():
                logs_content = self._safe_read_file(gcloud_path, max_lines=50)
                if not logs_content.startswith("[Error") and not logs_content.startswith("[File too large"):
                    # Filter for Antigravity-related entries
                    logs = logs_content.split('\n')
                    antigravity_logs = [line for line in logs if 'antigravity' in line.lower() or '429' in line]
                    if antigravity_logs:
                        recovery_data["antigravity_logs"][str(gcloud_path)] = antigravity_logs
        
        return recovery_data
    
    def generate_recovery_summary(self, recovery_data: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the recovery data."""
        platform = recovery_data.get("platform", "unknown")
        
        summary_parts = [
            f"# Rate Limit Recovery Report",
            f"**Platform**: {platform.title()}",
            f"**Recovery Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Session context summary
        if "session_data" in recovery_data and recovery_data["session_data"]:
            summary_parts.append("## Session Data Recovered")
            for session_file, data in recovery_data["session_data"].items():
                if isinstance(data, dict):
                    summary_parts.append(f"- **{Path(session_file).name}**: {len(data)} entries")
                else:
                    summary_parts.append(f"- **{Path(session_file).name}**: {len(str(data))} characters")
            summary_parts.append("")
        
        # Log summary
        if "logs" in recovery_data and recovery_data["logs"]:
            summary_parts.append("## Log Files Recovered")
            for log_file, logs in recovery_data["logs"].items():
                summary_parts.append(f"- **{Path(log_file).name}**: {len(logs)} lines")
            summary_parts.append("")
        
        # Error information
        if "error_info" in recovery_data and recovery_data["error_info"]:
            summary_parts.append("## Rate Limit Error Details")
            for error_source, errors in recovery_data["error_info"].items():
                if errors:
                    summary_parts.append(f"- **{Path(error_source).name}**: {len(errors)} error entries")
                    # Show first error as example
                    summary_parts.append(f"  - Example: {errors[0] if errors else 'No details'}")
            summary_parts.append("")
        
        # Recovery recommendations
        summary_parts.extend([
            "## Recovery Recommendations",
            "",
            "### Immediate Actions:",
            "1. **Wait for rate limit reset** - Check the platform's retry timing",
            "2. **Review collected data** - Examine the session context and logs above",
            "3. **Prepare resume strategy** - Identify what task was interrupted",
            "",
            "### Next Steps:",
            f"1. **Use memory skill** to store this recovery data: `./run.sh learn --problem 'Rate limited on {platform}' --solution 'Recovered session data'`",
            "2. **Resume the task** with appropriate rate limit handling",
            "3. **Monitor progress** using task-monitor skill if needed",
            "",
            "### Prevention:",
            "- Consider using different models or providers to distribute load",
            "- Implement exponential backoff in your workflows",
            "- Monitor usage patterns to anticipate rate limits"
        ])
        
        return "\n".join(summary_parts)
    
    def export_recovery_data(self, recovery_data: Dict[str, Any], format_type: str = "json", output_file: Optional[str] = None) -> str:
        """Export recovery data in specified format."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            platform = recovery_data.get('platform', 'unknown')
            output_file = self.pi_data_dir / f"rate_limit_recovery_{platform}_{timestamp}.{format_type}"
        else:
            output_file = Path(output_file)
        
        output_path = Path(output_file)
        
        if format_type.lower() == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(recovery_data, f, indent=2, default=str)
        
        elif format_type.lower() == "markdown":
            summary = self.generate_recovery_summary(recovery_data)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(summary)
        
        elif format_type.lower() == "txt":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Rate Limit Recovery - {recovery_data.get('platform', 'unknown')}\n")
                f.write(f"Time: {datetime.now()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(json.dumps(recovery_data, indent=2, default=str))
        
        return str(output_path)

def main():
    parser = argparse.ArgumentParser(description="Rate Limit Recovery Skill")
    parser.add_argument("command", choices=["recover"], help="Command to run")
    parser.add_argument("--platform", choices=["codex", "claude", "pi", "antigravity"], 
                       help="Specific platform to recover from")
    parser.add_argument("--session-id", help="Session ID for recovery")
    parser.add_argument("--workspace", help="Workspace path for Claude recovery")
    parser.add_argument("--task-id", help="Task ID for Antigravity recovery")
    parser.add_argument("--format", choices=["json", "markdown", "txt"], default="markdown",
                       help="Output format")
    parser.add_argument("--output", help="Output file path (default: ~/.pi/rate-limit-recovery/)")
    
    args = parser.parse_args()
    
    if args.command == "recover":
        recovery = RateLimitRecovery()
        
        # Auto-detect platform if not specified
        platform = args.platform or recovery.detect_platform()
        if not platform:
            print("Could not auto-detect platform. Please specify --platform")
            return 1
        
        print(f"Recovering from {platform} rate limiting...")
        
        # Perform platform-specific recovery
        if platform == "codex":
            recovery_data = recovery.recover_codex(args.session_id)
        elif platform == "claude":
            recovery_data = recovery.recover_claude(args.workspace)
        elif platform == "pi":
            recovery_data = recovery.recover_pi(args.session_id)
        elif platform == "antigravity":
            recovery_data = recovery.recover_antigravity(args.task_id)
        else:
            print(f"Unknown platform: {platform}")
            return 1
        
        # Generate and display summary
        summary = recovery.generate_recovery_summary(recovery_data)
        print(summary)
        
        # Export data
        output_file = recovery.export_recovery_data(recovery_data, args.format, args.output)
        print(f"\nRecovery data exported to: {output_file}")
        
        # Store in memory if available
        try:
            # Try to use the memory skill to store this recovery
            # Use the correct path to the memory skill based on Pi conventions
            home_dir = Path.home()
            memory_script = home_dir / ".pi" / "skills" / "memory" / "memory.py"
            if memory_script.exists():
                memory_cmd = [
                    sys.executable,
                    str(memory_script),
                    "learn",
                    "--problem", f"Rate limited on {platform} platform",
                    "--solution", f"Recovered session data from {platform} rate limit. See {output_file}"
                ]
                result = subprocess.run(memory_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    print("Recovery data stored in memory for future reference.")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass  # Memory skill not available
        
        return 0
    
    return 1

if __name__ == "__main__":
    sys.exit(main())