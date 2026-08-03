# Research

Extracted from `README.md` so the README stays a map rather than an
encyclopedia. The README links here; this file is the detail.

### Why This Matters

Most agent-memory systems retrieve facts and prior episodes. They do not give a
persistent persona a controlled way to combine emotionally important
experiences, externalize them, inspect the result, and carry a grounded
interpretation forward.

Persona Dream explores that missing middle. A persona could use a dream to
rehearse a difficult relationship, connect a present event to an older memory,
or surface a conflict it could not express directly. The dream is synthetic,
but its effect on later reasoning can still matter, provided every stage
preserves provenance, uncertainty, and the boundary between imagination and
history.

The same architecture could support persistent companions, game characters,
simulation agents, and other long-lived systems that need to adapt without
losing continuity or inventing a false past.

### Founding Research Question

Can a persona whose speech is rendered through Chatterbox, the voice layer:

1. recall emotionally salient past memories and relevant present events;
2. combine text, images, audio, video, relationships, and project or code
   activity into a synthetic dream;
3. render that dream into inspectable multimodal media;
4. use [`watch`](../watch/SKILL.md) to observe what the generated dream actually
   contains instead of assuming the renderer followed the prompt;
5. interpret those observations against its existing memories and persona state;
6. persist grounded ToM tags, graph edges, multimodal embeddings, and an
   explicitly synthetic dream memory; and
7. use that dream appropriately in later reasoning and conversation without
   confusing it with a literal historical event?

The experiment succeeds only when the dream can affect later recall or behavior
while the persona remains recognizably itself.

### The Rule That Keeps the Experiment Honest

One kind of evidence must never silently become another.

| Evidence class | What it means | Owning boundary |
|---|---|---|
| **Historical memory or present event** | Something stored or observed as part of the persona's real history | Memory / Graph Memory |
| **Dream intention** | What Persona Dream planned, scripted, or asked a renderer to create | Persona Dream |
| **Rendered dream observation** | What is actually visible, audible, or temporally present in returned media | `watch` |
| **Persona interpretation** | What the persona tentatively thinks the observed dream may mean | Persona Dream interpretation gate |
| **Theory-of-Mind inference** | A validated candidate belief, fear, desire, trust state, stance, or relationship update | Memory / ToM validation |
| **Durable persona change** | A promoted change to canonical goals, concerns, worldview, identity, or voice profile | `create-persona` |

Suppose the script asks Kai to answer Embry, but the generated video drops Kai
from the final scene. `watch` can report that Kai is absent. Persona Dream may
tentatively connect that absence to Embry's uncertainty about whether her
boundaries will be respected, but it must also preserve the simpler explanation:
the renderer failed to maintain character continuity.

A dream-derived record therefore keeps facts such as:

```json
{
  "synthetic_origin": true,
  "literal_historical_event": false
}
```

There is no direct path from a renderer defect to a durable personality rewrite.

### How a Dream Works

```text
create-persona
  canonical identity, voice profile, and identity-consistency tests
        |
        v
memory + graph-memory-operator
  past memories + present events + text/image/audio/video/code activity
  + ToM state + emotional intensity + graph relationships
        |
        v
persona-dream
  residue selection -> dream synthesis -> optional media production
        |
        v
watch
  frames + transcript + sound + scenes + visible evidence
        |
        v
persona self-interpretation
  intended dream vs observed dream + source-memory grounding
        |
        v
memory + graph-memory-operator
  synthetic dream memory + ToM tags/edges + Qdrant multimodal embeddings
        |
        v
future recall, reasoning, conversation, and Chatterbox expression
```

The ordinary experience should eventually be simple: a persona says `dream`, or
`dream about Kai and the surf trip`, and the system performs the grounded loop
behind the scenes. React Flow remains an optional human inspection and
correction surface, not a prerequisite for autonomous dreaming.

---
