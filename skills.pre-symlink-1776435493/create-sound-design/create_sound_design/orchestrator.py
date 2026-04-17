"""
Orchestrator for multi-round sound design workflow.

Coordinates scene analysis, sound search, timing, and export phases.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from .schemas import (
    SoundDesignSession,
    SoundDesignPhase,
    SoundDesignResult,
    SFXCue,
    SFXEvent,
    SceneSoundDesign,
    Question,
)
from .collaboration import (
    generate_session_id,
    save_session,
    load_session,
    generate_analysis_questions,
    generate_search_questions,
    generate_timing_questions,
    generate_export_questions,
    get_default_answers,
    should_advance_phase,
)
from .scene_analyzer import (
    analyze_script,
    analyze_storyboard,
    merge_cues,
    get_scenes_from_cues,
)
from .sound_searcher import search_and_rank
from .timing_engine import (
    create_event_from_cue_and_candidate,
    resolve_conflicts,
)
from .memory_integration import batch_record_usage


def start_session(
    script_path: str,
    output_dir: str = "",
    storyboard_path: str = "",
    project_name: str = "",
) -> SoundDesignResult:
    """
    Start a new sound design session.
    
    Analyzes script/storyboard and returns first set of questions.
    """
    # Create session
    session = SoundDesignSession(
        session_id=generate_session_id(),
        phase=SoundDesignPhase.ANALYSIS,
        script_path=script_path,
        storyboard_path=storyboard_path or None,
        output_dir=output_dir or str(Path(script_path).parent / "sfx"),
        project_name=project_name or Path(script_path).stem,
    )
    
    # Extract cues from script
    script_cues = analyze_script(script_path)
    
    # Extract from storyboard if provided
    storyboard_cues = []
    if storyboard_path:
        storyboard_cues = analyze_storyboard(storyboard_path)
    
    # Merge cues
    all_cues = merge_cues(script_cues, storyboard_cues)
    
    if not all_cues:
        return SoundDesignResult(
            status="error",
            phase=SoundDesignPhase.ANALYSIS,
            session_id=session.session_id,
            error="No SFX cues found in script/storyboard",
        )
    
    # Store cues in session
    for cue in all_cues:
        session.cues[cue.cue_id] = cue
    
    # Generate analysis questions
    session.pending_questions = generate_analysis_questions(all_cues)
    
    # Save session
    save_session(session)
    
    return SoundDesignResult(
        status="needs_input",
        phase=SoundDesignPhase.ANALYSIS,
        session_id=session.session_id,
        questions=session.pending_questions,
        resume_command=f"./run.sh continue {session.session_id}",
    )


def continue_session(
    session_id: str,
    answers: Dict[str, str],
    auto_approve: bool = False,
) -> SoundDesignResult:
    """
    Continue a session with provided answers.
    
    Processes answers and advances to next phase if ready.
    """
    session = load_session(session_id)
    if not session:
        return SoundDesignResult(
            status="error",
            phase=SoundDesignPhase.ANALYSIS,
            session_id=session_id,
            error=f"Session not found: {session_id}",
        )
    
    # Process answers
    for q_id, answer in answers.items():
        session.answers[q_id] = answer
        session.pending_questions = [
            q for q in session.pending_questions if q.id != q_id
        ]
    
    # Check if we should advance phase
    if should_advance_phase(session):
        result = advance_phase(session)
    else:
        result = SoundDesignResult(
            status="needs_input",
            phase=session.phase,
            session_id=session.session_id,
            questions=session.pending_questions,
            resume_command=f"./run.sh continue {session.session_id}",
        )
    
    # Save session
    save_session(session)
    
    return result


def advance_phase(session: SoundDesignSession) -> SoundDesignResult:
    """Advance session to next phase."""
    current_phase = session.phase
    
    if current_phase == SoundDesignPhase.ANALYSIS:
        return _advance_to_search(session)
    elif current_phase == SoundDesignPhase.SEARCH:
        return _advance_to_timing(session)
    elif current_phase == SoundDesignPhase.TIMING:
        return _advance_to_export(session)
    elif current_phase == SoundDesignPhase.EXPORT:
        return _complete_session(session)
    else:
        return SoundDesignResult(
            status="complete",
            phase=SoundDesignPhase.COMPLETE,
            session_id=session.session_id,
            scenes=session.scenes,
        )


def _advance_to_search(session: SoundDesignSession) -> SoundDesignResult:
    """Advance from analysis to search phase."""
    session.phase = SoundDesignPhase.SEARCH
    
    # Search for candidates for each cue
    all_questions = []
    for cue_id, cue in session.cues.items():
        candidates = search_and_rank(cue)
        session.candidates[cue_id] = candidates
        
        # Generate selection questions
        questions = generate_search_questions(cue, candidates)
        all_questions.extend(questions)
    
    session.pending_questions = all_questions
    
    return SoundDesignResult(
        status="needs_input",
        phase=SoundDesignPhase.SEARCH,
        session_id=session.session_id,
        questions=all_questions,
        resume_command=f"./run.sh continue {session.session_id}",
    )


def _load_scene_durations(script_path: str, scene_count: int) -> Dict[str, float]:
    """Load per-scene durations from the script JSON.

    Falls back to evenly splitting the total duration across scenes,
    or 30s default if the script cannot be read.
    """
    default = 30.0
    try:
        with open(script_path) as f:
            script = json.load(f)
    except Exception:
        return {}

    scenes = script.get("scenes", [])
    total_duration = float(script.get("duration_seconds", script.get("duration_target", 0)))
    durations: Dict[str, float] = {}

    for i, sc in enumerate(scenes):
        sid = sc.get("id", f"scene_{i + 1:02d}")
        scene_id = f"scene_{sid:02d}" if isinstance(sid, int) else str(sid)
        dur = sc.get("duration")
        if dur is not None:
            durations[scene_id] = float(dur)
        elif total_duration > 0 and len(scenes) > 0:
            durations[scene_id] = total_duration / len(scenes)
        else:
            durations[scene_id] = default

    return durations


def _advance_to_timing(session: SoundDesignSession) -> SoundDesignResult:
    """Advance from search to timing phase."""
    session.phase = SoundDesignPhase.TIMING

    # Load per-scene durations from script
    scene_durations = _load_scene_durations(
        session.script_path,
        len(get_scenes_from_cues(list(session.cues.values()))),
    )

    # Create events from selected candidates
    event_counter = 1
    scenes_by_id = get_scenes_from_cues(list(session.cues.values()))

    for cue_id, cue in session.cues.items():
        # Get selected candidate from answers
        answer = session.answers.get(f"select_{cue_id}", "")

        if "Skip" in answer or not answer:
            continue

        candidates = session.candidates.get(cue_id, [])
        if not candidates:
            continue

        # Parse selection (e.g., "1. sound_name...")
        try:
            if answer.startswith(("1.", "2.", "3.", "4.")):
                idx = int(answer[0]) - 1
                selected = candidates[idx] if idx < len(candidates) else candidates[0]
            else:
                selected = candidates[0]  # Default to first
        except (ValueError, IndexError):
            selected = candidates[0]

        # Get existing events for this scene
        scene_events = [
            e for e in session.events.values()
            if e.cue_id.startswith(cue.scene_id)
        ]

        # Use per-scene duration from script, fallback to 30s
        scene_duration = scene_durations.get(cue.scene_id, 30.0)

        # Create event
        event = create_event_from_cue_and_candidate(
            cue=cue,
            candidate=selected,
            scene_duration=scene_duration,
            existing_events=scene_events,
            event_counter=event_counter,
        )

        session.events[event.event_id] = event
        event_counter += 1

    # Resolve conflicts per the longest scene
    max_duration = max(scene_durations.values()) if scene_durations else 30.0
    events_list = list(session.events.values())
    resolved = resolve_conflicts(events_list, max_duration)
    session.events = {e.event_id: e for e in resolved}

    # Build scene sound designs
    for scene_id in scenes_by_id.keys():
        scene_events = [
            e for e in session.events.values()
            if e.cue_id.startswith(scene_id)
        ]
        session.scenes[scene_id] = SceneSoundDesign(
            scene_id=scene_id,
            duration=scene_durations.get(scene_id, 30.0),
            events=scene_events,
        )
    
    # Generate timing questions
    session.pending_questions = generate_timing_questions(list(session.events.values()))
    
    return SoundDesignResult(
        status="needs_input",
        phase=SoundDesignPhase.TIMING,
        session_id=session.session_id,
        questions=session.pending_questions,
        event_count=len(session.events),
        resume_command=f"./run.sh continue {session.session_id}",
    )


def _advance_to_export(session: SoundDesignSession) -> SoundDesignResult:
    """Advance from timing to export phase."""
    session.phase = SoundDesignPhase.EXPORT
    
    # Create output directory
    output_dir = Path(session.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build manifest
    manifest = {
        "project": session.project_name,
        "episode": session.episode,
        "created_at": datetime.now().isoformat(),
        "session_id": session.session_id,
        "scenes": {},
    }
    
    for scene_id, scene in session.scenes.items():
        manifest["scenes"][scene_id] = {
            "duration": scene.duration,
            "events": [
                {
                    "event_id": e.event_id,
                    "sfx_id": e.sfx_id,
                    "sfx_path": e.sfx_path,
                    "timestamp": e.timestamp,
                    "duration": e.duration,
                    "volume": e.volume,
                    "pan": e.pan,
                    "fade_in": e.fade_in,
                    "fade_out": e.fade_out,
                }
                for e in scene.events
            ],
        }
    
    # Write manifest
    manifest_path = output_dir / "sfx_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    # Record usage in memory
    scene_descriptions = {
        scene_id: f"Scene {scene_id}"
        for scene_id in session.scenes.keys()
    }
    
    memory_ids = batch_record_usage(
        events=list(session.events.values()),
        cues=session.cues,
        project_name=session.project_name,
        scene_descriptions=scene_descriptions,
        episode=session.episode,
        bridges=session.bridge_attributes,
    )
    
    # Generate export questions
    session.pending_questions = generate_export_questions(str(manifest_path))
    
    return SoundDesignResult(
        status="needs_input",
        phase=SoundDesignPhase.EXPORT,
        session_id=session.session_id,
        questions=session.pending_questions,
        scenes=session.scenes,
        manifest_path=str(manifest_path),
        memory_ids=memory_ids,
        event_count=len(session.events),
        resume_command=f"./run.sh continue {session.session_id}",
    )


def _complete_session(session: SoundDesignSession) -> SoundDesignResult:
    """Complete the session."""
    session.phase = SoundDesignPhase.COMPLETE
    
    # Get manifest path
    output_dir = Path(session.output_dir)
    manifest_path = output_dir / "sfx_manifest.json"
    
    return SoundDesignResult(
        status="complete",
        phase=SoundDesignPhase.COMPLETE,
        session_id=session.session_id,
        scenes=session.scenes,
        manifest_path=str(manifest_path),
        event_count=len(session.events),
    )


def get_session_status(session_id: str) -> SoundDesignResult:
    """Get current session status without advancing."""
    session = load_session(session_id)
    if not session:
        return SoundDesignResult(
            status="error",
            phase=SoundDesignPhase.ANALYSIS,
            session_id=session_id,
            error=f"Session not found: {session_id}",
        )
    
    return SoundDesignResult(
        status="needs_input" if session.pending_questions else "complete",
        phase=session.phase,
        session_id=session.session_id,
        questions=session.pending_questions,
        scenes=session.scenes,
        event_count=len(session.events),
        resume_command=f"./run.sh continue {session.session_id}",
    )


def run_sound_design_session(
    script_path: str,
    output_dir: str = "",
    storyboard_path: str = "",
    auto_approve: bool = True,
    model: str = "auto",
) -> SoundDesignResult:
    """
    Run a complete sound design session in auto-approve mode.
    
    This is the main entry point for pipeline integration (create-movie Phase 4).
    
    Args:
        script_path: Path to script JSON
        output_dir: Output directory for manifest
        storyboard_path: Optional path to storyboard YAML
        auto_approve: Whether to auto-approve all decisions
        model: Model to use (ignored, for API compatibility)
        
    Returns:
        SoundDesignResult with complete status and manifest path
    """
    logger.info(f"Starting sound design session for: {script_path}")
    
    # Start session
    result = start_session(
        script_path=script_path,
        output_dir=output_dir,
        storyboard_path=storyboard_path,
    )
    
    if result.status == "error":
        return result
    
    session_id = result.session_id
    max_iterations = 20  # Safety limit
    iteration = 0
    
    # Auto-approve loop
    while result.status == "needs_input" and iteration < max_iterations:
        iteration += 1
        
        # Get default answers
        answers = get_default_answers(result.questions)
        
        # Continue with auto-approved answers
        result = continue_session(session_id, answers, auto_approve=True)
        
        logger.debug(f"Iteration {iteration}: phase={result.phase.value}, status={result.status}")
    
    if iteration >= max_iterations:
        logger.warning("Max iterations reached, session may be incomplete")
    
    logger.info(f"Sound design complete: {result.event_count} SFX events placed")
    return result
