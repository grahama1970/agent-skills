Now I have a complete picture. Let me analyze this code-review skill implementation and provide my assessment.

## Analysis Summary

### Clarifying Questions (with answers)

1. **Should the skill support custom prompts via file?**
   - Currently prompts are hardcoded. Adding `--prompt-file` could be useful for customizing the Coder/Reviewer dialogue, but the current defaults are well-designed. **Recommendation**: Not critical, the hardcoded prompts are good.

2. **Is the current model list up-to-date?**
   - The models include futuristic names like `gpt-5`, `gpt-5.2-codex`, `o3`, `gemini-3-pro`. These appear to be speculative/placeholder models. **Recommendation**: Add a comment noting these are placeholder/future models, or provide mechanism to use custom model IDs.

3. **Should workspace cleanup be more aggressive?**
   - Cleanup uses `ignore_errors=True` which is appropriate for temp directories. **Recommendation**: Current approach is fine.

### Issues Found

1. **LGTM Detection Bug (Line 1670)**: The LGTM check splits on newline but doesn't handle cases where LGTM appears in the first line with other text properly. Also "LOOKS GOOD TO ME" check scans entire output, not just first line.

2. **Missing Provider Validation in loop command**: The `loop` command doesn't validate that `coder_provider` and `reviewer_provider` are valid before using them to fetch default models (lines 1737-1738).

3. **Inconsistent stderr/stdout messaging**: The `check` command writes error messages to stderr but JSON output to stdout, which is good. But some error paths in other commands mix this.

4. **SKILL.md path mismatch**: SKILL.md references `.agents/skills/code-review/` but the actual path is `.pi/skills/code-review/`.

5. **Missing `--raw` and `--extract-diff` options in SKILL.md documentation**.

6. **LOOP_REVIEWER_PROMPT could be clearer about "LGTM" requirement**: The prompt says "start your response with LGTM" but the detection also checks "LOOKS GOOD TO ME".

7. **`_loop_async` missing session continuation support**: The coder's fix rounds don't use `continue_session=True` even when the provider supports it.

```diff
--- a/.pi/skills/code-review/code_review.py
+++ b/.pi/skills/code-review/code_review.py
@@ -1326,11 +1326,12 @@ LOOP_REVIEWER_PROMPT = """You are the Reviewer. Critique the Coder's proposed so
 YOUR TASK:
 1. Answer any clarifying questions the Coder raised.
 2. Identify logic assumptions, bugs, or missing requirements.
 3. Verify if the code meets the Acceptance Criteria.
-4. If the solution is solid, start your response with "LGTM".
+4. If the solution is solid and ready to ship, respond with EXACTLY "LGTM" on a line by itself at the start of your response.
 5. If changes are needed, list them clearly.
 6. If YOU have clarifying questions before approving, list them.
+
+IMPORTANT: Only say "LGTM" if NO changes are required. Any feedback means another revision is needed.
 """
 
 LOOP_CODER_FIX_PROMPT = """You are the Coder. Fix your solution based on the Reviewer's feedback.
 
@@ -1623,6 +1624,7 @@ async def _loop_async(
     output_dir: Path,
     save_intermediate: bool,
     reasoning: Optional[str] = None,
+    continue_coder_session: bool = True,
 ) -> dict:
     """Run iterative Coder-Reviewer loop with mixed providers."""
     history = []
@@ -1633,11 +1635,12 @@ async def _loop_async(
     coder_prompt = LOOP_CODER_INIT_PROMPT.format(request=request_content)
     
     coder_output, rc = await _run_provider_async(
         coder_prompt, coder_model, add_dir, 
         log_file=output_dir / "coder_init.log" if save_intermediate else None,
         provider=coder_provider,
-        step_name="[Coder] Initial generation"
+        step_name="[Coder] Initial generation",
+        continue_session=False,  # First call never continues
     )
     if rc != 0: raise typer.Exit(code=1)
     
     if save_intermediate:
@@ -1665,9 +1668,14 @@ async def _loop_async(
         if save_intermediate:
             (output_dir / f"round{i}_review.md").write_text(reviewer_output)
 
-        # LGTM Check (Basic Heuristic)
-        if "LGTM" in reviewer_output.upper().split("\n")[0] or "LOOKS GOOD TO ME" in reviewer_output.upper():
-            typer.echo("\n[Reviewer] PASSED (LGTM detected)", err=True)
+        # LGTM Check: Look for explicit approval signal
+        # Check first few lines for LGTM (may have leading whitespace)
+        first_lines = "\n".join(reviewer_output.strip().split("\n")[:3]).upper()
+        is_lgtm = ("LGTM" in first_lines or 
+                   "LOOKS GOOD TO ME" in first_lines or
+                   "LOOKS GOOD" in first_lines and "APPROVED" in first_lines)
+        if is_lgtm:
+            typer.echo("\n[Reviewer] APPROVED (LGTM detected)", err=True)
             break
 
         # 3. Coder fixes
@@ -1681,7 +1689,9 @@ async def _loop_async(
         coder_output, rc = await _run_provider_async(
             fix_prompt, coder_model, add_dir,
             log_file=output_dir / f"round{i}_fix.log" if save_intermediate else None,
             provider=coder_provider,
-            step_name=f"[Coder] Round {i} Fix"
+            step_name=f"[Coder] Round {i} Fix",
+            # Continue session if provider supports it (maintains context)
+            continue_session=continue_coder_session,
         )
         if rc != 0: raise typer.Exit(code=1)
 
@@ -1719,6 +1729,7 @@ def loop(
     workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Workspace paths"),
     rounds: int = typer.Option(3, "--rounds", "-r", help="Max retries"),
     save_intermediate: bool = typer.Option(False, "--save-intermediate", "-s", help="Save intermediate logs"),
+    output_dir: Path = typer.Option("reviews", "--output-dir", "-o", help="Output directory"),
     reasoning: Optional[str] = typer.Option("high", "--reasoning", help="Reasoning for Reviewer (openai)"),
-    output_dir: Path = typer.Option("reviews", "--output-dir", "-o", help="Output directory"),
 ):
     """Run a feedback loop between a Coder Agent and a Reviewer Agent.
     
@@ -1729,6 +1740,14 @@ def loop(
         typer.echo(f"Error: File not found: {file}", err=True)
         raise typer.Exit(code=1)
         
+    # Validate providers
+    for prov, label in [(coder_provider, "coder"), (reviewer_provider, "reviewer")]:
+        if prov not in PROVIDERS:
+            typer.echo(f"Error: Unknown {label} provider '{prov}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
+            raise typer.Exit(code=1)
+    
     request_content = file.read_text()
     
     # Defaults
--- a/.pi/skills/code-review/SKILL.md
+++ b/.pi/skills/code-review/SKILL.md
@@ -34,9 +34,9 @@ metadata:
 ## Prerequisites
 
 ```bash
 # Check provider CLI availability
