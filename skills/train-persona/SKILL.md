---
name: train-persona
description: Train LoRA adapters for persona agents to embody defined characters with consistent voice, reasoning style, and grounded knowledge. Complements /create-persona which defines WHO the persona is; this skill trains HOW they respond.
triggers: train persona, persona training, lora persona, persona adapter, train character, persona lora

provides:
  - train-persona
composes: [task-monitor]
disciplines:
  - ml-training
  - persona-simulation
---

# train-persona

Train LoRA adapters for persona agents to embody defined characters with consistent voice, reasoning style, and grounded knowledge. Complements `/create-persona` which defines WHO the persona is; this skill trains HOW they respond.

## Prompt Iteration Rule (NON-NEGOTIABLE)

Persona voice prompts and reasoning trace templates MUST be validated through `/prompt-lab` before being baked into training data. NEVER hand-craft persona system prompts in Python strings.

- Before training: `/prompt-lab eval` the persona voice prompt against ground truth examples
- Comparing voice variants: `/prompt-lab compare` across models
- Only after prompt-lab validation → proceed to LoRA training

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PERSONA TRAINING PIPELINE                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  /create-persona                    /train-persona                   │
│  ┌──────────────┐                   ┌──────────────────────────────┐ │
│  │ Persona Def  │                   │ Training Pipeline            │ │
│  │ - Name       │                   │                              │ │
│  │ - Role       │──────────────────▶│ 1. Generate Conversations    │ │
│  │ - Goals      │                   │ 2. Upgrade Reasoning Traces  │ │
│  │ - Voice      │                   │ 3. λ-GRPO Training           │ │
│  │ - ToM (BDI)  │                   │ 4. Persona Consistency Gate  │ │
│  │ - Bridges    │                   │                              │ │
│  └──────────────┘                   └──────────────────────────────┘ │
│                                              │                       │
│                                              ▼                       │
│                                     ┌──────────────────┐            │
│                                     │ Persona LoRA     │            │
│                                     │ models/embry-v1/ │            │
│                                     └──────────────────┘            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Why Reasoning Quality Matters for Personas

Unlike hidden reasoning in query routers, **persona agents show their work to users**:

| Component | Reasoning Visibility | Training Focus |
|-----------|---------------------|----------------|
| Intent Mapper | Hidden | Output accuracy |
| **Persona Agent** | **Visible** | **Reasoning quality** |

Users judge personas by HOW they explain, not just WHAT they conclude.

## Training Approaches

| Approach | Description | Use When |
|----------|-------------|----------|
| **λ-GRPO (Recommended)** | GRPO with implicit PRM normalization | Most personas |
| **Trace Upgrading** | Multi-role critique for SFT data | High-stakes personas |
| **Correction Episodes** | Learn from conversation failures | Iterative improvement |

### λ-GRPO: Leveraging Implicit PRM

