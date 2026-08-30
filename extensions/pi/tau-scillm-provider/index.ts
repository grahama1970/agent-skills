import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, appendFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

const PROVIDER_ID = process.env.PI_SCILLM_PROVIDER_ID || "tau-scillm";
const BASE_URL = (process.env.PI_SCILLM_BASE_URL || process.env.SCILLM_BASE_URL || "http://127.0.0.1:4001/v1").replace(/\/+$/, "");
const HEALTH_URL = BASE_URL.replace(/\/v1$/, "");
const RECEIPT_DIR = process.env.PI_SCILLM_RECEIPT_DIR || join(homedir(), ".pi", "agent", "receipts", "tau-scillm-provider");
const DEFAULT_KEY = "sk-dev-proxy-123";

const STATIC_MODELS = [
  "gpt-5.5",
  "claude-sonnet-5",
  "claude-sonnet-high",
  "claude-sonnet",
  "claude-fable",
  "claude-opus-5",
  "claude-opus-high",
  "claude-haiku",
  "gemini-flash",
  "gemini-flash-high",
  "moonshot-text",
  "zai-glm",
  "zai-glm-flash",
  "deepseek-direct",
  "deepseek-ai/DeepSeek-V4-Flash-0731-TEE",
  "local-text",
  "local-glm",
  "vlm",
  "codex-vision",
];

type KeyInfo = {
  key: string;
  source: string;
  fingerprint: string;
};

type PendingReceipt = {
  request_id: string;
  provider_id: string;
  model_id: string;
  base_url: string;
  started_at: string;
  request_hash: string;
  payload_shape: Record<string, unknown>;
  key_fingerprint: string;
  key_source: string;
  status?: number;
  response_headers?: Record<string, string>;
  ended_at?: string;
  live: true;
  mocked: false;
};

let keyInfoCache: KeyInfo | null = null;
let pendingReceipt: PendingReceipt | null = null;

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function fingerprint(value: string): string {
  return sha256(value).slice(0, 12);
}

function envKey(names = ["PI_SCILLM_API_KEY", "SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY", "SCILLM_PROXY_KEY"]): KeyInfo | null {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) return { key: value, source: `env:${name}`, fingerprint: fingerprint(value) };
  }
  return null;
}

function dockerKey(): KeyInfo | null {
  try {
    const stdout = execFileSync("docker", [
      "inspect",
      "docker-scillm-proxy-1",
      "--format",
      "{{range .Config.Env}}{{println .}}{{end}}",
    ], { encoding: "utf8", timeout: 2000, stdio: ["ignore", "pipe", "ignore"] });
    for (const line of stdout.split(/\n/)) {
      const match = line.match(/^(SCILLM_MASTER_KEY|LITELLM_MASTER_KEY|SCILLM_PROXY_KEY)=(.+)$/);
      if (match?.[2]) return { key: match[2].trim(), source: `docker:docker-scillm-proxy-1:${match[1]}`, fingerprint: fingerprint(match[2].trim()) };
    }
  } catch {
    return null;
  }
  return null;
}

function resolveKey(): KeyInfo {
  if (keyInfoCache) return keyInfoCache;
  keyInfoCache = envKey(["PI_SCILLM_API_KEY"]) || dockerKey() || envKey(["SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY", "SCILLM_PROXY_KEY"]) || { key: DEFAULT_KEY, source: "dev-default", fingerprint: fingerprint(DEFAULT_KEY) };
  return keyInfoCache;
}

function modelConfig(id: string) {
  const image = /(?:vlm|vision|gemini|claude|gpt)/i.test(id);
  const reasoning = /(?:gpt|claude|opus|sonnet|fable)/i.test(id);
  return {
    id,
    name: `SciLLM ${id}`,
    reasoning,
    input: image ? ["text", "image"] : ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128000,
    maxTokens: 8192,
  };
}

