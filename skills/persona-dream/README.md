# persona-dream

![Persona Dream card](../../docs/assets/project-cards/persona-dream.webp)

Persona Dream turns persona memory residue into receipt-backed dream packets:
story seeds, frame prompts, contact sheets, reflections, and optional video
planning artifacts. The short version is agentic memories to movies, but the
contract is narrower and more useful: preserve the memory evidence, shape it
into inspectable dream material, and leave polished movie production to the
movie/audio skills.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start here |
|---|---|
| Explore a persona's memory residue | `./run.sh generate --persona <name>` |
| Build a fixture-backed dream packet | `./run.sh generate --persona <name> --fixture <file>` |
| Create video-planning material | `./run.sh generate --mode video_plan --persona <name>` |
| Write an approved reflection back to memory | `./run.sh generate --persona <name> --write-memory` |

## What It Produces

| Artifact | Purpose |
|---|---|
| `dream_request.json` | Persona, memory residue, mode, and run metadata |
| `response.json` | Model or fixture response captured for audit |
| `dream_packet.json` | Structured dream material for downstream tools |
| `contact_sheet.png` | Visual review surface when image frames are produced |
| `dream_reflection.md` | Human-readable summary and interpretation |
| `memory_write_receipt.json` | Proof for any memory write-back |

`video_plan` runs may also produce story outlines, bible material, storyboard
prompts, transcripts, and stage reports for later media skills.

## Proof Discipline

- Do not invent memory residue when recall is empty.
- Label fixture or synthetic residue clearly.
- Keep contact sheets and frame prompts tied to the request and response that
  produced them.
- Treat image, video, and memory write receipts as claims until the artifact is
  inspected.
- Use the movie/audio lane for final rendered media; Persona Dream owns the
  dream packet and planning evidence.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Calling it a finished movie generator | Treat it as a memory-to-dream planning lane |
| Skipping `SKILL.md` and writing ad hoc prompts | Start with the contract and existing run modes |
| Writing memory without a receipt | Preserve `memory_write_receipt.json` |
| Treating a contact sheet as final output | Use it as an inspectable review artifact |

## References

- [`SKILL.md`](SKILL.md) is the operational contract.
- Nested creative helpers live under `skills/persona-dream/skills/`.
