# Task List: Add Programmatic Video API Support to create-movie

**Created**: 2026-02-01
**Goal**: Enable Horus persona to autonomously create movies using programmatic video generation APIs (Kling AI, Luma, Runway, Stability) as alternatives to local-only LTX-2/Mochi/WAN generation.

## Context

The [`create-movie`](SKILL.md) and [`create-storyboard`](../create-storyboard/SKILL.md) skills currently rely entirely on **local video generation** (LTX-2, Mochi, WAN) or manual RunPod provisioning. This creates bottlenecks for the Horus persona ([`${MEMORY_PROJECT_PATH}/persona`]) to autonomously create movies:

1. **Hardware dependency**: Requires 24GB+ VRAM for quality generation
2. **Speed bottleneck**: 10-sec HD clip = 3.5-4.5 minutes (2-min film = 2-4 hours)
3. **No cloud fallback**: RunPod requires manual provisioning
4. **Limited iteration**: Long generation times discourage experimentation

**Solution**: Add programmatic API providers (Kling AI, Luma, Runway, Stability) with unified abstraction layer, automatic provider selection, cost controls, and async polling.

**Image Generation Note**: We already have programmatic image access via [`/create-image`](../../.pi/skills/create-image/SKILL.md) with Gemini nano-banana (FREE AI), FLUX.1-schnell, Mermaid diagrams, and placeholders. Video is the missing piece.

## Architecture

```
Current:
┌─────────────────────────────────────┐
│   orchestrator.py (Phase 4)         │
│                                      │
│   [Generate Phase]                   │
│   ├─> LTX-2 (local, 24GB VRAM)      │
│   ├─> Mochi (local, variable)       │
│   ├─> WAN 2.2 (local, silent)       │
│   └─> Manual RunPod                 │
└─────────────────────────────────────┘

Proposed:
┌─────────────────────────────────────────────────────────┐
│   orchestrator.py (Phase 4)                              │
│                                                          │
│   [Generate Phase with Provider Abstraction]             │
│   ├─> VideoProvider (base.py)                           │
│   │   ├─> LocalProvider (local.py)                      │
│   │   │   ├─> LTX-2 (24GB)                              │
│   │   │   ├─> Mochi                                     │
│   │   │   └─> WAN 2.2                                   │
│   │   ├─> KlingProvider (kling.py) ← NEW                │
│   │   │   └─> REST API + async polling                  │
│   │   ├─> LumaProvider (luma.py) ← NEW                  │
│   │   │   └─> REST API + async polling                  │
│   │   ├─> RunwayProvider (runway.py) ← NEW              │
│   │   │   └─> REST API + async polling                  │
│   │   └─> StabilityProvider (stability.py) ← NEW        │
│   │       └─> REST API + async polling                  │
│   └─> Auto-selection based on hardware/budget           │
└─────────────────────────────────────────────────────────┘
```

## Crucial Dependencies (Sanity Scripts)

| Library    | API/Method        | Sanity Script              | Status   |
| ---------- | ----------------- | -------------------------- | -------- |
| `httpx`    | Async HTTP client | `sanity/httpx_async.py`    | [ ] Pending |
| `tenacity` | Retry logic       | `sanity/tenacity_retry.py` | [ ] Pending |
| `pydantic` | API validation    | `sanity/pydantic_model.py` | [ ] Pending |

**API Connectivity Tests** (optional credentials):
| Service | Sanity Script | Status |
|---------|---------------|--------|
| Kling AI | `sanity/kling_api_connectivity.py` | [ ] Pending |
| Luma | `sanity/luma_api_connectivity.py` | [ ] Pending |
| Runway | `sanity/runway_api_connectivity.py` | [ ] Pending |
| Stability | `sanity/stability_api_connectivity.py` | [ ] Pending |

## Questions/Blockers

None

## Tasks

### P0: Setup & Foundation (Sequential)

- [ ] **Task 1**: Add API dependencies to pyproject.toml
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: None (file edit only)
  - **Definition of Done**:
    - Test: `cat pyproject.toml | rg "httpx|tenacity|pydantic"`
    - Assertion: Shows httpx>=0.27.0, tenacity>=9.0.0, pydantic>=2.0.0 in [project.dependencies]

- [ ] **Task 2**: Create sanity scripts for new dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Sanity**: Self-validating (sanity scripts validate themselves)
  - **Definition of Done**:
    - Test: `bash sanity/httpx_async.sh && python sanity/tenacity_retry.py && python sanity/pydantic_model.py`
    - Assertion: All exit 0, print "PASS"

- [ ] **Task 3**: Create video provider abstraction (base.py)
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Sanity**: None (pure Python ABC)
  - **Definition of Done**:
    - Test: `python -c "from video_providers.base import VideoProvider; print('OK')"`
    - Assertion: No import errors, VideoProvider is abstract class
  - **Required Methods**:

    ```python
    class VideoProvider(ABC):
        @abstractmethod
        async def generate(self, prompt: str, duration: int, **kwargs) -> str:
            """Submit generation task, return task_id"""
            pass

        @abstractmethod
        async def poll_status(self, task_id: str) -> tuple[str, Optional[float]]:
            """Return (status, progress). Status: queued|processing|completed|failed"""
            pass

        @abstractmethod
        async def download(self, task_id: str, output_path: Path) -> Path:
            """Download completed video, return local path"""
            pass

        @abstractmethod
        def get_capabilities(self) -> dict:
            """Return provider capabilities: max_duration, resolutions, features"""
            pass
    ```

