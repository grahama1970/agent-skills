"use strict";
// Adversarial coverage: the page changed or is incorrect, and the doctor must
// either self-correct (drifted primary -> working fallback) or stop with an
// actionable reason. Run: node --test preflight_doctor_adversarial.test.cjs
const test = require("node:test");
const assert = require("node:assert");
const { computeVerdict } = require("./lib/preflight_doctor.js");

const base = {
  href: "https://chatgpt.com/", title: "ChatGPT", loggedOut: false, cloudflare: false,
  composer: { primary: "#prompt-textarea", matched: "#prompt-textarea", id: "prompt-textarea" },
  send: { primary: 'button[data-testid="send-button"]', matched: 'button[data-testid="send-button"]' },
  modal: { present: false, text: null }, bodyText: "chatgpt ready",
};

test("healthy page -> PROCEED, submit uses the primary selector", () => {
  const r = computeVerdict(base, null);
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.selfCorrected, false);
  assert.equal(r.selfCorrect.composer, "#prompt-textarea");
});

test("ADVERSARIAL: composer primary renamed, fallback present -> self-correct and PROCEED", () => {
  const cap = { ...base, composer: { primary: "#prompt-textarea", matched: ".ProseMirror", id: null } };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.selfCorrected, true);
  assert.equal(r.drift[0].target, "composer");
  assert.equal(r.selfCorrect.composer, ".ProseMirror"); // submit self-heals to the fallback
});

test("ADVERSARIAL: send button data-testid changed, form-submit fallback -> self-correct", () => {
  const cap = { ...base, send: { primary: 'button[data-testid="send-button"]', matched: 'form button[type="submit"]' } };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.selfCorrected, true);
  assert.equal(r.selfCorrect.send, 'form button[type="submit"]');
});

test("ADVERSARIAL: composer entirely gone (no fallback) -> STOP_HANDOFF, no self-correct", () => {
  const cap = { ...base, composer: { primary: "#prompt-textarea", matched: null, id: null } };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "composer_selector_drift_all_missing");
  assert.equal(r.selfCorrect, null);
});

test("ADVERSARIAL: page is a login wall -> STOP_HANDOFF logged_out", () => {
  const cap = { ...base, href: "https://auth.openai.com/log-in", loggedOut: true };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "logged_out");
});

test("ADVERSARIAL: cloudflare challenge -> RETRY_AFTER_RELOAD (never solved)", () => {
  const cap = { ...base, cloudflare: true };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "RETRY_AFTER_RELOAD");
  assert.equal(r.reason, "cloudflare_challenge");
});

test("ADVERSARIAL: rate limited -> STOP_HANDOFF", () => {
  const cap = { ...base, bodyText: "too many requests. please try again later." };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "STOP_HANDOFF");
  assert.equal(r.reason, "rate_limited");
});

test("ADVERSARIAL: DOM changed since last successful run -> cross-run drift flagged", () => {
  const baseline = { composer: "#prompt-textarea", send: 'button[data-testid="send-button"]' };
  const cap = { ...base, composer: { primary: "#prompt-textarea", matched: ".ProseMirror", id: null } };
  const r = computeVerdict(cap, baseline);
  assert.equal(r.driftSinceBaseline.length, 1);
  assert.equal(r.driftSinceBaseline[0].target, "composer");
  assert.equal(r.driftSinceBaseline[0].now, ".ProseMirror");
});

test("LIVE-FOUND REGRESSION: send button absent BEFORE typing -> PROCEED (advisory), not a false STOP", () => {
  // ChatGPT renders the send button only after the composer has text; a false
  // STOP here (send_selector_drift_all_missing) broke real submits (host log
  // 2026-08-27T12:53:54Z). Composer present => PROCEED, send is advisory.
  const cap = { ...base, send: { primary: 'button[data-testid="send-button"]', matched: null } };
  const r = computeVerdict(cap, null);
  assert.equal(r.verdict, "PROCEED");
  assert.equal(r.reason, null);
  assert.equal(r.sendAdvisory, "send_button_absent_pre_typing_expected");
  assert.equal(r.selfCorrect.send, null); // submit re-locates send after typing
});
