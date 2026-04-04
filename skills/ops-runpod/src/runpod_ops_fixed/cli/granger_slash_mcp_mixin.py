"""
Granger Universal Slash Command and MCP Generation for Typer CLIs
Module: granger_slash_mcp_mixin.py
Description: Implementation of granger slash mcp mixin functionality

This is the STANDARD implementation for all Granger spoke projects.
It provides consistent MCP server generation with prompts support.

Usage:
    from granger_slash_mcp_mixin import add_slash_mcp_commands
    
    app = typer.Typer()
    add_slash_mcp_commands(app, project_name="your-project")

Version: 1.0.0
"""

import typer
from pathlib import Path
from typing import Optional, Set, Callable, Any, Dict, List
import json
import sys
import inspect
from functools import wraps
import asyncio
from contextlib import contextmanager, redirect_stdout
from io import StringIO
import traceback

# Import prompt infrastructure - this should be in every project
try:
    from runpod_ops_fixed.mcp.prompts import PromptRegistry, get_prompt_registry
    PROMPTS_AVAILABLE = True
except ImportError:
    PROMPTS_AVAILABLE = False
    # Define a placeholder when not available
    class PromptRegistry:
        pass


def add_slash_mcp_commands(
    app: typer.Typer,
    project_name: str,
    skip_commands: Optional[Set[str]] = None,
    command_prefix: str = "generate",
    output_dir: str = ".claude/commands",
    prompt_registry: Optional[PromptRegistry] = None,
    enable_fastmcp_server: bool = True
) -> typer.Typer:
    """
    Add slash command and MCP generation capabilities to any Typer app.
    
    This is the STANDARD implementation for all Granger projects.
    
    Args:
        app: The Typer application to enhance
        project_name: Name of the project (required for consistency)
        skip_commands: Set of command names to skip during generation
        command_prefix: Prefix for generation commands (default: "generate")
        output_dir: Default output directory for slash commands
        prompt_registry: Optional PromptRegistry for managing prompts
        enable_fastmcp_server: Whether to add serve-mcp command
        
    Returns:
        The enhanced Typer app
    """
    
    # Validate project name
    if not project_name:
        raise ValueError("project_name is required for Granger standard compliance")
    
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
    
    # Use provided registry or get global one
    if PROMPTS_AVAILABLE:
        registry = prompt_registry or get_prompt_registry()
    else:
        registry = None
    
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
        
        # Generate slash commands for CLI commands
        for command in app.registered_commands:
            cmd_name = command.name or command.callback.__name__
            
            if cmd_name in default_skip:
                continue
                
            func = command.callback
            docstring = func.__doc__ or f"Run {cmd_name} command"
            
            # Clean docstring
            doc_lines = docstring.strip().split('\n')
            short_desc = doc_lines[0]
            
            # Use project name as prefix
            slash_name = f"{project_name}:{cmd_name}"
            
            # Generate content
            content = f"""# {short_desc}

{docstring.strip()}

## Usage

`/{slash_name}`

## Examples

```
/{slash_name} --help
```

---
*Auto-generated slash command for {project_name}*
"""
            
            # Write file
            cmd_file = out_dir / f"{slash_name.replace(':', '-')}.md"
            cmd_file.write_text(content)
            
            if verbose:
                typer.echo(f"✅ Created: {cmd_file}")
            else:
                typer.echo(f"✅ /{slash_name}")
                
            generated += 1
        
        # Generate slash commands for prompts if available
        if PROMPTS_AVAILABLE and registry:
            typer.echo("\n📋 Generating prompt slash commands...")
            
            for prompt in registry.list_prompts():
                if prompt.name.startswith(project_name):
                    slash_name = prompt.name
                    
                    content = f"""# {prompt.description}

{prompt.description}

## Parameters
"""
                    for param, info in prompt.parameters.items():
                        content += f"- `{param}`: {info.get('description', 'No description')}\n"
                    
                    if prompt.examples:
                        content += "\n## Examples\n"
                        for example in prompt.examples:
                            content += f"- {example}\n"
                    
                    content += f"""
---
*Auto-generated prompt slash command for {project_name}*
"""
                    
                    cmd_file = out_dir / f"{slash_name.replace(':', '-')}.md"
                    cmd_file.write_text(content)
                    
                    if verbose:
                        typer.echo(f"✅ Created: {cmd_file}")
                    else:
                        typer.echo(f"✅ /{slash_name}")
                    
                    generated += 1
        
        typer.echo(f"\n📁 Generated {generated} commands in {out_dir}/")
    
    @app.command(name=f"{command_prefix}-mcp-config")
    def generate_mcp_config_command(
        output: Path = typer.Option("mcp.json", "--output", "-o"),
        host: str = typer.Option("localhost", "--host"),
        port: int = typer.Option(5000, "--port"),
        include_prompts: bool = typer.Option(True, "--prompts/--no-prompts")
    ):
        """Generate MCP (Model Context Protocol) configuration following Granger standard."""
        
        # Build tool definitions from CLI commands
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
        
        # Build prompts section if available
        prompts = {}
        if include_prompts and PROMPTS_AVAILABLE and registry:
            for prompt in registry.list_prompts():
                if prompt.name.startswith(project_name):
                    prompts[prompt.name] = {
                        "description": prompt.description,
                        "slash_command": f"/{prompt.name}",
                        "inputSchema": {
                            "type": "object",
                            "properties": prompt.parameters,
                            "required": prompt.required_params
                        }
                    }
                    
                    if prompt.examples:
                        prompts[prompt.name]["examples"] = prompt.examples
        
        # Build config following Granger standard
        config = {
            "name": project_name,
            "version": "1.0.0",
            "description": f"{project_name.title()} - Part of Granger ecosystem",
            "author": "Granger Project",
            "license": "MIT",
            "runtime": "python",
            "main": f"src/{project_name.replace('-', '_')}/mcp/server.py",
            "commands": {
                "serve": {
                    "description": f"Start the {project_name} MCP server",
                    "command": f"python -m {project_name.replace('-', '_')}.mcp.server"
                }
            },
            "tools": tools,
            "capabilities": {
                "tools": bool(tools),
                "prompts": bool(prompts),
                "resources": False
            }
        }
        
        if prompts:
            config["prompts"] = prompts
            
        # Add standard config schema
        config["config_schema"] = {
            "type": "object",
            "properties": {
                "log_level": {
                    "type": "string",
                    "description": "Logging level",
                    "default": "INFO",
                    "enum": ["DEBUG", "INFO", "WARNING", "ERROR"]
                }
            }
        }
        
        output.write_text(json.dumps(config, indent=2))
        typer.echo(f"✅ Generated MCP config: {output}")
        typer.echo(f"📋 Includes {len(tools)} tools")
        if prompts:
            typer.echo(f"📋 Includes {len(prompts)} prompts")
        typer.echo(f"\n✨ Config follows Granger MCP standard v1.0.0")
    
    if enable_fastmcp_server:
        @app.command(name="serve-mcp")
        def serve_mcp_command(
            host: str = typer.Option("localhost", "--host"),
            port: int = typer.Option(5000, "--port"),
            transport: str = typer.Option("stdio", "--transport", help="Transport: stdio or http"),
            debug: bool = typer.Option(False, "--debug")
        ):
            """Serve this CLI as an MCP server using FastMCP (Granger standard)."""
            
            # Import the project's MCP server
            try:
                project_module = project_name.replace('-', '_')
                server_module = f"{project_module}.mcp.server"
                
                # Try to import and run the server
                try:
                    server = __import__(server_module, fromlist=['serve'])
                    if hasattr(server, 'serve'):
                        typer.echo(f"🚀 Starting {project_name} MCP server...")
                        typer.echo(f"📡 Transport: {transport}")
                        if transport == "http":
                            typer.echo(f"📡 Endpoint: http://{host}:{port}/")
                        typer.echo("\nPress Ctrl+C to stop")
                        
                        # Call the serve function
                        server.serve()
                    else:
                        typer.echo(f"❌ No serve() function found in {server_module}")
                        raise typer.Exit(1)
                        
                except ImportError as e:
                    typer.echo(f"❌ Could not import {server_module}: {e}")
                    typer.echo("\nMake sure you have implemented:")
                    typer.echo(f"  src/{project_module}/mcp/server.py")
                    typer.echo("  with a serve() function")
                    raise typer.Exit(1)
                    
            except KeyboardInterrupt:
                typer.echo("\n\n🛑 Server stopped")
    
    return app


def slash_mcp_cli(project_name: str, **kwargs):
    """
    Decorator to automatically add slash/MCP commands to a Typer app.
    
    This follows the Granger standard for all spoke projects.
    
    Usage:
        @slash_mcp_cli(project_name="my-project")
        app = typer.Typer()
        
        @app.command()
        def hello(name: str):
            print(f"Hello {name}")
    """
    def decorator(app: typer.Typer) -> typer.Typer:
        return add_slash_mcp_commands(app, project_name=project_name, **kwargs)
    
    return decorator


# Validation
if __name__ == "__main__":
    print("✅ Granger slash_mcp_mixin v1.0.0")
    print("📚 This is the standard implementation for all Granger projects")
    print("\nFeatures:")
    print("  - Consistent project naming")
    print("  - Automatic prompt discovery")
    print("  - Standard MCP configuration")
    print("  - FastMCP server integration")
    print("\nUsage:")
    print('  add_slash_mcp_commands(app, project_name="your-project")')