> **Review Metadata**: Round 1 | Final Diff | Provider: github | Model: gpt-5
---

```diff
commit: introduce session-based collaborative workflow, structured errors, and robust checkpoints

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
+def start(
+    screenplay: Path = typer.Argument(..., help="Path to screenplay markdown file"),
+    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Base output directory"),
+    fidelity: str = typer.Option("sketch", "--fidelity", "-f", help="Panel fidelity: sketch|reference"),
+    format: str = typer.Option("mp4", "--format", help="Output format: mp4|html|panels"),
+    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON for agent mediation")
+):
+    """
+    Start a session: Parse → ASK → Plan → ASK → Generate → Review → Done
+    Emits JSON with status=needs_input and resume_command when input is required.
+    """
+    from screenplay_parser import parse_file, screenplay_to_dict
+    from camera_planner import generate_shot_plan, shot_plan_to_dict
+    from collaboration import (
+        Phase, generate_session_id, SessionState, StoryboardResult,
+        analyze_screenplay_ambiguities, analyze_shot_plan_for_approval,
+        save_session
+    )
+    # Validate screenplay presence and non-empty
+    if not screenplay.exists():
+        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id="", message=f"Screenplay not found: {screenplay}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
+    try:
+        content = screenplay.read_text()
+    except Exception as e:
+        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id="", message=f"Failed to read screenplay: {e}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
+    if not content.strip():
+        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id="", message="Screenplay is empty")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
+    # Create session and session-specific output dir
+    session_id = generate_session_id()
+    sess_dir = (output_dir / session_id).absolute()
+    sess_dir.mkdir(parents=True, exist_ok=True)
+    state = SessionState(session_id=session_id, phase=Phase.PARSE, screenplay_path=str(screenplay.absolute()))
+    state.answers["_config"] = {"fidelity": fidelity, "format": format, "output_dir": str(sess_dir)}
+    # Parse
+    parsed = parse_file(screenplay)
+    scenes = screenplay_to_dict(parsed)
+    state.parsed_scenes = scenes
+    # Ask clarifying questions about screenplay
+    qs = analyze_screenplay_ambiguities(scenes)
+    if qs:
+        state.questions = [q.to_dict() for q in qs]
+        save_session(state, sess_dir)
+        result = StoryboardResult(
+            status="needs_input",
+            phase=Phase.PARSE,
+            session_id=session_id,
+            questions=qs,
+            partial_results={"scenes_count": len(parsed.scenes)},
+            message=f"Parsed {len(parsed.scenes)} scenes; {len(qs)} question(s) need answers.",
+            resume_command=f"./run.sh continue --session {session_id} --answers '<JSON>'"
+        )
+        typer.echo(result.to_json() if json_output else result.message)
+        return
+    # Generate shot plan and approvals
+    plan = generate_shot_plan(scenes)
+    plan_dict = shot_plan_to_dict(plan)
+    state.shot_plan = plan_dict
+    (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+    approvals = analyze_shot_plan_for_approval(plan_dict)
+    if approvals:
+        state.phase = Phase.CAMERA_PLAN
+        state.questions = [q.to_dict() for q in approvals]
+        save_session(state, sess_dir)
+        result = StoryboardResult(
+            status="needs_input",
+            phase=Phase.CAMERA_PLAN,
+            session_id=session_id,
+            questions=approvals,
+            partial_results={"total_shots": plan.total_shots, "total_duration": plan.total_duration, "shot_plan_file": str(sess_dir / "shot_plan.json")},
+            message="Shot approvals required before panel generation.",
+            resume_command=f"./run.sh continue --session {session_id} --answers '<JSON>'"
+        )
+        typer.echo(result.to_json() if json_output else result.message)
+        return
+    # No approvals needed; proceed to generation
+    state.phase = Phase.GENERATE_PANELS
+    save_session(state, sess_dir)
+    typer.echo(json.dumps({"status": "in_progress", "phase": "generate_panels", "session_id": session_id}) if json_output else f"Session {session_id} ready for panel generation")
+
+@app.command("continue")
+def continue_session(
+    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
+    answers: str = typer.Option("{}", "--answers", "-a", help="JSON answers to previous questions"),
+    search_dir: Path = typer.Option(Path("./output"), "--search-dir", help="Directory containing sessions"),
+    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON for agent mediation")
+):
+    """
+    Continue a session: applies answers, advances phase, asks next questions or completes.
+    """
+    from collaboration import Phase, load_session, find_session, save_session, StoryboardResult
+    from camera_planner import generate_shot_plan, shot_plan_to_dict
+    from panel_generator import generate_panels
+    from animatic_assembler import assemble
+    # Locate session
+    sess_path = find_session(session, search_dir)
+    if not sess_path:
+        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id=session, message=f"Session not found: {session}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
+    state = load_session(sess_path)
+    sess_dir = sess_path.parent
+    # Merge answers
+    try:
+        provided = json.loads(answers)
+    except json.JSONDecodeError as e:
+        result = StoryboardResult(status="error", phase=state.phase, session_id=state.session_id, message=f"Invalid JSON in answers: {e}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
+    state.answers.update(provided)
+    # Advance phases
+    if state.phase == Phase.PARSE:
+        # Re-plan shots using updated answers if needed
+        plan = generate_shot_plan(state.parsed_scenes or {})
+        plan_dict = shot_plan_to_dict(plan)
+        state.shot_plan = plan_dict
+        (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+        state.phase = Phase.CAMERA_PLAN
+        save_session(state, sess_dir)
+        from collaboration import analyze_shot_plan_for_approval
+        approvals = analyze_shot_plan_for_approval(plan_dict)
+        if approvals:
+            state.questions = [q.to_dict() for q in approvals]
+            save_session(state, sess_dir)
+            result = StoryboardResult(
+                status="needs_input",
+                phase=Phase.CAMERA_PLAN,
+                session_id=state.session_id,
+                questions=approvals,
+                partial_results={"total_shots": plan.total_shots, "total_duration": plan.total_duration},
+                message="Shot approvals required.",
+                resume_command=f"./run.sh continue --session {state.session_id} --answers '<JSON>'"
+            )
+            typer.echo(result.to_json() if json_output else result.message)
+            return
+    if state.phase == Phase.CAMERA_PLAN:
+        # Proceed to panel generation
+        state.phase = Phase.GENERATE_PANELS
+        save_session(state, sess_dir)
+        config = state.answers.get("_config", {})
+        fidelity = config.get("fidelity", "sketch")
+        panels_dir = sess_dir / "panels"
+        try:
+            paths = generate_panels(state.shot_plan or {}, panels_dir, fidelity=fidelity)
+        except RuntimeError as re:
+            # Structured error for unsupported fidelity
+            result = StoryboardResult(
+                status="error",
+                phase=Phase.GENERATE_PANELS,
+                session_id=state.session_id,
+                message=f"{re}. Hint: use fidelity='sketch' or 'reference', or call /create-image per panel."
+            )
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
+        except Exception as e:
+            result = StoryboardResult(status="error", phase=Phase.GENERATE_PANELS, session_id=state.session_id, message=f"Panel generation failed: {e}")
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
+        state.panels = [str(p) for p in paths]
+        (panels_dir / "shot_plan.json").write_text(json.dumps(state.shot_plan or {}, indent=2))
+        state.phase = Phase.ASSEMBLE
+        save_session(state, sess_dir)
+        typer.echo(json.dumps({"status": "in_progress", "phase": "assemble", "session_id": state.session_id, "panels_generated": len(paths)}) if json_output else f"Generated {len(paths)} panels; assembling…")
+    if state.phase == Phase.ASSEMBLE:
+        config = state.answers.get("_config", {})
+        output_format = config.get("format", "mp4")
+        panels_dir = sess_dir / "panels"
+        plan_path = panels_dir / "shot_plan.json"
+        # Determine output path
+        output_path = sess_dir / ("storyboard.html" if output_format == "html" else "animatic.mp4")
+        try:
+            final_path = assemble(panels_dir, plan_path, output_path, output_format)
+            state.phase = Phase.COMPLETE
+            state.output_path = str(final_path)
+            save_session(state, sess_dir)
+            result = StoryboardResult(
+                status="complete",
+                phase=Phase.COMPLETE,
+                session_id=state.session_id,
+                output_files=[str(final_path), str(panels_dir), str(plan_path)],
+                message=f"Storyboard complete: {final_path}"
+            )
+            typer.echo(result.to_json() if json_output else result.message)
+        except FileNotFoundError as e:
+            result = StoryboardResult(status="error", phase=Phase.ASSEMBLE, session_id=state.session_id, message=f"Assembly failed (missing dependency): {e}")
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
+        except Exception as e:
+            result = StoryboardResult(status="error", phase=Phase.ASSEMBLE, session_id=state.session_id, message=f"Assembly error: {e}. Panels at {panels_dir}")
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
+
+@app.command()
+def status(
+    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
+    search_dir: Path = typer.Option(Path("./output"), "--search-dir", help="Directory containing sessions"),
+    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON")
+):
+    """Report current session status and next resume command."""
+    from collaboration import Phase, load_session, find_session, StoryboardResult, Question
+    sess_path = find_session(session, search_dir)
+    if not sess_path:
+        typer.echo(json.dumps({"status": "error", "message": f"Session not found: {session}"}) if json_output else f"Session not found: {session}")
+        raise typer.Exit(1)
+    state = load_session(sess_path)
+    result = StoryboardResult(
+        status="complete" if state.phase == Phase.COMPLETE else "in_progress",
+        phase=state.phase,
+        session_id=state.session_id,
+        questions=[Question(**q) for q in state.questions] if state.questions else [],
+        partial_results={
+            "scenes": len(state.parsed_scenes.get("scenes", [])) if state.parsed_scenes else 0,
+            "shots": state.shot_plan.get("total_shots", 0) if state.shot_plan else 0,
+            "panels": len(state.panels)
+        },
+        output_files=[state.output_path] if state.output_path else [],
+        message=f"Phase: {state.phase.value}",
+        resume_command=f"./run.sh continue --session {state.session_id} --answers '<JSON>'" if state.phase != Phase.COMPLETE else ""
+    )
+    typer.echo(result.to_json() if json_output else result.message)
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
+    beat_position: str = "middle"
+) -> str:
@@
-    # Fall back to scene type patterns
-    if scene_type.lower() in SCENE_PATTERNS:
+    # Fall back to scene type patterns
+    if scene_type.lower() in SCENE_PATTERNS:
         pattern = SCENE_PATTERNS[scene_type.lower()]
         position_map = {
             "opening": 0,
             "middle": len(pattern) // 2,
             "climax": -2 if len(pattern) > 2 else -1,
             "closing": -1
         }
         idx = position_map.get(beat_position, 1)
         return pattern[idx]
 
-    return "MS"  # DEFAULT - no user consultation
+    # Default conservative shot; ambiguities are surfaced by orchestrator via approval questions
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
+            # Explicitly fail to avoid silent stub behavior; orchestrator will emit a structured error
+            raise RuntimeError("fidelity='generated' is not implemented; use 'sketch' or 'reference'")
```


Total usage est:       1 Premium request
Total duration (API):  34.6s
Total duration (wall): 36.1s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                38.8k input, 3.8k output, 0 cache read, 0 cache write (Est. 1 Premium request)
