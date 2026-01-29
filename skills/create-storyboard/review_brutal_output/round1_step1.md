> **Review Metadata**: Round 1 | Step 1 | Provider: github | Model: gpt-5
---

✓ Read orchestrator.py (580 lines)

✓ Read screenplay_parser.py (371 lines)

✓ Read camera_planner.py (329 lines)

✓ Read panel_generator.py (345 lines)

Clarifying questions:
- Should the collaboration protocol be JSON-only with a “needs_input” status and resume command, or do you prefer an explicit --interactive CLI mode with human-readable prompts?
- How should shot approval be expressed: per-shot approve/modify/skip, or batch defaults with overrides?
- For /create-movie integration, do you want file-based session handoff (JSON in output dir) or Python API import?

```diff
*** a/.pi/skills/create-storyboard/orchestrator.py
--- b/.pi/skills/create-storyboard/orchestrator.py
@@
-@app.command()
-def create(
-    screenplay: Path = typer.Argument(...),
-    output: Path = typer.Option(Path("animatic.mp4")),
-    fidelity: str = typer.Option("sketch"),
-    format: str = typer.Option("mp4"),
-    duration: Optional[float] = typer.Option(None),
-    store_learnings: bool = typer.Option(True)
-):
-    """
-    PROBLEM: This runs end-to-end with ZERO checkpoints.
-    No way for calling agent to:
-    1. Review parsed scenes before planning
-    2. Approve shot selections
-    3. Preview panels before assembly
-    """
-    typer.echo(f"🎬 Creating storyboard from {screenplay}")
-
-    # Phase 1: Parse - NO CHECKPOINT
-    parsed = parse_file(screenplay)
-
-    # Phase 2: Camera Planning - NO CHECKPOINT
-    shot_plan = generate_shot_plan(scenes_data)
-
-    # Phase 3: Generate Panels - NO CHECKPOINT
-    panel_paths = generate_panels(plan_data, panels_dir, fidelity=fidelity)
-
-    # Phase 4: Assemble - FINAL OUTPUT, TOO LATE TO CHANGE
-    result = assemble(panels_dir, plan_path, output, format)
+@app.command()
+def create(
+    screenplay: Path = typer.Argument(...),
+    output: Path = typer.Option(Path("animatic.mp4")),
+    fidelity: str = typer.Option("sketch"),
+    format: str = typer.Option("mp4"),
+    duration: Optional[float] = typer.Option(None),
+    store_learnings: bool = typer.Option(False, help="Stub: not implemented, will error if True"),
+    interactive: bool = typer.Option(False, help="Enable collaborative checkpoints"),
+    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON with needs_input and resume command")
+):
+    """
+    Collaborative workflow:
+    Parse → ASK → Plan → ASK → Generate → Review → Done
+    """
+    typer.echo(f"🎬 Creating storyboard from {screenplay}")
+    if store_learnings:
+        typer.echo("⚠️ store_learnings is not implemented; set to False.", err=True)
+        raise typer.Exit(1)
+    if not screenplay.exists() or not screenplay.read_text().strip():
+        typer.echo("❌ Screenplay missing or empty.", err=True)
+        raise typer.Exit(1)
+    # Phase 1: Parse
+    parsed = parse_file(screenplay)
+    scenes_data = screenplay_to_dict(parsed)
+    if interactive:
+        # Emit questions about ambiguities
+        from collaboration import analyze_screenplay_ambiguities
+        qs = analyze_screenplay_ambiguities(scenes_data)
+        if qs:
+            payload = {
+                "status": "needs_input",
+                "phase": "parse",
+                "questions": [q.to_dict() for q in qs],
+                "partial_results": {"scenes_count": len(parsed.scenes)},
+                "resume_command": "./run.sh continue --session <ID> --answers '<JSON>'"
+            }
+            if json_output:
+                typer.echo(json.dumps(payload))
+            else:
+                typer.echo("Questions found; please provide answers via --json resume flow.", err=True)
+            return
+    # Phase 2: Camera Planning
+    shot_plan = generate_shot_plan(scenes_data)
+    plan_data = shot_plan_to_dict(shot_plan)
+    if interactive:
+        from collaboration import analyze_shot_plan_for_approval
+        qs = analyze_shot_plan_for_approval(plan_data)
+        if qs:
+            payload = {
+                "status": "needs_input",
+                "phase": "camera_plan",
+                "questions": [q.to_dict() for q in qs],
+                "partial_results": {
+                    "total_shots": shot_plan.total_shots,
+                    "total_duration": shot_plan.total_duration
+                },
+                "resume_command": "./run.sh continue --session <ID> --answers '<JSON>'"
+            }
+            typer.echo(json.dumps(payload) if json_output else "Shot approvals needed.", err=True)
+            return
+    # Phase 3: Generate Panels
+    panels_dir = output.parent / "panels"
+    try:
+        panel_paths = generate_panels(plan_data, panels_dir, fidelity=fidelity)
+    except Exception as e:
+        typer.echo(f"❌ Panel generation failed: {e}", err=True)
+        raise typer.Exit(1)
+    if interactive:
+        payload = {
+            "status": "in_progress",
+            "phase": "generate_panels",
+            "partial_results": {"panels_generated": len(panel_paths)},
+            "output_files": [str(p) for p in panel_paths[:5]]
+        }
+        typer.echo(json.dumps(payload) if json_output else f"Generated {len(panel_paths)} panels.")
+    # Phase 4: Assemble
+    plan_path = panels_dir / "shot_plan.json"
+    plan_path.write_text(json.dumps(plan_data, indent=2))
+    try:
+        result = assemble(panels_dir, plan_path, output, format)
+    except Exception as e:
+        typer.echo(f"❌ Assembly failed: {e}", err=True)
+        typer.echo(f"Panels available at {panels_dir}", err=True)
+        raise typer.Exit(1)
+    typer.echo(f"✅ Output: {result}")
*** a/.pi/skills/create-storyboard/camera_planner.py
--- b/.pi/skills/create-storyboard/camera_planner.py
@@
-def auto_select_shot(
-    scene_type: str,
-    emotion: Optional[str] = None,
-    beat_position: str = "middle"
-) -> str:
+def auto_select_shot(
+    scene_type: str,
+    emotion: Optional[str] = None,
+    beat_position: str = "middle",
+    confirm_on_ambiguity: bool = True
+) -> str:
@@
-    # Fall back to scene type patterns
+    # Fall back to scene type patterns
     if scene_type.lower() in SCENE_PATTERNS:
         pattern = SCENE_PATTERNS[scene_type.lower()]
         position_map = {
             "opening": 0,
             "middle": len(pattern) // 2,
             "climax": -2 if len(pattern) > 2 else -1,
             "closing": -1
         }
         idx = position_map.get(beat_position, 1)
         return pattern[idx]
-
-    return "MS"  # DEFAULT - no user consultation
+    # Ambiguity: unknown scene type
+    if confirm_on_ambiguity:
+        return "ASK:unknown_scene_type"  # signal orchestrator to ask
+    return "MS"
*** a/.pi/skills/create-storyboard/panel_generator.py
--- b/.pi/skills/create-storyboard/panel_generator.py
@@
-        elif fidelity == 'generated':
-            # For generated, we create a reference panel with a note
-            # Actual AI generation would call /create-image skill
-            generate_reference_panel(shot, config, output_path)  # <-- STUB!
-            # TODO: Integrate with /create-image skill for AI generation
+        elif fidelity == 'generated':
+            # Explicitly fail to avoid silent stub behavior
+            raise RuntimeError("fidelity='generated' is not implemented; use 'sketch' or 'reference'")
```

