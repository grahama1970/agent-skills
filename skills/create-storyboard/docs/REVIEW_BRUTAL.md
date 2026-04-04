# BRUTAL CODE REVIEW: create-storyboard Skill

**Reviewer**: Self-assessment based on user criteria
**Date**: 2026-01-29

---

## 🔴 CRITICAL ISSUES

### 1. **ZERO COLLABORATION - Total Autonomous Execution**

The entire skill runs end-to-end with NO user interaction. This is fundamentally broken for creative work.

```python
# orchestrator.py - THE PROBLEM
def create(...):
    parsed = parse_file(screenplay)      # NO CHECKPOINT
    shot_plan = generate_shot_plan(...)  # NO CHECKPOINT
    panel_paths = generate_panels(...)   # NO CHECKPOINT
    result = assemble(...)               # TOO LATE
```

**What SHOULD happen:**

```python
def create(...):
    parsed = parse_file(screenplay)

    # CHECKPOINT 1: Review parsed scenes
    questions = analyze_ambiguities(parsed)
    if questions:
        return {"status": "needs_input", "questions": questions, "partial": parsed}

    shot_plan = generate_shot_plan(...)

    # CHECKPOINT 2: Approve shot selections
    if not approved:
        return {"status": "needs_approval", "shots": shot_plan}
```

**Verdict**: This is a **BLOCKING BUG**. The skill is unusable for collaborative movie-making.

---

### 2. **Aspirational Features That Don't Work**

| Feature              | Claim                    | Reality                     |
| -------------------- | ------------------------ | --------------------------- |
| `fidelity=generated` | AI-generated images      | Just calls `reference` mode |
| `store_learnings`    | Memory integration       | Prints "(pending)"          |
| `/memory` recall     | Uses prior techniques    | Not implemented             |
| Reference fetching   | `/surf`, `/ingest-movie` | Not implemented             |

**These should be REMOVED or clearly stubbed:**

```python
# BAD: Silent fallback
elif fidelity == 'generated':
    generate_reference_panel(...)  # Silently does something else!

# GOOD: Explicit error
elif fidelity == 'generated':
    raise NotImplementedError("AI generation requires /create-image skill - use --fidelity sketch")
```

---

### 3. **Missing Error Handling**

```python
# screenplay_parser.py - No validation
def parse_file(filepath: Path) -> Screenplay:
    content = filepath.read_text()  # What if file is binary?
    # What if screenplay is empty?
    # What if no scenes found?
```

**Failures that will crash silently:**

- Empty screenplay
- Binary file passed
- No INT./EXT. headings found
- Missing fonts in panel_generator
- FFmpeg not installed
- Invalid shot plan JSON

---

## 🟡 OVERENGINEERED FEATURES

### 1. **Camera Movement Suggestions**

```python
def suggest_camera_movement(shot_code, scene_energy):
    # 30 lines of logic that returns... "static" most of the time
```

This adds complexity but the output isn't used meaningfully. The panels just show `[static]`.

**Simplify**: Remove movement suggestions until animatic actually supports camera moves.

---

### 2. **Excessive Dataclasses**

```python
@dataclass
class DialogueLine: ...
@dataclass
class ActionBlock: ...
@dataclass
class SceneHeading: ...
@dataclass
class Scene: ...
@dataclass
class Screenplay: ...
```

For parsing, simple dicts would work. The structured types add cognitive overhead without enabling type checking (no mypy configured).

---

### 3. **HTML Gallery Feature**

The interactive HTML gallery is ~150 lines of embedded JavaScript. This is cool but:

- Not a core requirement
- Adds maintenance burden
- Could be a separate optional output mode

---

## 🟢 MISSING FEATURES FOR COLLABORATIVE USE

### 1. **Question Generation**

```python
def analyze_ambiguities(screenplay: Screenplay) -> list[Question]:
    """Identify scenes needing human clarification."""
    questions = []

    for scene in screenplay.scenes:
        # No emotion markers? Ask.
        if not scene.notes.get('beats'):
            questions.append({
                "scene": scene.number,
                "question": f"Scene {scene.number} has no emotional beats. Is this tense, emotional, or action?",
                "options": ["tense", "emotional", "action", "dialogue", "peaceful"]
            })

        # References to films? Offer to search memory.
        for ref in scene.notes.get('references', []):
            questions.append({
                "scene": scene.number,
                "question": f"Reference to '{ref}' found. Should I search /memory for learned techniques?",
                "options": ["yes", "no", "skip_all_references"]
            })

    return questions
```

### 2. **Structured Output for Agent Communication**

```python
# Return JSON instead of just printing
{
    "status": "needs_input",
    "phase": "camera_planning",
    "questions": [...],
    "partial_results": {...},
    "resume_command": "./run.sh resume --session abc123"
}
```

### 3. **Approval Workflow**

```bash
# Step 1: Parse
./run.sh create screenplay.md --phase parse
# Output: scenes.json + questions.json

# Step 2: Agent/user answers questions
./run.sh create screenplay.md --answers answers.json --phase plan

# Step 3: Review shot plan
./run.sh create screenplay.md --phase generate --approve-shots

# Step 4: Final assembly
./run.sh create screenplay.md --phase assemble
```

### 4. **Session State**

```python
# Save state between phases for resume capability
state = {
    "phase": "camera_planning",
    "screenplay_path": str(screenplay),
    "parsed_scenes": scenes_json,
    "shot_plan": None,
    "panels": [],
    "user_answers": {},
    "timestamp": datetime.now().isoformat()
}
save_state(session_id, state)
```

---

## CONCRETE RECOMMENDATIONS

### Immediate (Fix before using):

1. **Add `--interactive` flag** that pauses at each phase
2. **Add `--dry-run`** that shows what would be done without generating
3. **Raise errors** for unimplemented features instead of silent fallback
4. **Add input validation** in parser

### Short-term (Before /create-movie integration):

1. **Implement question generation** for ambiguous scenes
2. **Return structured JSON** instead of printing
3. **Add session state** for multi-step workflow
4. **Add `--approve` checkpoints**

### Long-term:

1. **Memory integration** with `horus-storyboarding` scope
2. **AI panel generation** via `/create-image`
3. **Reference image search** via `/surf`

---

## SEVERITY SUMMARY

| Category                   | Issue Count | Blocking? |
| -------------------------- | ----------- | --------- |
| Critical (Collaboration)   | 1           | YES       |
| Critical (Broken Features) | 4           | YES       |
| Critical (Error Handling)  | 6           | NO        |
| Overengineered             | 3           | NO        |
| Missing Features           | 4           | Partial   |

**Overall Assessment**:
The skill is a **good proof-of-concept** but is **not production-ready** for collaborative filmmaking. The core pipeline works (parse → plan → generate → assemble), but the lack of checkpoints and question-asking makes it unusable for the intended Horus persona workflow.

**Next Action**: Implement `--interactive` mode with structured question output before integrating with `/create-movie`.
