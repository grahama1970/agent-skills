#!/usr/bin/env python3
"""
Create-Storyboard Orchestrator (Collaborative Version)

Main CLI entry point with support for human-agent collaboration loop.
Each phase returns structured JSON and pauses for input when needed.

COLLABORATION PATTERN:
1. Agent calls: ./run.sh start screenplay.md
2. Skill returns: {status: "needs_input", questions: [...], session_id: "abc"}
3. Agent answers questions (or user provides input)
4. Agent calls: ./run.sh continue --session abc --answers '{"q1": "answer"}'
5. Skill proceeds to next phase or returns more questions
6. Repeat until status: "complete"
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from screenplay_parser import parse_file, parse_screenplay, screenplay_to_dict, Screenplay
from camera_planner import generate_shot_plan, shot_plan_to_dict
from panel_generator import generate_panels, PanelConfig
from animatic_assembler import assemble, AnimaticConfig
try:
    from collaboration import (
        Phase, Question, SessionState, StoryboardResult,
        generate_session_id, save_session, load_session, find_session,
        analyze_screenplay_ambiguities, analyze_shot_plan_for_approval,
        format_questions_for_display, apply_answers_to_scenes
    )
except ImportError:
    # We'll handle this in the commands to provide structured errors if needed
    Phase = None
from creative_suggestions import (
    analyze_scene_for_suggestions, format_suggestions_for_conversation,
    CreativeSuggestion
)
from memory_bridge import (
    recall_film_reference, enhance_suggestions_with_memory,
    learn_technique, MEMORY_SCOPE
)

app = typer.Typer(
    name="create-storyboard",
    help="Transform screenplay to animatic with collaborative human-agent workflow"
)


def output_result(result: StoryboardResult, json_output: bool = False):
    """Output result in requested format."""
    if json_output:
        typer.echo(result.to_json())
    else:
        # Human-readable output
        typer.echo(f"\n{'='*60}")
        typer.echo(f"📊 Status: {result.status.upper()}")
        typer.echo(f"📍 Phase: {result.phase.value}")
        typer.echo(f"🔑 Session: {result.session_id}")
        typer.echo(f"{'='*60}")
        
        if result.message:
            typer.echo(f"\n{result.message}")
        
        if result.questions:
            typer.echo(format_questions_for_display(result.questions))
        
        if result.output_files:
            typer.echo("\n📁 Output files:")
            for f in result.output_files:
                typer.echo(f"   - {f}")
        
        if result.resume_command:
            typer.echo(f"\n▶️  To continue: {result.resume_command}")
        
        typer.echo("")


@app.command()
def start(
    screenplay: Path = typer.Argument(..., help="Path to screenplay markdown file"),
    output_dir: Path = typer.Option(Path("./output"), "--output-dir", "-o", help="Output directory"),
    fidelity: str = typer.Option("sketch", "--fidelity", "-f", help="Panel fidelity: sketch|reference"),
    format: str = typer.Option("mp4", "--format", help="Output format: mp4|html|panels"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip all questions, use defaults"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output structured JSON for agent consumption")
):
    """
    Start a new storyboard session. Returns questions if input needed.
    
    AGENT WORKFLOW:
    1. Call 'start screenplay.md --json'
    2. Check response.status
    3. If "needs_input": answer questions and call 'continue'
    4. If "complete": collect output files
    """
    # Validate input
    if not screenplay.exists():
        result = StoryboardResult(
            status="error",
            phase=Phase.PARSE,
            session_id="",
            message=f"Screenplay file not found: {screenplay}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    
    # Basic binary/empty validation
    try:
        with open(screenplay, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                result = StoryboardResult(
                    status="error",
                    phase=Phase.PARSE,
                    session_id="",
                    message=f"File appears to be binary: {screenplay}. Please provide a markdown screenplay."
                )
                output_result(result, json_output)
                raise typer.Exit(1)
            if not chunk.strip():
                result = StoryboardResult(
                    status="error",
                    phase=Phase.PARSE,
                    session_id="",
                    message=f"Screenplay file is empty: {screenplay}"
                )
                output_result(result, json_output)
                raise typer.Exit(1)
    except Exception as e:
        if isinstance(e, typer.Exit): raise
        result = StoryboardResult(status="error", phase=Phase.PARSE, session_id="", message=f"Error reading file: {e}")
        output_result(result, json_output)
        raise typer.Exit(1)
    
    # Create session
    session_id = generate_session_id()
    sess_dir = (output_dir / session_id).absolute()
    try:
        sess_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        result = StoryboardResult(
            status="error",
            phase=Phase.PARSE,
            session_id=session_id,
            message=f"Failed to create session directory: {e}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    
    state = SessionState(
        session_id=session_id,
        phase=Phase.PARSE,
        screenplay_path=str(screenplay.absolute()),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Store config in session
    state.answers['_config'] = {
        'fidelity': fidelity,
        'format': format,
        'auto_approve': auto_approve,
        'output_dir': str(output_dir)
    }
    
    # Phase 1: Parse
    try:
        parsed = parse_file(screenplay)
        if not parsed.scenes:
            result = StoryboardResult(
                status="error",
                phase=Phase.PARSE,
                session_id=session_id,
                message=f"No scenes found in screenplay. Ensure headings use INT./EXT. format."
            )
            output_result(result, json_output)
            raise typer.Exit(1)
        
        scenes_data = screenplay_to_dict(parsed)
        state.parsed_scenes = scenes_data
        
    except Exception as e:
        result = StoryboardResult(
            status="error",
            phase=Phase.PARSE,
            session_id=session_id,
            message=f"Parse error: {str(e)}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    
    # Analyze for questions
    questions = analyze_screenplay_ambiguities(scenes_data)
    
    if questions and not auto_approve:
        # Save session and return questions
        state.phase = Phase.PARSE
        state.questions = [q.to_dict() for q in questions]
        save_session(state, output_dir)
        
        result = StoryboardResult(
            status="needs_input",
            phase=Phase.PARSE,
            session_id=session_id,
            questions=questions,
            partial_results={"scenes_count": len(parsed.scenes)},
            message=f"Parsed {len(parsed.scenes)} scenes. {len(questions)} question(s) need answers before proceeding.",
            resume_command=f"./run.sh continue --session {session_id} --answers '<JSON>'"
        )
        output_result(result, json_output)
        return
    
    # No questions or auto-approve - proceed to camera planning
    state.phase = Phase.CAMERA_PLAN
    save_session(state, output_dir)
    
    # Continue to next phase
    _execute_camera_plan(state, output_dir, json_output)


@app.command("continue")
def continue_session(
    session: str = typer.Option(..., "--session", "-s", help="Session ID to continue"),
    answers: str = typer.Option("{}", "--answers", "-a", help="JSON answers to questions"),
    search_dir: Path = typer.Option(Path("./output"), "--search-dir", help="Directory to search for session"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output structured JSON")
):
    """
    Continue an existing session with answers to previous questions.
    
    AGENT WORKFLOW:
    1. Receive "needs_input" from previous call
    2. Process questions, determine answers
    3. Call 'continue --session ID --answers JSON'
    4. Check response for more questions or completion
    """
    # Find session
    session_path = find_session(session, search_dir)
    if not session_path:
        result = StoryboardResult(
            status="error",
            phase=Phase.PARSE,
            session_id=session,
            message=f"Session not found: {session}. Search in: {search_dir}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    
    # Load session
    state = load_session(session_path)
    output_dir = session_path.parent
    
    # Parse answers
    try:
        answer_dict = json.loads(answers)
        state.answers.update(answer_dict)
    except json.JSONDecodeError as e:
        result = StoryboardResult(
            status="error",
            phase=state.phase,
            session_id=state.session_id,
            message=f"Invalid JSON in answers: {e}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    
    # Advance
    if state.phase == Phase.PARSE:
        # Apply emotion/reference answers to scenes
        if state.parsed_scenes:
            state.parsed_scenes, invalid_ids = apply_answers_to_scenes(state.parsed_scenes, answer_dict)
            if invalid_ids and not json_output:
                typer.echo(f"⚠️ Warning: Some answer IDs were not recognized or mapped: {', '.join(invalid_ids)}", err=True)
        
        state.phase = Phase.CAMERA_PLAN
        save_session(state, output_dir)
        _execute_camera_plan(state, output_dir, json_output)
    
    elif state.phase == Phase.CAMERA_PLAN:
        # Apply approvals/overrides to shot plan before generation
        # approvals format in answers: { "approvals": { "1-1": { "approve": true, ... }, "1-2": { "shot_code": "CU" } } }
        approvals_input = answer_dict.get("approvals")
        if approvals_input and state.shot_plan and isinstance(state.shot_plan.get("shots"), list):
            shots = state.shot_plan["shots"]
            for key, override in approvals_input.items():
                try:
                    s_str, sh_str = key.split("-")
                    s_num = int(s_str)
                    sh_num = int(sh_str)
                except (ValueError, AttributeError):
                    continue
                
                for shot in shots:
                    if shot.get("scene_number") == s_num and shot.get("shot_number") == sh_num:
                        if override.get("approve") is False:
                            # Skip shot: mark zero duration
                            shot["duration"] = 0.0
                        if "shot_code" in override and override["shot_code"]:
                            shot["shot_code"] = override["shot_code"]
                        if "duration" in override and isinstance(override["duration"], (int, float)):
                            shot["duration"] = float(override["duration"])
            
            # Persist modified plan
            try:
                plan_path = output_dir / "shot_plan.json"
                plan_path.write_text(json.dumps(state.shot_plan, indent=2))
            except OSError as e:
                typer.echo(f"⚠️ Warning: Failed to persist modified shot plan: {e}", err=True)
        
        # Validate shot plan structure before generation
        if not state.shot_plan or not isinstance(state.shot_plan.get("shots"), list) or not state.shot_plan["shots"]:
            result = StoryboardResult(
                status="error",
                phase=Phase.GENERATE_PANELS,
                session_id=state.session_id,
                message="Invalid or empty shot plan. Ensure planning completed and approvals applied."
            )
            output_result(result, json_output)
            raise typer.Exit(1)
            
        state.phase = Phase.GENERATE_PANELS
        save_session(state, output_dir)
        _execute_generate_panels(state, output_dir, json_output)
    
    elif state.phase == Phase.GENERATE_PANELS:
        state.phase = Phase.ASSEMBLE
        save_session(state, output_dir)
        _execute_assemble(state, output_dir, json_output)
    
    else:
        result = StoryboardResult(
            status="complete",
            phase=state.phase,
            session_id=state.session_id,
            message="Session already complete."
        )
        output_result(result, json_output)


def _execute_camera_plan(state: SessionState, output_dir: Path, json_output: bool):
    """Execute camera planning phase with creative suggestions."""
    config = state.answers.get('_config', {})
    auto_approve = config.get('auto_approve', False)
    
    # Generate creative suggestions for each scene
    all_suggestions = []
    for scene in state.parsed_scenes.get('scenes', []):
        scene_suggestions = analyze_scene_for_suggestions(scene, scene.get('number', 1))
        all_suggestions.extend(scene_suggestions)
    
    # Enhance suggestions with memory (learned techniques)
    if all_suggestions:
        all_suggestions = enhance_suggestions_with_memory(all_suggestions, state.parsed_scenes)
    
    # Generate shot plan
    shot_plan = generate_shot_plan(state.parsed_scenes)
    plan_data = shot_plan_to_dict(shot_plan)
    state.shot_plan = plan_data
    
    # Save shot plan to file
    plan_path = output_dir / "shot_plan.json"
    try:
        plan_path.write_text(json.dumps(plan_data, indent=2))
    except OSError as e:
        typer.echo(f"⚠️ Warning: Failed to save shot plan: {e}", err=True)
    
    # Save creative suggestions
    suggestions_path = output_dir / "creative_suggestions.json"
    try:
        suggestions_path.write_text(json.dumps(
            [s.to_dict() if hasattr(s, 'to_dict') else s for s in all_suggestions],
            indent=2
        ))
    except OSError as e:
        typer.echo(f"⚠️ Warning: Failed to save suggestions: {e}", err=True)
    
    # Combine approval questions with creative suggestions
    approval_questions = analyze_shot_plan_for_approval(plan_data)
    
    # Convert suggestions to questions for the collaboration loop
    suggestion_questions = []
    for s in all_suggestions:
        s_dict = s.to_dict() if hasattr(s, 'to_dict') else s
        suggestion_questions.append(Question(
            id=s_dict.get('id', f"suggestion_{len(suggestion_questions)}"),
            scene_number=s_dict.get('scene_number', 1),
            question_type="creative_suggestion",
            question=s_dict.get('suggestion', ''),
            options=s_dict.get('response_options', ['approve', 'modify', 'skip']),
            context=s_dict.get('rationale', '')
        ))
    
    all_questions = suggestion_questions + approval_questions
    
    if all_questions and not auto_approve:
        state.phase = Phase.CAMERA_PLAN
        state.questions = [q.to_dict() for q in all_questions]
        save_session(state, output_dir)
        
        # Format creative message
        creative_msg = format_suggestions_for_conversation(
            [s for s in all_suggestions if hasattr(s, 'format_for_conversation')]
        ) if all_suggestions else ""
        
        result = StoryboardResult(
            status="needs_input",
            phase=Phase.CAMERA_PLAN,
            session_id=state.session_id,
            questions=all_questions,
            partial_results={
                "total_shots": shot_plan.total_shots,
                "total_duration": shot_plan.total_duration,
                "shot_plan_file": str(plan_path),
                "suggestions_file": str(suggestions_path)
            },
            message=f"Generated {shot_plan.total_shots} shots ({shot_plan.total_duration:.1f}s).\n\n{creative_msg}\nPlease review my creative suggestions and shot selections.",
            resume_command=f"./run.sh continue --session {state.session_id} --answers '<JSON>'"
        )
        output_result(result, json_output)
        return
    
    # Proceed to panel generation
    state.phase = Phase.GENERATE_PANELS
    save_session(state, output_dir)
    _execute_generate_panels(state, output_dir, json_output)


def _execute_generate_panels(state: SessionState, output_dir: Path, json_output: bool):
    """Execute panel generation phase."""
    config = state.answers.get('_config', {})
    fidelity = config.get('fidelity', 'sketch')
    
    # Generate panels
    panels_dir = output_dir / "panels"
    try:
        panel_paths = generate_panels(state.shot_plan, panels_dir, fidelity=fidelity)
    except RuntimeError as e:
        # Catch explicit stubs from panel_generator.py
        result = StoryboardResult(
            status="error",
            phase=Phase.GENERATE_PANELS,
            session_id=state.session_id,
            message=str(e)
        )
        output_result(result, json_output)
        raise typer.Exit(1)
    except Exception as e:
        result = StoryboardResult(
            status="error",
            phase=Phase.GENERATE_PANELS,
            session_id=state.session_id,
            message=f"Panel generation failed: {e}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)
        
    state.panels = [str(p) for p in panel_paths]
    
    # Save shot plan for assembler
    plan_path = panels_dir / "shot_plan.json"
    try:
        plan_path.write_text(json.dumps(state.shot_plan, indent=2))
    except OSError:
        pass
    
    # No questions for panel generation - proceed to assembly
    state.phase = Phase.ASSEMBLE
    save_session(state, output_dir)
    
    result = StoryboardResult(
        status="in_progress",
        phase=Phase.GENERATE_PANELS,
        session_id=state.session_id,
        partial_results={"panels_generated": len(panel_paths)},
        output_files=[str(p) for p in panel_paths[:5]],  # Show first 5
        message=f"Generated {len(panel_paths)} panels. Proceeding to assembly...",
        resume_command=""
    )
    output_result(result, json_output)
    
    _execute_assemble(state, output_dir, json_output)


def _execute_assemble(state: SessionState, output_dir: Path, json_output: bool):
    """Execute assembly phase."""
    config = state.answers.get('_config', {})
    output_format = config.get('format', 'mp4')
    
    panels_dir = output_dir / "panels"
    plan_path = panels_dir / "shot_plan.json"
    
    if output_format == 'panels':
        # Just panels, no assembly needed
        state.phase = Phase.COMPLETE
        state.output_path = str(panels_dir)
        save_session(state, output_dir)
        
        result = StoryboardResult(
            status="complete",
            phase=Phase.COMPLETE,
            session_id=state.session_id,
            output_files=[str(panels_dir)],
            message=f"✅ Storyboard complete! Panels saved to {panels_dir}"
        )
        output_result(result, json_output)
        return
    
    # Assemble video or HTML
    if output_format == 'html':
        output_path = output_dir / "storyboard.html"
    else:
        output_path = output_dir / "animatic.mp4"
    
    try:
        result_path = assemble(panels_dir, plan_path, output_path, output_format)
        state.phase = Phase.COMPLETE
        state.output_path = str(result_path)
        save_session(state, output_dir)
        
        result = StoryboardResult(
            status="complete",
            phase=Phase.COMPLETE,
            session_id=state.session_id,
            output_files=[str(result_path), str(panels_dir), str(plan_path)],
            message=f"✅ Storyboard complete! Output: {result_path}"
        )
        output_result(result, json_output)
        
    except Exception as e:
        state.error = str(e)
        save_session(state, output_dir)
        
        result = StoryboardResult(
            status="error",
            phase=Phase.ASSEMBLE,
            session_id=state.session_id,
            message=f"Assembly error: {e}. Panels are still available at {panels_dir}"
        )
        output_result(result, json_output)
        raise typer.Exit(1)


@app.command()
def status(
    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
    search_dir: Path = typer.Option(Path("./output"), "--search-dir", help="Directory to search"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output structured JSON")
):
    """Check status of an existing session."""
    session_path = find_session(session, search_dir)
    if not session_path:
        typer.echo(f"Session not found: {session}")
        raise typer.Exit(1)
    
    state = load_session(session_path)
    
    result = StoryboardResult(
        status="in_progress" if state.phase != Phase.COMPLETE else "complete",
        phase=state.phase,
        session_id=state.session_id,
        questions=[Question(**q) for q in state.questions] if state.questions else [],
        partial_results={
            "scenes": len(state.parsed_scenes.get('scenes', [])) if state.parsed_scenes else 0,
            "shots": state.shot_plan.get('total_shots', 0) if state.shot_plan else 0,
            "panels": len(state.panels)
        },
        output_files=[state.output_path] if state.output_path else [],
        message=f"Session at phase: {state.phase.value}",
        resume_command=f"./run.sh continue --session {state.session_id} --answers '<JSON>'" if state.questions else ""
    )
    output_result(result, json_output)


@app.command()
def demo(
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip questions"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output JSON")
):
    """Run demo with sample screenplay, showing collaboration loop."""
    
    sample_screenplay = """
