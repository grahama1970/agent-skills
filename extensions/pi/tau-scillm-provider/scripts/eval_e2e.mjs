#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const extensionPath = resolve(scriptDir, "..", "index.ts");
const repoRoot = resolve(scriptDir, "..", "..", "..", "..");
const outDir = process.env.TAU_SCILLM_PROVIDER_EVAL_DIR || "/tmp/tau-scillm-provider-eval";
mkdirSync(outDir, { recursive: true });

function writeCase(name, data) {
  const path = join(outDir, `${name}.json`);
  writeFileSync(path, JSON.stringify({ schema: "tau_scillm_provider.eval.v1", case: name, ...data }, null, 2) + "\n", "utf8");
  return path;
}

function fail(name, message, extra = {}) {
  const path = writeCase(name, { ok: false, message, ...extra });
  console.error(`${name}: FAIL: ${message}; receipt=${path}`);
  process.exit(1);
}

function pass(name, data) {
  const path = writeCase(name, { ok: true, ...data });
  console.log(`${name}: PASS receipt=${path}`);
}

function runPi(args, env = {}, timeoutMs = 120_000) {
  const childEnv = { ...process.env, ...env };
  return spawnSync("pi", args, {
    cwd: repoRoot,
    env: childEnv,
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: 20 * 1024 * 1024,
  });
}

function parseJsonLines(text) {
  const events = [];
  for (const line of (text || "").split(/\n/)) {
    if (!line.trim().startsWith("{")) continue;
    try { events.push(JSON.parse(line)); } catch {}
  }
  return events;
}

function assertNoLoadError(name, result) {
  const combined = `${result.stdout || ""}\n${result.stderr || ""}`;
  if (/Failed to load extension|SyntaxError|TypeError|Cannot find module/.test(combined)) {
    fail(name, "Pi reported an extension load error", { status: result.status, stdout: result.stdout, stderr: result.stderr });
  }
}

function providerRegistered() {
  const name = "provider-registered";
  const result = runPi(["--no-extensions", "-e", extensionPath, "--list-models"], {}, 60_000);
  assertNoLoadError(name, result);
  const hasProvider = /^tau-scillm\s+local-text\b/m.test(result.stdout || "");
  if (result.status !== 0 || !hasProvider) {
    fail(name, "tau-scillm/local-text was not listed by Pi", { status: result.status, stdout: result.stdout, stderr: result.stderr });
  }
  pass(name, { provider_id: "tau-scillm", model_id: "local-text", pi_exit_code: result.status, readback: "pi --list-models stdout" });
}

function requestContract() {
  const name = "request-contract";
  const capturePath = join(outDir, "capture-fetch.ts");
  const capturedPath = join(outDir, "captured-fetch.json");
  writeFileSync(capturePath, `
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { writeFileSync } from "node:fs";
export default function(_pi: ExtensionAPI) {
  globalThis.fetch = (async (input: any, init?: any) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url.endsWith('/v1/models') || url.endsWith('/models')) {
      return new Response(JSON.stringify({ object: 'list', data: [{ id: 'local-text', object: 'model', owned_by: 'scillm' }] }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    const headers: Record<string, string> = {};
    const merged = new Headers(input instanceof Request ? input.headers : init?.headers);
    for (const [k, v] of merged.entries()) headers[k] = /authorization|api|key|token/i.test(k) ? '<redacted>' : v;
    let body = init?.body;
    if (input instanceof Request) body = await input.clone().text();
    writeFileSync(${JSON.stringify(capturedPath)}, JSON.stringify({ url, method: init?.method || (input instanceof Request ? input.method : undefined), headers, body: typeof body === 'string' ? JSON.parse(body) : String(body ?? '') }, null, 2));
    process.exit(43);
  }) as any;
}
`, "utf8");
  rmSync(capturedPath, { force: true });
  const result = runPi(["--no-extensions", "-e", capturePath, "-e", extensionPath, "--mode", "json", "--no-session", "--no-tools", "--provider", "tau-scillm", "--model", "local-text", "-p", "say ok"], {}, 60_000);
  if (result.status !== 43 || !existsSync(capturedPath)) {
    fail(name, "fetch capture did not intercept the chat completion request", { status: result.status, stdout: result.stdout, stderr: result.stderr });
  }
  const captured = JSON.parse(readFileSync(capturedPath, "utf8"));
  const headers = captured.headers || {};
  const body = captured.body || {};
  const problems = [];
  if (captured.url !== "http://127.0.0.1:4001/v1/chat/completions") problems.push(`url=${captured.url}`);
  if (headers["x-caller-skill"] !== "pi-scillm-provider") problems.push("missing x-caller-skill");
  if (headers["x-pi-provider"] !== "tau-scillm") problems.push("missing x-pi-provider");
  if (headers.authorization !== "<redacted>") problems.push("authorization header absent or not redacted in capture");
  if (body.model !== "local-text") problems.push(`body.model=${body.model}`);
  if (body.stream !== true) problems.push(`body.stream=${body.stream}`);
  if (!Array.isArray(body.messages) || body.messages.length < 2) problems.push("messages missing");
  if (problems.length) fail(name, "provider request contract mismatch", { problems, captured });
  pass(name, { readback: capturedPath, url: captured.url, provider_header: headers["x-pi-provider"], caller_header: headers["x-caller-skill"], model: body.model, stream: body.stream });
}

