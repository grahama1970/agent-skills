"""
Timing engine for calculating timestamps, volumes, and mix parameters.

Handles placement of SFX events avoiding conflicts and setting appropriate levels.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger

from .schemas import SFXCue, SFXEvent, SFXCandidate


@dataclass
class Conflict:
    """A timing conflict between two events."""
    event_a_id: str
    event_b_id: str
    overlap_start: float
    overlap_end: float
    severity: str  # "minor", "moderate", "severe"


# Volume guidelines by intensity and context
VOLUME_MATRIX = {
    # (intensity, has_dialogue, has_music) -> volume
    ("subtle", False, False): 0.3,
    ("subtle", True, False): 0.2,
    ("subtle", False, True): 0.2,
    ("subtle", True, True): 0.15,
    ("moderate", False, False): 0.6,
    ("moderate", True, False): 0.4,
    ("moderate", False, True): 0.4,
    ("moderate", True, True): 0.3,
    ("prominent", False, False): 0.9,
    ("prominent", True, False): 0.7,
    ("prominent", False, True): 0.6,
    ("prominent", True, True): 0.5,
}


def calculate_timestamp(
    cue: SFXCue,
    scene_duration: float,
    existing_events: List[SFXEvent],
    candidate_duration: float = 1.0
) -> float:
    """
    Determine optimal placement for an SFX event.
    
    Uses cue's timestamp_hint if available, otherwise distributes
    evenly while avoiding overlaps with existing events.
    """
    # Use hint if provided
    if cue.timestamp_hint is not None:
        proposed = cue.timestamp_hint
        
        # Check for conflicts and adjust if needed
        for event in existing_events:
            event_end = event.timestamp + event.duration
            proposed_end = proposed + candidate_duration
            
            # Check for overlap
            if proposed < event_end and proposed_end > event.timestamp:
                # Shift to after this event with small gap
                proposed = event_end + 0.1
        
        # Ensure within scene bounds
        return max(0.0, min(proposed, scene_duration - candidate_duration))
    
    # No hint - distribute evenly
    if not existing_events:
        # First event - place at 10% of scene duration
        return scene_duration * 0.1
    
    # Find largest gap between existing events
    sorted_events = sorted(existing_events, key=lambda e: e.timestamp)
    
    best_gap_start = 0.0
    best_gap_size = sorted_events[0].timestamp
    
    for i in range(len(sorted_events) - 1):
        current_end = sorted_events[i].timestamp + sorted_events[i].duration
        next_start = sorted_events[i + 1].timestamp
        gap_size = next_start - current_end
        
        if gap_size > best_gap_size:
            best_gap_size = gap_size
            best_gap_start = current_end
    
    # Check gap at end
    last_event_end = sorted_events[-1].timestamp + sorted_events[-1].duration
    end_gap = scene_duration - last_event_end
    if end_gap > best_gap_size:
        best_gap_size = end_gap
        best_gap_start = last_event_end
    
    # Place in middle of best gap
    return best_gap_start + (best_gap_size - candidate_duration) / 2


def calculate_volume(
    cue: SFXCue,
    has_dialogue: bool = False,
    has_music: bool = False
) -> float:
    """
    Set volume based on intensity and competing audio.
    
    Args:
        cue: The SFX cue with intensity info
        has_dialogue: Whether scene has dialogue at this point
        has_music: Whether scene has background music
        
    Returns:
        Volume level between 0.0 and 1.0
    """
    key = (cue.intensity, has_dialogue, has_music)
    return VOLUME_MATRIX.get(key, 0.5)


def calculate_pan(cue: SFXCue) -> float:
    """
    Calculate pan position based on cue description.
    
    Looks for spatial indicators in description.
    Returns value between -1.0 (left) and 1.0 (right).
    """
    desc_lower = cue.description.lower()
    
    # Check for explicit spatial indicators
    if any(word in desc_lower for word in ["left", "stage left", "from left"]):
        return -0.5
    if any(word in desc_lower for word in ["right", "stage right", "from right"]):
        return 0.5
    if any(word in desc_lower for word in ["far left", "hard left"]):
        return -0.8
    if any(word in desc_lower for word in ["far right", "hard right"]):
        return 0.8
    if any(word in desc_lower for word in ["behind", "rear", "back"]):
        return 0.0  # Center but could be processed differently in surround
    
    # Default to center
    return 0.0


def generate_fade_curves(
    event: SFXEvent,
    transition_type: str = "normal"
) -> Tuple[float, float]:
    """
    Calculate fade_in/fade_out for smooth transitions.
    
    Args:
        event: The SFX event
        transition_type: "normal", "abrupt", "smooth", "ambient"
        
    Returns:
        Tuple of (fade_in, fade_out) in seconds
    """
    if transition_type == "abrupt":
        return (0.01, 0.01)
    
    if transition_type == "smooth":
        # 10% of duration for fades
        fade = min(event.duration * 0.1, 0.5)
        return (fade, fade)
    
    if transition_type == "ambient":
        # Longer fades for ambient sounds
        fade_in = min(event.duration * 0.2, 1.0)
        fade_out = min(event.duration * 0.3, 1.5)
        return (fade_in, fade_out)
    
    # Normal - short fades to avoid clicks
    return (0.05, 0.1)


def detect_conflicts(events: List[SFXEvent]) -> List[Conflict]:
    """
    Find overlapping events that may need adjustment.
    
    Returns list of conflicts sorted by severity.
    """
    conflicts = []
    
    for i, event_a in enumerate(events):
        a_start = event_a.timestamp
        a_end = a_start + event_a.duration
        
        for event_b in events[i + 1:]:
            b_start = event_b.timestamp
            b_end = b_start + event_b.duration
            
            # Check for overlap
            if a_start < b_end and a_end > b_start:
                overlap_start = max(a_start, b_start)
                overlap_end = min(a_end, b_end)
                overlap_duration = overlap_end - overlap_start
                
                # Determine severity
                min_duration = min(event_a.duration, event_b.duration)
                overlap_ratio = overlap_duration / min_duration
                
                if overlap_ratio > 0.8:
                    severity = "severe"
                elif overlap_ratio > 0.4:
                    severity = "moderate"
                else:
                    severity = "minor"
                
                conflicts.append(Conflict(
                    event_a_id=event_a.event_id,
                    event_b_id=event_b.event_id,
                    overlap_start=overlap_start,
                    overlap_end=overlap_end,
                    severity=severity,
                ))
    
    # Sort by severity
    severity_order = {"severe": 0, "moderate": 1, "minor": 2}
    conflicts.sort(key=lambda c: severity_order[c.severity])
    
    return conflicts


def resolve_conflicts(
    events: List[SFXEvent],
    scene_duration: float
) -> List[SFXEvent]:
    """
    Attempt to resolve conflicts by adjusting timestamps.
    
    Strategy:
    1. Keep events with timestamp_hint fixed
    2. Shift others to avoid overlap
    3. Reduce volume for unavoidable overlaps
    """
    conflicts = detect_conflicts(events)
    
    if not conflicts:
        return events
    
    # Build event lookup
    event_lookup = {e.event_id: e for e in events}
    
    for conflict in conflicts:
        event_a = event_lookup[conflict.event_a_id]
        event_b = event_lookup[conflict.event_b_id]
        
        # Try to shift the later event
        if event_b.timestamp >= event_a.timestamp:
            # Shift event_b to after event_a
            new_start = event_a.timestamp + event_a.duration + 0.1
            if new_start + event_b.duration <= scene_duration:
                event_b.timestamp = new_start
            else:
                # Can't shift, reduce volumes instead
                event_a.volume *= 0.8
                event_b.volume *= 0.8
                logger.warning(
                    f"Unresolvable conflict: {event_a.event_id} and {event_b.event_id}, "
                    "reduced volumes"
                )
    
    return list(event_lookup.values())


def create_event_from_cue_and_candidate(
    cue: SFXCue,
    candidate: SFXCandidate,
    scene_duration: float,
    existing_events: List[SFXEvent],
    has_dialogue: bool = False,
    has_music: bool = False,
    event_counter: int = 1
) -> SFXEvent:
    """
    Create a fully configured SFXEvent from a cue and selected candidate.
    """
    # Calculate timing
    timestamp = calculate_timestamp(
        cue, scene_duration, existing_events, candidate.duration
    )
    
    # Calculate volume
    volume = calculate_volume(cue, has_dialogue, has_music)
    
    # Calculate pan
    pan = calculate_pan(cue)
    
    # Determine transition type from category
    if cue.category == "ambient":
        transition_type = "ambient"
    elif cue.category == "impact":
        transition_type = "abrupt"
    elif cue.category == "transition":
        transition_type = "smooth"
    else:
        transition_type = "normal"
    
    # Create event
    event = SFXEvent(
        event_id=f"evt_{event_counter:03d}",
        cue_id=cue.cue_id,
        sfx_id=candidate.sfx_id,
        sfx_path=candidate.path,
        timestamp=timestamp,
        duration=candidate.duration,
        volume=volume,
        pan=pan,
    )
    
    # Set fades
    fade_in, fade_out = generate_fade_curves(event, transition_type)
    event.fade_in = fade_in
    event.fade_out = fade_out
    
    return event