### P1: API Provider Implementations (Parallel after Task 3)

- [ ] **Task 4**: Implement Kling AI provider (kling.py)
  - Agent: general-purpose
  - Parallel: 1 (can run with Tasks 5-7)
  - Dependencies: Task 3
  - **Sanity**: `sanity/kling_api_connectivity.py` (requires `KLING_API_KEY`)
  - **Definition of Done**:
    - Test: `python sanity/kling_api_connectivity.py`
    - Assertion: Exits 0, prints "PASS: Kling API connectivity OK" (or "SKIP: No KLING_API_KEY")
  - **API Endpoints**:
    - POST `https://api.klingai.com/v1/videos/generations`
    - GET `https://api.klingai.com/v1/videos/generations/{task_id}`

- [ ] **Task 5**: Implement Luma Dream Machine provider (luma.py)
  - Agent: general-purpose
  - Parallel: 1 (can run with Tasks 4, 6-7)
  - Dependencies: Task 3
  - **Sanity**: `sanity/luma_api_connectivity.py` (requires `LUMA_API_KEY`)
  - **Definition of Done**:
    - Test: `python sanity/luma_api_connectivity.py`
    - Assertion: Exits 0, prints "PASS: Luma API connectivity OK" (or "SKIP: No LUMA_API_KEY")
  - **API Endpoints**:
    - POST `https://api.lumalabs.ai/dream-machine/v1/generations`
    - GET `https://api.lumalabs.ai/dream-machine/v1/generations/{id}`

- [ ] **Task 6**: Implement Runway Gen-3 provider (runway.py)
  - Agent: general-purpose
  - Parallel: 1 (can run with Tasks 4-5, 7)
  - Dependencies: Task 3
  - **Sanity**: `sanity/runway_api_connectivity.py` (requires `RUNWAY_API_KEY`)
  - **Definition of Done**:
    - Test: `python sanity/runway_api_connectivity.py`
    - Assertion: Exits 0, prints "PASS: Runway API connectivity OK" (or "SKIP: No RUNWAY_API_KEY")
  - **API Endpoints**:
    - POST `https://api.runwayml.com/v1/generate`
    - GET `https://api.runwayml.com/v1/tasks/{task_id}`

- [ ] **Task 7**: Implement Stability AI provider (stability.py)
  - Agent: general-purpose
  - Parallel: 1 (can run with Tasks 4-6)
  - Dependencies: Task 3
  - **Sanity**: `sanity/stability_api_connectivity.py` (requires `STABILITY_API_KEY`)
  - **Definition of Done**:
    - Test: `python sanity/stability_api_connectivity.py`
    - Assertion: Exits 0, prints "PASS: Stability API connectivity OK" (or "SKIP: No STABILITY_API_KEY")
  - **API Endpoints**:
    - POST `https://api.stability.ai/v2alpha/generation/video`
    - GET `https://api.stability.ai/v2alpha/generation/video/{id}`

### P2: Local Provider Refactor (Sequential after Task 3)

- [ ] **Task 8**: Refactor existing local generation into local.py provider
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 3
  - **Sanity**: Existing `sanity/docker.sh` and `sanity/ffmpeg.sh` (already PASS)
  - **Definition of Done**:
    - Test: `python -c "from video_providers.local import LocalProvider; print('OK')"`
    - Assertion: No import errors, LocalProvider implements VideoProvider interface
  - **Notes**: Extract existing LTX-2/Mochi/WAN logic from orchestrator.py into LocalProvider

### P3: Orchestrator Integration (Sequential after Tasks 4-8)

- [ ] **Task 9**: Add provider selection to orchestrator.py
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Tasks 4, 5, 6, 7, 8
  - **Sanity**: None (integration logic)
  - **Definition of Done**:
    - Test: `./run.sh generate --help | rg "video-provider"`
    - Assertion: Shows `--video-provider [local|kling|luma|runway|stability|auto]` option
  - **Implementation**:
    ```python
    @click.option('--video-provider',
                  type=click.Choice(['local', 'kling', 'luma', 'runway', 'stability', 'auto']),
                  default='auto',
                  help='Video generation provider')
    def generate(video_provider: str, ...):
        provider = select_provider(video_provider, hardware_profile, budget)
        for scene in scenes:
            task_id = await provider.generate(scene.prompt, scene.duration)
            status = await provider.poll_status(task_id)
            path = await provider.download(task_id, output_dir)
    ```

