"""
Orchestrator for create-cast skill.

Coordinates the multi-round casting workflow:
1. Script Analysis
2. Reference Discovery  
3. Identity Generation
4. Identity Pack Build
5. Voice Casting
"""

from pathlib import Path
from typing import Optional, Dict, Any

from .schemas import (
    CastingSession, CastingPhase, CastingResult,
    CharacterSpec, CharacterRole
)
from .collaboration import (
    create_new_session, save_session, load_session, apply_answers,
    advance_phase, build_result
)
from .script_analyzer import analyze_script
from .reference_finder import (
    find_references_for_all_characters, is_discover_talent_available
)
from .identity_generator import generate_candidate_looks, is_create_image_available
from .identity_pack import build_identity_pack, export_identity_packs
from .voice_matcher import find_voices_for_all_characters


def run_casting_session(
    script_path: str,
    output_dir: str = "",
    auto_approve: bool = True,
    model: str = "auto",
) -> CastingResult:
    """
    Run a complete casting session in auto-approve mode.

    This is the main entry point for pipeline integration (create-movie).
    Runs all phases with auto-approval of defaults.

    Args:
        script_path: Path to script file (JSON or markdown)
        output_dir: Output directory for identity packs
        auto_approve: Auto-approve all questions (default True for pipeline)
        model: LLM model (unused, for API compatibility)

    Returns:
        CastingResult with final status and any partial results
    """
    # Start the session
    result = start_casting_session(str(script_path), str(output_dir), auto_approve=True)

    if result.status == "error":
        return result

    session_id = result.session_id

    # Auto-approve through all phases
    max_iterations = 10  # Safety limit
    iteration = 0

    while result.status == "needs_input" and iteration < max_iterations:
        iteration += 1

        # Build auto-approve answers from defaults
        answers = {}
        for q in result.questions:
            if q.default:
                answers[q.id] = q.default
            elif q.options:
                answers[q.id] = q.options[0]
            else:
                answers[q.id] = "approve"

        # Continue with answers
        result = continue_session(session_id, answers, auto_approve=True)

        if result.status == "error":
            break

    # Add partial results for caller
    session = load_session(session_id)
    if session:
        result.partial_results = {
            "characters": list(session.characters.keys()),
            "identity_packs": list(session.identity_packs.keys()),
            "voice_assignments": list(session.voice_assignments.keys()),
        }

    return result


def start_casting_session(
    script_path: str,
    output_dir: str = "",
    auto_approve: bool = False
) -> CastingResult:
    """
    Start a new casting session.
    
    Performs initial script analysis and returns questions for Round 1.
    """
    # Validate script exists
    if not Path(script_path).exists():
        return CastingResult(
            status="error",
            phase=CastingPhase.ANALYSIS,
            session_id="",
            error=f"Script not found: {script_path}",
        )
    
    # Create session
    session = create_new_session(script_path, output_dir)
    
    # Analyze script for characters
    try:
        characters = analyze_script(script_path)
        session.characters = characters
    except Exception as e:
        session.error = f"Script analysis failed: {e}"
        save_session(session)
        return build_result(session)
    
    # Save and return result
    save_session(session)
    return build_result(session, auto_approve)


def continue_session(
    session_id: str,
    answers: Dict[str, Any],
    auto_approve: bool = False
) -> CastingResult:
    """
    Continue a casting session with provided answers.
    
    Applies answers, advances phase if complete, and returns next questions.
    """
    session = load_session(session_id)
    if not session:
        return CastingResult(
            status="error",
            phase=CastingPhase.ANALYSIS,
            session_id=session_id,
            error=f"Session not found: {session_id}",
        )
    
    # Apply answers
    session = apply_answers(session, answers)
    
    # Process current phase and potentially advance
    session = process_phase(session)
    
    # Save and return
    save_session(session)
    return build_result(session, auto_approve)


