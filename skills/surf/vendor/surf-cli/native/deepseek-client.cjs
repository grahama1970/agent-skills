const { insertPromptText } = require("./prompt-insert.cjs");

const DEEPSEEK_URL = "https://chat.deepseek.com/";
const DEFAULT_MODE = "Expert";
const SUPPORTED_MODES = ["Instant", "Expert", "Vision"];

// Verified against the live app on 2026-07-28 (agent-skills#1067):
// - the composer is a plain <textarea placeholder="Message DeepSeek">;
// - mode chips are <span> labels inside a chip <div>, duplicated by an
//   aria-hidden [data-role="measure"] clone that must be filtered out;
// - the empty state announces the active mode as "Start chatting with <Mode>";
// - the assistant turn renders into .ds-assistant-message-main-content, and the
//   completion sentinel survives verbatim there even though document.body
//   innerText shows a punctuation-stripped copy from the sidebar title.
const SELECTORS = {
  promptTextarea: "textarea",
  assistantContent: ".ds-assistant-message-main-content",
  sendButton: 'div[role="button"][class*="ds-button--primary"]',
};

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// cdp.evaluateScript resolves to the raw Runtime.evaluate payload
// ({ result: { value, type }, exceptionDetails }), so unwrap to the value and
// surface page-side exceptions instead of returning a descriptor object.
async function evaluate(cdp, expression) {
  const payload = await cdp(expression);
  if (payload && typeof payload === "object") {
    if (payload.exceptionDetails) {
      const details = payload.exceptionDetails;
      throw new Error(details.exception?.description || details.text || "page evaluate threw");
    }
    if (payload.error) throw new Error(String(payload.error));
    if (payload.result && typeof payload.result === "object" && "value" in payload.result) {
      return payload.result.value;
    }
    if ("value" in payload) return payload.value;
  }
  return payload;
}

function parseJsonResult(value, label) {
  if (value == null) throw new Error(`${label}: empty evaluate result`);
  if (typeof value === "object") return value;
  try {
    return JSON.parse(String(value));
  } catch (error) {
    throw new Error(`${label}: unparsable evaluate result (${String(value).slice(0, 120)})`);
  }
}

const activeModeExpression = `(() => {
  const match = (document.body.innerText || "").match(/Start chatting with (Instant|Expert|Vision)/i);
  return JSON.stringify({ activeMode: match ? match[1] : "", inConversation: !match });
})()`;

function modeChipExpression(mode) {
  return `(() => {
    const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
    const chip = [...document.querySelectorAll("span")].find((span) =>
      norm(span.textContent).toLowerCase() === ${JSON.stringify(mode.toLowerCase())} &&
      !span.closest('[aria-hidden="true"],[data-role="measure"]'));
    if (!chip) return JSON.stringify({ found: false });
    const target = chip.parentElement || chip;
    const rect = target.getBoundingClientRect();
    if (!rect.width || !rect.height) return JSON.stringify({ found: false, reason: "chip_not_visible" });
    return JSON.stringify({
      found: true,
      x: Math.round(rect.x + rect.width / 2),
      y: Math.round(rect.y + rect.height / 2),
    });
  })()`;
}

async function readActiveMode(cdp) {
  return parseJsonResult(await evaluate(cdp, activeModeExpression), "active mode probe");
}

// Synthetic MouseEvents do not flip the DeepSeek mode chip (observed on the live
// app); a real CDP mouse press at the chip centre does.
// Mirrors the CDP controller's click sequence: a hover first, then press with
// buttons=1 and release with buttons=0. A bare press/release pair does not flip
// the DeepSeek mode chip.
async function clickPoint(inputCdp, x, y) {
  await inputCdp("Input.dispatchMouseEvent", { type: "mouseMoved", x, y, button: "none", buttons: 0, modifiers: 0 });
  await delay(100);
  await inputCdp("Input.dispatchMouseEvent", {
    type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1, modifiers: 0,
  });
  await delay(12);
  await inputCdp("Input.dispatchMouseEvent", {
    type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1, modifiers: 0,
  });
}

