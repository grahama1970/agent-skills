# a-detection — delivery and verification

**Status: USABLE_WITH_GAPS as a local research prototype.**
**Release and real-world detector efficacy: NOT_ESTABLISHED.**

## Executed

| Check | Result |
|---|---|
| Frozen core suite | **96 passed, zero failures, zero skips, in each of 3 runs** |
| Full suite | **96 passed / 1 failed in each of 3 runs** |
| Full-suite failure | Chromium managed-policy navigation block: ERR_BLOCKED_BY_ADMINISTRATOR |
| Real HTTP → SQLite → export → independent reconstruction → deletion | Passed in all completed runs |
| Fresh Unicode edit probes | 128 fresh edit probes per run; included in tests, not 128 independent human sessions |
| Source identity | Identical frozen digest for core and full profiles; unchanged through each run |
| Wheel build | Passed |
| Installed-wheel smoke | Passed in existing dependency environment; static assets and default abstention read back |
| Python compilation / JavaScript syntax / shell syntax | Passed |
| Native setup-project plan/audit and agentic-evals calls | Attempted adapters; BLOCKED_EXTERNAL because no local native checkout was mounted |

The fresh venv install without dependencies could not import Loguru. The wheel was
then installed and exercised in the existing build environment. This proves the
packaged runtime with present dependencies, **not** a successful clean installation.

## What the bundle does

A local browser workbench and FastAPI service collect consented, ordered Unicode
editor changes under server-enforced deadlines. SQLite transactions support exact
idempotent retries, export, independent reconstruction, retention and deletion.
Strict typed responses cannot assert proven authorship or automatic penalties.

A Python-code classifier can be trained from raw/normalized/structural features.
Train/tune/calibration/test data are separated. Group and duplicate leakage, held-out
families, fixed-threshold replay and confidence bounds have executable guards.
An optional local-only contrastive two-model adapter is included; numerical math
was tested, but live weights were not available.

## What has not been proven

No real-human detector benchmark, pretrained detector, multilingual detector,
unseen-provider effectiveness, fairness qualification or working browser journey
is claimed. Synthetic training tests prove mechanisms only. Unsupported or
unqualified cases abstain. The understanding prompt is not an automated grader.

The requested repository skill contracts were inspected and applied, with native
handoff commands and fixtures. They were **not** executed as a complete native
skill chain. No native acceptance, Battle, create-report, skill-conformance,
independent human signature or release-readiness receipt is invented.

Docker, Ruff, clean uv resolution and real Transformer inference were unavailable
or unexecuted. The full profile remains fail-closed.

## Evidence links

[Core report](qualification-core/20260917T161943Z-3a2c354c/report.json) ·
[Full report](qualification-full/20260917T162153Z-ab00e8a8/report.json) ·
[Wheel readback](wheel-readback.json) ·
[Native invocation results](native/) ·
[Machine-readable summary](SUMMARY.json)

Frozen source digest: `136b73c047ef2b8e08ad679de2359d98bb65c0ed665ecb37fa97ee67b1a7d24e`.

## Run locally

```bash
cd a-detection
uv sync --extra dev
uv run a-detection doctor
uv run a-detection serve --port 8765
```

Open `http://127.0.0.1:8765`. Resolve and commit a real uv.lock on a network-enabled
machine before claiming reproducible deployment. See README.md and
`docs/NEXT_STEPS.md` for the native skills and real-data qualification sequence.
