# Voice-Stack Cutover Runbook — parent-supervised ONLY

Every step here STOPS or REPLACES a live service. Do not run any of it except
in a supervised cutover window. Build/validation was completed 2026-09-16
without touching any running container (compose config exit 0; all three
images built; `docker ps` names+ports identical before/after).

## Images validated (build evidence)

| Service | Tag | Size | Notes |
|---|---|---|---|
| voice-control | `embry-voice-control:core-gate-r1` | 198MB | includes hardened speak_core.py via `chatterbox-speak` build context |
| chatterbox | `embry-voice/chatterbox-runtime:r1` | 10.2GB | from `chatterbox/docker/Dockerfile.runtime` |
| realtime-stt | `embry-voice/realtimestt-embry:r1` | 12.3GB | cu128 torch, openwakeword pinned models |

## Env required at cutover (export before compose commands)

```bash
export REALTIMESTT_REPO=/home/graham/workspace/experiments/RealtimeSTT
export CHATTERBOX_REPO=/home/graham/workspace/experiments/chatterbox
export HF_HOME=/var/lib/docker/volumes/chatterbox-hf-cache/_data   # reuses the live cache volume's data
export EMBRY_REF_AUDIO=/home/graham/workspace/experiments/agent-skills/skills/persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav
export EMBRY_AUDIO_RUNTIME_DIR=/tmp/compose-validate/embry-audio    # or a durable host path; must exist
export EMBRY_OPENWAKEWORD_MODEL_DIR=/home/graham/workspace/experiments/RealtimeSTT/models/wake
export EMBRY_OPENWAKEWORD_MODEL_SHA256=2ad9cafd125439b11a9b1cfdbf6dbeddfbbb2daa1c25c91266c47543332fe664  # hey_embry_v1.onnx
export WHISPER_API_KEY=whisper-a8dda6bd134200903c58e4a7150d7947a6ae119a24644369
```

## Pre-cutover compose gaps to close FIRST (documented deviations)

These were found by comparing `docker inspect chatterbox-fork-agent-server`
against compose.yaml. compose currently validates WITHOUT them; add before
`up` or the new chatterbox loses ASR:

1. **ASR env missing in compose** (running container has it):
   `CHATTERBOX_ASR_OPENAI_BASE_URL` + `WHISPER_API_KEY`. The running value
   points at the docker-network name `whisper`, which does NOT exist on the
   `embry-voice` compose network. Set it to a host-reachable address instead,
   e.g. `http://172.17.0.1:9000` (bridge gateway → published :9000), and keep
   `WHISPER_API_KEY` out of the tracked file (env or `.env`, gitignored).
2. **`/work` ro mount missing** (running: `chatterbox repo -> /work:ro`) and
   `CHATTERBOX_REF_AUDIO_ROOTS` is `/data` in compose vs `/data:/voices:/work`
   running. Add the mount + widened roots if any caller resolves refs from
   `/work`/`/voices`.
3. Optional sidecar `CHATTERBOX_QWEN_SIDECAR_URL` is absent in the running
   container too — no action.

## Ref-voice parity — VERIFIED MATCH

Running container mounts
`agent-skills/skills/persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav -> /data/embry_ref.wav:ro`
and sets `CHATTERBOX_REF_AUDIO=/data/embry_ref.wav`. compose.yaml's
`EMBRY_REF_AUDIO` default target is the same file/path. Post-up, verify:

```bash
docker compose -f deploy/compose.yaml exec chatterbox sha256sum /data/embry_ref.wav
sha256sum /home/graham/workspace/experiments/agent-skills/skills/persona-dream/voice_clone_candidates/embry_kling_clone_candidate.wav
```

## Cutover steps (in order)

1. **Pre-checks**
   - Current services healthy:
     `curl -s http://127.0.0.1:8018/health | grep '"model_loaded":true'`
   - No receipts in flight: check newest mtime under the live artifacts volume
     is older than a few minutes; no active `/turn` in the journal instance
     (`:8032` /health).
   - Record current state: `docker ps > /tmp/pre-cutover-ps.txt`.
2. **Stop the ad-hoc chatterbox (frees ~9GB VRAM — REQUIRED before `up`)**
   ```bash
   docker stop chatterbox-fork-agent-server
   docker rename chatterbox-fork-agent-server chatterbox-fork-agent-server-retired-$(date +%Y%m%d)
   ```
   (rename, do not `rm` — instant rollback needs the old container intact)
3. **Compose up** (from `skills/embry-voice-control/deploy/`, env exported):
   ```bash
   docker compose -f compose.yaml up -d
   ```
   GPU WARNING: at cutover the GPU sat at 22.4/24.5GiB used. This only fits
   because step 2 frees ~9GB. Do NOT `up` before the stop.
4. **Health gates** (all three, in dependency order):
   ```bash
   curl -s http://127.0.0.1:8019/health   # voice-control
   curl -s http://127.0.0.1:8020/health && curl -s http://127.0.0.1:8020/readiness  # embry stt
   curl -s http://127.0.0.1:8018/health | grep '"model_loaded":true'  # chatterbox
   ```
5. **Smoke checks**
   - CLI: `cd skills/chatterbox-speak && ./run.sh speak --text 'Cutover check.' --voice embry` → exit 0 + receipt.
   - Gateway: `curl -s -X POST http://127.0.0.1:8019/speak -H 'content-type: application/json' -d '{"text":"Gateway check.","voice":"embry"}'` → receipt with `plan_sha256`.
   - Barge-in: start a long planned-pause render via the gateway, then
     `POST /cancel` with the turn id; assert receipt shows cancellation and the
     listener :8020 stays healthy throughout.
6. **Retire the old whisper + journal drift decision** (explicitly out of scope
   here): generic `whisper` :9000 and `embry-voice-journal-8032` stay up until
   the embry runtime proves out over some soak period.

## ROLLBACK (any failed gate)

```bash
cd skills/embry-voice-control/deploy && docker compose -f compose.yaml down
docker rename chatterbox-fork-agent-server-retired-<date> chatterbox-fork-agent-server
/home/graham/workspace/experiments/chatterbox/scripts/start_agent_server_docker.sh   # VERIFIED exists (rc, 6167 bytes)
curl -s http://127.0.0.1:8018/health | grep '"model_loaded":true'
```

The old container comes back with its original mounts (repo ro, /out, ref wav,
chatterbox-hf-cache) — identical to its pre-cutover state.