-python .agents/skills/code-review/code_review.py check
-python .agents/skills/code-review/code_review.py check --provider anthropic
-python .agents/skills/code-review/code_review.py check --provider openai
-python .agents/skills/code-review/code_review.py check --provider google
+python .pi/skills/code-review/code_review.py check
+python .pi/skills/code-review/code_review.py check --provider anthropic
+python .pi/skills/code-review/code_review.py check --provider openai
+python .pi/skills/code-review/code_review.py check --provider google
 ```
 
 ## Quick Start
@@ -44,19 +44,19 @@ python .agents/skills/code-review/code_review.py check --provider google
 ```bash
 # Single-step review (default: github/copilot)
-python .agents/skills/code-review/code_review.py review --file request.md
+python .pi/skills/code-review/code_review.py review --file request.md
 
 # Use different provider
-python .agents/skills/code-review/code_review.py review --file request.md --provider anthropic
+python .pi/skills/code-review/code_review.py review --file request.md --provider anthropic
 
 # OpenAI with high reasoning
-python .agents/skills/code-review/code_review.py review --file request.md --provider openai --reasoning high
+python .pi/skills/code-review/code_review.py review --file request.md --provider openai --reasoning high
 
 # Include uncommitted local files via workspace
-python .agents/skills/code-review/code_review.py review --file request.md --workspace ./src --workspace ./tests
+python .pi/skills/code-review/code_review.py review --file request.md --workspace ./src --workspace ./tests
 
 # Full 3-step pipeline (generate -> judge -> finalize)
-python .agents/skills/code-review/code_review.py review-full --file request.md
+python .pi/skills/code-review/code_review.py review-full --file request.md
 ```
 
 ## Commands
@@ -79,6 +79,8 @@ python .agents/skills/code-review/code_review.py review-full --file request.md
 ```bash
 code_review.py loop \
   --coder-provider anthropic --coder-model opus-4.5 \
   --reviewer-provider openai --reviewer-model gpt-5.2-codex \
   --rounds 5 --file request.md
 ```
+
+The Reviewer signals approval by responding with "LGTM" at the start of its response. The loop exits early when LGTM is detected.
 
 ### review-full (Single Provider Pipeline)
@@ -148,6 +150,28 @@ python .agents/skills/code-review/code_review.py review \
 
 The workspace is automatically cleaned up after the review completes.
 
+## Single-Shot Review Options
+
+The `review` command has additional options for processing output:
+
+| Option           | Short | Description                           |
+| ---------------- | ----- | ------------------------------------- |
+| `--file`         | `-f`  | Markdown request file (required)      |
+| `--provider`     | `-P`  | Provider (github, anthropic, etc.)    |
+| `--model`        | `-m`  | Model (provider-specific)             |
+| `--workspace`    | `-w`  | Copy local paths to temp workspace    |
+| `--add-dir`      | `-d`  | Add directory for file access         |
+| `--reasoning`    | `-R`  | Reasoning effort (openai only)        |
+| `--raw`          |       | Output raw response (no JSON wrapper) |
+| `--extract-diff` |       | Extract only the diff block           |
+
+```bash
+# Get just the diff, ready to pipe to git apply
+code_review.py review --file request.md --raw --extract-diff > fix.patch
+git apply fix.patch
+```
+
 ## Provider-Specific Notes
 
 ### GitHub Copilot (`github`)
```

This diff addresses:

1. **Improved LGTM detection** - Checks first 3 lines instead of just first line, handles more approval phrases
2. **Provider validation in loop command** - Validates providers before using them
3. **Fixed SKILL.md paths** - Changed `.agents/` to `.pi/`
4. **Added missing documentation** - Documented `--raw` and `--extract-diff` options
5. **Clearer LGTM instruction in prompt** - Made it explicit that LGTM should be on its own line
6. **Session continuation for coder fixes** - Added `continue_session` parameter to maintain context across fix rounds
