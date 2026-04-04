# Intervention Controls

Session: session-1775148582

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks | <2s |
| `KILL_<task_id>` | Kill specific task mid-stream | <2s |
| `ABORT` | Kill ALL, stop plan | <2s |
| `SKIP_<task_id>` | Skip queued task (on unpause) | Next pause |

## Task IDs

- `1`: Complete QuarantineView.tsx — 9 missing data-qid (code-runner/0)
- `2`: Instrument CorpusView.tsx — 13 missing data-qid (code-runner/0)
- `3`: Instrument TraceabilityView.tsx — 4 missing data-qid (code-runner/1)
- `4`: Instrument CascadeView.tsx — 3 missing data-qid (code-runner/1)
- `5`: Instrument ThreatMatrixView.tsx — 8 missing data-qid (code-runner/1)
- `6`: Instrument LemmaGraphView.tsx — 9 missing data-qid (code-runner/1)
- `7`: Instrument remaining views — QualityView(3), MonitorView(2), RequirementsView(2), SupervisorView(1) (code-runner/1)
- `8`: Instrument ExtractionReviewModal.tsx — 11 missing data-qid (code-runner/2)
- `9`: Instrument EvidenceCasePanel.tsx — 11 missing data-qid (code-runner/2)
- `10`: Instrument ChatFAB.tsx — 4 missing data-qid (code-runner/2)
- `11`: Complete SpotReextract.tsx — 3 missing data-qid (code-runner/2)
- `12`: Complete BboxEditor.tsx — 3 missing + BboxWorkspace.tsx — 7 missing (code-runner/3)
- `13`: Instrument MonitorStrip.tsx(3) + RequirementsBlock.tsx(3) + PdfCanvas.tsx(1) (code-runner/3)
- `14`: Verify 100% data-qid coverage — 0 missing interactive elements (local/4)
- `15`: Generate deterministic test manifest from data-qid registry (code-runner/4)
