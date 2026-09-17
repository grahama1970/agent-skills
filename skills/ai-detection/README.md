# ai-detection

**A local-first coding-assessment evidence workbench and AI-code detector research project.**

Record a consented editing session, reconstruct exactly what the server received,
train a Python-code baseline, and evaluate a frozen detector without confusing
software tests with proof of human or AI authorship.

**Current scope:** an implemented research prototype. No pretrained detector is
bundled. The default response is `INSUFFICIENT_EVIDENCE`. Real-world detection and
full release readiness are **NOT_ESTABLISHED**. See [the retained evidence](evidence/)
and [current project knowledge](docs/PROJECT_KNOWLEDGE.md).

## Start locally

```bash
cd ai-detection
uv sync --extra dev
uv run ai-detection doctor
uv run ai-detection serve --port 8765
```

Open `http://127.0.0.1:8765`. Consent is required before editing. The page has a
server-enforced assessment timer, a document editor, an evidence result, record
export, and authenticated deletion. The understanding-check prompt is advisory;
this version does not automatically grade candidate competence.

Dependencies were exercised in the build environment without registry access;
`constraints-tested.txt` records those installed versions. On the agent-skills
integration machine (2026-09-17) a clean `uv sync --extra dev` resolved and a
committed `uv.lock` now pins the dependency set, including the integration-time
`python-dotenv` addition. The venv lives on external storage via
`UV_PROJECT_ENVIRONMENT`, never inside the skill folder.

## What is implemented

| Component | Scope |
|---|---|
| Browser workbench | Vanilla JavaScript, local assets, Unicode-aware document edits, consent, timer, export/delete |
| Python service | FastAPI, strict Pydantic contracts, transactional SQLite, bounded requests, token-scoped records |
| Code baseline | Raw tokens + normalized token/AST view + structural ratios; trainable logistic classifier |
| Model artifacts | Data-only JSON weights, feature-version checks and optional canonical SHA-256 pinning |
| Study protocol | Train/tune/calibration/test separation; group, duplicate and unseen-family checks |
| Numeric efficacy gate | Recomputed held-out performance, fixed threshold, conservative simultaneous confidence bounds |
| Contrastive research | Optional pinned, local-only Transformers adapter; mathematical tests, no live weight qualification |
| Evaluation | Positive, negative and adversarial tests, fresh sampling, real HTTP, independent reconstruction, repeated receipts |
| Native skills | Delegating setup-project and agentic-evals adapters; full native certification remains unexecuted |

The trained baseline supports **Python only**. The editor can capture JavaScript,
Java and Go, but the classifier abstains on those languages. It does not silently
pretend Python training established multilingual performance.

## Inspect a file or evidence record

```bash
uv run ai-detection analyze examples/example.py
uv run ai-detection verify-evidence /path/to/ai-detection-session.json
```

The analyzer never executes submitted code. An elevated score can only recommend
review; the result schema cannot assert proven authorship or an automatic penalty.
Pasted content, typing cadence and accessibility input methods are not classifiers.

## Train and evaluate

Use the [dataset contract](docs/DATASET.md), including provenance and independent
splits, before collecting data. Real-human labels cannot be invented by an LLM.

```bash
uv run ai-detection audit-dataset /external/study.jsonl
uv run ai-detection train /external/study.jsonl \
  --output /external/model.json --report /external/training-report.json
uv run ai-detection benchmark /external/study.jsonl \
  --model /external/model.json --output /external/heldout-report.json
```

To serve a trained artifact, set `AI_DETECTION_MODEL` and
`AI_DETECTION_MODEL_SHA256` using the **canonical model digest emitted by train**,
not the file's whitespace-sensitive byte checksum. Unqualified/synthetic artifacts
remain research scores and cannot produce a non-abstaining disposition.

`efficacy-gate` consumes `examples/efficacy-request.json` after its paths and study
requirements have been replaced with real study values. It re-runs evaluation,
checks held-out-family TPR lower bounds and a held-out-human FPR upper bound, and
rejects synthetic data. Numerical success still does not certify human provenance,
accessibility, or production suitability.

## Test the mechanisms, then the capabilities

```bash
# Focused contract sanity checks.
bash sanity.sh

# Three independent runs of the core suite, including actual HTTP transport.
bash scripts/verify.sh --profile core --trials 3 --samples 128

# Also requires a working real Chromium browser journey. Failure is not skipped.
bash scripts/verify.sh --profile full --trials 3 --samples 128
```

Each run retains source hashes, JUnit, stdout/stderr, independent readback and a
JSON/HTML report. In the original delivery environment Chromium navigation was
blocked (`ERR_BLOCKED_BY_ADMINISTRATOR`) and that failure was retained. On the
agent-skills integration machine the real browser journey EXECUTES and PASSES
(3/3 full-profile trials) after three root-cause repairs: CSP-safe Playwright
waits, a premature blob-URL revocation that aborted exports, and avoidance of
snap-confined Chromium whose namespaced `/tmp` yields empty download artifacts.
See `docs/PROJECT_KNOWLEDGE.md` and `reports/qualification/`.

## How this project was set up with skills

The current `setup-project`, `agentic-evals`, `best-practices-python` and
`best-practices-skills` contracts were read from `grahama1970/agent-skills`.
The source brief, policy inputs, draft immutable goal, source-backed research,
claim/seam fixtures and skill wrapper follow those inspected requirements.

**Reading a contract is not executing its owning tool.** The delivery
environment could not mount the native checkout, so the adapters delegate and
retained `BLOCKED_EXTERNAL`. On the agent-skills integration machine the native
chain was executed for real: setup-project `plan` PASS, `audit` fail-closed on
the still-missing acceptance/battle/create-report chain, agentic-evals
mechanisms READY and release profile USABLE_WITH_GAPS (efficacy awaits a real
human study). Receipts are retained under `reports/`.

```bash
export AGENT_SKILLS_ROOT=/path/to/agent-skills
uv run ai-detection native-setup --plan
uv run ai-detection native-setup
uv run ai-detection native-evals
uv run ai-detection native-evals --release
uv run ai-detection release-gate
```

The full setup config deliberately keeps `client_contract_gate: required`.
Acceptance-contract, Battle, create-report, native claim qualification and genuine
human-study evidence must be supplied by their owning workflows. No lookalike
native receipts or owner signatures are included. Full native compatibility and
conformance still require execution on your checkout. [Provenance and gaps](docs/SKILLS_PROVENANCE.md).

## Research, architecture and operations

[Research and implementation map](docs/RESEARCH.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Evaluation contract](docs/EVALUATION.md) · [Dataset format](docs/DATASET.md) ·
[Threat model and privacy](docs/SECURITY.md) · [Operator handoff](docs/NEXT_STEPS.md)

`AI_DETECTION_HOME` controls private runtime data. Otherwise the application prefers
writable `/mnt/storage12tb/skills/ai-detection`, then the user's XDG data directory.
Keep corpora and model weights outside the repository. No remote model calls,
camera, microphone, tab surveillance, global clipboard reading, or shell execution
of candidate code are part of the application.

A [Dockerfile](Dockerfile), [Compose definition](docker-compose.yml) and CI workflow
are included as deployment handoffs, not executed deployment proof.

## Not claimed

This is not a universal AI-authorship detector, a DataAnnotation clone, a watermark
service, a reproduced UniXcoder/DualCodeDetect paper result, or an automatic hiring
adjudicator. No real-human accuracy, fairness, all-provider coverage, Docker success,
clean dependency resolution beyond the committed uv.lock, or native release-chain
PASS is claimed. The retained readiness report is the authority for what was
actually executed.