CRITICAL issues to fix:
- Lack of collaborative checkpoints; add JSON “needs_input” questions and resume flow.
- Silent aspirational stubs (generated fidelity, store_learnings); make them explicit errors.
- Brittle defaults in auto_select_shot; signal ambiguity to orchestrator instead of forcing “MS”.
- Missing error handling for empty screenplay and assembly/panel generation failures; add validations and try/except.

Overengineered features to simplify:
- Remove or error for unimplemented store_learnings until memory_bridge is real.
- Avoid complex creative suggestion loops unless answers are consumed; start with shot approval questions only.

Missing features for collaborative use:
- Session management and resume commands for /create-movie mediation.
- Structured question objects and JSON outputs per phase.
- Shot approval hooks and screenplay ambiguity questions.

Recommendations:
- Adopt a session-based CLI with start/continue/status commands emitting JSON for agent orchestration.
- Gate aspirational features behind explicit flags that error with clear guidance.
- Introduce a lightweight question schema and map planner/ parser ambiguities to it.
- Use file-based handoff (output_dir/session_id with JSON artifacts) for simple integration with /create-movie.


Total usage est:       1 Premium request
Total duration (API):  23.2s
Total duration (wall): 24.9s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                40.5k input, 2.4k output, 0 cache read, 0 cache write (Est. 1 Premium request)
