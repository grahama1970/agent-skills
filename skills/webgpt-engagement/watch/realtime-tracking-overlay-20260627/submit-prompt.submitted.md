Please review the attached Watch real-time tracking overlay bundle.

Task: assess whether the event-derived overlay payload is the right bridge from Watch live-track JSONL events to the browser/modal overlay, and recommend the next bounded implementation step.

Please return:
- verdict: ACCEPT / REVISE / BLOCKED
- required schema changes, if any
- next bounded implementation step
- proof commands/artifacts required before claiming progress

Important constraints:
- Do not redesign the whole Watch UI.
- Do not treat Brave/movie-domain actor data as proof of segment visibility.
- Keep the memory pipeline as intent -> extract entities -> recall -> create evidence case when needed -> answer/clarify/deflect.
- Separate dry-run/mocked/live proof. The attached payload is dry-run geometry plumbing only, not live YOLO/ByteTrack, identity, memory, Qdrant, or recall proof.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260627T200421Z:0e045280>>>

Do not print anything after that marker.
