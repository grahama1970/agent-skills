# Live Evidence — Project State

Generated bundle date: 2026-08-12

| Area | State | Evidence boundary |
|---|---|---|
| Python service and contracts | IMPLEMENTED | 17 unit tests and local HTTP sanity pass. |
| React/Tailwind/shadcn source | IMPLEMENTED | QuerySpec instrumentation, file-size, offline TypeScript sanity, and a static design preview pass. Full Vite build requires dependency installation. |
| Real ripgrep retrieval | DEMONSTRATED_BOUNDED | Sanity uses an actual temporary repository and `rg`, not a mock. |
| RealtimeSTT microphone path | IMPLEMENTED_NOT_LIVE_PROVEN_HERE | Adapter and consent gate included; this build environment had no audio device/model install. |
| PipeWire meeting-audio path | IMPLEMENTED_NOT_LIVE_PROVEN_HERE | External PCM adapter included; requires a real host source. The UI Stop state is polled by the listener to end capture. |
| Graph Memory HTTP/CLI lane | CONTRACT_IMPLEMENTED_NOT_LIVE_PROVEN_HERE | Uses `/intent`, `/recall`, and sibling `memory/run.sh`; no live GMO service was available in the packaging runtime. |
| Brave / Dogpile | MANUAL_OPTIONAL_NOT_TESTED | Disabled from automatic transcript handling. |
| Raw-audio retention | DISABLED | Journal stores text events and evidence cards only. |

The bundle is ready for repository insertion and prepared-host integration. It
does not claim that live audio, GPU inference, Graph Memory, or external search
were exercised during packaging.

Bounded package validation: `docs/validation/package-validation.json`.