def process_phase(session: CastingSession) -> CastingSession:
    """
    Process the current phase and advance if complete.
    """
    phase = session.phase
    
    if phase == CastingPhase.ANALYSIS:
        # Check if all required answers are in
        required_answered = "confirm_characters" in session.answers
        if required_answered and session.answers.get("confirm_characters") == "approve":
            # Move to discovery
            session = advance_phase(session)
            session = run_discovery_phase(session)
            
    elif phase == CastingPhase.DISCOVERY:
        # Check if discovery complete
        skip_all = session.answers.get("skip_all_references") == "skip_all"
        refs_handled = all(
            f"{name.lower()}_reference" in session.answers
            for name in session.reference_inspirations
        )
        
        if skip_all or refs_handled:
            session = advance_phase(session)
            session = run_generation_phase(session)
            
    elif phase == CastingPhase.GENERATION:
        # Check if looks selected
        looks_selected = all(
            f"{name.lower()}_look" in session.answers
            for name in session.candidate_looks
        )
        
        if looks_selected:
            session = advance_phase(session)
            session = run_pack_build_phase(session)
            
    elif phase == CastingPhase.PACK_BUILD:
        # Check if packs approved
        packs_approved = all(
            session.answers.get(f"{name.lower()}_pack_approve") == "approve"
            for name in session.identity_packs
        )
        
        if packs_approved:
            session = advance_phase(session)
            session = run_voice_phase(session)
            
    elif phase == CastingPhase.VOICE:
        # Check if voices approved
        voices_handled = all(
            f"{name.lower()}_voice" in session.answers or
            f"{name.lower()}_voice_missing" in session.answers
            for name in session.voice_assignments
        )
        
        if voices_handled:
            session = advance_phase(session)
            # Complete!
    
    return session


def run_discovery_phase(session: CastingSession) -> CastingSession:
    """Run the reference discovery phase."""
    if is_discover_talent_available():
        try:
            references = find_references_for_all_characters(session.characters)
            session.reference_inspirations = references
        except Exception as e:
            # Discovery failed but not fatal - can continue without refs
            pass
    
    return session


def run_generation_phase(session: CastingSession) -> CastingSession:
    """Run the identity generation phase."""
    output_dir = Path(session.output_dir) if session.output_dir else Path.home() / ".pi" / "create-cast" / "output" / session.session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for char_name, char in session.characters.items():
        if char.role in [CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST, CharacterRole.SUPPORTING]:
            # Get selected reference if any
            ref = None
            refs = session.reference_inspirations.get(char_name, [])
            selected_ref_name = session.answers.get(f"{char_name.lower()}_reference")
            for r in refs:
                if r.name == selected_ref_name:
                    r.selected = True
                    ref = r
                    break
            
            # Generate candidate looks
            looks = generate_candidate_looks(
                char,
                output_dir / "candidates",
                reference=ref,
                num_candidates=3,
            )
            session.candidate_looks[char_name] = looks
    
    return session


def run_pack_build_phase(session: CastingSession) -> CastingSession:
    """Run the identity pack build phase."""
    output_dir = Path(session.output_dir) if session.output_dir else Path.home() / ".pi" / "create-cast" / "output" / session.session_id
    
    for char_name, looks in session.candidate_looks.items():
        # Find selected look
        selected = None
        selected_answer = session.answers.get(f"{char_name.lower()}_look", "")
        
        if "look_" in selected_answer:
            try:
                idx = int(selected_answer.replace("look_", "")) - 1
                if 0 <= idx < len(looks):
                    selected = looks[idx]
                    selected.selected = True
            except (ValueError, IndexError):
                pass
        
        if not selected and looks:
            selected = looks[0]
            selected.selected = True
        
        if selected:
            char = session.characters.get(char_name)
            if char:
                pack = build_identity_pack(char, selected, output_dir)
                session.identity_packs[char_name] = pack
    
    return session


def run_voice_phase(session: CastingSession) -> CastingSession:
    """Run the voice casting phase."""
    assignments = find_voices_for_all_characters(session.characters)
    session.voice_assignments = assignments
    
    # Update identity packs with voice info
    for char_name, assignment in assignments.items():
        if char_name in session.identity_packs:
            session.identity_packs[char_name].voice_model = assignment.model_name
    
    return session


def export_session(session_id: str, output_dir: str) -> Dict[str, str]:
    """
    Export a completed session's identity packs.
    """
    session = load_session(session_id)
    if not session:
        return {"error": f"Session not found: {session_id}"}
    
    if session.phase != CastingPhase.COMPLETE:
        return {"error": f"Session not complete. Current phase: {session.phase.value}"}
    
    return export_identity_packs(session.identity_packs, Path(output_dir))


def get_session_status(session_id: str) -> Dict[str, Any]:
    """Get detailed status for a session."""
    session = load_session(session_id)
    if not session:
        return {"error": f"Session not found: {session_id}"}
    
    return {
        "session_id": session.session_id,
        "phase": session.phase.value,
        "script_path": session.script_path,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "characters": list(session.characters.keys()),
        "characters_with_packs": list(session.identity_packs.keys()),
        "characters_with_voices": list(session.voice_assignments.keys()),
        "pending_questions": len(session.questions),
        "answers_provided": len(session.answers),
        "error": session.error,
    }
