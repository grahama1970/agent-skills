# Separate speaker teleprompter

**User job:** read speaking cues on a second monitor while the audience sees only
slides. The primary object is the current slide's `notes`, not the claim ledger
or debugger output.

Open **Teleprompter** beside the rehearsal controls. It opens a separate
`/teleprompter?source=…` page and reuses the named companion window on subsequent
clicks. Move that window to the other monitor. The audience page remains intact.

The reader uses 64px speaking text by default, adjustable from 32–96px with
**A− / A+**, with high contrast, generous spacing and one bullet per nonempty
notes line. Leading bullet markers are removed; words are not summarized or
invented. Author short talking points in `slide.notes`; keep long scripts in
the project narrative. Empty notes are reported explicitly.

The source page publishes its actual selected slide through the browser's native
BroadcastChannel. A session-scoped source ID isolates presentations; the companion
requests the current state on opening or reload. Slide changes reset the reader's
scroll position. A missing source displays a waiting/disconnected message rather
than pretending the last notes are current. Keep the source tab open in the same
browser profile and origin.

Notes remain speaker-view text: opening the companion does not change slide
content, export files, approvals, execute code or start recording. When recording,
select the audience display—not the teleprompter window. This is not an access-
control boundary against other scripts on the same origin.

## Acceptance

- Separate URL/window, not an embedded drawer or replacement for the slide view.
- Real source notes, oversized readable bullets, working font-size controls.
- Correct slide/notes after source navigation and companion reload.
- Reopening reuses one companion; malformed or cross-source messages are ignored.
- No code execution or source-document writes from the reader.
- Screenshot inspection on the real browser surface; no simulated render proof.

Applicable guidance: best-practices-design, best-practices-react, and the existing
pitchdeck speaker-note/source boundaries. The human specified the reading layout;
no additional dashboard or alternative-design selection is needed.