async function fetchModels(signal: AbortSignal | undefined) {
  const key = resolveKey();
  const response = await fetch(`${BASE_URL}/models`, {
    signal,
    headers: {
      authorization: `Bearer ${key.key}`,
      "x-caller-skill": "pi-scillm-provider",
    },
  });
  if (!response.ok) throw new Error(`SciLLM model refresh failed: HTTP ${response.status}`);
  const payload = await response.json() as { data?: Array<{ id?: unknown }> };
  const ids = (payload.data ?? []).map((item) => String(item.id || "").trim()).filter(Boolean);
  return [...new Set(ids)].map(modelConfig);
}

function writeReceipt(receipt: Record<string, unknown>): void {
  mkdirSync(RECEIPT_DIR, { recursive: true });
  const latest = join(RECEIPT_DIR, "latest.json");
  const jsonl = join(RECEIPT_DIR, "requests.jsonl");
  const text = JSON.stringify(receipt, null, 2);
  writeFileSync(latest, text + "\n", "utf8");
  appendFileSync(jsonl, JSON.stringify(receipt) + "\n", "utf8");
}

function payloadShape(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== "object") return { type: typeof payload };
  const obj = payload as Record<string, unknown>;
  return {
    keys: Object.keys(obj).sort(),
    model: typeof obj.model === "string" ? obj.model : undefined,
    message_count: Array.isArray(obj.messages) ? obj.messages.length : undefined,
    input_count: Array.isArray(obj.input) ? obj.input.length : undefined,
    stream: obj.stream,
  };
}

function isOurProvider(ctx: any): boolean {
  return ctx?.model?.provider === PROVIDER_ID || ctx?.model?.provider?.id === PROVIDER_ID;
}

export default function tauScillmProvider(pi: ExtensionAPI): void {
  const key = resolveKey();

  pi.registerProvider(PROVIDER_ID, {
    name: "Tau/SciLLM Local",
    baseUrl: BASE_URL,
    apiKey: key.key,
    api: "openai-completions",
    headers: {
      "X-Caller-Skill": "pi-scillm-provider",
      "X-Pi-Provider": PROVIDER_ID,
    },
    models: STATIC_MODELS.map(modelConfig),
    async refreshModels({ signal }: { signal?: AbortSignal }) {
      return fetchModels(signal);
    },
  });

  pi.registerCommand("tau-scillm-provider", {
    description: "Show Tau/SciLLM local provider status without exposing the proxy key",
    handler: async (_args: string, ctx: any) => {
      const resolved = resolveKey();
      let status = "unknown";
      try {
        const response = await fetch(`${HEALTH_URL}/health/liveliness`, { signal: ctx.signal });
        status = response.ok ? "ok" : `HTTP ${response.status}`;
      } catch (error) {
        status = error instanceof Error ? error.message : String(error);
      }
      ctx.ui.notify(`Tau/SciLLM provider ${PROVIDER_ID}: ${status}; base=${BASE_URL}; key=${resolved.source}:${resolved.fingerprint}; receipts=${RECEIPT_DIR}`, status === "ok" ? "info" : "warning");
    },
  });

  pi.on("before_provider_request", (event: any, ctx: any) => {
    if (!isOurProvider(ctx)) return;
    const resolved = resolveKey();
    pendingReceipt = {
      request_id: randomUUID(),
      provider_id: PROVIDER_ID,
      model_id: String(ctx?.model?.id || "unknown"),
      base_url: BASE_URL,
      started_at: new Date().toISOString(),
      request_hash: sha256(JSON.stringify(event.payload)),
      payload_shape: payloadShape(event.payload),
      key_fingerprint: resolved.fingerprint,
      key_source: resolved.source,
      live: true,
      mocked: false,
    };
    writeReceipt({ ...pendingReceipt, phase: "before_provider_request" });
  });

  pi.on("after_provider_response", (event: any, ctx: any) => {
    if (!isOurProvider(ctx) || !pendingReceipt) return;
    const receipt = {
      ...pendingReceipt,
      phase: "after_provider_response",
      status: event.status,
      response_headers: event.headers,
      ended_at: new Date().toISOString(),
    };
    writeReceipt(receipt);
    pendingReceipt = null;
  });
}
