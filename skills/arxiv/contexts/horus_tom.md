# Horus Theory of Mind Extraction Context

You are extracting knowledge to implement Theory of Mind for Horus, an AI agent with:
- Persistent persona state (drives, moods, defense mechanisms)
- User relationship tracking (trust, respect, familiarity)
- Character arc evolution over time

## What to Extract

Focus on **actionable implementation patterns**:

1. **BDI Architecture**
   - How to represent Beliefs, Desires, Intentions as data structures
   - How to update BDI state based on observations
   - Causal vs equal relationships between B, D, and I

2. **Mental State Tracking**
   - First-order ToM: tracking direct beliefs ("I believe X")
   - Second-order ToM: recursive beliefs ("I believe you believe X")
   - Confidence scoring for inferred states

3. **Counterfactual Reflection**
   - When to trigger reflection (surprise, prediction errors)
   - How to generate alternative hypotheses
   - How to update beliefs based on reflection

4. **Multi-Agent Dynamics**
   - How agents model each other's mental states
   - Trust and relationship dynamics
   - Communication strategies based on ToM

5. **Implementation Techniques**
   - Prompt structures for ToM reasoning
   - State representation schemas
   - Update algorithms and confidence decay

## What to SKIP

- Abstract/introduction summaries (too generic)
- Acknowledgments, references, appendix boilerplate
- Dataset descriptions without methodology insights
- Evaluation metrics without implementation guidance
- "Future work" without concrete approaches

## Output Format

For each knowledge chunk, ask:
- "How would I implement this in code?"
- "What data structure does this suggest?"
- "What function/method would use this?"

Phrase questions as implementation problems:
- BAD: "What does the paper say about BDI?"
- GOOD: "How should an agent update its belief confidence when observations contradict expectations?"

Phrase answers as actionable guidance:
- BAD: "The paper mentions using confidence scores"
- GOOD: "Track confidence as float [0,1]. When observation contradicts belief, multiply confidence by 0.7. When confirmed, set to min(confidence * 1.2, 1.0)"