Based on [GRPO is Secretly a Process Reward Model](https://arxiv.org/abs/2509.21154), standard GRPO already induces step-level rewards through prefix-sharing. λ-GRPO normalizes by process set size for better exploration/exploitation.

```python
# Standard GRPO loss
loss = -advantage * log_prob

# λ-GRPO (normalize by prefix overlap)
loss = -advantage * log_prob / process_set_size
```

## Quick Start

```bash
cd .pi/skills/train-persona

# 1. Generate training data from persona definition
./run.sh generate --persona "Embry" --conversations 1000

# 2. Upgrade reasoning traces (multi-role critique)
./run.sh upgrade-traces --input data/embry/conversations.jsonl

# 3. Train with λ-GRPO
./run.sh train --persona "Embry" --grpo-steps 2000 --lambda-grpo

# 4. Evaluate persona consistency
./run.sh evaluate --persona "Embry" --samples 50

# 5. Test inference
./run.sh chat --persona "Embry"
```

## Training Data Generation

### From Persona Definition

```bash
# Pull persona from /create-persona
./run.sh generate --persona "Embry" \
    --source create-persona \
    --conversations 1000 \
    --include-reasoning
```

Generates conversations with explicit reasoning traces:

```json
{
  "persona": "Embry",
  "query": "How do I detect RF jamming attacks?",
  "reasoning_trace": [
    {"step": 1, "thought": "RF jamming is covered under SPARTA REC techniques..."},
    {"step": 2, "thought": "Let me check the specific controls for detection..."},
    {"step": 3, "thought": "CM-0045 Spectrum Monitoring is the primary countermeasure..."}
  ],
  "response": "Great question! RF jamming detection involves...",
  "grounding_sources": ["REC-0012", "CM-0045"]
}
```

### From Episodic Archives

```bash
# Extract from past conversations
./run.sh generate --persona "Embry" \
    --source episodic-archiver \
    --resolved-only \
    --min-turns 3
```

## Trace Upgrading (ArkAgent-inspired)

For high-stakes personas, upgrade SFT data with multi-role critique:

```bash
./run.sh upgrade-traces \
    --input data/embry/conversations.jsonl \
    --output data/embry/upgraded.jsonl \
    --critique-mode multi-role
```

### Multi-Role Critique

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TRACE UPGRADE (per conversation)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. PROPOSER: Generate initial reasoning trace                      │
│     "Step 1: RF jamming falls under reconnaissance..."              │
│                                                                      │
│  2. SKEPTIC: Challenge each step                                    │
│     "Step 2 assumes ground-based jamming - what about space-to-     │
│      space? Also, the SPARTA ID should be REC-0012, not REC-012"   │
│                                                                      │
│  3. ALT_PATH: Propose alternative reasoning                         │
│     "Could also approach via CM-0045 countermeasure first..."       │
│                                                                      │
│  4. VERIFIER: Check against grounding sources                       │
│     "Verified: REC-0012 ✓, CM-0045 ✓, grounding score 0.87"        │
│                                                                      │
│  5. MODERATOR: Synthesize final trace + correction episodes         │
│     Output: improved_trace, episodes[], confidence                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Correction Episodes

Extracted for training:

```json
{
  "episode_id": "ep_001",
  "state_before": "Step 1: RF jamming is a REC technique...",
  "bad_step": "Step 2: The ID is REC-012...",
  "critique": "SPARTA IDs use 4 digits (REC-0012)",
  "fixed_step": "Step 2: The technique ID is REC-0012...",
  "verification": "Confirmed against SPARTA source"
}
```

## λ-GRPO Training

```bash
./run.sh train \
    --persona "Embry" \
    --train-file data/embry/upgraded.jsonl \
    --grpo-steps 2000 \
    --lambda-grpo \
    --rewards persona_consistency,grounding,reasoning_coherence
```

### Reward Functions

| Reward | Weight | Description |
|--------|--------|-------------|
| `persona_consistency` | 30% | Voice, tone, knowledge boundaries match persona |
| `grounding` | 30% | Responses cite correct sources |
| `reasoning_coherence` | 25% | Steps follow logically, no contradictions |
| `format` | 15% | Proper structure, citations formatted |

### Persona Consistency Reward

```python
def persona_consistency_reward(response: str, persona: Persona) -> float:
    """Check if response matches persona definition."""
    score = 0.0

    # Voice match (uses persona.voice_description)
    voice_match = check_voice_markers(response, persona.voice_markers)
    score += 0.3 * voice_match

    # Knowledge boundaries (stays in scope)
    in_scope = check_knowledge_scope(response, persona.knowledge_domains)
    score += 0.3 * in_scope

    # Escalation patterns (knows when to defer)
    appropriate_escalation = check_escalation(response, persona.escalation_triggers)
    score += 0.2 * appropriate_escalation

    # Humility markers (for intern personas)
    if persona.template == "intern":
        humility = check_humility_markers(response)
        score += 0.2 * humility

    return score
```

## Evaluation

```bash
./run.sh evaluate --persona "Embry" --samples 50
```

### Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| `persona_fidelity` | ≥0.85 | Matches persona definition |
| `reasoning_coherence` | ≥0.80 | Logical step progression |
| `grounding_accuracy` | ≥0.75 | Correct source citations |
| `escalation_accuracy` | ≥0.90 | Knows when to defer |
| `voice_consistency` | ≥0.85 | Maintains character voice |

### Reality Check Integration

```bash
# Use /reality-check-sparta for grounding verification
./run.sh evaluate --persona "Embry" \
    --reality-check \
    --samples 50
```

## Persona Templates

### Embry (Brandon's Intern)

```yaml
name: Embry
template: intern
knowledge_domains:
  - SPARTA framework
  - Space cybersecurity basics
voice_markers:
  - slight southern cadence
  - mechanical metaphors
  - eager but humble
escalation_triggers:
  - novel threats not in SPARTA
  - policy questions
  - "Let me check with Brandon"
humility_patterns:
  - "I'm still learning"
  - "Based on my training"
  - "Brandon would know better"
```

### Horus

```yaml
name: Horus
template: expert
knowledge_domains:
  - All lore collections
  - Technical implementations
  - Creative writing
voice_markers:
  - authoritative
  - references personal experiences
  - bridges across domains
escalation_triggers:
  - factual disputes
  - out-of-domain queries
```

## Commands

### Data Generation

| Command | Description |
|---------|-------------|
| `generate` | Generate training conversations |
| `upgrade-traces` | Apply multi-role critique |
| `extract-episodes` | Extract correction episodes |

### Training

| Command | Description |
|---------|-------------|
| `train` | Run λ-GRPO training |
| `warmup` | SFT warmup before GRPO |
| `merge` | Merge LoRA into base model |

### Evaluation

| Command | Description |
|---------|-------------|
| `evaluate` | Run persona evaluation suite |
| `chat` | Interactive chat with persona |
| `compare` | Compare persona versions |

## Output Structure

```
models/
├── embry-v1/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   ├── persona_config.json      # Persona definition snapshot
│   ├── training_args.json
│   └── eval_results.json
└── horus-v1/
    └── ...

data/
├── embry/
│   ├── conversations.jsonl      # Raw generated
│   ├── upgraded.jsonl           # After trace upgrade
│   ├── episodes.jsonl           # Correction episodes
│   └── eval/
│       └── test.jsonl
└── horus/
    └── ...
```

## Integration

### With /create-persona

```bash
# 1. Create persona definition
cd .pi/skills/create-persona
./run.sh create "Embry" --template intern --learn

# 2. Train persona model
cd .pi/skills/train-persona
./run.sh train --persona "Embry" --from-definition
```

### With /memory

Trained personas can query memory with persona-appropriate scoping:

```python
from train_persona import PersonaAgent

embry = PersonaAgent.load("models/embry-v1")
response = embry.respond(
    query="How do I detect RF jamming?",
    memory_scope="sparta-qra"  # Persona's allowed scope
)
```

### With /episodic-archiver

Extract training signal from past conversations:

```bash
./run.sh generate --persona "Embry" \
    --source episodic-archiver \
    --filter "persona:embry,status:resolved"
```

## Scheduler Integration

```yaml
# In .agents/services.yaml
train-persona-embry:
  description: "Weekly Embry persona training"
  command: |
    cd .pi/skills/train-persona
    ./run.sh train --persona Embry --grpo-steps 1000 --lambda-grpo
  schedule: "0 2 * * 3"  # Wednesday 2am
  timeout: 14400  # 4 hours
  depends_on: [episodic-nightly-reflection]
```

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/create-persona` | Defines persona (input to training) |
| `/memory` | Provides grounding sources |
| `/episodic-archiver` | Provides training signal from conversations |
| `/reality-check-sparta` | Validates grounding quality |
| `/create-intent-map` | Shares λ-GRPO infrastructure |
| `/interview` | Collaborative persona refinement |
