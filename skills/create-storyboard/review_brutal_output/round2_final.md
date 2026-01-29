> **Review Metadata**: Round 2 | Final Diff | Provider: github | Model: gpt-5
---

```diff
commit: add guarded collaboration imports, shot plan validation, and apply approvals before generation

*** a/.pi/skills/create-storyboard/orchestrator.py
--- b/.pi/skills/create-storyboard/orchestrator.py
@@
 @app.command()
 def start(
     screenplay: Path = typer.Argument(..., help="Path to screenplay markdown file"),
     output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Base output directory"),
     fidelity: str = typer.Option("sketch", "--fidelity", "-f", help="Panel fidelity: sketch|reference"),
     format: str = typer.Option("mp4", "--format", help="Output format: mp4|html|panels"),
     json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON for agent mediation")
 ):
@@
-    from screenplay_parser import parse_file, screenplay_to_dict
-    from camera_planner import generate_shot_plan, shot_plan_to_dict
-    from collaboration import (
-        Phase, generate_session_id, SessionState, StoryboardResult,
-        analyze_screenplay_ambiguities, analyze_shot_plan_for_approval,
-        save_session
-    )
+    from screenplay_parser import parse_file, screenplay_to_dict
+    from camera_planner import generate_shot_plan, shot_plan_to_dict
+    try:
+        from collaboration import (
+            Phase, generate_session_id, SessionState, StoryboardResult,
+            analyze_screenplay_ambiguities, analyze_shot_plan_for_approval,
+            save_session
+        )
+    except Exception as e:
+        # Structured error if collaboration utilities are unavailable
+        typer.echo(json.dumps({
+            "status": "error",
+            "phase": "parse",
+            "message": f"Collaboration module missing or incompatible: {e}"
+        }) if json_output else f"Collaboration module missing or incompatible: {e}")
+        raise typer.Exit(1)
@@
-    sess_dir = (output_dir / session_id).absolute()
-    sess_dir.mkdir(parents=True, exist_ok=True)
+    sess_dir = (output_dir / session_id).absolute()
+    try:
+        sess_dir.mkdir(parents=True, exist_ok=True)
+    except OSError as e:
+        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id=session_id, message=f"Cannot create session directory: {e}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
@@
-    (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+    try:
+        (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+    except OSError as e:
+        result = StoryboardResult(status="error", phase=Phase.CAMERA_PLAN, session_id=session_id, message=f"Failed to persist shot plan: {e}")
+        typer.echo(result.to_json() if json_output else result.message)
+        raise typer.Exit(1)
@@
 @app.command("continue")
 def continue_session(
     session: str = typer.Option(..., "--session", "-s", help="Session ID"),
     answers: str = typer.Option("{}", "--answers", "-a", help="JSON answers to previous questions"),
     search_dir: Path = typer.Option(Path("./output"), "--search-dir", help="Directory containing sessions"),
     json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON for agent mediation")
 ):
@@
-    from collaboration import Phase, load_session, find_session, save_session, StoryboardResult
+    try:
+        from collaboration import Phase, load_session, find_session, save_session, StoryboardResult
+    except Exception as e:
+        typer.echo(json.dumps({
+            "status": "error",
+            "phase": "parse",
+            "message": f"Collaboration module missing or incompatible: {e}"
+        }) if json_output else f"Collaboration module missing or incompatible: {e}")
+        raise typer.Exit(1)
     from camera_planner import generate_shot_plan, shot_plan_to_dict
     from panel_generator import generate_panels
     from animatic_assembler import assemble
@@
-    state.answers.update(provided)
+    state.answers.update(provided)
@@
-    if state.phase == Phase.PARSE:
+    if state.phase == Phase.PARSE:
         plan = generate_shot_plan(state.parsed_scenes or {})
         plan_dict = shot_plan_to_dict(plan)
         state.shot_plan = plan_dict
-        (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+        try:
+            (sess_dir / "shot_plan.json").write_text(json.dumps(plan_dict, indent=2))
+        except OSError as e:
+            result = StoryboardResult(status="error", phase=Phase.CAMERA_PLAN, session_id=state.session_id, message=f"Failed to persist shot plan: {e}")
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
@@
-    if state.phase == Phase.CAMERA_PLAN:
+    if state.phase == Phase.CAMERA_PLAN:
+        # Apply approvals/overrides to shot plan before generation
+        approvals_input = provided.get("approvals") or state.answers.get("approvals")
+        if approvals_input and state.shot_plan and isinstance(state.shot_plan.get("shots"), list):
+            shots = state.shot_plan["shots"]
+            # approvals format: { "<scene>-<shot>": { "approve": bool, "shot_code": "CU", "duration": 2.5 } }
+            for key, override in approvals_input.items():
+                try:
+                    s_str, sh_str = key.split("-")
+                    s_num = int(s_str)
+                    sh_num = int(sh_str)
+                except Exception:
+                    continue
+                for shot in shots:
+                    if shot.get("scene_number") == s_num and shot.get("shot_number") == sh_num:
+                        if override.get("approve") is False:
+                            # simple skip: mark zero duration
+                            shot["duration"] = 0.0
+                        if "shot_code" in override and override["shot_code"]:
+                            shot["shot_code"] = override["shot_code"]
+                        if "duration" in override and isinstance(override["duration"], (int, float)):
+                            shot["duration"] = float(override["duration"])
+            # Persist modified plan
+            try:
+                (sess_dir / "shot_plan.json").write_text(json.dumps(state.shot_plan, indent=2))
+            except OSError:
+                pass
+        # Validate shot plan structure before generation
+        if not state.shot_plan or not isinstance(state.shot_plan.get("shots"), list) or not state.shot_plan["shots"]:
+            result = StoryboardResult(
+                status="error",
+                phase=Phase.GENERATE_PANELS,
+                session_id=state.session_id,
+                message="Invalid or empty shot plan; ensure planning completed and approvals applied."
+            )
+            typer.echo(result.to_json() if json_output else result.message)
+            raise typer.Exit(1)
         state.phase = Phase.GENERATE_PANELS
         save_session(state, sess_dir)
         config = state.answers.get("_config", {})
         fidelity = config.get("fidelity", "sketch")
         panels_dir = sess_dir / "panels"
         try:
-            paths = generate_panels(state.shot_plan or {}, panels_dir, fidelity=fidelity)
+            paths = generate_panels(state.shot_plan, panels_dir, fidelity=fidelity)
         except RuntimeError as re:
             result = StoryboardResult(
                 status="error",
                 phase=Phase.GENERATE_PANELS,
                 session_id=state.session_id,
                 message=f"{re}. Hint: use fidelity='sketch' or 'reference', or call /create-image per panel."
             )
             typer.echo(result.to_json() if json_output else result.message)
             raise typer.Exit(1)
         except Exception as e:
             result = StoryboardResult(status="error", phase=Phase.GENERATE_PANELS, session_id=state.session_id, message=f"Panel generation failed: {e}")
             typer.echo(result.to_json() if json_output else result.message)
             raise typer.Exit(1)
         state.panels = [str(p) for p in paths]
-        (panels_dir / "shot_plan.json").write_text(json.dumps(state.shot_plan or {}, indent=2))
+        try:
+            (panels_dir / "shot_plan.json").write_text(json.dumps(state.shot_plan, indent=2))
+        except OSError:
+            pass
         state.phase = Phase.ASSEMBLE
         save_session(state, sess_dir)
         typer.echo(json.dumps({"status": "in_progress", "phase": "assemble", "session_id": state.session_id, "panels_generated": len(paths)}) if json_output else f"Generated {len(paths)} panels; assembling…")
     if state.phase == Phase.ASSEMBLE:
         config = state.answers.get("_config", {})
         output_format = config.get("format", "mp4")
         panels_dir = sess_dir / "panels"
         plan_path = panels_dir / "shot_plan.json"
         output_path = sess_dir / ("storyboard.html" if output_format == "html" else "animatic.mp4")
         try:
             final_path = assemble(panels_dir, plan_path, output_path, output_format)
             state.phase = Phase.COMPLETE
             state.output_path = str(final_path)
             save_session(state, sess_dir)
             result = StoryboardResult(
                 status="complete",
                 phase=Phase.COMPLETE,
                 session_id=state.session_id,
                 output_files=[str(final_path), str(panels_dir), str(plan_path)],
                 message=f"Storyboard complete: {final_path}"
             )
             typer.echo(result.to_json() if json_output else result.message)
         except FileNotFoundError as e:
             result = StoryboardResult(status="error", phase=Phase.ASSEMBLE, session_id=state.session_id, message=f"Assembly failed (missing dependency): {e}")
             typer.echo(result.to_json() if json_output else result.message)
             raise typer.Exit(1)
         except Exception as e:
             result = StoryboardResult(status="error", phase=Phase.ASSEMBLE, session_id=state.session_id, message=f"Assembly error: {e}. Panels at {panels_dir}")
             typer.echo(result.to_json() if json_output else result.message)
             raise typer.Exit(1)
*** a/.pi/skills/create-storyboard/camera_planner.py
--- b/.pi/skills/create-storyboard/camera_planner.py
@@
 def auto_select_shot(
     scene_type: str,
     emotion: Optional[str] = None,
     beat_position: str = "middle"
 ) -> str:
@@
-    return "MS"  # DEFAULT - no user consultation
+    # Default conservative shot; ambiguities are surfaced by orchestrator via approval questions
+    return "MS"
*** a/.pi/skills/create-storyboard/panel_generator.py
--- b/.pi/skills/create-storyboard/panel_generator.py
@@
         elif fidelity == 'generated':
             # Explicitly fail to avoid silent stub behavior; orchestrator will emit a structured error
             raise RuntimeError("fidelity='generated' is not implemented; use 'sketch' or 'reference'")
```


Total usage est:       1 Premium request
Total duration (API):  19.8s
Total duration (wall): 21.6s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                61.2k input, 2.6k output, 0 cache read, 0 cache write (Est. 1 Premium request)
