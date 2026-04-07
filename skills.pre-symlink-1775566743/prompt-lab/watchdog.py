"""
Prompt Lab Skill - Watchdog
Continual monitoring of skill health.
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List

import typer
from rich.console import Console

from config import SKILL_DIR, MODELS_FILE
from evaluation import load_prompt, load_ground_truth, load_models_config, EvalResult, EvalSummary
from llm import call_llm_batch, TaxonomyResponse
from utils import notify_task_monitor

app = typer.Typer(help="Prompt Lab Watchdog: Continual skill health monitoring")
console = Console()

@app.command()
def check(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p"),
    model: str = typer.Option("deepseek", "--model", "-m"),
    samples: int = typer.Option(3, "--samples", "-n"),
    task_name: str = typer.Option("prompt-lab-health", "--task-name"),
):
    """Run a quick health check evaluation and notify task-monitor."""
    console.print(f"[bold]Watchdog: Checking health of {prompt} on {model}...[/bold]")
    
    models_config = load_models_config()
    if model not in models_config:
        console.print(f"[red]Model {model} not found.[/red]")
        return
        
    model_config = models_config[model]
    system, user_template = load_prompt(prompt, SKILL_DIR)
    test_cases = load_ground_truth("taxonomy", SKILL_DIR)[:samples]
    
    requests = []
    for tc in test_cases:
        requests.append({
            "system": system,
            "user": user_template.format(name=tc.name, description=tc.description)
        })
        
    async def run_check():
        results = await call_llm_batch(requests, model_config)
        
        eval_results = []
        for i, res in enumerate(results):
            tc = test_cases[i]
            validated = res.validated or TaxonomyResponse()
            
            eval_results.append(EvalResult(
                case_id=tc.id,
                predicted_conceptual=validated.conceptual,
                predicted_tactical=validated.tactical,
                expected_conceptual=tc.expected_conceptual,
                expected_tactical=tc.expected_tactical,
                rejected_tags=res.rejected_tags,
                confidence=validated.confidence,
                latency_ms=res.total_latency_ms,
                correction_success=res.success
            ))
            
        summary = EvalSummary(
            prompt_name=prompt,
            model_name=model,
            timestamp=time.ctime(),
            results=eval_results
        )
        
        passed = summary.avg_f1 >= 0.8
        status = "passed" if passed else "failed"
        
        metrics = {
            "avg_f1": summary.avg_f1,
            "latency": summary.avg_latency_ms,
            "rejected_count": summary.total_rejected,
            "watchdog_timestamp": time.time()
        }
        
        message = f"Watchdog check {status}: F1={summary.avg_f1:.2f}, Latency={summary.avg_latency_ms:.0f}ms"
        
        notify_task_monitor(
            task_name=task_name,
            status=status,
            metrics=metrics,
            message=message,
            metadata={"prompt": prompt, "model": model}
        )
        
        console.print(f"\n[bold]{message}[/bold]")
        
    asyncio.run(run_check())

if __name__ == "__main__":
    app()