async function selectMode(cdp, inputCdp, mode, log = () => {}) {
  const desired = SUPPORTED_MODES.find((item) => item.toLowerCase() === String(mode || "").toLowerCase());
  if (!desired) {
    throw new Error(`Unsupported DeepSeek mode: ${mode}. Supported: ${SUPPORTED_MODES.join(", ")}`);
  }
  const before = await readActiveMode(cdp);
  if (before.inConversation) {
    // The mode banner only exists on the empty state, so an existing
    // conversation cannot prove which tier will answer.
    throw new Error(
      `deepseek_mode_unverifiable: the controlled tab is already in a conversation, so ${desired} mode cannot be confirmed. Use a fresh DeepSeek tab.`,
    );
  }
  if (before.activeMode.toLowerCase() === desired.toLowerCase()) {
    log(`Mode already ${desired}`);
    return { mode: desired, changed: false, verified: true, before: before.activeMode };
  }
  const chip = parseJsonResult(await evaluate(cdp, modeChipExpression(desired)), "mode chip probe");
  if (!chip.found) {
    throw new Error(`deepseek_mode_chip_missing: no visible ${desired} chip on the controlled tab`);
  }
  // The chip does not react while the tab is hidden: synthetic events are
  // ignored on every ancestor and a background CDP click leaves the mode at
  // Instant. Bring the page to front for the click, then verify.
  await inputCdp("Page.bringToFront", {}).catch(() => {});
  await delay(200);
  await clickPoint(inputCdp, chip.x, chip.y);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await delay(150);
    const after = await readActiveMode(cdp);
    if (after.activeMode.toLowerCase() === desired.toLowerCase()) {
      log(`Mode selected: ${desired}`);
      return { mode: desired, changed: true, verified: true, before: before.activeMode };
    }
  }
  throw new Error(
    `deepseek_mode_not_applied: clicked the ${desired} chip but the app still reports ${before.activeMode}`,
  );
}

async function waitForPromptReady(cdp, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await evaluate(
      cdp,
      `(() => !!document.querySelector(${JSON.stringify(SELECTORS.promptTextarea)}))()`,
    ).catch(() => false);
    if (ready === true || ready === "true") return true;
    await delay(300);
  }
  return false;
}

async function typePrompt(cdp, inputCdp, prompt) {
  const focused = await evaluate(
    cdp,
    `(() => {
      const node = document.querySelector(${JSON.stringify(SELECTORS.promptTextarea)});
      if (!node) return false;
      node.focus();
      return document.activeElement === node;
    })()`,
  );
  if (focused !== true && focused !== "true") {
    throw new Error("Failed to focus the DeepSeek composer");
  }
  await insertPromptText(inputCdp, prompt);
  await delay(250);
  const chars = await evaluate(
    cdp,
    `(() => (document.querySelector(${JSON.stringify(SELECTORS.promptTextarea)})?.value || "").length)()`,
  );
  if (Number(chars) <= 0) {
    throw new Error("DeepSeek composer stayed empty after prompt insertion");
  }
  return Number(chars);
}

async function clickSend(cdp, inputCdp) {
  const target = parseJsonResult(
    await evaluate(
      cdp,
      `(() => {
        const button = document.querySelector(${JSON.stringify(SELECTORS.sendButton)});
        if (!button) return JSON.stringify({ found: false });
        const rect = button.getBoundingClientRect();
        return JSON.stringify({
          found: true,
          x: Math.round(rect.x + rect.width / 2),
          y: Math.round(rect.y + rect.height / 2),
        });
      })()`,
    ),
    "send button probe",
  );
  if (!target.found) throw new Error("DeepSeek send button not found");
  await clickPoint(inputCdp, target.x, target.y);
}

