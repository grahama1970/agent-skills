"use strict";
/**
 * Preflight DOM doctor for the /ask webgpt submit path (webgpt-submit.sh).
 *
 * Unlike the copy in chatgpt-client.cjs query() (surf's standalone CLI), this
 * runs PAGE-SIDE via `surf js` — which is how webgpt-submit.sh drives the DOM —
 * so it actually executes on the /ask webgpt lane.
 *
 * Two exports:
 *   captureExpression(): a self-contained IIFE string injected with `surf js`
 *     that returns the raw DOM capture (which layered selector matched, blocking
 *     states) — no verdict logic in the page.
 *   computeVerdict(capture, baseline): PURE function turning a capture (+ the
 *     last-good per-provider fingerprint) into the receipt, including
 *     self-correction: the exact selector the submit should use, so a drifted
 *     primary anchor self-heals to a working fallback instead of failing.
 *
 * Boundary: detects captcha/challenge and returns RETRY_AFTER_RELOAD or
 * STOP_HANDOFF; never solves or clicks through bot-detection.
 */

// Layered selectors, primary (stable data-testid) first. Mirrors surf's client.
const COMPOSER = [
  "#prompt-textarea",
  '[data-testid="composer-textarea"]',
  'textarea[name="prompt-textarea"]',
  ".ProseMirror",
];
const SEND = [
  'button[data-testid="send-button"]',
  'button[data-testid*="composer-send"]',
  'form button[type="submit"]',
];

/** The page-side capture. Returns a plain object; contains no verdict logic. */
function captureExpression() {
  const composer = JSON.stringify(COMPOSER);
  const send = JSON.stringify(SEND);
  return `(() => {
    const firstMatch = (arr) => { for (const s of arr) { try { if (document.querySelector(s)) return s; } catch (e) {} } return null; };
    const composerSel = ${composer};
    const sendSel = ${send};
    const cMatch = firstMatch(composerSel);
    const sMatch = firstMatch(sendSel);
    const cEl = cMatch ? document.querySelector(cMatch) : null;
    const modal = document.querySelector('[role="dialog"], [role="alertdialog"], [aria-modal="true"]');
    const title = String(document.title || '').toLowerCase();
    const body = String(document.body && document.body.innerText || '').toLowerCase().replace(/\\s+/g, ' ').slice(0, 4000);
    const cfText = body.includes('checking your browser') || body.includes('verify you are human') ||
      body.includes('needs to review the security') || title.includes('just a moment');
    return {
      href: location.href,
      title: document.title || '',
      loggedOut: /\\/auth\\/(login|log-in)|auth0|login\\.(openai|chatgpt)/i.test(location.href) ||
        body.includes('log in') && !cMatch,
      composer: { primary: composerSel[0], matched: cMatch, id: (cEl && cEl.id) || null },
      send: { primary: sendSel[0], matched: sMatch },
      cloudflare: Boolean(cfText),
      modal: { present: !!modal, text: modal ? String(modal.innerText || '').slice(0, 600) : null },
      bodyText: body,
    };
  })()`;
}

function _rateLimited(bodyText) {
  const t = String(bodyText || "");
  const hasTitle = t.includes("too many requests") || t.includes("you've hit your limit") || t.includes("you have hit your limit");
  const hasThrottle = t.includes("making requests too quickly") || t.includes("please wait a few minutes") ||
    t.includes("please try again later") || t.includes("temporarily limited access to your conversations");
  return hasTitle && hasThrottle;
}

/**
 * Pure verdict + self-correction. baseline is the last-good fingerprint for this
 * provider ({composer, send}) or null.
 * Returns receipt: { verdict, reason, drift[], driftSinceBaseline[], selfCorrect, ... }
 */
function computeVerdict(cap, baseline) {
  cap = cap || {};
  const composer = cap.composer || { primary: null, matched: null };
  const send = cap.send || { primary: null, matched: null };
  const rateLimited = _rateLimited(cap.bodyText);

  // In-run drift: primary anchor changed but a fallback matched.
  const drift = [];
  if (composer.matched && composer.primary && composer.matched !== composer.primary) {
    drift.push({ target: "composer", expected: composer.primary, matched_fallback: composer.matched });
  }
  if (send.matched && send.primary && send.matched !== send.primary) {
    drift.push({ target: "send", expected: send.primary, matched_fallback: send.matched });
  }

  // Cross-run drift vs last-good fingerprint.
  const driftSinceBaseline = [];
  if (baseline) {
    if (baseline.composer !== composer.matched) {
      driftSinceBaseline.push({ target: "composer", was: baseline.composer || null, now: composer.matched || null });
    }
    if (baseline.send !== send.matched) {
      driftSinceBaseline.push({ target: "send", was: baseline.send || null, now: send.matched || null });
    }
  }

  // NOTE (live-verified 2026-08-27): ChatGPT renders the send button only AFTER
  // the composer has text, so send-absence BEFORE typing is expected, not a
  // failure. The pre-typing gate is the composer + blocking states; the send
  // button is advisory here (reported + drift-tracked). surf's existing
  // post-submit "Prompt accepted" / sentinel check verifies send actually
  // worked. Hard-failing on pre-typing send-absence gave a false STOP that
  // would break every real submit.
  let verdict = "PROCEED";
  let reason = null;
  if (cap.loggedOut) { verdict = "STOP_HANDOFF"; reason = "logged_out"; }
  else if (cap.cloudflare) { verdict = "RETRY_AFTER_RELOAD"; reason = "cloudflare_challenge"; }
  else if (!composer.matched) { verdict = "STOP_HANDOFF"; reason = "composer_selector_drift_all_missing"; }
  else if (rateLimited) { verdict = "STOP_HANDOFF"; reason = "rate_limited"; }
  const sendAdvisory = !send.matched ? "send_button_absent_pre_typing_expected" : null;

  // Self-correction: the submit uses the selector that actually resolved, so a
  // drifted primary self-heals to a working fallback. Null on STOP.
  const selfCorrect = verdict === "PROCEED"
    ? { composer: composer.matched, send: send.matched }
    : null;

  return {
    schema: "surf.preflight_doctor.v1",
    verdict, reason,
    href: cap.href || null,
    title: cap.title || null,
    cloudflare: Boolean(cap.cloudflare),
    loggedOut: Boolean(cap.loggedOut),
    rateLimited,
    modal: cap.modal || { present: false, text: null },
    composer, send,
    sendAdvisory,
    drift, driftSinceBaseline,
    selfCorrect,
    selfCorrected: drift.length > 0 && verdict === "PROCEED",
  };
}

module.exports = { COMPOSER, SEND, captureExpression, computeVerdict };