function liveReceiptE2e() {
  const name = "live-receipt-e2e";
  const receiptDir = join(outDir, "live-receipts");
  rmSync(receiptDir, { recursive: true, force: true });
  const env = { PI_SCILLM_RECEIPT_DIR: receiptDir, SCILLM_PROXY_KEY: "sk-stale-shell-key-must-not-win" };
  delete env.PI_SCILLM_API_KEY;
  const result = runPi(["--no-extensions", "-e", extensionPath, "--mode", "json", "--no-session", "--no-tools", "--provider", "tau-scillm", "--model", "local-text", "-p", "Return the word PASS only."], env, 150_000);
  assertNoLoadError(name, result);
  const receiptPath = join(receiptDir, "latest.json");
  if (result.status !== 0 || !existsSync(receiptPath)) {
    fail(name, "Pi live provider call did not complete with a receipt", { status: result.status, stdout: result.stdout, stderr: result.stderr });
  }
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
  const events = parseJsonLines(result.stdout);
  const assistantEnd = events.find((e) => e.type === "message_end" && e.message?.role === "assistant");
  const problems = [];
  if (receipt.provider_id !== "tau-scillm") problems.push(`receipt.provider_id=${receipt.provider_id}`);
  if (receipt.model_id !== "local-text") problems.push(`receipt.model_id=${receipt.model_id}`);
  if (receipt.status !== 200) problems.push(`receipt.status=${receipt.status}`);
  if (receipt.live !== true) problems.push("receipt.live is not true");
  if (receipt.mocked !== false) problems.push("receipt.mocked is not false");
  if (!String(receipt.key_source || "").startsWith("docker:docker-scillm-proxy-1:")) problems.push(`receipt.key_source=${receipt.key_source}`);
  if (!assistantEnd || assistantEnd.message?.stopReason !== "stop") problems.push("assistant message_end stopReason was not stop");
  if (problems.length) fail(name, "live receipt contract mismatch", { problems, receipt, status: result.status, stdout: result.stdout, stderr: result.stderr });
  pass(name, { receipt_path: receiptPath, provider_id: receipt.provider_id, model_id: receipt.model_id, status: receipt.status, live: receipt.live, mocked: receipt.mocked, key_source: receipt.key_source, assistant_stop_reason: assistantEnd.message.stopReason });
}

function badExplicitKey() {
  const name = "bad-explicit-key-fails-closed";
  const receiptDir = join(outDir, "bad-key-receipts");
  rmSync(receiptDir, { recursive: true, force: true });
  const result = runPi(["--no-extensions", "-e", extensionPath, "--mode", "json", "--no-session", "--no-tools", "--provider", "tau-scillm", "--model", "local-text", "-p", "say ok"], { PI_SCILLM_API_KEY: "sk-invalid-pi-scillm-provider-eval", PI_SCILLM_RECEIPT_DIR: receiptDir }, 60_000);
  assertNoLoadError(name, result);
  const combined = `${result.stdout || ""}\n${result.stderr || ""}`;
  const saw401 = combined.includes("Invalid API key") || combined.includes("401");
  const receiptPath = join(receiptDir, "latest.json");
  const receipt = existsSync(receiptPath) ? JSON.parse(readFileSync(receiptPath, "utf8")) : null;
  if (!saw401 || !receipt || receipt.key_source !== "env:PI_SCILLM_API_KEY" || receipt.phase !== "before_provider_request") {
    fail(name, "bad explicit PI_SCILLM_API_KEY was not the failing auth source", { status: result.status, saw401, receipt, stdout: result.stdout, stderr: result.stderr });
  }
  pass(name, { saw401, key_source: receipt.key_source, phase: receipt.phase, readback: receiptPath });
}

const command = process.argv[2];
switch (command) {
  case "provider-registered": providerRegistered(); break;
  case "request-contract": requestContract(); break;
  case "live-receipt-e2e": liveReceiptE2e(); break;
  case "bad-explicit-key-fails-closed": badExplicitKey(); break;
  default:
    console.error(`usage: ${process.argv[1]} provider-registered|request-contract|live-receipt-e2e|bad-explicit-key-fails-closed`);
    process.exit(2);
}
