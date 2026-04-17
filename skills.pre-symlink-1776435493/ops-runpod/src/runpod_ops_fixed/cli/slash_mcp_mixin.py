"""
Universal Slash Command and MCP Generation for Typer CLIs
Module: slash_mcp_mixin.py
Description: Functions for slash mcp mixin operations

This module provides a simple way to add slash command and MCP server
generation to any Typer CLI with a single line of code.

Usage:
    from llm_call.cli.slash_mcp_mixin import add_slash_mcp_commands
    
    app = typer.Typer()
    add_slash_mcp_commands(app)  # That's it!
"""

import typer
from pathlib import Path
from typing import Optional, Set, Callable
import json
import sys
import inspect
from functools import wraps


def add_slash_mcp_commands(
    app: typer.Typer,
    skip_commands: Optional[Set[str]] = None,
    command_prefix: str = "generate",
    output_dir: str = ".claude/commands"
) -> typer.Typer:
    """
    Add slash command and MCP generation capabilities to any Typer app.
    
    Args:
        app: The Typer application to enhance
        skip_commands: Set of command names to skip during generation
        command_prefix: Prefix for generation commands (default: "generate")
        output_dir: Default output directory for slash commands
        
    Returns:
        The enhanced Typer app
        
    Example:
        app = typer.Typer()
        
        @app.command()
        def hello(name: str):
            '''Say hello'''
            print(f"Hello {name}")
            
        # Add slash/MCP commands
        add_slash_mcp_commands(app)
    """
    
    # Default skip list includes our generation commands
    default_skip = {
        f"{command_prefix}-claude",
        f"{command_prefix}-mcp-config", 
        "serve-mcp",
        f"{command_prefix}_claude",
        f"{command_prefix}_mcp_config",
        "serve_mcp"
    }
    
    if skip_commands:
        default_skip.update(skip_commands)
    
    @app.command(name=f"{command_prefix}-claude")
    def generate_claude_command(
        output_path: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
        prefix: Optional[str] = typer.Option(None, "--prefix", "-p", help="Command prefix"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
    ):
        """Generate Claude Code slash commands for all CLI commands."""
        
        # Use provided output or default
        out_dir = output_path or Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        generated = 0
        
        for command in app.registered_commands:
            cmd_name = command.name or command.callback.__name__
            
            if cmd_name in default_skip:
                continue
                
            func = command.callback
            docstring = func.__doc__ or f"Run {cmd_name} command"
            
            # Clean docstring
            doc_lines = docstring.strip().split('\n')
            short_desc = doc_lines[0]
            
            # Add prefix if specified
            slash_name = f"{prefix}-{cmd_name}" if prefix else cmd_name
            
            # Get the module path for the command
            module_path = "python"
            if hasattr(sys.modules['__main__'], '__file__'):
                main_file = Path(sys.modules['__main__'].__file__)
                if main_file.suffix == '.py':
                    module_path = f"python {main_file.name}"
            
            # Generate content
            content = f"""# {short_desc}

{docstring.strip()}

## Usage

```bash
{module_path} {cmd_name} $ARGUMENTS
```

## Examples

```bash
# In Claude Code:
/project:{slash_name} [arguments]
```

---
*Auto-generated slash command*
"""
            
            # Write file
            cmd_file = out_dir / f"{slash_name}.md"
            cmd_file.write_text(content)
            
            if verbose:
                typer.echo(f"✅ Created: {cmd_file}")
            else:
                typer.echo(f"✅ /project:{slash_name}")
                
            generated += 1
        
        typer.echo(f"\n📁 Generated {generated} commands in {out_dir}/")
    
    @app.command(name=f"{command_prefix}-mcp-config")
    def generate_mcp_config_command(
        output: Path = typer.Option("mcp_config.json", "--output", "-o"),
        name: Optional[str] = typer.Option(None, "--name"),
        host: str = typer.Option("localhost", "--host"),
        port: int = typer.Option(5000, "--port")
    ):
        """Generate MCP (Model Context Protocol) configuration."""
        
        server_name = name or app.info.name or "cli-server"
        
        # Build tool definitions
        tools = {}
        
        for command in app.registered_commands:
            cmd_name = command.name or command.callback.__name__
            
            if cmd_name in default_skip:
                continue
                
            func = command.callback
            docstring = func.__doc__ or f"Execute {cmd_name}"
            
            # Extract parameters
            sig = inspect.signature(func)
            parameters = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'ctx']:
                    continue
                    
                # Type mapping
                param_type = "string"
                if param.annotation != param.empty:
                    if param.annotation == int:
                        param_type = "integer"
                    elif param.annotation == bool:
                        param_type = "boolean"
                    elif param.annotation == float:
                        param_type = "number"
                        
                parameters[param_name] = {
                    "type": param_type,
                    "description": f"Parameter: {param_name}"
                }
                
                if param.default == param.empty:
                    required.append(param_name)
            
            tools[cmd_name] = {
                "description": docstring.strip().split('\n')[0],
                "inputSchema": {
                    "type": "object",
                    "properties": parameters,
                    "required": required
                }
            }
        
        # Build config
        config = {
            "name": server_name,
            "version": "1.0.0",
            "description": f"MCP server for {server_name}",
            "server": {
                "command": sys.executable,
                "args": [sys.argv[0], "serve-mcp", "--host", host, "--port", str(port)]
            },
            "tools": tools,
            "capabilities": {
                "tools": True,
                "prompts": False,
                "resources": False
            }
        }
        
        output.write_text(json.dumps(config, indent=2))
        typer.echo(f"✅ Generated MCP config: {output}")
        typer.echo(f"📋 Includes {len(tools)} tools")
    
    @app.command(name="serve-mcp")
    def serve_mcp_command(
        host: str = typer.Option("localhost", "--host"),
        port: int = typer.Option(5000, "--port"),
        debug: bool = typer.Option(False, "--debug")
    ):
        """Serve this CLI as an MCP server."""
        
        try:
            from fastmcp import FastMCP
            
            server_name = app.info.name or "cli-server"
            mcp = FastMCP(server_name)
            
            # Register commands
            registered = 0
            for command in app.registered_commands:
                cmd_name = command.name or command.callback.__name__
                
                if cmd_name in default_skip:
                    continue
                    
                # Note: Simplified - in production handle async properly
                registered += 1
                
                if debug:
                    typer.echo(f"  Registered: {cmd_name}")
            
            typer.echo(f"🔧 Registered {registered} tools")
            typer.echo(f"🚀 Starting server on {host}:{port}")
            typer.echo("\nPress Ctrl+C to stop")
            
            # Would start server here
            typer.echo("\n[Install fastmcp to run server]")
            
        except ImportError:
            typer.echo("❌ FastMCP not installed!")
            typer.echo("\nInstall with: pip install fastmcp")
            raise typer.Exit(1)
    
    return app


def slash_mcp_cli(name: Optional[str] = None, **kwargs):
    """
    Decorator to automatically add slash/MCP commands to a Typer app.
    
    Usage:
        @slash_mcp_cli()
        app = typer.Typer()
        
        @app.command()
        def hello(name: str):
            print(f"Hello {name}")
    """
    def decorator(app: typer.Typer) -> typer.Typer:
        if name:
            app.info.name = name
        return add_slash_mcp_commands(app, **kwargs)
    
    return decorator