function assistantSnapshotExpression(sentinel) {
  return `(() => {
    const nodes = [...document.querySelectorAll(${JSON.stringify(SELECTORS.assistantContent)})];
    const last = nodes[nodes.length - 1];
    const text = last ? (last.innerText || "") : "";
    return JSON.stringify({
      count: nodes.length,
      text,
      chars: text.length,
      hasSentinel: ${JSON.stringify(Boolean(sentinel))} ? text.includes(${JSON.stringify(sentinel || "")}) : false,
    });
  })()`;
}

// Sentinel matching is deliberately scoped to the assistant container: the page
// body also carries the prompt echo and a sidebar title, so a body-wide match
// would report delivery proof from our own prompt text.
async function waitForResponse(cdp, { sentinel, timeoutMs = 900000, stablePolls = 2 }) {
  const deadline = Date.now() + timeoutMs;
  let stable = 0;
  let previous = "";
  while (Date.now() < deadline) {
    const snapshot = parseJsonResult(
      await evaluate(cdp, assistantSnapshotExpression(sentinel)).catch(() => null),
      "assistant snapshot",
    );
    if (sentinel && snapshot.hasSentinel) {
      if (snapshot.text === previous) {
        stable += 1;
        if (stable >= stablePolls) {
          return { text: snapshot.text, hasSentinel: true, source: "assistant_container" };
        }
      } else {
        stable = 0;
      }
      previous = snapshot.text;
    } else if (!sentinel && snapshot.chars > 0) {
      if (snapshot.text === previous) {
        stable += 1;
        if (stable >= stablePolls) {
          return { text: snapshot.text, hasSentinel: false, source: "assistant_container" };
        }
      } else {
        stable = 0;
      }
      previous = snapshot.text;
    }
    await delay(700);
  }
  throw new Error("DeepSeek response timeout");
}

async function setDeepseekFiles(inputCdp, filePaths, log) {
  const result = await inputCdp("Runtime.evaluate", {
    expression: `(() => {
      const input = document.querySelector('input[type=file]');
      if (!input || input.tagName !== 'INPUT' || input.type !== 'file') return null;
      return input;
    })()`,
    userGesture: true,
  });
  const objectId = result?.result?.objectId;
  if (!objectId) {
    log("No file input on the DeepSeek composer");
    return false;
  }
  await inputCdp("DOM.setFileInputFiles", { files: filePaths, objectId });
  // DOM.setFileInputFiles populates input.files but a React composer only
  // notices through its own listeners. Without an explicit change/input pair
  // DeepSeek submitted happily and answered "No image attached" -- a lane that
  // looks like the model ignored the picture when it never received one.
  await inputCdp("Runtime.callFunctionOn", {
    objectId,
    functionDeclaration: `function () {
      this.dispatchEvent(new Event('input', { bubbles: true }));
      this.dispatchEvent(new Event('change', { bubbles: true }));
      return this.files ? this.files.length : 0;
    }`,
    userGesture: true,
  });
  return true;
}


