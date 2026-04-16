"""
Module: unified_cli.py
Description: Unified CLI entry point with MCP and slash command integration

External Dependencies:
- typer: https://typer.tiangolo.com/
- rich: https://rich.readthedocs.io/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> runpod --help
>>> runpod slash /runpod create 70B 4
>>> runpod mcp start

Expected Output:
>>> RunPod Operations Manager v1.0.0
>>> Instance created: abc123
>>> MCP server started on stdio

Example Usage:
>>> # Direct CLI
>>> runpod create-instance 70B --hours 4
>>> # Slash command
>>> runpod slash /runpod optimize 70B --tokens 1000000
>>> # MCP server
>>> runpod mcp start
"""

import sys
import typer
from rich.console import Console
from loguru import logger
from pathlib import Path
import asyncio

from runpod_ops_fixed.cli.main import app as main_app, RunPodCLI
from runpod_ops_fixed.mcp.server import RunPodMCPServer

# Create unified app
unified_app = typer.Typer(
    name="runpod",
    help="RunPod Operations Manager - Unified CLI",
    add_completion=False,
    rich_markup_mode="rich"
)

console = Console()

# Add the main app as a subcommand (but also allow direct commands)
# This allows both "runpod create-instance" and "runpod ops create-instance"
unified_app.registered_commands.extend(main_app.registered_commands)


@unified_app.command()
def slash(
    command: str = typer.Argument(..., help="Slash command to execute")
):
    """Execute RunPod slash commands"""
    cli = RunPodCLI()
    
    try:
        # Parse and execute slash command
        result = cli.handle_slash_command(command)
        
        if result.get("success"):
            console.print(f"[green] Command executed successfully[/green]")
            if result.get("output"):
                console.print(result["output"])
        else:
            console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error executing slash command: {e}[/red]")
        raise typer.Exit(1)


@unified_app.command()
def mcp(
    action: str = typer.Argument("start", help="MCP action (start/stop/status)"),
    stdio: bool = typer.Option(True, "--stdio", help="Use stdio transport"),
    port: int = typer.Option(None, "--port", "-p", help="Port for HTTP transport")
):
    """Manage MCP server"""
    
    if action == "start":
        try:
            server = RunPodMCPServer()
            
            if stdio:
                console.print("[green]Starting RunPod MCP server on stdio...[/green]")
                asyncio.run(server.run_stdio())
            else:
                if not port:
                    console.print("[red]Error: --port required for HTTP transport[/red]")
                    raise typer.Exit(1)
                    
                console.print(f"[green]Starting RunPod MCP server on port {port}...[/green]")
                asyncio.run(server.run_http(port))
                
        except KeyboardInterrupt:
            console.print("\n[yellow]MCP server stopped[/yellow]")
        except Exception as e:
            console.print(f"[red]Error starting MCP server: {e}[/red]")
            raise typer.Exit(1)
            
    elif action == "stop":
        console.print("[yellow]MCP server stop not implemented (use Ctrl+C)[/yellow]")
        
    elif action == "status":
        # Check if MCP server is running
        console.print("[blue]MCP server status check not implemented[/blue]")
        console.print("Check process list for 'runpod mcp start'")
        
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Valid actions: start, stop, status")
        raise typer.Exit(1)


@unified_app.command()
def integrate():
    """Show integration instructions"""
    console.print("[bold]RunPod Integration Instructions[/bold]\n")
    
    console.print("[cyan]1. Slash Commands:[/cyan]")
    console.print("   Add to ~/.claude/commands/runpod.sh:")
    console.print("   [dim]runpod slash \"$@\"[/dim]\n")
    
    console.print("[cyan]2. MCP Server:[/cyan]")
    console.print("   Add to Claude Desktop config:")
    console.print("   [dim]{")
    console.print('     "mcpServers": {')
    console.print('       "runpod": {')
    console.print('         "command": "runpod",')
    console.print('         "args": ["mcp", "start", "--stdio"]')
    console.print('       }')
    console.print('     }')
    console.print("   }[/dim]\n")
    
    console.print("[cyan]3. Environment Variables:[/cyan]")
    console.print("   Export in ~/.bashrc or ~/.zshrc:")
    console.print("   [dim]export RUNPOD_API_KEY=your_api_key_here[/dim]\n")
    
    console.print("[cyan]4. Test Integration:[/cyan]")
    console.print("   [dim]# Test CLI")
    console.print("   runpod list-instances")
    console.print("   ")
    console.print("   # Test slash command")
    console.print("   runpod slash '/runpod optimize 70B'")
    console.print("   ")
    console.print("   # Test MCP")
    console.print("   runpod mcp start --stdio[/dim]")


def main():
    """Main entry point"""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="INFO"
    )
    
    # Run CLI
    unified_app()


# Module validation
if __name__ == "__main__":
    # Test unified CLI
    cli = RunPodCLI()
    server = RunPodMCPServer()
    
    # Verify components
    assert hasattr(cli, "app")
    assert hasattr(cli, "handle_slash_command")
    assert hasattr(server, "run_stdio")
    assert len(unified_app.registered_commands) > 5  # Should have all commands
    
    print(" Module validation passed")