# Demo Screenplay

INT. APARTMENT - NIGHT

[LIGHTING: Low key, practical desk lamp only]
[REF: Blade Runner 2049 apartment scene]

SARAH enters the dark apartment, flipping on a small desk lamp.

SARAH
(whispering)
Hello? Is anyone here?

She moves cautiously through the room.

MYSTERIOUS VOICE (O.S.)
I've been waiting for you.

Sarah spins around, fear in her eyes.

EXT. CITY STREET - DAY

Cars rush by. People hurry along the sidewalk.

SARAH walks determinedly, phone pressed to her ear.

SARAH
I need backup. Now.
"""
    
    # Write sample to temp file
    demo_dir = Path("./demo_session")
    demo_dir.mkdir(exist_ok=True)
    screenplay_path = demo_dir / "sample_screenplay.md"
    screenplay_path.write_text(sample_screenplay)
    
    if not json_output:
        typer.echo("🎬 Starting demo storyboard session...\n")
        typer.echo("This demonstrates the COLLABORATION LOOP:")
        typer.echo("  1. Skill analyzes screenplay, asks questions")
        typer.echo("  2. Agent/user provides answers")
        typer.echo("  3. Skill continues, may ask more questions")
        typer.echo("  4. Repeat until complete\n")
    
    # Start session
    start(
        screenplay=screenplay_path,
        output_dir=demo_dir / "output",
        fidelity="sketch",
        format="mp4",
        auto_approve=auto_approve,
        json_output=json_output
    )


if __name__ == "__main__":
    app()
