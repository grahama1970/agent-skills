"""
Module: main.py
Description: Main CLI entry point for RunPod operations management

External Dependencies:
- typer: https://typer.tiangolo.com/
- rich: https://rich.readthedocs.io/
- loguru: https://loguru.readthedocs.io/

Sample Input:
>>> runpod_ops create-instance 70B --hours 4
>>> runpod_ops monitor abc123
>>> runpod_ops optimize 70B --tokens 1000000

Expected Output:
>>> Instance created: {"id": "abc123", "gpu": "A100-80GB", "cost_per_hour": 3.09}
>>> Monitoring instance abc123... [live updates]
>>> Optimal config: {"gpu": "A100-80GB", "cost": 12.36}

Example Usage:
>>> runpod_ops --help
>>> runpod_ops create-instance --help
>>> runpod_ops list-instances
"""

import os
import typer
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger
import asyncio
from datetime import datetime

from runpod_ops_fixed.core import (
    RunPodManager,
    InstanceOptimizer,
    CostCalculator,
    InstanceMonitor,
    TrainingOrchestrator,
    InferenceServer
)
from runpod_ops_fixed.cli.slash_mcp_mixin_class import GrangerSlashMCPMixin, SlashMCPMixin

# Initialize CLI app
app = typer.Typer(
    name="runpod_ops",
    help="RunPod GPU instance management for LLM training and inference",
    add_completion=False,
    rich_markup_mode="rich"
)

# Initialize console for rich output
console = Console()

# CLI State
state = {
    "manager": None,
    "optimizer": None,
    "calculator": None,
    "monitor": None,
    "orchestrator": None,
    "inference_server": None
}


def initialize_components():
    """Initialize RunPod components lazily"""
    if state["manager"] is None:
        state["manager"] = RunPodManager()
        state["optimizer"] = InstanceOptimizer()
        state["calculator"] = CostCalculator()
        state["monitor"] = InstanceMonitor()
        state["orchestrator"] = TrainingOrchestrator()
        state["inference_server"] = InferenceServer()


