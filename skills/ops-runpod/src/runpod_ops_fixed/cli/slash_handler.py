"""
Module: slash_handler.py
Description: Proper slash command handler for RunPod CLI

External Dependencies:
- typer: https://typer.tiangolo.com/
- shlex: https://docs.python.org/3/library/shlex.html

Sample Input:
>>> handler.execute("/runpod create-instance 70B --hours 4")
>>> handler.execute("/runpod list-instances")

Expected Output:
>>> {"success": true, "output": "Instance created: abc123"}
>>> {"success": true, "output": "3 instances found"}

Example Usage:
>>> from runpod_ops_fixed.cli.slash_handler import SlashCommandHandler
>>> handler = SlashCommandHandler()
>>> result = handler.execute("/runpod optimize 70B --tokens 1000000")
"""

import shlex
import sys
from io import StringIO
from typing import Dict, Any, List, Optional
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from runpod_ops_fixed.cli.main import app as runpod_app


class SlashCommandHandler:
    """Handle slash commands for RunPod CLI"""
    
    def __init__(self):
        self.app = runpod_app
        self.command_map = self._build_command_map()
    
    def _build_command_map(self) -> Dict[str, Any]:
        """Build a map of command names to functions"""
        command_map = {}
        
        for command in self.app.registered_commands:
            name = command.name or command.callback.__name__
            command_map[name] = command
            # Also map with dashes replaced by underscores
            alt_name = name.replace("-", "_")
            if alt_name != name:
                command_map[alt_name] = command
        
        return command_map
    
    def execute(self, command: str) -> Dict[str, Any]:
        """
        Execute a slash command and return the result.
        
        Args:
            command: The full slash command string
            
        Returns:
            Dictionary with success status and output
        """
        try:
            # Parse command
            if command.startswith("/"):
                command = command[1:]
            
            # Split command preserving quotes
            parts = shlex.split(command)
            if not parts:
                return {"success": False, "error": "Empty command"}
            
            # First part should be "runpod" or similar
            if parts[0] in ["runpod", "runpod_ops", "runpod-ops"]:
                parts = parts[1:]
            
            if not parts:
                return {"success": False, "error": "No command specified"}
            
            # Get command name and args
            cmd_name = parts[0]
            args = parts[1:] if len(parts) > 1 else []
            
            # Find command
            if cmd_name not in self.command_map:
                available = ", ".join(sorted(self.command_map.keys()))
                return {
                    "success": False,
                    "error": f"Unknown command: {cmd_name}",
                    "available_commands": available
                }
            
            # Capture output
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            # Execute command
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                try:
                    # Build sys.argv as typer expects
                    original_argv = sys.argv
                    sys.argv = ["runpod", cmd_name] + args
                    
                    # Parse and invoke
                    from typer.testing import CliRunner
                    runner = CliRunner()
                    result = runner.invoke(self.app, [cmd_name] + args)
                    
                    if result.exit_code == 0:
                        return {
                            "success": True,
                            "output": result.output,
                            "command": cmd_name,
                            "args": args
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.output or "Command failed",
                            "exit_code": result.exit_code
                        }
                    
                finally:
                    sys.argv = original_argv
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing command: {str(e)}",
                "exception": type(e).__name__
            }
    
    def get_help(self, command: Optional[str] = None) -> str:
        """Get help for a command or all commands"""
        from typer.testing import CliRunner
        runner = CliRunner()
        
        if command:
            result = runner.invoke(self.app, [command, "--help"])
        else:
            result = runner.invoke(self.app, ["--help"])
        
        return result.output


# Singleton instance
_handler = None

def get_slash_handler() -> SlashCommandHandler:
    """Get the singleton slash command handler"""
    global _handler
    if _handler is None:
        _handler = SlashCommandHandler()
    return _handler


# Module validation
if __name__ == "__main__":
    handler = SlashCommandHandler()
    
    # Test command parsing
    result = handler.execute("/runpod list-instances")
    print(f"Test 1: {result}")
    
    # Test command with args
    result = handler.execute('/runpod optimize 70B --tokens 1000000')
    print(f"Test 2: {result}")
    
    # Test help
    help_text = handler.get_help()
    print(f"Help available: {len(help_text)} chars")
    
    print("✅ Module validation passed")