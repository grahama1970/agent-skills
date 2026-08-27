#!/usr/bin/env node
"use strict";
/**
 * Preflight-doctor runner for the /ask webgpt submit path.
 *
 * Modes:
 *   --tab-id <id> [--run-sh <path>]   Capture the LIVE page via `surf js`, apply
 *                                     the verdict + self-correction + cross-run
 *                                     baseline, print the receipt, exit by
 *                                     verdict (0 PROCEED, 2 RETRY_AFTER_RELOAD,
 *                                     3 STOP_HANDOFF, 4 capture error).
 *   --capture-file <json>             Compute the verdict from a saved capture
 *                                     (hermetic tests). Same exit codes.
 *
 * On PROCEED the per-provider selector fingerprint is persisted so the next run
 * can flag cross-run drift. Baseline path: SURF_PREFLIGHT_BASELINE or
 * ~/.surf/preflight-baselines.json. Best-effort; never blocks on baseline I/O.
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { captureExpression, computeVerdict } = require("./lib/preflight_doctor.js");

const EXIT = { PROCEED: 0, RETRY_AFTER_RELOAD: 2, STOP_HANDOFF: 3, CAPTURE_ERROR: 4 };

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : dflt;
}

function baselinePath() {
  return process.env.SURF_PREFLIGHT_BASELINE ||
    path.join(os.homedir() || os.tmpdir(), ".surf", "preflight-baselines.json");
}
function providerKey(href) {
  let host = "";
  try { host = new URL(href || "").host; } catch (e) { host = ""; }
  if (/chatgpt\.com|chat\.openai\.com/.test(host)) return "chatgpt";
  return host || "unknown";
}
function loadBaselines() {
  try { return JSON.parse(fs.readFileSync(baselinePath(), "utf8")) || {}; } catch (e) { return {}; }
}
function saveBaselines(all) {
  try {
    const p = baselinePath();
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(all, null, 2));
    return true;
  } catch (e) { return false; }
}

function captureLive(tabId, runSh) {
  const res = spawnSync(runSh, ["js", captureExpression(), "--tab-id", tabId, "--no-activate"],
    { encoding: "utf8", timeout: 30000 });
  if (res.status !== 0) {
    return { error: `surf js failed rc=${res.status}: ${(res.stderr || "").slice(0, 300)}` };
  }
  // surf js prints the evaluated value as JSON (possibly with surrounding lines).
  const out = res.stdout || "";
  const start = out.indexOf("{");
  const end = out.lastIndexOf("}");
  if (start < 0 || end <= start) return { error: `no JSON in surf js output: ${out.slice(0, 200)}` };
  try { return { capture: JSON.parse(out.slice(start, end + 1)) }; }
  catch (e) { return { error: `capture parse failed: ${e.message}` }; }
}

function main() {
  const captureFile = arg("--capture-file");
  const tabId = arg("--tab-id");
  const runSh = arg("--run-sh", path.join(__dirname, "..", "run.sh"));

  let capture;
  if (captureFile) {
    capture = JSON.parse(fs.readFileSync(captureFile, "utf8"));
  } else if (tabId) {
    const r = captureLive(tabId, runSh);
    if (r.error) {
      console.log(JSON.stringify({ schema: "surf.preflight_doctor.v1", verdict: "STOP_HANDOFF",
        reason: "capture_error", error: r.error }, null, 2));
      return EXIT.CAPTURE_ERROR;
    }
    capture = r.capture;
  } else {
    console.error("usage: preflight_run.cjs (--tab-id <id> | --capture-file <json>)");
    return EXIT.CAPTURE_ERROR;
  }

  const provider = providerKey(capture.href);
  const baselines = loadBaselines();
  const receipt = computeVerdict(capture, baselines[provider] || null);
  receipt.provider = provider;
  receipt.baselineFirstSeen = !baselines[provider];

  if (receipt.verdict === "PROCEED") {
    baselines[provider] = { composer: receipt.composer.matched, send: receipt.send.matched, updated_at: Date.now() };
    receipt.baselinePersisted = saveBaselines(baselines);
  } else {
    receipt.baselinePersisted = false;
  }

  console.log(JSON.stringify(receipt, null, 2));
  return EXIT[receipt.verdict] !== undefined ? EXIT[receipt.verdict] : EXIT.STOP_HANDOFF;
}

process.exit(main());