@app.command()
def create_instance(
    model_size: str = typer.Argument(..., help="Model size (e.g., 7B, 13B, 70B)"),
    hours: float = typer.Option(4.0, "--hours", "-h", help="Number of hours to run"),
    gpu_type: Optional[str] = typer.Option(None, "--gpu", "-g", help="Specific GPU type"),
    spot: bool = typer.Option(False, "--spot", "-s", help="Use spot instances"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Preferred region"),
    tokens: Optional[int] = typer.Option(None, "--tokens", "-t", help="Number of tokens to train")
):
    """Create a new RunPod instance with automatic GPU optimization"""
    initialize_components()
    
    with console.status("[bold green]Creating RunPod instance...") as status:
        try:
            # Get optimal GPU if not specified
            if not gpu_type:
                # Use new GPU optimizer via handler
                from runpod_ops_fixed.handlers import RunPodHandler
                handler = RunPodHandler()
                
                # Optimize based on tokens or hours
                params = {
                    "operation": "optimize",
                    "model_size": model_size,
                    "is_training": True,
                    "use_spot": spot
                }
                
                if tokens:
                    params["tokens"] = tokens
                else:
                    params["tokens"] = int(hours * 1000000)  # Estimate 1M tokens/hour
                
                result = handler.handle(params)
                
                if result["success"]:
                    config = result["data"]["recommendations"]
                    gpu_type = config["gpu_id"]
                    console.print(f"[blue]Selected optimal GPU: {config['gpu_type']}[/blue]")
                    console.print(f"[blue]Method: {config['training_method']}[/blue]")
                    console.print(f"[blue]Total cost: ${config['total_cost']:.2f} for {config['hours_needed']:.1f} hours[/blue]")
                else:
                    # Fallback to legacy optimizer (returns dict, not object)
                    optimizer = state["optimizer"]
                    config = optimizer.get_optimal_config(model_size, hours=int(hours))
                    gpu_type = config["gpu_type"]
            
            # Create instance
            manager = state["manager"]
            instance = manager.create_training_instance(
                model_size=model_size,
                gpu_type=gpu_type,
                hours=hours,
                spot=spot,
                region=region
            )
            
            # Display result
            console.print("\n[bold green] Instance created successfully![/bold green]")
            
            table = Table(title="Instance Details")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")
            
            table.add_row("Instance ID", instance.id)
            table.add_row("GPU Type", instance.gpu_type)
            table.add_row("Status", instance.status)
            table.add_row("Cost/Hour", f"${instance.cost_per_hour:.2f}")
            table.add_row("Total Cost", f"${instance.cost_per_hour * hours:.2f}")
            table.add_row("SSH Command", f"ssh root@{instance.ssh_host} -p {instance.ssh_port}")
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error creating instance: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def list_instances(
    active_only: bool = typer.Option(True, "--active", "-a", help="Show only active instances"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table/json)")
):
    """List all RunPod instances"""
    initialize_components()

    try:
        manager = state["manager"]
        # list_instances is async, so run it with asyncio
        instances = asyncio.run(manager.list_instances(active_only=active_only))
        
        if format == "json":
            console.print_json([inst.dict() for inst in instances])
        else:
            table = Table(title="RunPod Instances")
            table.add_column("ID", style="cyan")
            table.add_column("GPU", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Cost/Hour", style="magenta")
            table.add_column("Uptime", style="white")
            
            for inst in instances:
                uptime = "N/A"
                if inst.created_at:
                    uptime = str(datetime.now() - inst.created_at).split('.')[0]
                
                table.add_row(
                    inst.id,
                    inst.gpu_type,
                    inst.status,
                    f"${inst.cost_per_hour:.2f}",
                    uptime
                )
            
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error listing instances: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def monitor(
    instance_id: str = typer.Argument(..., help="Instance ID to monitor"),
    interval: int = typer.Option(5, "--interval", "-i", help="Update interval in seconds")
):
    """Monitor a running instance"""
    initialize_components()
    
    async def monitor_loop():
        monitor = state["monitor"]
        
        while True:
            try:
                metrics = await monitor.get_instance_metrics(instance_id)
                
                console.clear()
                console.print(f"[bold]Monitoring Instance: {instance_id}[/bold]\n")
                
                # GPU metrics
                console.print("[cyan]GPU Metrics:[/cyan]")
                console.print(f"  Utilization: {metrics['gpu_utilization']}%")
                console.print(f"  Memory: {metrics['gpu_memory_used']}GB / {metrics['gpu_memory_total']}GB")
                console.print(f"  Temperature: {metrics['gpu_temp']}°C\n")
                
                # System metrics
                console.print("[cyan]System Metrics:[/cyan]")
                console.print(f"  CPU: {metrics['cpu_percent']}%")
                console.print(f"  RAM: {metrics['ram_used']}GB / {metrics['ram_total']}GB")
                console.print(f"  Disk: {metrics['disk_used']}GB / {metrics['disk_total']}GB\n")
                
                # Training metrics if available
                if metrics.get('training_loss'):
                    console.print("[cyan]Training Metrics:[/cyan]")
                    console.print(f"  Loss: {metrics['training_loss']:.4f}")
                    console.print(f"  Learning Rate: {metrics['learning_rate']:.2e}")
                    console.print(f"  Steps: {metrics['training_steps']}")
                
                console.print("\n[dim]Press Ctrl+C to stop monitoring[/dim]")
                
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                await asyncio.sleep(interval)
    
    try:
        asyncio.run(monitor_loop())
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped[/yellow]")


@app.command()
def optimize(
    model_size: str = typer.Argument(..., help="Model size (e.g., 7B, 13B, 70B)"),
    tokens: Optional[int] = typer.Option(None, "--tokens", "-t", help="Number of tokens to process"),
    hours: Optional[float] = typer.Option(None, "--hours", "-h", help="Training hours"),
    batch_size: int = typer.Option(4, "--batch", "-b", help="Batch size"),
    sequence_length: int = typer.Option(2048, "--seq-len", "-s", help="Sequence length"),
    max_budget: Optional[float] = typer.Option(None, "--max-budget", help="Maximum budget in USD"),
    inference: bool = typer.Option(False, "--inference", help="Optimize for inference (default: training)"),
    spot: bool = typer.Option(True, "--spot", help="Use spot instances")
):
    """Find optimal GPU configuration for a model using real benchmarks"""
    initialize_components()
    
    with console.status("[bold green]Calculating optimal configuration...") as status:
        try:
            # Use new GPU optimizer via handler
            from runpod_ops_fixed.handlers import RunPodHandler
            handler = RunPodHandler()
            
            # Build params
            params = {
                "operation": "optimize",
                "model_size": model_size,
                "is_training": not inference,
                "batch_size": batch_size,
                "sequence_length": sequence_length,
                "use_spot": spot
            }
            
            if tokens:
                params["tokens"] = tokens
            elif hours:
                # Estimate tokens based on hours (rough estimate)
                params["tokens"] = int(hours * 1000000)  # 1M tokens/hour estimate
            else:
                # Default to 10M tokens
                params["tokens"] = 10000000
                
            if max_budget:
                params["max_budget"] = max_budget
            
            # Get optimization result
            result = handler.handle(params)
            
            if result["success"]:
                data = result["data"]
                config = data["recommendations"]
                
                # Display main recommendation
                console.print("\n[bold]🎯 Optimal Configuration[/bold]\n")
                
                table = Table(show_header=False)
                table.add_column("Property", style="cyan", width=25)
                table.add_column("Value", style="white")
                
                table.add_row("GPU Type", config["gpu_type"])
                table.add_row("Number of GPUs", str(config["gpu_count"]))
                table.add_row("Training Method", config["training_method"])
                table.add_row("Cost per Hour", f"${config['cost_per_hour']:.2f}")
                table.add_row("Tokens per Hour", f"{config['tokens_per_hour']:,}")
                table.add_row("Hours Needed", f"{config['hours_needed']:.1f}")
                table.add_row("Total Cost", f"${config['total_cost']:.2f}")
                
                if "memory_used_gb" in config:
                    table.add_row("Memory Usage", f"{config['memory_used_gb']:.1f} GB")
                    table.add_row("Memory Utilization", f"{config['memory_utilization']:.0f}%")
                
                console.print(table)
                
                # Show alternatives if available
                if "alternatives" in data and data["alternatives"]:
                    console.print("\n[bold]💡 Alternative Configurations[/bold]\n")
                    
                    alt_table = Table()
                    alt_table.add_column("GPU", style="cyan")
                    alt_table.add_column("Method", style="yellow")
                    alt_table.add_column("$/hr", style="green")
                    alt_table.add_column("Hours", style="white")
                    alt_table.add_column("Total $", style="magenta")
                    alt_table.add_column("vs Optimal", style="red")
                    
                    for alt in data["alternatives"][:5]:
                        # Avoid division by zero
                        if config["total_cost"] > 0:
                            cost_diff = ((alt["total_cost"] / config["total_cost"]) - 1) * 100
                            diff_str = f"+{cost_diff:.0f}%" if cost_diff > 0 else f"{cost_diff:.0f}%"
                        else:
                            diff_str = "N/A"
                        
                        alt_table.add_row(
                            alt["gpu_type"],
                            alt["training_method"],
                            f"${alt['cost_per_hour']:.2f}",
                            f"{alt['hours_needed']:.1f}",
                            f"${alt['total_cost']:.2f}",
                            diff_str
                        )
                    
                    console.print(alt_table)
                
                # Show optimization insights
                console.print("\n[bold]📊 Optimization Insights[/bold]\n")
                
                if config["training_method"] == "FSDP":
                    console.print("• [yellow]Using FSDP[/yellow] - Model requires sharding across GPUs")
                    console.print("• Consider using regular PyTorch instead of Unsloth")
                elif config["gpu_count"] > 1:
                    console.print("• [yellow]Using DDP[/yellow] - Distributed training for better performance")
                
                if "A40" in config["gpu_type"] or "A10" in config["gpu_type"]:
                    console.print("• [green]Cost-optimized choice[/green] - Slower but more economical")
                elif "H100" in config["gpu_type"]:
                    console.print("• [blue]Speed-optimized choice[/blue] - Fastest available GPU")
                
                if spot:
                    console.print("• [cyan]Spot pricing[/cyan] - 50-70% cheaper but may be interrupted")
                    
            else:
                console.print(f"[red]Optimization failed: {result.get('error', 'Unknown error')}[/red]")
                raise typer.Exit(1)
                
        except Exception as e:
            console.print(f"[red]Error during optimization: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def terminate(
    instance_id: str = typer.Argument(..., help="Instance ID to terminate"),
    force: bool = typer.Option(False, "--force", "-f", help="Force termination without confirmation")
):
    """Terminate a RunPod instance"""
    initialize_components()
    
    if not force:
        confirm = typer.confirm(f"Are you sure you want to terminate instance {instance_id}?")
        if not confirm:
            console.print("[yellow]Termination cancelled[/yellow]")
            return
    
    try:
        manager = state["manager"]
        
        with console.status("[bold red]Terminating instance...") as status:
            success = manager.terminate_instance(instance_id)
            
        if success:
            console.print(f"[green] Instance {instance_id} terminated successfully[/green]")
        else:
            console.print(f"[red]Failed to terminate instance {instance_id}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error terminating instance: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def estimate_cost(
    model_size: str = typer.Argument(..., help="Model size (e.g., 7B, 13B, 70B)"),
    tokens: Optional[int] = typer.Option(None, "--tokens", "-t", help="Number of tokens"),
    hours: Optional[float] = typer.Option(None, "--hours", "-h", help="Training hours"),
    gpu_type: Optional[str] = typer.Option(None, "--gpu", "-g", help="Specific GPU type")
):
    """Estimate training costs"""
    initialize_components()
    
    if not tokens and not hours:
        console.print("[red]Error: Specify either --tokens or --hours[/red]")
        raise typer.Exit(1)
    
    calculator = state["calculator"]
    optimizer = state["optimizer"]
    
    try:
        # Get GPU config
        if gpu_type:
            config = optimizer.gpu_configs.get(gpu_type)
            if not config:
                console.print(f"[red]Unknown GPU type: {gpu_type}[/red]")
                raise typer.Exit(1)
        else:
            config = optimizer.get_optimal_config(model_size)
            gpu_type = config["gpu_type"]
        
        # Calculate costs using config dict from optimizer (has estimated_cost, estimated_hours, etc.)
        cost_per_hour = config.get("estimated_cost", 0) / max(config.get("estimated_hours", 1), 0.1)

        if hours:
            total_cost = hours * cost_per_hour

            table = Table(title="Cost Estimate by Hours")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Model Size", model_size)
            table.add_row("GPU Type", gpu_type)
            table.add_row("Hours", f"{hours:.1f}")
            table.add_row("Cost per Hour", f"${cost_per_hour:.2f}")
            table.add_row("Total Cost", f"${total_cost:.2f}")

        else:  # tokens
            # Use tokens_per_second from config to estimate time
            tokens_per_second = config.get("tokens_per_second", 1000)
            hours_needed = tokens / (tokens_per_second * 3600)
            total_cost = hours_needed * cost_per_hour

            table = Table(title="Cost Estimate by Tokens")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Model Size", model_size)
            table.add_row("GPU Type", gpu_type)
            table.add_row("Tokens", f"{tokens:,}")
            table.add_row("Tokens per Hour", f"{int(tokens_per_second * 3600):,}")
            table.add_row("Hours Needed", f"{hours_needed:.1f}")
            table.add_row("Cost per Hour", f"${cost_per_hour:.2f}")
            table.add_row("Total Cost", f"${total_cost:.2f}")
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error estimating cost: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def start_training(
    config_file: Path = typer.Argument(..., help="Training configuration file"),
    instance_id: Optional[str] = typer.Option(None, "--instance", "-i", help="Use existing instance"),
    auto_terminate: bool = typer.Option(True, "--auto-terminate", help="Terminate instance after training")
):
    """Start a training job on RunPod"""
    initialize_components()
    
    if not config_file.exists():
        console.print(f"[red]Config file not found: {config_file}[/red]")
        raise typer.Exit(1)
    
    try:
        # Load config
        with open(config_file) as f:
            config = json.load(f)
        
        orchestrator = state["orchestrator"]
        
        with console.status("[bold green]Starting training job...") as status:
            # Start training
            job_id = asyncio.run(
                orchestrator.start_training(
                    config=config,
                    instance_id=instance_id,
                    auto_terminate=auto_terminate
                )
            )
        
        console.print(f"[green] Training job started: {job_id}[/green]")
        console.print(f"\nMonitor with: [cyan]runpod_ops monitor {instance_id or job_id}[/cyan]")
        
    except Exception as e:
        console.print(f"[red]Error starting training: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def serve(
    model_path: str = typer.Argument(..., help="Path to model or HuggingFace model ID"),
    instance_id: Optional[str] = typer.Option(None, "--instance", "-i", help="Use existing instance"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to serve on")
):
    """Start inference server on RunPod"""
    initialize_components()
    
    try:
        server = state["inference_server"]
        
        with console.status("[bold green]Starting inference server...") as status:
            endpoint = asyncio.run(
                server.deploy(
                    model_path=model_path,
                    instance_id=instance_id,
                    port=port
                )
            )
        
        console.print(f"[green] Inference server started![/green]")
        console.print(f"\nEndpoint: [cyan]{endpoint}[/cyan]")
        console.print(f"\nTest with:")
        console.print(f'[dim]curl -X POST {endpoint}/generate -d \'{{"prompt": "Hello", "max_tokens": 50}}\'[/dim]')
        
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def deploy_docker(
    image: str = typer.Argument(..., help="Docker image to deploy (e.g., grahamco/runpod-sglang-base)"),
    mode: str = typer.Option("inference", "--mode", "-m", help="Deployment mode (inference/finetune/shell)"),
    model_name: Optional[str] = typer.Option(None, "--model", help="Model to load"),
    gpu_type: Optional[str] = typer.Option(None, "--gpu", "-g", help="GPU type (auto-selected if not specified)"),
    spot: bool = typer.Option(True, "--spot", "-s", help="Use spot instances"),
    volume_size: int = typer.Option(100, "--volume", "-v", help="Volume size in GB"),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Environment file with additional vars")
):
    """Deploy a Docker image on RunPod with optimized GPU selection"""
    initialize_components()
    
    with console.status("[bold green]Preparing Docker deployment...") as status:
        try:
            # Get optimal GPU if not specified
            if not gpu_type and model_name:
                from runpod_ops_fixed.handlers import RunPodHandler
                handler = RunPodHandler()
                
                # Determine model size from name
                model_size = "7B"  # Default
                for size in ["180B", "70B", "30B", "13B", "8B", "7B", "3B", "1B"]:
                    if size.lower() in model_name.lower():
                        model_size = size
                        break
                
                # Optimize GPU selection
                result = handler.handle({
                    "operation": "optimize",
                    "model_size": model_size,
                    "is_training": mode == "finetune",
                    "use_spot": spot,
                    "tokens": 10000000  # Default estimate
                })
                
                if result["success"]:
                    config = result["data"]["recommendations"]
                    gpu_type = config["gpu_id"]
                    gpu_count = config["gpu_count"]
                    console.print(f"[blue]Auto-selected: {config['gpu_type']} x{gpu_count}[/blue]")
                else:
                    gpu_type = "RTX_4090"
                    gpu_count = 1
            else:
                gpu_type = gpu_type or "RTX_4090"
                gpu_count = 1
            
            # Build environment variables
            env_vars = {
                "MODE": mode,
                "HF_TOKEN": os.getenv("HF_TOKEN", "")
            }
            
            if model_name:
                env_vars["MODEL_NAME"] = model_name
            
            # Add mode-specific env vars
            if mode == "inference":
                env_vars["PORT"] = "8000"
                env_vars["TENSOR_PARALLEL"] = str(gpu_count)
            elif mode == "finetune":
                env_vars["WANDB_API_KEY"] = os.getenv("WANDB_API_KEY", "")
                env_vars["TRAINING_METHOD"] = "sft"
            
            # Load additional env vars from file
            if env_file and env_file.exists():
                with open(env_file) as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            key, value = line.strip().split("=", 1)
                            env_vars[key] = value
            
            # Determine ports based on mode
            ports = "8000/http" if mode == "inference" else "8888/http,6006/http"
            
            # Create instance configuration
            config = {
                "gpu_type": gpu_type,
                "gpu_count": gpu_count,
                "disk_size": 50,
                "volume_size": volume_size,
                "image": image,
                "env": env_vars,
                "ports": ports,
                "spot": spot,
                "metadata": {
                    "docker_image": image,
                    "deployment_mode": mode,
                    "model": model_name or "none"
                }
            }
            
            # Create the instance
            manager = state["manager"]
            instance = asyncio.run(manager.create_instance("general", config))
            
            # Display result
            console.print("\n[bold green]✅ Docker deployment successful![/bold green]")
            
            table = Table(title="Deployment Details")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")
            
            table.add_row("Instance ID", instance.id)
            table.add_row("Docker Image", image)
            table.add_row("Mode", mode)
            table.add_row("GPU", f"{instance.gpu_count}x {instance.gpu_type}")
            table.add_row("Cost/Hour", f"${instance.cost_per_hour:.2f}")
            table.add_row("Volume Size", f"{volume_size} GB")
            
            if model_name:
                table.add_row("Model", model_name)
            
            console.print(table)
            
            # Mode-specific instructions
            if mode == "inference":
                console.print(f"\n[yellow]SGLang endpoint:[/yellow] http://{instance.id}.runpod.net:8000")
                console.print("\nTest with:")
                console.print(f'curl -X POST http://{instance.id}.runpod.net:8000/generate \\')
                console.print('  -d \'{"text": "Hello", "sampling_params": {"max_new_tokens": 50}}\'')
            elif mode == "finetune":
                console.print(f"\n[yellow]TensorBoard:[/yellow] http://{instance.id}.runpod.net:6006")
                console.print(f"[yellow]Jupyter:[/yellow] http://{instance.id}.runpod.net:8888")
            elif mode == "shell":
                ssh_info = instance.metadata.get("ssh", {})
                if ssh_info:
                    console.print(f"\n[yellow]SSH:[/yellow] ssh {ssh_info.get('username', 'root')}@{ssh_info.get('hostname', 'ssh.runpod.io')} -p {ssh_info.get('port', 22)}")
            
            console.print(f"\n[dim]To terminate: runpod terminate {instance.id}[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error deploying Docker image: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def version():
    """Show version information"""
    console.print("[bold]RunPod Operations Manager[/bold]")
    console.print("Version: 1.0.0")
    console.print("Part of the Granger ecosystem")
    console.print("\nDocker Images:")
    console.print("- grahamco/runpod-sglang-base:latest (inference)")
    console.print("- grahamco/runpod-sglang-finetune:latest (training)")


# Create mixed CLI class
class RunPodCLI(GrangerSlashMCPMixin, SlashMCPMixin):
    """RunPod CLI with slash command and MCP integration"""
    
    def __init__(self):
        self.app = app
        self.console = console
        super().__init__()
        
        # Import slash handler
        from runpod_ops_fixed.cli.slash_handler import get_slash_handler
        self.slash_handler = get_slash_handler()
    
    def handle_slash_command(self, command: str) -> Dict[str, Any]:
        """Handle slash command execution with proper integration"""
        return self.slash_handler.execute(command)


# Module validation
if __name__ == "__main__":
    # Test CLI creation
    cli = RunPodCLI()
    assert cli.app is not None
    assert hasattr(cli, "handle_slash_command")
    assert hasattr(cli, "get_mcp_tools")
    print(" Module validation passed")