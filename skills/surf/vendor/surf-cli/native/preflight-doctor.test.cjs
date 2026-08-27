"use strict";
// Verdict/drift coverage for preflightDoctor (chatgpt-client.cjs).
// Run: node --test preflight-doctor.test.cjs
const test = require("node:test");
const assert = require("node:assert");
const _os = require("node:os"), _path = require("node:path"), _fs = require("node:fs");
process.env.SURF_PREFLIGHT_BASELINE = _path.join(
  _fs.mkdtempSync(_path.join(_os.tmpdir(), "surfpf-")), "baselines.json");
const { preflightDoctor } = require("./chatgpt-client.cjs");

function mockCdp(scn) {
  return async (expr) => {
    if (expr.includes("document.title.toLowerCase")) return { result: { value: scn.title || "chatgpt" } };
    if (expr.includes("hasChallengeScript"))
      return {
        result: {
          value: scn.cf
            ? { hasChallengeText: true, hasVisibleChallenge: true, hasChatGptShell: false }
            : { hasChallengeText: false, hasVisibleChallenge: false, hasChatGptShell: true },
        },
      };
    if (expr.includes("loggedOut")) return { result: { value: scn.capture } };
    return { result: { value: null } };
  };
}

const healthy = {
  href: "https://chatgpt.com/", title: "ChatGPT", loggedOut: false,
  composer: { primary: "#prompt-textarea", matched: "#prompt-textarea", id: "prompt-textarea" },
  send: { primary: 'button[data-testid="send-button"]', matched: 'button[data-testid="send-button"]' },
  modal: { present: false, text: null }, bodyText: "chatgpt ready",
};

test("healthy page -> PROCEED, no drift", async () => {
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture: healthy }));
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.drift.length, 0);
});

test("primary composer anchor changed but fallback matches -> PROCEED + drift", async () => {
  const capture = { ...healthy, composer: { primary: "#prompt-textarea", matched: ".ProseMirror", id: null } };
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture }));
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.drift.length, 1);
  assert.equal(r.drift[0].target, "composer");
});

test("logged out -> STOP_HANDOFF", async () => {
  const capture = { ...healthy, href: "https://auth.openai.com/log-in", loggedOut: true };
  const r = await preflightDoctor(mockCdp({ title: "log in", cf: false, capture }));
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "logged_out");
});

test("all composer selectors gone -> STOP_HANDOFF", async () => {
  const capture = { ...healthy, composer: { primary: "#prompt-textarea", matched: null, id: null } };
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture }));
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "composer_selector_drift_all_missing");
});

test("cloudflare challenge -> RETRY_AFTER_RELOAD (never solved)", async () => {
  const r = await preflightDoctor(mockCdp({ title: "just a moment", cf: true, capture: healthy }));
  assert.equal(r.verdict, "RETRY_AFTER_RELOAD");
  assert.equal(r.reason, "cloudflare_challenge");
});

test("rate limited (surf two-marker detector) -> STOP_HANDOFF", async () => {
  const capture = { ...healthy, bodyText: "too many requests. please try again later." };
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture }));
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "rate_limited");
});

test("baseline: first run for a provider -> baselineFirstSeen, no cross-run drift", async () => {
  const cap = { ...healthy, href: "https://baseline-probe.local/" };
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture: cap }));
  assert.equal(r.baselineFirstSeen, true);
  assert.equal(r.driftSinceBaseline.length, 0);
  assert.equal(r.baselinePersisted, true);
});

test("baseline: matched selector changed since last run -> driftSinceBaseline", async () => {
  const host = "https://baseline-probe2.local/";
  await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture: { ...healthy, href: host } }));
  const changed = { ...healthy, href: host, send: { primary: 'button[data-testid="send-button"]', matched: 'form button[type="submit"]' } };
  const r = await preflightDoctor(mockCdp({ title: "chatgpt", cf: false, capture: changed }));
  assert.equal(r.baselineFirstSeen, false);
  assert.equal(r.driftSinceBaseline.length, 1);
  assert.equal(r.driftSinceBaseline[0].target, "send");
  assert.equal(r.driftSinceBaseline[0].now, 'form button[type="submit"]');
});