//: The composer shows the file name once it has accepted the upload. Waiting on
//: that, rather than on a fixed sleep, is the difference between attaching and
//: appearing to attach.
async function waitForAttachmentVisible(cdp, names, log, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  const wanted = names.map((n) => String(n).split("/").pop());
  while (Date.now() < deadline) {
    const body = await evaluate(cdp, "document.body.innerText || ''").catch(() => "");
    if (wanted.some((n) => n && String(body).includes(n))) return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  log(`Attachment name never appeared in the composer: ${wanted.join(", ")}`);
  return false;
}

//: An upload is asynchronous: the composer shows a chip once the file is
//: accepted. Sending before it settles submits a prompt with no attachment,
//: which reads as a model that ignored the image.
async function waitForAttachmentSettled(cdp, log, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const busy = await evaluate(
      cdp,
      "(document.body.innerText||'').match(/uploading|上传中/i) ? '1' : '0'",
    ).catch(() => "0");
    if (String(busy) !== "1") {
      await new Promise((r) => setTimeout(r, 1200));
      return true;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
  log("Attachment still uploading at deadline; submitting anyway");
  return false;
}

async function query(options) {
  const {
    prompt,
    mode = DEFAULT_MODE,
    file,
    timeout = 900000,
    sentinel,
    stablePolls = 2,
    keepTab = false,
    noActivate = false,
    createTab,
    closeTab,
    cdpEvaluate,
    cdpCommand,
    uploadFile,
    log = () => {},
  } = options;
  const attachments = Array.isArray(file) ? file.filter(Boolean) : (file ? [file] : []);
  const startTime = Date.now();
  log("Starting DeepSeek query");
  const tabInfo = await createTab();
  const tabId = tabInfo?.tabId;
  if (!tabId) throw new Error("Failed to obtain a DeepSeek tab");
  log(`${tabInfo.reused ? "Using" : "Created"} tab ${tabId}`);

  const cdp = (expression) => cdpEvaluate(tabId, expression);
  const inputCdp = (method, params, timeoutMs) => cdpCommand(tabId, method, params, timeoutMs);

  try {
    if (!(await waitForPromptReady(cdp))) throw new Error("DeepSeek composer not ready");
    log("Prompt ready");
    const modeSelection = await selectMode(cdp, inputCdp, mode, log);
    if (attachments.length) {
      // chat.deepseek.com renders one unhidden multiple-file input accepting
      // .png/.jpg/.jpeg/.webp (verified on a live tab 2026-08-16), so files go
      // in directly via DOM.setFileInputFiles -- the same path grok uses. This
      // used to throw "attachments are not supported for this provider",
      // which was true of the old provider allowlist and not of the page.
      // Prefer the extension's upload path; it intercepts the file chooser
      // the way the composer expects. The direct-input write is kept only as a
      // fallback for hosts that do not inject uploadFile.
      let uploaded = false;
      if (typeof uploadFile === "function") {
        try {
          await uploadFile(tabId, attachments);
          uploaded = true;
        } catch (err) {
          log(`Extension upload failed (${err && err.message}); trying direct input`);
        }
      }
      if (!uploaded) uploaded = await setDeepseekFiles(inputCdp, attachments, log);
      if (!uploaded) {
        throw new Error("deepseek_attachment_input_missing: no file input found on the DeepSeek composer");
      }
      if (!(await waitForAttachmentVisible(cdp, attachments, log))) {
        throw new Error(
          "deepseek_attachment_not_visible: the file never appeared in the composer; " +
          "submitting would ask about an image DeepSeek never received",
        );
      }
      log(`Attached ${attachments.length} file(s)`);
      await waitForAttachmentSettled(cdp, log);
    }
    const composerChars = await typePrompt(cdp, inputCdp, prompt);
    log(`Prompt typed (${composerChars} chars in composer)`);
    await clickSend(cdp, inputCdp);
    log("Prompt sent, waiting for response...");
    const response = await waitForResponse(cdp, { sentinel, timeoutMs: timeout, stablePolls });
    const conversationUrl = await evaluate(cdp, "window.location.href").catch(() => null);
    log(`Response received (${response.text.length} chars)`);
    return {
      response: response.text,
      mode: modeSelection.mode,
      modeVerified: modeSelection.verified,
      modeChanged: modeSelection.changed,
      modeBefore: modeSelection.before,
      tabId,
      controlledTabId: tabId,
      conversationUrl,
      responseSource: response.source,
      sentinel,
      hasSentinel: response.hasSentinel,
      tookMs: Date.now() - startTime,
      activated: tabInfo.activated === true,
      noActivate: noActivate === true,
    };
  } finally {
    if (!keepTab) await closeTab(tabId).catch(() => {});
  }
}

module.exports = {
  query,
  selectMode,
  readActiveMode,
  waitForResponse,
  assistantSnapshotExpression,
  modeChipExpression,
  DEEPSEEK_URL,
  DEFAULT_MODE,
  SUPPORTED_MODES,
  SELECTORS,
};