- [ ] **Task 10**: Add cost tracking and budget controls
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 9
  - **Sanity**: None (feature logic)
  - **Definition of Done**:
    - Test: `./run.sh generate --max-cost 5.00 --video-provider kling ...` (with mock)
    - Assertion: Warns "Budget: $3.60 / $5.00" before API calls, stops if exceeded
  - **Implementation**:
    - Track cost per clip (provider-specific rates)
    - Accumulate total cost per session
    - Warn before spending (if `VIDEO_API_WARN_BEFORE_SPEND=true`)
    - Hard stop if exceeds `--max-cost` or `VIDEO_API_MAX_COST_PER_PROJECT`

- [ ] **Task 11**: Add async polling with progress display
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 9
  - **Sanity**: None (UI feature)
  - **Definition of Done**:
    - Test: Run generate with Kling provider, observe Rich progress bar
    - Assertion: Shows "Generating clip 1/12... [38%] ETA: 2m 15s"
  - **Implementation**: Use Rich's Progress with SpinnerColumn for each clip

### P4: Documentation & Testing (Sequential after Task 11)

- [ ] **Task 12**: Update SKILL.md with API provider documentation
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 11
  - **Sanity**: None (documentation)
  - **Definition of Done**:
    - Test: `rg "Kling AI|Luma|Runway|Stability" SKILL.md`
    - Assertion: Shows provider comparison table, API setup instructions, cost estimates
  - **Required Sections**:
    - API Provider Comparison Table
    - Environment Variables (KLING_API_KEY, LUMA_API_KEY, etc.)
    - Cost Analysis (per-clip pricing)
    - Auto-Selection Logic
    - Examples with `--video-provider` flag

- [ ] **Task 13**: Create integration test with mock API responses
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 11
  - **Sanity**: Self-testing (CI test)
  - **Definition of Done**:
    - Test: `python sanity/mock_api_integration.py`
    - Assertion: Exits 0, tests all providers with mock HTTP responses (no real API calls)
  - **Implementation**: Use `pytest` with `httpx_mock` or `responses` library

- [ ] **Task 14**: Update orchestrate sanity check
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Tasks 12, 13
  - **Sanity**: `sanity.sh` (existing)
  - **Definition of Done**:
    - Test: `bash sanity.sh`
    - Assertion: All checks PASS (existing + new API sanity scripts with SKIP for missing keys)

### P5: Extend to create-storyboard (Sequential after P4)

- [ ] **Task 15**: Add video provider support to create-storyboard
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 14
  - **Sanity**: `../create-storyboard/sanity/run_all.sh`
  - **Definition of Done**:
    - Test: `cd ../create-storyboard && ./run.sh start screenplay.md --video-provider kling`
    - Assertion: Storyboard uses Kling for panel-to-video conversion (if --fidelity=animated)

## Prior Art / References

- [`create-movie/SKILL.md`](SKILL.md) - Current video generation documentation (LTX-2, Mochi, WAN)
- [`create-storyboard/SKILL.md`](../create-storyboard/SKILL.md) - Storyboard skill needing video API
- [`/create-image`](../../.pi/skills/create-image/SKILL.md) - Existing image generation with nano-banana
- User research: Kling AI official API at [app.klingai.com/global/dev](https://app.klingai.com/global/dev)

## API Rate Limits & Quotas

| Provider  | Free Tier       | Rate Limit  | Notes                        |
| --------- | --------------- | ----------- | ---------------------------- |
| Kling AI  | No free tier    | ~10 req/min | Pay-per-use, $0.10-0.50/clip |
| Luma      | Trial credits   | ~5 req/min  | Credits system               |
| Runway    | Enterprise only | Custom      | No free tier                 |
| Stability | Credits         | ~10 req/min | Credits expire               |

**Implementation**: Add rate limit tracking per provider, exponential backoff on 429 errors.

## Cost Estimation Matrix

Example: 2-minute movie = 12 x 10-second clips

| Scenario        | Provider      | Clips | Cost  | Time      | Use Case              |
| --------------- | ------------- | ----- | ----- | --------- | --------------------- |
| Rapid iteration | Kling AI      | 12    | $3.60 | 30-60 min | Horus exploring ideas |
| Quality preview | Luma          | 12    | $3.60 | 1-2 hours | Pre-production review |
| Final render    | Local (LTX-2) | 12    | $0    | 2-4 hours | Overnight batch       |
| Professional    | Runway        | 12    | $6.00 | 1-2 hours | Client deliverable    |

**Default for Horus**: Auto-select based on hardware availability and budget.

## Success Metrics

1. Horus persona can autonomously create 30-second movie without local GPU
2. Generation time for 12-clip film: <1 hour (vs 2-4 hours local)
3. Total cost per film: <$5 (within budget for experimentation)
4. Zero manual intervention required (no RunPod provisioning)

## Notes

- All API providers use async polling pattern (POST → poll → download)
- Provider abstraction allows easy addition of new services (Veo, Pika, etc.)
- Cost tracking prevents runaway spending
- Fallback to local generation if API fails or budget exceeded
- Integration with existing [`/create-image`](../../.pi/skills/create-image/SKILL.md) nano-banana for image assets
