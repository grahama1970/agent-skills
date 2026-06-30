#!/usr/bin/env python3
"""Golden-state PersonaPlex wrapper for grounded Embry experiments.

Imports Moshi/PersonaPlex modules instead of forking ``moshi.server``. It does
Embry voice/persona pre-roll once at boot, clones the preconditioned streaming
state, restores it for sessions, runs memory-first + Brave staged grounding,
and wires optional Deepgram live ASR/VAD into the WebSocket interaction loop.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import os
import random
import sys
import time
import wave
from pathlib import Path
from typing import Any

ROOT = Path("${HOME}/workspace/experiments/agent-skills")
PERSONAPLEX_ROOT = Path("${HOME}/workspace/experiments/personaplex")
PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
    if sys.argv[0].endswith(".py") and not any("unittest" in a for a in sys.argv):
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])

_nvidia_libs = sorted(Path(PERSONAPLEX_PYTHON).parents[1].glob("lib/python*/site-packages/nvidia/*/lib"))
if _nvidia_libs and "nvidia/cudnn/lib" not in os.environ.get("LD_LIBRARY_PATH", ""):
    env = dict(os.environ)
    existing_ld = env.get("LD_LIBRARY_PATH")
    env["LD_LIBRARY_PATH"] = ":".join([*(str(path) for path in _nvidia_libs if path.is_dir()), *( [existing_ld] if existing_ld else [] )])
    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], env)

import aiohttp
from aiohttp import web
import numpy as np
import sphn
import torch

from personaplex_deepgram_live import DeepgramLiveClient, OutputGate
from personaplex_memory_flow import (
    evidence_case_gate_product,
    intent_requires_evidence_case,
    memory_route_product_with_sources,
    planned_brave_query,
    planned_recall_payload,
)
from personaplex_p2_server_callsite import make_p2_callsite_for_server


BRAVE_RUN = ROOT / "skills/brave-search/run.sh"
MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_VOICE_PROMPT = Path(
    "/mnt/storage12tb/skills/personaplex/outputs/e2e/"
    "embry-conversational-20260622T152647Z/neutral/voice-prompt.pt"
)
DEFAULT_TEXT_PROMPT = (
    "You are Embry Lawson. You are warm, concise, grounded, and emotionally "
    "present. Use retrieved facts when supplied. If evidence is limited, say so."
)
DEFAULT_BRAVE_QUERY = "Hawaii weather surf forecast today"
DEFAULT_OUTPUT_DIR = Path("/mnt/storage12tb/skills/personaplex/outputs/golden-state-wrapper")
DEFAULT_P2_RUN_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/p2-server-callsite")

def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)


def wrap_with_system_tags(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("<system>") and cleaned.endswith("<system>"):
        return cleaned
    return f"<system> {cleaned} <system>"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def ms_since(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


def clone_streaming_state(value: Any) -> Any:
    if torch.is_tensor(value):
        return value.detach().clone()
    if dataclasses.is_dataclass(value):
        kwargs = {field.name: clone_streaming_state(getattr(value, field.name)) for field in dataclasses.fields(value)}
        return type(value)(**kwargs)
    if isinstance(value, dict):
        return {key: clone_streaming_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clone_streaming_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clone_streaming_state(item) for item in value)
    return value


async def timed_post(endpoint: str, payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    start = time.monotonic()
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 2.0))
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(
                f"{MEMORY_URL}{endpoint}",
                json=payload,
                headers={"Accept": "application/json"},
            ) as response:
                text = await response.text()
                status_code = response.status
                content_type = response.headers.get("content-type", "")
        parsed = json.loads(text) if "application/json" in content_type else None
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "elapsed_ms": ms_since(start),
            "json": parsed,
            "text_excerpt": None if parsed is not None else text[:1000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": ms_since(start),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


async def brave_search(query: str, count: int) -> dict[str, Any]:
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        f"source ~/.zshrc >/dev/null 2>&1; {BRAVE_RUN} web {json.dumps(query)} --count {count} --json",
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        proc.kill()
        stdout_raw, stderr_raw = await proc.communicate()
        return {
            "ok": False,
            "elapsed_ms": ms_since(start),
            "returncode": proc.returncode,
            "stderr_excerpt": stderr_raw.decode("utf-8", errors="replace")[-1200:],
            "error": "brave_search_timeout",
        }
    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    out: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "elapsed_ms": ms_since(start),
        "returncode": proc.returncode,
        "stderr_excerpt": stderr[-1200:],
    }
    try:
        out["json"] = json.loads(stdout)
    except json.JSONDecodeError:
        out["ok"] = False
        out["stdout_excerpt"] = stdout[:1200]
        out["error"] = "Brave output was not JSON"
    return out


def compact_memory(recall: dict[str, Any], limit: int = 280) -> str:
    items = (recall.get("json") or {}).get("items") or []
    for item in items:
        text = item.get("retrieval_text") or item.get("text") or item.get("summary") or item.get("problem")
        if text:
            return str(text)[:limit]
    return "No strong Embry persona memory returned."


def compact_brave(brave: dict[str, Any], limit: int = 300) -> str:
    results = (brave.get("json") or {}).get("results") or []
    if not results:
        return "No current Brave Search result returned."
    top = results[0]
    return f"{top.get('title', '')}: {top.get('description', '')}"[:limit]


def compact_answer_route(route: dict[str, Any], limit: int = 420) -> str:
    data = route.get("json") or {}
    if data.get("can_answer"):
        text = data.get("final_response") or data.get("source_answer") or data.get("answer")
        if text:
            return str(text)[:limit]
    questions = data.get("questions") or data.get("clarifying_questions")
    if questions:
        return f"Clarification needed: {questions[0]}"[:limit]
    if data.get("should_deflect"):
        return str(data.get("message") or data.get("reason") or "This should be deflected.")[:limit]
    return "Memory route did not produce a final answer."


def write_wav(path: Path, pcm: np.ndarray, sample_rate: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(pcm, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm16.tobytes())
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "duration_seconds": round(float(len(pcm16)) / float(sample_rate), 3),
    }


class GoldenEmbryServer:
    def __init__(self, args: argparse.Namespace):
        sys.path.insert(0, str(PERSONAPLEX_ROOT))
        from huggingface_hub import hf_hub_download
        import sentencepiece
        from moshi.models import loaders, LMGen

        self.args = args
        self.device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
        self.timings: dict[str, float] = {}
        self.model_lock = asyncio.Lock()
        self.frame_size = 0

        seed_all(args.seed)
        boot_start = time.monotonic()
        load_start = time.monotonic()
        mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        tokenizer_path = hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)
        moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        self.mimi = loaders.get_mimi(mimi_weight, self.device)
        self.other_mimi = loaders.get_mimi(mimi_weight, self.device)
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)  # type: ignore
        lm = loaders.get_moshi_lm(moshi_weight, device=self.device, cpu_offload=args.cpu_offload)
        lm.eval()
        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)
        self.lm_gen = LMGen(lm, audio_silence_frame_cnt=int(0.5 * self.mimi.frame_rate),
                            sample_rate=self.mimi.sample_rate, device=self.device,
                            frame_rate=self.mimi.frame_rate, save_voice_prompt_embeddings=False)
        self.mimi.streaming_forever(1)
        self.other_mimi.streaming_forever(1)
        self.lm_gen.streaming_forever(1)
        self._sync_cuda()
        self.timings["load_ms"] = ms_since(load_start)

        self._warmup()
        self._build_golden_state(args.voice_prompt, args.text_prompt)
        self.timings["boot_total_ms"] = ms_since(boot_start)

    def _sync_cuda(self) -> None:
        if self.device.type == "cuda":
            torch.cuda.synchronize()

    def _warmup(self) -> None:
        start = time.monotonic()
        with torch.no_grad():
            for _ in range(4):
                chunk = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
                codes = self.mimi.encode(chunk)
                _ = self.other_mimi.encode(chunk)
                for c in range(codes.shape[-1]):
                    tokens = self.lm_gen.step(codes[:, :, c : c + 1])
                    if tokens is None:
                        continue
                    _ = self.mimi.decode(tokens[:, 1:9])
                    _ = self.other_mimi.decode(tokens[:, 1:9])
        self._sync_cuda()
        self.timings["warmup_ms"] = ms_since(start)

    def _build_golden_state(self, voice_prompt: Path, text_prompt: str) -> None:
        if not voice_prompt.exists():
            raise FileNotFoundError(f"voice prompt not found: {voice_prompt}")
        start = time.monotonic()
        self.lm_gen.load_voice_prompt_embeddings(str(voice_prompt))
        self.lm_gen.text_prompt_tokens = self.text_tokenizer.encode(wrap_with_system_tags(text_prompt))
        with torch.no_grad():
            self.mimi.reset_streaming()
            self.other_mimi.reset_streaming()
            self.lm_gen.reset_streaming()
            self.lm_gen.step_system_prompts(self.mimi)
            self.mimi.reset_streaming()
        self._sync_cuda()
        self.timings["golden_pre_roll_ms"] = ms_since(start)

        clone_start = time.monotonic()
        self.golden_state = clone_streaming_state(self.lm_gen.get_streaming_state())
        self._sync_cuda()
        self.timings["golden_clone_ms"] = ms_since(clone_start)

    def restore_golden_state(self) -> float:
        start = time.monotonic()
        with torch.no_grad():
            self.mimi.reset_streaming()
            self.other_mimi.reset_streaming()
            self.lm_gen.set_streaming_state(clone_streaming_state(self.golden_state))
        self._sync_cuda()
        return ms_since(start)

    async def iter_research_stages(self, question: str, brave_query: str, brave_count: int):
        start = time.monotonic()

        async def named(name: str, awaitable):
            result = await awaitable
            return name, result

        intent_result = await timed_post(
            "/intent",
            {"q": question, "scope": "persona_memory", "fast": True},
        )
        intent_data = intent_result.get("json") or {}
        recall_payload = planned_recall_payload(intent_result)
        search_query = planned_brave_query(intent_result, brave_query)
        yield {
            "name": "intent", "elapsed_ms": ms_since(start), "result": intent_result,
            "inject_text": (
                "Internal routing note for the next answer: "
                f"intent={intent_data.get('action')}; recall_profile={intent_data.get('recall_profile')}. "
                "Do not mention this routing note to the user."
            )}

        tasks = [
            asyncio.create_task(named("memory", timed_post("/recall", recall_payload))),
            asyncio.create_task(named("brave", brave_search(search_query, brave_count))),
        ]
        if intent_requires_evidence_case(intent_result):
            tasks.append(asyncio.create_task(named("route", evidence_case_gate_product(question, intent_result))))

        recall_result: dict[str, Any] | None = None
        brave_result: dict[str, Any] | None = None
        route_yielded = False
        for completed in asyncio.as_completed(tasks):
            name, result = await completed
            stage: dict[str, Any] = {"name": name, "elapsed_ms": ms_since(start), "result": result, "inject_text": ""}
            if name == "memory":
                recall_result = result
                stage["inject_text"] = f"Memory grounding for the next answer: {compact_memory(result)}"
            elif name == "brave":
                brave_result = result
                stage["inject_text"] = f"Current web grounding for the next answer: {compact_brave(result)}"
            elif name == "route":
                route_yielded = True
                if result.get("requires_evidence_case"):
                    stage["inject_text"] = (
                        "Evidence gate for the next answer: this request needs "
                        "a create-evidence-case verdict before a factual answer. "
                        "Acknowledge the need to check evidence; do not provide "
                        "a compliance conclusion yet."
                    )
                else:
                    stage["inject_text"] = f"Memory route product for the next answer: {compact_answer_route(result)}"
            yield stage

        if not route_yielded:
            route_result = await memory_route_product_with_sources(question, intent_result, recall_result, brave_result, timed_post)
            yield {
                "name": "route", "elapsed_ms": ms_since(start), "result": route_result,
                "inject_text": f"Memory route product for the next answer: {compact_answer_route(route_result)}",
            }

    async def research_turn(self, question: str, brave_query: str, brave_count: int) -> dict[str, Any]:
        start = time.monotonic()
        stages: list[dict[str, Any]] = []
        intent: dict[str, Any] | None = None
        recall: dict[str, Any] | None = None
        brave: dict[str, Any] | None = None
        route: dict[str, Any] | None = None
        async for stage in self.iter_research_stages(question, brave_query, brave_count):
            stages.append(stage)
            if stage["name"] == "intent":
                intent = stage["result"]
            elif stage["name"] == "memory":
                recall = stage["result"]
            elif stage["name"] == "brave":
                brave = stage["result"]
            elif stage["name"] == "route":
                route = stage["result"]
        intent = intent or {"ok": False, "error": "intent_not_returned"}
        recall = recall or {"ok": False, "error": "memory_not_returned"}
        brave = brave or {"ok": False, "error": "brave_not_returned"}
        route = route or {"ok": False, "error": "route_not_returned"}
        evidence_gated = bool(route.get("requires_evidence_case"))
        script = self.script_from_research(question=question, recall=recall, brave=brave, route=route, evidence_gated=evidence_gated)
        return {
            "schema": "personaplex.research_turn.v1",
            "created_at": utc_now(),
            "ok": bool(recall.get("ok") and brave.get("ok") and (route.get("ok") or evidence_gated)),
            "elapsed_ms": ms_since(start),
            "question": question,
            "brave_query": brave_query,
            "evidence_gated": evidence_gated,
            "stage_order": [
                {
                    "name": stage["name"],
                    "elapsed_ms": stage["elapsed_ms"],
                    "inject_text_chars": len(stage.get("inject_text") or ""),
                    "ok": bool((stage.get("result") or {}).get("ok")),
                }
                for stage in stages
            ],
            "intent": intent,
            "recall": recall,
            "brave": brave,
            "route": route,
            "script": script,
            "script_chars": len(script),
        }

    def script_from_research(
        self,
        *,
        question: str,
        recall: dict[str, Any],
        brave: dict[str, Any],
        route: dict[str, Any],
        evidence_gated: bool,
    ) -> str:
        if evidence_gated:
            return (
                "I need to check the evidence case before I answer that. "
                "I can look at the internal memory and current sources, but I should not give a compliance conclusion until the evidence case is built."
            )
        route_text = compact_answer_route(route)
        if route.get("ok") and route_text != "Memory route did not produce a final answer.":
            return route_text
        memory_text = compact_memory(recall)
        search_text = compact_brave(brave)
        return (
            "I found partial context. "
            f"Memory says: {memory_text}. "
            f"Current search says: {search_text}. "
            "I would treat that as preliminary rather than final."
        )

    def force_speech_to_wav(self, text: str, out_path: Path) -> dict[str, Any]:
        start = time.monotonic()
        tokens = self.text_tokenizer.encode(text.strip())
        audio_chunks: list[np.ndarray] = []
        with torch.no_grad():
            self.restore_golden_state()
            silence = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=self.device)
            codes = self.mimi.encode(silence)
            for token in tokens:
                forced = torch.tensor([int(token)], dtype=torch.long, device=self.device)
                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=forced)
                if step_tokens is None:
                    continue
                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
            for _ in range(6):
                step_tokens = self.lm_gen.step(codes[:, :, :1], text_token=torch.tensor([3], dtype=torch.long, device=self.device))
                if step_tokens is None:
                    continue
                main_pcm = self.mimi.decode(step_tokens[:, 1:9])
                audio_chunks.append(main_pcm.cpu()[0, 0].numpy())
        self._sync_cuda()
        pcm = np.concatenate(audio_chunks) if audio_chunks else np.zeros(self.frame_size, dtype=np.float32)
        wav = write_wav(out_path, pcm, int(self.mimi.sample_rate))
        return {
            "text": text,
            "text_chars": len(text),
            "text_tokens": len(tokens),
            "elapsed_ms": ms_since(start),
            "wav": wav,
        }

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response(
            {
                "schema": "personaplex.golden_state_server.health.v1",
                "ok": True,
                "device": str(self.device),
                "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                "timings": self.timings,
                "voice_prompt": str(self.args.voice_prompt),
                "claim_boundary": "golden-state wrapper booted; /api/chat supports optional Deepgram live ASR/VAD when DEEPGRAM_API_KEY is set",
                "p2_callsite_enabled": bool(self.args.enable_p2_callsite),
                "p2_run_root": str(self.args.p2_run_root),
            }
        )

    async def research_endpoint(self, request: web.Request) -> web.Response:
        payload = await request.json()
        question = str(payload.get("question") or self.args.default_question)
        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
        brave_count = int(payload.get("brave_count") or 3)
        result = await self.research_turn(question, brave_query, brave_count)
        return web.json_response(result)

    async def grounded_speech_endpoint(self, request: web.Request) -> web.Response:
        payload = await request.json()
        question = str(payload.get("question") or self.args.default_question)
        brave_query = str(payload.get("brave_query") or self.args.default_brave_query)
        brave_count = int(payload.get("brave_count") or 3)
        output_dir = Path(payload.get("output_dir") or self.args.output_dir)
        run_id = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        research = await self.research_turn(question, brave_query, brave_count)
        script = str(payload.get("script") or research["script"])
        async with self.model_lock:
            speech = self.force_speech_to_wav(script, output_dir / f"embry-grounded-{run_id}.wav")
        receipt = {
            "schema": "personaplex.grounded_speech_receipt.v1",
            "created_at": utc_now(),
            "ok": bool(research.get("ok") and speech["wav"]["bytes"] > 44),
            "question": question,
            "brave_query": brave_query,
            "research": research,
            "speech": speech,
            "claim_boundary": (
                "This proves research routing plus forced PersonaPlex speech WAV. "
                "It is not live ASR/VAD full-duplex proof."
            ),
        }
        receipt_path = output_dir / f"embry-grounded-{run_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        receipt["receipt_path"] = str(receipt_path)
        return web.json_response(receipt)

    async def chat(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        opened = time.monotonic()
        scripted_question = request.query.get("scripted_question", "")
        brave_query = request.query.get("brave_query", self.args.default_brave_query)
        use_deepgram = request.query.get("deepgram", "1") != "0"
        close = False
        opus_writer = sphn.OpusStreamWriter(self.mimi.sample_rate)
        opus_reader = sphn.OpusStreamReader(self.mimi.sample_rate)
        injection_tokens: asyncio.Queue[int] = asyncio.Queue()
        output_gate = OutputGate()
        deepgram = DeepgramLiveClient(
            sample_rate=int(self.mimi.sample_rate),
            model=self.args.deepgram_model,
            enabled=use_deepgram,
        )
        session_id = request.query.get("session_id") or f"golden-{id(ws)}"
        p2_callsite = make_p2_callsite_for_server(
            session_id=session_id,
            persona_id="embry",
            run_root=Path(self.args.p2_run_root) / session_id,
            memory_url=self.args.memory_url,
            deterministic=False,
        ) if self.args.enable_p2_callsite else None

        async with self.model_lock:
            restore_ms = self.restore_golden_state()
            await ws.send_bytes(b"\x00")
            await ws.send_bytes(
                b"\x04"
                + json.dumps(
                    {
                        "event": "handshake",
                        "restore_ms": restore_ms,
                        "elapsed_ms": ms_since(opened),
                        "scripted_question": bool(scripted_question),
                        "deepgram_enabled": deepgram.enabled,
                    }
                ).encode("utf-8")
            )

            async def run_grounding(question: str, source: str) -> None:
                output_gate.close(f"grounding:{source}")
                await ws.send_bytes(
                    b"\x04" + json.dumps({
                        "event": "grounding_started",
                        "source": source,
                        "question": question,
                        "gate": output_gate.snapshot(),
                    }).encode("utf-8")
                )
                try:
                    stage_count = 0
                    async for stage in self.iter_research_stages(question, brave_query, 3):
                        stage_count += 1
                        tokens = self.text_tokenizer.encode(wrap_with_system_tags(stage["inject_text"])) if stage.get("inject_text") else []
                        for token in tokens:
                            injection_tokens.put_nowait(int(token))
                        await ws.send_bytes(
                            b"\x04"
                            + json.dumps(
                                {
                                    "event": "grounding_stage_queued",
                                    "stage": stage["name"],
                                    "stage_elapsed_ms": stage["elapsed_ms"],
                                    "stage_ok": bool((stage.get("result") or {}).get("ok")),
                                    "queued_tokens": len(tokens),
                                    "queue_depth": injection_tokens.qsize(),
                                    "gate": output_gate.snapshot(),
                                }
                            ).encode("utf-8")
                        )
                    output_gate.open()
                    await ws.send_bytes(
                        b"\x04" + json.dumps({
                            "event": "grounding_complete",
                            "source": source,
                            "stages": stage_count,
                            "queue_depth": injection_tokens.qsize(),
                            "gate": output_gate.snapshot(),
                        }).encode("utf-8")
                    )
                except Exception as exc:
                    output_gate.open()
                    await ws.send_bytes(
                        b"\x04" + json.dumps({
                            "event": "grounding_error",
                            "source": source,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }).encode("utf-8")
                    )

            async def run_p2_grounding(question: str, source: str, user_audio_bytes: bytes = b"") -> None:
                if p2_callsite is None:
                    await run_grounding(question, source)
                    return
                output_gate.close(f"p2_grounding:{source}")
                await ws.send_bytes(
                    b"\x04" + json.dumps({
                        "event": "p2_grounding_started",
                        "source": source,
                        "question": question,
                        "session_id": session_id,
                        "gate": output_gate.snapshot(),
                    }).encode("utf-8")
                )
                routed = await p2_callsite.route_speech_final(
                    question,
                    source=source,
                    user_audio_bytes=user_audio_bytes or question.encode("utf-8"),
                    user_audio_codec="live/opus" if source == "deepgram" else "fixture/text",
                )
                response_text = routed.get("response_text") or "I need one more grounded detail before I can answer safely."
                queued_tokens = []
                if routed.get("status") == "sealed":
                    queued_tokens = self.text_tokenizer.encode(wrap_with_system_tags(response_text))
                    for token in queued_tokens:
                        injection_tokens.put_nowait(int(token))
                    if not p2_callsite.output_blocked():
                        output_gate.open()
                await ws.send_bytes(
                    b"\x04" + json.dumps({
                        "event": "p2_grounding_complete",
                        "source": source,
                        "turn_id": routed.get("turn_id"),
                        "generation": routed.get("generation"),
                        "status": routed.get("status"),
                        "route_endpoint": routed.get("route_endpoint"),
                        "sealed_key": routed.get("sealed_key"),
                        "queued_tokens": len(queued_tokens),
                        "queue_depth": injection_tokens.qsize(),
                        "p1_gate_receipt": routed.get("gate_receipt"),
                        "gate": output_gate.snapshot(),
                    }).encode("utf-8")
                )

            retrieval_tasks: set[asyncio.Task] = set()
            if scripted_question:
                scripted_task = asyncio.create_task(
                    run_p2_grounding(scripted_question, "scripted_question") if p2_callsite is not None else run_grounding(scripted_question, "scripted_question")
                )
                retrieval_tasks.add(scripted_task)
                scripted_task.add_done_callback(retrieval_tasks.discard)

            async def deepgram_loop() -> None:
                if not deepgram.enabled:
                    while not close:
                        await asyncio.sleep(0.25)
                    return
                asr_task = asyncio.create_task(deepgram.run())
                try:
                    while not close and deepgram.enabled:
                        turn = await deepgram.turn_queue.get()
                        await ws.send_bytes(
                            b"\x04" + json.dumps({
                                "event": "asr_turn_final",
                                "transcript": turn.text,
                                "asr_elapsed_ms": turn.elapsed_ms,
                                "speech_final": turn.speech_final,
                                "is_final": turn.is_final,
                            }).encode("utf-8")
                        )
                        task = asyncio.create_task(
                            run_p2_grounding(turn.text, "deepgram") if p2_callsite is not None else run_grounding(turn.text, "deepgram")
                        )
                        retrieval_tasks.add(task)
                        task.add_done_callback(retrieval_tasks.discard)
                finally:
                    await deepgram.close()
                    asr_task.cancel()

            async def receive_loop() -> None:
                nonlocal close
                try:
                    async for message in ws:
                        if message.type != aiohttp.WSMsgType.BINARY:
                            continue
                        data = message.data
                        if not data:
                            continue
                        if data[0] == 1:
                            opus_reader.append_bytes(data[1:])
                        elif data[0] == 3:
                            await ws.send_bytes(b"\x04" + b'{"event":"control_received"}')
                finally:
                    close = True

            async def opus_loop() -> None:
                all_pcm_data = None
                while not close:
                    await asyncio.sleep(0.001)
                    pcm = opus_reader.read_pcm()
                    if pcm.shape[-1] == 0:
                        continue
                    all_pcm_data = pcm if all_pcm_data is None else np.concatenate((all_pcm_data, pcm))
                    while all_pcm_data.shape[-1] >= self.frame_size:
                        chunk = all_pcm_data[: self.frame_size]
                        all_pcm_data = all_pcm_data[self.frame_size:]
                        deepgram.enqueue_pcm(chunk)
                        chunk_tensor = torch.from_numpy(chunk).to(device=self.device)[None, None]
                        with torch.no_grad():
                            codes = self.mimi.encode(chunk_tensor)
                            _ = self.other_mimi.encode(chunk_tensor)
                            for c in range(codes.shape[-1]):
                                forced_text = None
                                if not injection_tokens.empty():
                                    forced_text = torch.tensor(
                                        [injection_tokens.get_nowait()],
                                        dtype=torch.long,
                                        device=self.device,
                                    )
                                tokens = self.lm_gen.step(codes[:, :, c : c + 1], text_token=forced_text)
                                if tokens is None:
                                    continue
                                main_pcm = self.mimi.decode(tokens[:, 1:9])
                                _ = self.other_mimi.decode(tokens[:, 1:9])
                                if output_gate.active or (p2_callsite is not None and p2_callsite.output_blocked()):
                                    opus_writer.append_pcm(np.zeros(self.frame_size, dtype=np.float32))
                                    continue
                                opus_writer.append_pcm(main_pcm.detach().cpu()[0, 0].numpy())
                                text_token = int(tokens[0, 0, 0].item())
                                if text_token not in (0, 3):
                                    piece = self.text_tokenizer.id_to_piece(text_token).replace("▁", " ")
                                    if p2_callsite is not None and not p2_callsite.should_emit_model_output(piece, factual=True):
                                        continue
                                    await ws.send_bytes(b"\x02" + piece.encode("utf-8"))

            async def send_loop() -> None:
                while not close:
                    await asyncio.sleep(0.001)
                    payload = opus_writer.read_bytes()
                    if payload:
                        await ws.send_bytes(b"\x01" + payload)

            tasks = [
                asyncio.create_task(receive_loop(), name="receive_loop"),
                asyncio.create_task(opus_loop(), name="opus_loop"),
                asyncio.create_task(send_loop(), name="send_loop"),
                asyncio.create_task(deepgram_loop(), name="deepgram_loop"),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            first_errors: list[dict[str, str]] = []
            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is not None:
                    error = {
                        "task": task.get_name(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                    first_errors.append(error)
                    print(f"chat task failed: {json.dumps(error, sort_keys=True)}", file=sys.stderr, flush=True)
            if first_errors and not ws.closed:
                await ws.send_bytes(
                    b"\x04" + json.dumps({
                        "event": "chat_loop_error",
                        "errors": first_errors,
                    }).encode("utf-8")
                )
            if p2_callsite is not None and not ws.closed:
                try:
                    await ws.send_bytes(
                        b"\x04" + json.dumps({
                            "event": "p2_session_final_receipt",
                            "receipt": p2_callsite.final_receipt(),
                        }, default=str).encode("utf-8")
                    )
                except Exception:
                    pass
            for task in pending:
                task.cancel()
            for task in retrieval_tasks:
                task.cancel()
        return ws


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9008)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--seed", type=int, default=42424242)
    parser.add_argument("--voice-prompt", type=Path, default=DEFAULT_VOICE_PROMPT)
    parser.add_argument("--text-prompt", default=DEFAULT_TEXT_PROMPT)
    parser.add_argument("--default-question", default="Embry, what is the weather like in Hawaii today?")
    parser.add_argument("--default-brave-query", default=DEFAULT_BRAVE_QUERY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--deepgram-model", default=os.environ.get("DEEPGRAM_MODEL", "nova-3"))
    parser.add_argument("--memory-url", default=MEMORY_URL)
    parser.add_argument("--p2-run-root", type=Path, default=DEFAULT_P2_RUN_ROOT)
    parser.add_argument("--disable-p2-callsite", dest="enable_p2_callsite", action="store_false")
    parser.set_defaults(enable_p2_callsite=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = GoldenEmbryServer(args)
    app = web.Application()
    app.router.add_get("/health", server.health)
    app.router.add_post("/api/research-turn", server.research_endpoint)
    app.router.add_post("/api/grounded-speech", server.grounded_speech_endpoint)
    app.router.add_get("/api/chat", server.chat)
    web.run_app(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
