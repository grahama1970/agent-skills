"""Model judging and comparison CLI commands."""
import asyncio

import typer

from config import SKILL_DIR, PROMPTS_DIR
from llm import call_llm, call_llm_raw
from evaluation import load_prompt, load_models_config
from qra_evaluation import load_qra_ground_truth

from pl_app import app, console


@app.command()
def judge(
    prompt: str = typer.Option("tactic_control_prompt", "--prompt", "-p"),
    model_a: str = typer.Option("deepseek", "--model-a"),
    model_b: str = typer.Option("qwen3-235b", "--model-b"),
    meta_model: str = typer.Option("deepseek", "--meta-model"),
    cases: int = typer.Option(1, "--cases", "-n"),
):
    """Deep side-by-side judging of two models using an Agent-as-Judge."""
    from config import PROMPTS_DIR
    import asyncio
    
    models_config = load_models_config()
    system_prompt, _ = load_prompt(prompt, SKILL_DIR)
    from qra_evaluation import load_qra_ground_truth as load_gt_qra
    test_cases = load_gt_qra(SKILL_DIR)[:cases]
    
    console.print(f"[bold]Judging {model_a} vs {model_b}[/bold] on {prompt}\n")
    
    async def get_outputs():
        results = []
        for tc in test_cases:
            user_msg = f"TACTIC:\n{tc.name}\n{tc.description}"
            out_a, lat_a = await call_llm(system_prompt, user_msg, models_config[model_a])
            out_b, lat_b = await call_llm(system_prompt, user_msg, models_config[model_b])
            results.append({"case": tc.id, "a": out_a, "b": out_b})
        return results
        
    outputs = asyncio.run(get_outputs())
    
    # 2. Peer Review (Agent-as-Judge)
    for row in outputs:
        judge_prompt = f"""You are a judge of QRA (Question-Reasoning-Answer) quality.
Below are two outputs from different models for the same prompt.
Select the better output based on:
1. Verbatim citation accuracy.
2. Question clarity and lack of ambiguity.
3. Adherence to JSON format.

OUTPUT A (from {model_a}):
{row['a']}

OUTPUT B (from {model_b}):
{row['b']}

Return ONLY valid JSON:
{{ "winner": "A|B", "reasoning": "Detailed technical explanation" }}"""
        
        async def run_judge():
            from llm import call_llm_raw
            return await call_llm_raw([{"role": "user", "content": judge_prompt}], models_config[meta_model])
            
        decision = asyncio.run(run_judge())
        
        console.print(f"[bold cyan]Case: {row['case']}[/bold cyan]")
        winner = decision.get("winner", "Unknown")
        winner_name = model_a if winner == "A" else model_b if winner == "B" else "Unknown"
        console.print(f"  [bold green]Winner:[/bold green] {winner_name}")
        console.print(f"  [dim]Reasoning: {decision.get('reasoning', 'N/A')}[/dim]\n")


@app.command()
def compare(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    models: str = typer.Option("deepseek", "--models", "-m", help="Comma-separated model names"),
):
    """Compare multiple models on the same prompt."""
    model_list = [m.strip() for m in models.split(",")]

    console.print(f"[bold]Comparing {len(model_list)} models on prompt '{prompt}'[/bold]")
    console.print()

    for model in model_list:
        console.print(f"[bold cyan]--- {model} ---[/bold cyan]")
        eval_sparta(prompt=prompt, model=model, cases=0, verbose=False) # Changed eval to eval_sparta
        console.print()


