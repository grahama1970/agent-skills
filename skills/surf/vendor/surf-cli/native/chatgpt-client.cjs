const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const CHATGPT_URL = "https://chatgpt.com/";

const SELECTORS = {
  promptTextarea: '#prompt-textarea, [data-testid="composer-textarea"], textarea[name="prompt-textarea"], [role="textbox"][aria-label*="Chat"], [role="textbox"][contenteditable="true"], [contenteditable="true"][data-virtualkeyboard="true"]',
  sendButton: 'button[data-testid="send-button"], button[data-testid*="composer-send"], form button[type="submit"]',
  modelButton: '[data-testid="model-switcher-dropdown-button"]',
  reasoningButton: 'button[data-testid*="reason"], button[aria-label*="reason" i], button[aria-label*="thinking" i], button[aria-label*="effort" i]',
  menuContainer: '[role="menu"], [data-radix-collection-root]',
  menuItem: 'button, [role="menuitem"], [role="menuitemradio"], [data-testid*="model-switcher-"]',
  assistantMessage: '[data-message-author-role="assistant"], [data-turn="assistant"]',
  stopButton: '[data-testid="stop-button"]',
  finishedActions: 'button[data-testid="copy-turn-action-button"], button[data-testid="good-response-turn-action-button"]',
  conversationTurn: 'article[data-testid^="conversation-turn"], div[data-testid^="conversation-turn"]',
  fileInput: 'input[type="file"]',
  cloudflareScript: 'script[src*="/challenge-platform/"]',
};

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const BACKGROUND_WAKE_EVERY_POLLS = 5;

async function wakeBackgroundTab(inputCdp, log, reason = "poll") {
  if (!inputCdp) return false;
  try {
    await inputCdp("Page.setWebLifecycleState", { state: "active" });
    log?.(`Background tab lifecycle set to active (${reason})`);
    return true;
  } catch (err) {
    log?.(`Page.setWebLifecycleState skipped (${reason}): ${err?.message || err}`);
    return false;
  }
}

async function nudgeBackgroundRendering(cdp, inputCdp, log, reason = "poll") {
  await wakeBackgroundTab(inputCdp, log, reason);
  try {
    await evaluate(
      cdp,
      `(() => {
        try {
          document.dispatchEvent(new Event('visibilitychange'));
          if (typeof document.onvisibilitychange === 'function') {
            document.onvisibilitychange(new Event('visibilitychange'));
          }
        } catch (_) {}
        return {
          documentHidden: document.hidden === true,
          visibilityState: document.visibilityState || null,
          documentHasFocus: typeof document.hasFocus === 'function' ? document.hasFocus() : null,
        };
      })()`,
    );
  } catch (err) {
    log?.(`Background render nudge skipped (${reason}): ${err?.message || err}`);
  }
}


function buildClickDispatcher() {
  return `function dispatchClickSequence(target){
    if(!target || !(target instanceof EventTarget)) return false;
    const types = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    for (const type of types) {
      const common = { bubbles: true, cancelable: true, view: window };
      let event;
      if (type.startsWith('pointer') && 'PointerEvent' in window) {
        event = new PointerEvent(type, { ...common, pointerId: 1, pointerType: 'mouse' });
      } else {
        event = new MouseEvent(type, common);
      }
      target.dispatchEvent(event);
    }
    return true;
  }`;
}

function hasRequiredCookies(cookies) {
  if (!cookies || !Array.isArray(cookies)) return false;
  const hasValue = (c) => Boolean(c && c.value);
  const legacy = cookies.find(
    (c) => c.name === "__Secure-next-auth.session-token" && hasValue(c)
  );
  if (legacy) return true;
  // NextAuth may shard large session cookies as .0, .1, ...
  return cookies.some(
    (c) => /^__Secure-next-auth\.session-token\.\d+$/.test(c.name) && hasValue(c)
  );
}

async function evaluate(cdp, expression) {
  const result = await cdp(expression);
  if (result.exceptionDetails) {
    const desc = result.exceptionDetails.exception?.description || 
                 result.exceptionDetails.text || 
                 "Evaluation failed";
    throw new Error(desc);
  }
  if (result.error) {
    throw new Error(result.error);
  }
  return result.result?.value;
}

function withTimeout(promise, timeoutMs, label) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timeoutId));
}

function isoNow() {
  return new Date().toISOString();
}

function sha256Text(text) {
  return crypto.createHash("sha256").update(text || "", "utf8").digest("hex");
}

function tailExcerpt(text, maxChars = 700) {
  const value = String(text || "");
  if (value.length <= maxChars) return value;
  return value.slice(value.length - maxChars);
}

function heartbeatEventsPath(heartbeatFile) {
  if (!heartbeatFile) return null;
  const parsed = path.parse(String(heartbeatFile));
  return path.join(parsed.dir, `${parsed.name}.events.jsonl`);
}

function writeAssistantHeartbeat(heartbeatFile, event) {
  if (!heartbeatFile) return;
  try {
    const file = String(heartbeatFile);
    const dir = path.dirname(file);
    fs.mkdirSync(dir, { recursive: true });
    let existing = fs.existsSync(file)
      ? JSON.parse(fs.readFileSync(file, "utf8"))
      : {};
    const sentinelChanged = Boolean(
      event.sentinel && existing.sentinel && existing.sentinel !== event.sentinel
    );
    if (sentinelChanged) existing = {};
    const assistantText = String(event.assistantText || "");
    const observedAt = isoNow();
    const assistant = {
      observed_at: observedAt,
      changed_at: event.changedAtIso || null,
      poll_count: event.pollCount,
      message_chars: assistantText.length,
      message_sha256: sha256Text(assistantText),
      tail_excerpt: tailExcerpt(assistantText),
      sentinel_seen: event.sentinelSeen === true,
      page_sentinel_seen: event.pageSentinelSeen === true,
      stable_poll_count: event.stableCycles,
      required_stable_polls: event.requiredStableCycles,
      stable_ms: event.stableMs,
      message_id: event.messageId || null,
      turn_index: Number.isFinite(event.turnIndex) ? event.turnIndex : null,
      source: event.source || null,
      stop_visible: event.stopVisible === true,
      finished_actions_visible: event.finished === true,
      document_hidden: event.documentHidden === true,
      visibility_state: event.visibilityState || null,
      background_hidden_polls: event.hiddenPolls || 0,
      hidden_recovery_used: event.hiddenRecoveryUsed === true,
    };
    const payload = {
      ...existing,
      schema: existing.schema || "surf.webgpt_heartbeat.v1",
      sentinel: event.sentinel || existing.sentinel || null,
      stream_schema: "surf.webgpt_assistant_stream.v1",
      updated_at: observedAt,
      last_browser_observation_at: observedAt,
      phase: event.phase || existing.phase || "generating",
      page_state: event.pageState || existing.page_state || "waiting_for_sentinel",
      assistant_message_chars: assistant.message_chars,
      assistant_message_sha256: assistant.message_sha256,
      assistant_tail_excerpt: assistant.tail_excerpt,
      assistant_last_changed_at: assistant.changed_at,
      assistant_sentinel_seen: assistant.sentinel_seen,
      assistant_page_sentinel_seen: assistant.page_sentinel_seen,
      assistant_stable_poll_count: assistant.stable_poll_count,
      assistant_required_stable_polls: assistant.required_stable_polls,
      assistant_stable_ms: assistant.stable_ms,
      assistant_message_id: assistant.message_id,
      assistant_turn_index: assistant.turn_index,
      assistant_source: assistant.source,
      assistant_stop_visible: assistant.stop_visible,
      assistant_finished_actions_visible: assistant.finished_actions_visible,
      assistant_document_hidden: assistant.document_hidden,
      assistant_visibility_state: assistant.visibility_state,
      assistant_background_hidden_polls: assistant.background_hidden_polls,
      assistant_hidden_recovery_used: assistant.hidden_recovery_used,
      assistant_observation: assistant,
      assistant_event_log: heartbeatEventsPath(file),
      prepared_prompt_is_transport_proof: false,
    };
    const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
    fs.writeFileSync(tmp, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    fs.renameSync(tmp, file);
    const eventPath = heartbeatEventsPath(file);
    if (eventPath) {
      if (sentinelChanged) fs.writeFileSync(eventPath, "", "utf8");
      const eventPayload = {
        schema: "surf.webgpt_assistant_stream_event.v1",
        event: "assistant_snapshot",
        observed_at: observedAt,
        phase: payload.phase,
        page_state: payload.page_state,
        assistant,
      };
      fs.appendFileSync(eventPath, `${JSON.stringify(eventPayload)}\n`, "utf8");
    }
  } catch (_) {
    // Heartbeat must never change WebGPT transport behavior or proof semantics.
  }
}

const assistantSnapshotExpression = (sentinel, baselineAssistantCount = 0) => {
  const baseline = Number.isFinite(baselineAssistantCount) && baselineAssistantCount >= 0
    ? Math.floor(baselineAssistantCount)
    : 0;
  const sentinelLiteral = JSON.stringify(sentinel || null);
  return `(() => {
    const BASELINE = ${baseline};
    const SENTINEL = ${sentinelLiteral};
    const CONVERSATION_SELECTOR = '${SELECTORS.conversationTurn}';
    const ASSISTANT_SELECTOR = '${SELECTORS.assistantMessage}';
    const STOP_SELECTOR = '${SELECTORS.stopButton}';
    const FINISHED_SELECTOR = '${SELECTORS.finishedActions}';
    const isAssistantTurn = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const role = (node.getAttribute('data-message-author-role') || '').toLowerCase();
      if (role === 'assistant') return true;
      const turn = (node.getAttribute('data-turn') || '').toLowerCase();
      if (turn === 'assistant') return true;
      return Boolean(node.querySelector(ASSISTANT_SELECTOR));
    };
    const directAssistantTurns = Array.from(document.querySelectorAll(ASSISTANT_SELECTOR))
      .filter((node) => node instanceof HTMLElement);
    const conversationTurns = Array.from(document.querySelectorAll(CONVERSATION_SELECTOR));
    const assistantTurns = directAssistantTurns.length
      ? directAssistantTurns
      : conversationTurns.filter((node) => isAssistantTurn(node));
    const newAssistantTurns = assistantTurns.slice(BASELINE);
    let baselineFallback = false;
    let lastAssistantTurn = newAssistantTurns.length
      ? newAssistantTurns[newAssistantTurns.length - 1]
      : null;
    const sentinelVariants = SENTINEL ? [SENTINEL] : [];
    const findSentinel = (text) => sentinelVariants.find((marker) => text.includes(marker)) || null;
    if (!lastAssistantTurn && SENTINEL && assistantTurns.length) {
      // ChatGPT can mutate an already-counted assistant container after we capture the
      // baseline. The per-submit sentinel is unique, so only fall back when that exact
      // marker is present in an existing assistant turn.
      for (let idx = assistantTurns.length - 1; idx >= 0; idx--) {
        const candidate = assistantTurns[idx];
        const candidateText = (candidate?.innerText || candidate?.textContent || '').trim();
        if (findSentinel(candidateText)) {
          lastAssistantTurn = candidate;
          baselineFallback = true;
          break;
        }
      }
    }
    const documentHidden = document.hidden === true;
    const visibilityState = document.visibilityState || null;
    const documentHasFocus = typeof document.hasFocus === 'function' ? document.hasFocus() : null;
    if (!lastAssistantTurn) {
      return {
        text: '',
        stopVisible: Boolean(document.querySelector(STOP_SELECTOR)),
        finished: false,
        source: 'awaiting-assistant-turn',
        pageTextContainsSentinel: false,
        documentHidden,
        visibilityState,
        documentHasFocus,
        baselineAssistantCount: BASELINE,
        newAssistantTurnCount: 0,
      };
    }
    const messageRoot = lastAssistantTurn.querySelector(ASSISTANT_SELECTOR) || lastAssistantTurn;
    const contentRoot = messageRoot.querySelector('.markdown') ||
                       messageRoot.querySelector('[data-message-content]') ||
                       messageRoot.querySelector('.prose') ||
                       messageRoot;
    const contentText = (contentRoot?.innerText || contentRoot?.textContent || '').trim();
    const turnText = (messageRoot?.innerText || messageRoot?.textContent || '').trim();
    const contentSentinel = findSentinel(contentText);
    const turnSentinel = findSentinel(turnText);
    let text = SENTINEL && !contentSentinel && turnSentinel
      ? turnText
      : contentText;
    const sentinelMatch = findSentinel(text);
    const stopVisible = Boolean(document.querySelector(STOP_SELECTOR));
    const finished = Boolean(lastAssistantTurn.querySelector(FINISHED_SELECTOR));
    const messageId = messageRoot.getAttribute('data-message-id') || null;
    const turnTextForSentinel = turnText || contentText || '';
    const pageTextContainsSentinel = Boolean(SENTINEL && findSentinel(turnTextForSentinel));
    let source = baselineFallback ? 'assistant-dom-baseline-fallback' : 'assistant-dom';
    if (SENTINEL && pageTextContainsSentinel && !findSentinel(text)) {
      const marker = findSentinel(turnTextForSentinel);
      const idx = marker ? turnTextForSentinel.lastIndexOf(marker) : -1;
      if (idx >= 0) {
        text = turnTextForSentinel.slice(Math.max(0, idx - 12000), idx + marker.length).trim();
        source = 'page-text-fallback';
      }
    }
    return {
      text,
      stopVisible,
      finished,
      messageId,
      turnIndex: assistantTurns.length - 1,
      source,
      pageTextContainsSentinel,
      sentinelMatch,
      documentHidden,
      visibilityState,
      documentHasFocus,
      baselineAssistantCount: BASELINE,
      newAssistantTurnCount: newAssistantTurns.length,
    };
  })()`;
};

async function assistantSnapshot(cdp, sentinel, timeoutMs = 12000, baselineAssistantCount = 0) {
  return withTimeout(
    evaluate(cdp, assistantSnapshotExpression(sentinel, baselineAssistantCount)),
    timeoutMs,
    "ChatGPT assistant DOM snapshot",
  );
}

async function waitForPageLoad(cdp, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await evaluate(cdp, "document.readyState");
    if (ready === "complete" || ready === "interactive") {
      return;
    }
    await delay(100);
  }
  throw new Error("Page did not load in time");
}

async function isCloudflareBlocked(cdp) {
  const title = await evaluate(cdp, "document.title.toLowerCase()");
  if (title && title.includes("just a moment")) return true;
  const state = await evaluate(
    cdp,
    `(() => {
      const text = document.body?.innerText || "";
      const hasChallengeText = /verify you are human|checking your browser|just a moment|cloudflare|turnstile/i.test(text);
      const hasComposer = Boolean(document.querySelector('${SELECTORS.promptTextarea}'));
      const hasConversation = Boolean(document.querySelector('${SELECTORS.assistantMessage}'));
      const hasScript = Boolean(document.querySelector('${SELECTORS.cloudflareScript}'));
      return { hasChallengeText, hasComposer, hasConversation, hasScript };
    })()`
  );
  return Boolean(state?.hasChallengeText && !state?.hasComposer && !state?.hasConversation);
}

async function recoverCloudflareChallenge(cdp, inputCdp, log, options = {}) {
  const {
    maxReloads = 1,
    reloadWaitMs = 2000,
    pageLoadTimeoutMs = 45000,
  } = options;
  if (!(await isCloudflareBlocked(cdp))) return { detected: false, reloads: 0 };

  for (let reloads = 1; reloads <= maxReloads; reloads += 1) {
    log?.(`Cloudflare challenge detected; hard reloading controlled tab (${reloads}/${maxReloads})`);
    await inputCdp("Page.reload", { ignoreCache: true });
    if (reloadWaitMs > 0) await delay(reloadWaitMs);
    await waitForPageLoad(cdp, pageLoadTimeoutMs);
    if (!(await isCloudflareBlocked(cdp))) {
      log?.(`Cloudflare challenge cleared after ${reloads} hard reload(s)`);
      return { detected: true, reloads, recovered: true };
    }
  }

  const error = new Error(
    `Cloudflare challenge persisted after ${maxReloads} automatic hard reload(s)`,
  );
  error.code = "cloudflare_challenge_persisted";
  error.cloudflareRecovery = { detected: true, reloads: maxReloads, recovered: false };
  throw error;
}

async function checkLoginStatus(cdp) {
  const result = await evaluate(
    cdp,
    `(async () => {
      try {
        const response = await fetch('/backend-api/me', { 
          cache: 'no-store', 
          credentials: 'include' 
        });
        const hasLoginCta = Array.from(document.querySelectorAll('a[href*="/auth/login"], button'))
          .some(el => {
            const text = (el.textContent || '').toLowerCase().trim();
            return text.startsWith('log in') || text.startsWith('sign in');
          });
        return { 
          status: response.status, 
          hasLoginCta,
          url: location.href
        };
      } catch (e) {
        return { status: 0, error: e.message, url: location.href };
      }
    })()`
  );
  return result || { status: 0 };
}

async function waitForPromptReady(cdp, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  const selectors = JSON.stringify(SELECTORS.promptTextarea.split(", "));
  while (Date.now() < deadline) {
    const found = await evaluate(
      cdp,
      `(() => {
        const selectors = ${selectors};
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          if (node && !node.hasAttribute('disabled')) {
            return true;
          }
        }
        return false;
      })()`
    );
    if (found) return true;
    await delay(200);
  }
  return false;
}

async function assertReadyForNewPrompt(cdp) {
  const state = await evaluate(
    cdp,
    `(() => {
      const STOP_SELECTOR = '${SELECTORS.stopButton}';
      const SEND_SELECTOR = '${SELECTORS.sendButton}';
      const PROMPT_SELECTOR = '${SELECTORS.promptTextarea}';
      const stop = document.querySelector(STOP_SELECTOR);
      const send = document.querySelector(SEND_SELECTOR);
      const prompt = document.querySelector(PROMPT_SELECTOR);
      const promptText = prompt ? (prompt.innerText || prompt.value || prompt.textContent || '').trim() : '';
      const visibleText = (document.body?.innerText || '').slice(-4000);
      const buttons = Array.from(document.querySelectorAll('button'))
        .map((button) => ({
          text: (button.innerText || button.textContent || '').trim(),
          aria: (button.getAttribute('aria-label') || '').trim(),
          testid: (button.getAttribute('data-testid') || '').trim(),
          disabled: button.disabled ||
            button.hasAttribute('disabled') ||
            button.getAttribute('aria-disabled') === 'true' ||
            button.getAttribute('data-disabled') === 'true',
        }));
      const activeStopButton = buttons.find((button) => {
        const label = (button.text + ' ' + button.aria + ' ' + button.testid).toLowerCase();
        return !button.disabled && (
          label.includes('stop answering') ||
          label.includes('stop generating') ||
          label.includes('stop response') ||
          button.testid === 'stop-button'
        );
      }) || null;
      const stoppedThinkingCount = buttons.filter((button) => {
        const label = (button.text + ' ' + button.aria).toLowerCase();
        return label.includes('stopped thinking');
      }).length;
      const disabled = send
        ? (send.hasAttribute('disabled') ||
           send.getAttribute('aria-disabled') === 'true' ||
           send.getAttribute('data-disabled') === 'true')
        : null;
      return {
        stopVisible: Boolean(stop) || Boolean(activeStopButton),
        activeStopLabel: activeStopButton ? (activeStopButton.text || activeStopButton.aria || activeStopButton.testid || null) : null,
        stoppedThinkingCount,
        sendPresent: Boolean(send),
        sendDisabled: disabled,
        promptPresent: Boolean(prompt),
        promptChars: promptText.length,
        promptPreview: promptText.slice(0, 200),
        documentHidden: document.hidden === true,
        visibilityState: document.visibilityState || null,
        documentHasFocus: typeof document.hasFocus === 'function' ? document.hasFocus() : null,
        tailContainsStoppedThinking: visibleText.toLowerCase().includes('stopped thinking'),
        title: document.title || '',
        url: location.href || '',
      };
    })()`
  );
  if (state?.stopVisible) {
    const err = new Error("ChatGPT page is busy before submit: stop button is visible; wait, extract the existing response, or use a fresh reviewer tab");
    err.chatgptPageState = state;
    throw err;
  }
  if (!state?.promptPresent) {
    const err = new Error("ChatGPT prompt composer not present before submit");
    err.chatgptPageState = state || null;
    throw err;
  }
  if (state?.promptChars > 0) {
    const err = new Error("ChatGPT prompt composer is not empty before submit; clear the draft or use a fresh reviewer tab");
    err.chatgptPageState = state;
    throw err;
  }
  return state;
}

async function attemptOptionalSelection(kind, requested, selector, log, onUnavailable) {
  if (!requested) {
    return { requested: null, selected: null, status: null, error: null };
  }
  try {
    const selected = await selector(requested);
    return { requested, selected, status: "selected", error: null };
  } catch (error) {
    const message = error?.message || String(error);
    if (onUnavailable) await onUnavailable().catch(() => {});
    log?.(`${kind} selection unavailable for ${requested}; preserving current browser setting: ${message}`);
    return {
      requested,
      selected: null,
      status: "unavailable_using_current",
      error: message,
    };
  }
}

async function selectModel(cdp, desiredModel, timeoutMs = 8000) {
  const modelButton = await evaluate(
    cdp,
    `(() => {
      const btn = document.querySelector('${SELECTORS.modelButton}');
      return btn ? true : false;
    })()`
  );
  if (!modelButton) {
    throw new Error("Model selector button not found");
  }
  await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const btn = document.querySelector('${SELECTORS.modelButton}');
      if (btn) dispatchClickSequence(btn);
    })()`
  );
  await delay(300);
  const normalizedModel = desiredModel.toLowerCase().replace(/[^a-z0-9]/g, "");
  const result = await evaluate(
    cdp,
    `(async () => {
      ${buildClickDispatcher()}
      const TIMEOUT_MS = ${timeoutMs};
      const targetModel = ${JSON.stringify(normalizedModel)};
      const menuSelector = '${SELECTORS.menuContainer}';
      const itemSelector = '${SELECTORS.menuItem}';
      const normalize = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const deadline = Date.now() + TIMEOUT_MS;
      while (Date.now() < deadline) {
        const menu = document.querySelector(menuSelector);
        if (!menu) {
          await new Promise(r => setTimeout(r, 100));
          continue;
        }
        const items = Array.from(menu.querySelectorAll(itemSelector));
        let bestMatch = null;
        let bestScore = 0;
        for (const item of items) {
          const text = normalize(item.textContent || '');
          const testId = normalize(item.getAttribute('data-testid') || '');
          let score = 0;
          if (text.includes(targetModel) || testId.includes(targetModel)) score = 100;
          else if (targetModel.includes(text) || targetModel.includes(testId)) score = 50;
          if (score > bestScore) {
            bestScore = score;
            bestMatch = item;
          }
        }
        if (bestMatch) {
          dispatchClickSequence(bestMatch);
          await new Promise(r => setTimeout(r, 200));
          return { success: true, label: bestMatch.textContent?.trim() };
        }
        await new Promise(r => setTimeout(r, 100));
      }
      return { success: false, error: 'Model option not found' };
    })()`
  );
  if (!result || !result.success) {
    throw new Error(`Model not found: ${desiredModel}`);
  }
  return result.label;
}

async function selectReasoning(cdp, desiredReasoning, timeoutMs = 8000) {
  const normalizedReasoning = desiredReasoning.toLowerCase().replace(/[^a-z0-9]/g, "");
  const clicked = await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const normalize = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const desired = ${JSON.stringify(normalizedReasoning)};
      const visible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const explicit = Array.from(document.querySelectorAll('${SELECTORS.reasoningButton}'))
        .filter(visible);
      const semantic = Array.from(document.querySelectorAll('button,[role="button"]'))
        .filter(visible)
        .filter((button) => {
          const text = normalize(button.textContent || '');
          const aria = normalize(button.getAttribute('aria-label') || '');
          const testId = normalize(button.getAttribute('data-testid') || '');
          const combined = text + ' ' + aria + ' ' + testId;
          const inComposer = Boolean(button.closest('form') || button.closest('[data-testid*="composer"]') || button.closest('#composer-background'));
          const currentReasoningLabels = new Set(['auto', 'fast', 'pro', 'heavy', 'heavyreasoning']);
          if (combined.includes('reason') || combined.includes('think') || combined.includes('effort')) return true;
          if (inComposer && currentReasoningLabels.has(text)) return true;
          if (desired.length >= 3 && text === desired) return true;
          return desired.includes(text) && text.length >= 4;
        });
      const candidates = [...explicit, ...semantic];
      const seen = new Set();
      for (const button of candidates) {
        if (seen.has(button)) continue;
        seen.add(button);
        dispatchClickSequence(button);
        return {
          success: true,
          label: (button.textContent || button.getAttribute('aria-label') || button.getAttribute('data-testid') || '').trim(),
        };
      }
      return { success: false, error: 'Reasoning selector button not found' };
    })()`
  );
  if (!clicked || !clicked.success) {
    throw new Error(`Reasoning selector button not found for: ${desiredReasoning}`);
  }
  await delay(300);
  const result = await evaluate(
    cdp,
    `(async () => {
      ${buildClickDispatcher()}
      const TIMEOUT_MS = ${timeoutMs};
      const targetReasoning = ${JSON.stringify(normalizedReasoning)};
      const menuSelector = '${SELECTORS.menuContainer}, [role="listbox"], [role="dialog"], [data-radix-popper-content-wrapper]';
      const itemSelector = '${SELECTORS.menuItem}, [role="option"], [cmdk-item], [data-value]';
      const normalize = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const visible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const deadline = Date.now() + TIMEOUT_MS;
      while (Date.now() < deadline) {
        const containers = Array.from(document.querySelectorAll(menuSelector)).filter(visible);
        const roots = containers.length ? containers : [document.body];
        let bestMatch = null;
        let bestScore = 0;
        for (const root of roots) {
          const items = Array.from(root.querySelectorAll(itemSelector)).filter(visible);
          for (const item of items) {
            const textRaw = (item.textContent || '').trim();
            const text = normalize(textRaw);
            const aria = normalize(item.getAttribute('aria-label') || '');
            const testId = normalize(item.getAttribute('data-testid') || '');
            const value = normalize(item.getAttribute('data-value') || '');
            let score = 0;
            if (text === targetReasoning || aria === targetReasoning || value === targetReasoning) score = 120;
            else if (text.includes(targetReasoning) || aria.includes(targetReasoning) || testId.includes(targetReasoning) || value.includes(targetReasoning)) score = 100;
            else if (targetReasoning.includes(text) && text.length >= 3) score = 70;
            if (score > bestScore) {
              bestScore = score;
              bestMatch = item;
            }
          }
        }
        if (bestMatch) {
          const label = (bestMatch.textContent || bestMatch.getAttribute('aria-label') || bestMatch.getAttribute('data-value') || '').trim();
          dispatchClickSequence(bestMatch);
          await new Promise(r => setTimeout(r, 250));
          return { success: true, label };
        }
        await new Promise(r => setTimeout(r, 100));
      }
      return { success: false, error: 'Reasoning option not found' };
    })()`
  );
  if (!result || !result.success) {
    throw new Error(`Reasoning option not found: ${desiredReasoning}`);
  }
  return result.label;
}

async function attachFile(cdp, inputCdp, filePath, log = () => {}) {
  const fs = require("fs");
  const path = require("path");
  const absolutePath = path.resolve(filePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`File not found: ${absolutePath}`);
  }

  // Wait for a file input to appear. ChatGPT lazily mounts the hidden
  // <input type="file"> when the composer attach button is interactable;
  // recent revs mount it unconditionally, but we poll defensively.
  const selectorJson = JSON.stringify(SELECTORS.fileInput);
  const deadline = Date.now() + 5000;
  let found = false;
  while (Date.now() < deadline) {
    const probe = await evaluate(
      cdp,
      `(() => !!document.querySelector(${selectorJson}))()`,
    );
    if (probe) {
      found = true;
      break;
    }
    await delay(150);
  }
  if (!found) {
    throw new Error(
      "ChatGPT file input (input[type=\"file\"]) not present in the DOM; ChatGPT may have moved or hidden the attach control.",
    );
  }

  // Resolve the file input via CDP DOM traversal so we can call
  // DOM.setFileInputFiles with a real nodeId. Runtime.evaluate can return
  // a remoteObjectId but CDP setFileInputFiles requires either nodeId or
  // backendNodeId on most Chrome builds, so we go through DOM.querySelector.
  const doc = await inputCdp("DOM.getDocument", { depth: 0, pierce: false });
  if (!doc || !doc.root || typeof doc.root.nodeId !== "number") {
    throw new Error("DOM.getDocument did not return a usable root nodeId");
  }
  const node = await inputCdp("DOM.querySelector", {
    nodeId: doc.root.nodeId,
    selector: SELECTORS.fileInput,
  });
  if (!node || !node.nodeId) {
    throw new Error("DOM.querySelector returned no nodeId for the ChatGPT file input");
  }
  await inputCdp("DOM.setFileInputFiles", {
    files: [absolutePath],
    nodeId: node.nodeId,
  });

  // Give ChatGPT a moment to process the file (it reads, hashes, sometimes
  // uploads). If the attachment is not yet visible after a brief wait we
  // surface the failure so the caller can decide to retry rather than send
  // a prompt that references a missing attachment.
  const previewDeadline = Date.now() + 20000;
  while (Date.now() < previewDeadline) {
    const preview = await evaluate(
      cdp,
      `(() => {
        const previewSelectors = [
          '[data-testid*="attachment"]',
          'div[role="img"][aria-label]',
          'div[data-testid="composer-attachments"] div',
          'form div[draggable="true"]',
        ];
        for (const sel of previewSelectors) {
          if (document.querySelector(sel)) return true;
        }
        return false;
      })()`,
    );
    if (preview) {
      log(`File attachment preview visible`);
      return { attached: true };
    }
    await delay(250);
  }
  // No preview shown, but the input file was set. Proceed; ChatGPT often
  // accepts files without a visible thumbnail (especially text/markdown).
  log(`File attachment set (no preview detected within 20s; proceeding)`);
  return { attached: true, previewVisible: false };
}


async function typePrompt(cdp, inputCdp, prompt) {
  const selectors = JSON.stringify(SELECTORS.promptTextarea.split(", "));
  const encodedPrompt = JSON.stringify(prompt);
  const promptStart = JSON.stringify(prompt.slice(0, Math.min(prompt.length, 160)));
  const promptEnd = JSON.stringify(prompt.slice(Math.max(0, prompt.length - 160)));
  const focused = await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const selectors = ${selectors};
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node) continue;
        dispatchClickSequence(node);
        if (typeof node.focus === 'function') node.focus();
        const doc = node.ownerDocument;
        const selection = doc?.getSelection?.();
        if (selection) {
          const range = doc.createRange();
          range.selectNodeContents(node);
          range.collapse(false);
          selection.removeAllRanges();
          selection.addRange(range);
        }
        return true;
      }
      return false;
    })()`
  );
  if (!focused) {
    throw new Error("Failed to focus prompt textarea");
  }
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Control",
    code: "ControlLeft",
    windowsVirtualKeyCode: 17,
    nativeVirtualKeyCode: 17,
    modifiers: 2,
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "a",
    code: "KeyA",
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
    modifiers: 2,
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "a",
    code: "KeyA",
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
    modifiers: 2,
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Control",
    code: "ControlLeft",
    windowsVirtualKeyCode: 17,
    nativeVirtualKeyCode: 17,
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Backspace",
    code: "Backspace",
    windowsVirtualKeyCode: 8,
    nativeVirtualKeyCode: 8,
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Backspace",
    code: "Backspace",
    windowsVirtualKeyCode: 8,
    nativeVirtualKeyCode: 8,
  });
  await delay(100);
  await inputCdp("Input.insertText", { text: prompt });
  await delay(300);
  let verified = await evaluate(
    cdp,
    `(() => {
      const selectors = ${selectors};
      const promptStart = ${promptStart};
      const promptEnd = ${promptEnd};
      const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
      const normalizedStart = normalize(promptStart);
      const normalizedEnd = normalize(promptEnd);
      const hasPrompt = (text) => {
        const normalized = normalize(text);
        return Boolean(normalized && normalized.includes(normalizedStart) && normalized.includes(normalizedEnd));
      };
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node) continue;
        const text = node.innerText || node.value || node.textContent || '';
        if (hasPrompt(text)) return true;
      }
      const active = document.activeElement;
      const activeText = active ? (active.innerText || active.value || active.textContent || '') : '';
      if (hasPrompt(activeText)) return true;
      const activeForm = active?.closest?.('form, main, [data-testid*="composer"], #composer-background');
      const activeFormText = activeForm ? (activeForm.innerText || activeForm.textContent || '') : '';
      if (hasPrompt(activeFormText)) return true;
      if (hasPrompt(document.body?.innerText || document.body?.textContent || '')) return true;
      return false;
    })()`
  );
  if (!verified) {
    await evaluate(
      cdp,
      `(() => {
        const selectors = ${selectors};
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          if (!node) continue;
          if ('value' in node) {
            node.value = ${encodedPrompt};
          } else {
            node.textContent = ${encodedPrompt};
          }
          node.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
          node.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
          return true;
        }
        return false;
      })()`
    );
    await delay(300);
    verified = await evaluate(
      cdp,
      `(() => {
        const selectors = ${selectors};
        const promptStart = ${promptStart};
        const promptEnd = ${promptEnd};
        const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
        const normalizedStart = normalize(promptStart);
        const normalizedEnd = normalize(promptEnd);
        const hasPrompt = (text) => {
          const normalized = normalize(text);
          return Boolean(normalized && normalized.includes(normalizedStart) && normalized.includes(normalizedEnd));
        };
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          if (!node) continue;
          const text = node.innerText || node.value || node.textContent || '';
          if (hasPrompt(text)) return true;
        }
        const active = document.activeElement;
        const activeText = active ? (active.innerText || active.value || active.textContent || '') : '';
        if (hasPrompt(activeText)) return true;
        const activeForm = active?.closest?.('form, main, [data-testid*="composer"], #composer-background');
        const activeFormText = activeForm ? (activeForm.innerText || activeForm.textContent || '') : '';
        if (hasPrompt(activeFormText)) return true;
        if (hasPrompt(document.body?.innerText || document.body?.textContent || '')) return true;
        return false;
      })()`
    );
  }
  if (!verified) {
    throw new Error("Failed to replace ChatGPT prompt composer with submitted WebGPT request");
  }
}


async function captureAssistantBaseline(cdp) {
  const expr = `(() => {
    const ASSISTANT_SELECTOR = '${SELECTORS.assistantMessage}';
    const CONVERSATION_SELECTOR = '${SELECTORS.conversationTurn}';
    const isAssistantTurn = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const role = (node.getAttribute('data-message-author-role') || '').toLowerCase();
      if (role === 'assistant') return true;
      const turn = (node.getAttribute('data-turn') || '').toLowerCase();
      if (turn === 'assistant') return true;
      return Boolean(node.querySelector(ASSISTANT_SELECTOR));
    };
    const directAssistantTurns = Array.from(document.querySelectorAll(ASSISTANT_SELECTOR))
      .filter((node) => node instanceof HTMLElement);
    const conversationTurns = Array.from(document.querySelectorAll(CONVERSATION_SELECTOR));
    const assistantTurns = directAssistantTurns.length
      ? directAssistantTurns
      : conversationTurns.filter((node) => isAssistantTurn(node));
    const last = assistantTurns.length ? assistantTurns[assistantTurns.length - 1] : null;
    const userTurns = Array.from(document.querySelectorAll('[data-message-author-role="user"], [data-turn="user"]'))
      .filter((node) => node instanceof HTMLElement);
    return {
      assistantCount: assistantTurns.length,
      lastMessageId: last ? (last.getAttribute('data-message-id') || null) : null,
      userCount: userTurns.length,
    };
  })()`;
  const value = await evaluate(cdp, expr);
  return {
    assistantCount: Number.isFinite(value?.assistantCount) ? value.assistantCount : 0,
    lastMessageId: value?.lastMessageId || null,
    userCount: Number.isFinite(value?.userCount) ? value.userCount : 0,
  };
}

async function clickSend(cdp, inputCdp) {
  const selectors = SELECTORS.sendButton.split(", ");
  const selectorsJson = JSON.stringify(selectors);
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    const result = await evaluate(
      cdp,
      `(() => {
        ${buildClickDispatcher()}
        const selectors = ${selectorsJson};
        let button = null;
        for (const selector of selectors) {
          button = document.querySelector(selector);
          if (button) break;
        }
        if (!button) return 'missing';
        const disabled = button.hasAttribute('disabled') || 
                        button.getAttribute('aria-disabled') === 'true' ||
                        button.getAttribute('data-disabled') === 'true';
        if (disabled) return 'disabled';
        dispatchClickSequence(button);
        return 'clicked';
      })()`
    );
    if (result === "clicked") return true;
    if (result === "missing") break;
    await delay(100);
  }
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
    text: "\r",
  });
  await inputCdp("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
  });
  return true;
}

async function waitForSubmitAccepted(cdp, prompt, timeoutMs = 10000, baseline = {}) {
  const promptStart = JSON.stringify(prompt.slice(0, Math.min(prompt.length, 160)));
  const promptEnd = JSON.stringify(prompt.slice(Math.max(0, prompt.length - 160)));
  const baselineAssistantCount = Number.isFinite(baseline.assistantCount) ? baseline.assistantCount : 0;
  const baselineUserCount = Number.isFinite(baseline.userCount) ? baseline.userCount : 0;
  const deadline = Date.now() + timeoutMs;
  let lastState = null;
  while (Date.now() < deadline) {
    lastState = await evaluate(
      cdp,
      `(() => {
        const STOP_SELECTOR = '${SELECTORS.stopButton}';
        const PROMPT_SELECTOR = '${SELECTORS.promptTextarea}';
        const promptStart = ${promptStart};
        const promptEnd = ${promptEnd};
        const prompt = document.querySelector(PROMPT_SELECTOR);
        const text = prompt ? (prompt.innerText || prompt.value || prompt.textContent || '') : '';
        const assistantTurns = document.querySelectorAll('[data-message-author-role="assistant"], [data-turn="assistant"]');
        const userTurns = Array.from(document.querySelectorAll('[data-message-author-role="user"], [data-turn="user"]'));
        const lastUser = userTurns.length ? userTurns[userTurns.length - 1] : null;
        const lastUserText = lastUser ? (lastUser.innerText || lastUser.textContent || '') : '';
        return {
          stopVisible: Boolean(document.querySelector(STOP_SELECTOR)),
          promptPresent: Boolean(prompt),
          composerStillContainsPrompt: Boolean(text && text.includes(promptStart) && text.includes(promptEnd)),
          composerChars: text.length,
          assistantCount: assistantTurns.length,
          userCount: userTurns.length,
          lastUserContainsPrompt: Boolean(lastUserText && lastUserText.includes(promptStart) && lastUserText.includes(promptEnd)),
        };
      })()`
    );
    const assistantAdvanced = Number(lastState?.assistantCount || 0) > baselineAssistantCount;
    const userTurnAdvanced = Number(lastState?.userCount || 0) > baselineUserCount && lastState?.lastUserContainsPrompt === true;
    if (lastState?.stopVisible || assistantAdvanced || userTurnAdvanced) {
      return { accepted: true, ...lastState };
    }
    await delay(200);
  }
  const err = new Error("ChatGPT did not accept submitted prompt: prompt remained in the composer after send");
  err.chatgptSubmitState = lastState || null;
  throw err;
}

async function waitForResponse(cdp, timeoutMs = 2700000, options = {}) {
  const sentinel = options.sentinel || null;
  const baselineAssistantCount = Number.isFinite(options.baselineAssistantCount)
    ? options.baselineAssistantCount
    : 0;
  const noActivate = options.noActivate === true;
  const inputCdp = options.inputCdp || null;
  const log = options.log || (() => {});
  const activateTabForRecovery = typeof options.activateTabForRecovery === "function"
    ? options.activateTabForRecovery
    : null;
  const heartbeatFile = options.heartbeatFile || null;
  const hiddenRecoveryPolls = Number.parseInt(process.env.SURF_WEBGPT_HIDDEN_RECOVERY_POLLS || "25", 10);
  const hiddenRecoveryIdleMs = Number.parseInt(process.env.SURF_WEBGPT_HIDDEN_RECOVERY_IDLE_MS || "30000", 10);
  const stableStallMs = Number.parseInt(process.env.SURF_WEBGPT_STABLE_STALL_MS || "0", 10);
  const deadline = Date.now() + timeoutMs;
  let previousText = "";
  let stableCycles = 0;
  const requiredStableCycles = Number.isInteger(options.stablePolls) && options.stablePolls > 0
    ? options.stablePolls
    : 6;
  const minStableMs = 1200;
  let lastChangeAt = Date.now();
  let lastSnapshotError = null;
  let pollCount = 0;
  let hiddenPolls = 0;
  let hiddenRecoveryUsed = false;
  let lastVisibilityState = null;
  let lastDocumentHidden = null;
  let lastNonEmptySnapshot = null;
  if (noActivate) {
    await nudgeBackgroundRendering(cdp, inputCdp, log, "start");
  }
  while (Date.now() < deadline) {
    pollCount++;
    if (noActivate && (pollCount === 1 || pollCount % BACKGROUND_WAKE_EVERY_POLLS === 0)) {
      await nudgeBackgroundRendering(cdp, inputCdp, log, `poll-${pollCount}`);
    }
    let snapshot;
    try {
      snapshot = await assistantSnapshot(cdp, sentinel, 12000, baselineAssistantCount);
      lastSnapshotError = null;
    } catch (err) {
      lastSnapshotError = err;
      await delay(400);
      continue;
    }
    if (!snapshot) {
      await delay(400);
      continue;
    }
    if (snapshot.documentHidden === true) {
      hiddenPolls++;
      if (noActivate) {
        await nudgeBackgroundRendering(cdp, inputCdp, log, `hidden-poll-${pollCount}`);
        const idleMs = Date.now() - lastChangeAt;
        const pageHasSentinelNow = sentinel ? snapshot.pageTextContainsSentinel === true : false;
        const assistantHasSentinelNow = sentinel
          ? ((snapshot.text || "").includes(sentinel) || snapshot.sentinelMatch === sentinel)
          : false;
        if (
          !hiddenRecoveryUsed
          && activateTabForRecovery
          && hiddenPolls >= hiddenRecoveryPolls
          && idleMs >= hiddenRecoveryIdleMs
          && !assistantHasSentinelNow
          && !pageHasSentinelNow
        ) {
          hiddenRecoveryUsed = true;
          log(`Hidden-tab stall recovery: activating controlled tab after hidden_polls=${hiddenPolls} idle_ms=${idleMs}`);
          try {
            await activateTabForRecovery();
            await delay(1500);
            await nudgeBackgroundRendering(cdp, inputCdp, log, "post-activate-recovery");
            lastChangeAt = Date.now();
          } catch (err) {
            log(`Hidden-tab stall recovery failed: ${err?.message || err}`);
          }
        }
      }
    }
    lastVisibilityState = snapshot.visibilityState || null;
    lastDocumentHidden = snapshot.documentHidden === true;
    const currentText = snapshot.text || "";
    const currentLength = currentText.length;
    if (currentLength > 0) {
      lastNonEmptySnapshot = { ...snapshot };
    }
    if (currentText !== previousText) {
      previousText = currentText;
      stableCycles = 0;
      lastChangeAt = Date.now();
    } else {
      stableCycles++;
    }
    const stableMs = Date.now() - lastChangeAt;
    const hasAssistantSentinel = sentinel
      ? ((snapshot.text || "").includes(sentinel) || snapshot.sentinelMatch === sentinel)
      : true;
    const pageHasSentinel = sentinel ? snapshot.pageTextContainsSentinel === true : false;
    const hasSentinel = sentinel ? hasAssistantSentinel : true;
    writeAssistantHeartbeat(heartbeatFile, {
      phase: hasSentinel ? "sentinel_seen" : "generating",
      pageState: hasSentinel ? "stabilizing_response" : "waiting_for_sentinel",
      assistantText: currentText,
      sentinelSeen: hasAssistantSentinel,
      pageSentinelSeen: pageHasSentinel,
      stableCycles,
      requiredStableCycles,
      stableMs,
      changedAtIso: new Date(lastChangeAt).toISOString(),
      messageId: snapshot.messageId,
      turnIndex: snapshot.turnIndex,
      source: snapshot.source,
      stopVisible: snapshot.stopVisible,
      finished: snapshot.finished,
      documentHidden: snapshot.documentHidden,
      visibilityState: snapshot.visibilityState,
      hiddenPolls,
      hiddenRecoveryUsed,
      pollCount,
      sentinel,
    });
    if (
      sentinel
      && stableStallMs > 0
      && currentLength > 0
      && !hasAssistantSentinel
      && stableCycles >= requiredStableCycles
      && stableMs >= stableStallMs
    ) {
      const error = new Error(`Stable assistant response stalled without sentinel after ${stableMs}ms`);
      error.partialResponse = {
        text: currentText,
        messageId: snapshot.messageId || null,
        turnIndex: snapshot.turnIndex,
        sentinel,
        hasSentinel: false,
        source: snapshot.source || "assistant-dom",
        pageTextContainsSentinel: pageHasSentinel,
        documentHiddenAtCompletion: snapshot.documentHidden === true,
        visibilityStateAtCompletion: snapshot.visibilityState || null,
        backgroundHiddenPolls: hiddenPolls,
        backgroundPollCount: pollCount,
        hiddenRecoveryUsed,
      };
      throw error;
    }
    // Background/hidden tabs often keep [data-testid=stop-button] in the DOM until the tab
    // is focused, even after the assistant message is complete. In --no-activate mode we
    // trust a stable sentinel on the post-submit assistant turn instead of stop-button absence.
    const stopGateOk = !snapshot.stopVisible
      || (noActivate && hasSentinel && (snapshot.finished || pageHasSentinel || snapshot.source === 'page-text-fallback'));
    if (stopGateOk && hasSentinel) {
      const stableEnough = stableCycles >= requiredStableCycles && stableMs >= minStableMs;
      const finishedVisible = snapshot.finished;
      const responseComplete = sentinel ? stableEnough : (finishedVisible || stableEnough);
      if (responseComplete && currentLength > 0) {
        return {
          text: snapshot.text,
          messageId: snapshot.messageId,
          turnIndex: snapshot.turnIndex,
          sentinel,
          hasSentinel,
          source: snapshot.source,
          pageTextContainsSentinel: snapshot.pageTextContainsSentinel,
          documentHiddenAtCompletion: snapshot.documentHidden === true,
          visibilityStateAtCompletion: snapshot.visibilityState || null,
          backgroundHiddenPolls: hiddenPolls,
          backgroundPollCount: pollCount,
          hiddenRecoveryUsed,
        };
      }
    }
    await delay(400);
  }
  const detail = lastSnapshotError ? `; last snapshot error: ${lastSnapshotError.message}` : "";
  const hiddenDetail = noActivate
    ? `; hidden_polls=${hiddenPolls}; last_visibility=${lastVisibilityState || "unknown"}; document_hidden=${lastDocumentHidden}`
    : "";
  const err = new Error(`Response timeout${hiddenDetail}${detail}`);
  if (lastNonEmptySnapshot?.text) {
    err.partialResponse = {
      text: lastNonEmptySnapshot.text,
      messageId: lastNonEmptySnapshot.messageId || null,
      turnIndex: lastNonEmptySnapshot.turnIndex,
      sentinel,
      hasSentinel: false,
      source: lastNonEmptySnapshot.source || "assistant-dom",
      pageTextContainsSentinel: lastNonEmptySnapshot.pageTextContainsSentinel === true,
      documentHiddenAtCompletion: lastNonEmptySnapshot.documentHidden === true,
      visibilityStateAtCompletion: lastNonEmptySnapshot.visibilityState || null,
      backgroundHiddenPolls: hiddenPolls,
      backgroundPollCount: pollCount,
      hiddenRecoveryUsed,
      timeout: true,
      timeoutError: err.message,
    };
  }
  throw err;
}

async function extractAssistantResponse(options) {
  const {
    tabId,
    sentinel,
    cdpEvaluate,
    timeout = 12000,
    wait = false,
    stablePolls = 3,
    noActivate = false,
  } = options;
  if (!tabId) {
    throw new Error("tabId required");
  }
  const cdp = (expr) => cdpEvaluate(tabId, expr);
  if (wait) {
    if (!sentinel) throw new Error("sentinel required with chatgpt.extract --wait");
    const result = await waitForResponse(cdp, timeout, {
      sentinel,
      stablePolls,
      noActivate,
      baselineAssistantCount: 0,
    });
    return {
      response: result.text,
      tabId,
      controlledTabId: tabId,
      messageId: result.messageId || null,
      responseSource: result.source || "assistant-dom",
      sentinel,
      hasSentinel: result.hasSentinel === true,
      pageTextContainsSentinel: result.pageTextContainsSentinel === true,
      documentHiddenAtCompletion: result.documentHiddenAtCompletion === true,
      visibilityStateAtCompletion: result.visibilityStateAtCompletion || null,
      stopVisible: false,
      finished: true,
      turnIndex: result.turnIndex,
    };
  }
  const snapshot = await assistantSnapshot(cdp, sentinel, timeout);
  const text = snapshot?.text || "";
  const hasSentinel = sentinel ? text.includes(sentinel) : false;
  return {
    response: text,
    tabId,
    controlledTabId: tabId,
    messageId: snapshot?.messageId || null,
    responseSource: snapshot?.source || "assistant-dom",
    sentinel: sentinel || null,
    hasSentinel,
    pageTextContainsSentinel: snapshot?.pageTextContainsSentinel === true,
    documentHiddenAtCompletion: snapshot?.documentHidden === true,
    visibilityStateAtCompletion: snapshot?.visibilityState || null,
    stopVisible: snapshot?.stopVisible === true,
    finished: snapshot?.finished === true,
    turnIndex: snapshot?.turnIndex,
  };
}

async function query(options) {
  const {
    prompt,
    model,
    reasoning,
    file,
    timeout = 2700000,
    sentinel,
    stablePolls,
    keepTab = false,
    noActivate = false,
    heartbeatFile = null,
    getCookies,
    createTab,
    closeTab,
    cdpEvaluate,
    cdpCommand,
    log = () => {},
  } = options;
  const startTime = Date.now();
  log("Starting ChatGPT query");
  const { cookies } = await getCookies();
  if (!hasRequiredCookies(cookies)) {
    throw new Error("ChatGPT login required");
  }
  log(`Got ${cookies.length} cookies`);
  const tabInfo = await createTab();
  const { tabId } = tabInfo;
  if (!tabId) {
    throw new Error("Failed to create ChatGPT tab");
  }
  log(`Created tab ${tabId}`);
  if (typeof options.pinControlledTab === "function") {
    try {
      await options.pinControlledTab(tabId);
      log(`Pinned controlled tab ${tabId} (autoDiscardable=false)`);
    } catch (err) {
      log(`Pin controlled tab skipped: ${err?.message || err}`);
    }
  }
  const activateTabForRecovery = noActivate && typeof options.activateTab === "function"
    ? () => options.activateTab(tabId)
    : null;
  
  const cdp = (expr) => cdpEvaluate(tabId, expr);
  const inputCdp = (method, params) => cdpCommand(tabId, method, params);
  
  try {
    await waitForPageLoad(cdp);
    log("Page loaded");
    await recoverCloudflareChallenge(cdp, inputCdp, log);
    const loginStatus = await checkLoginStatus(cdp);
    if (loginStatus.status !== 200 || loginStatus.hasLoginCta) {
      throw new Error("ChatGPT login required");
    }
    log("Login verified");
    const promptReady = await waitForPromptReady(cdp);
    if (!promptReady) {
      throw new Error("Prompt textarea not ready");
    }
    await assertReadyForNewPrompt(cdp);
    log("Prompt ready");
    const modelSelection = await attemptOptionalSelection(
      "Model", model, (value) => selectModel(cdp, value), log,
      () => inputCdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 }),
    );
    const reasoningSelection = await attemptOptionalSelection(
      "Reasoning", reasoning, (value) => selectReasoning(cdp, value), log,
      () => inputCdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 }),
    );
    if (file) {
      await attachFile(cdp, inputCdp, file, log);
      log(`File attached: ${file}`);
    }
    await typePrompt(cdp, inputCdp, prompt);
    log("Prompt typed");
    const assistantBaseline = await captureAssistantBaseline(cdp);
    log(`Assistant baseline count: ${assistantBaseline.assistantCount}`);
    await clickSend(cdp, inputCdp);
    const submitState = await waitForSubmitAccepted(cdp, prompt, 10000, assistantBaseline);
    log(`Prompt accepted: sentinel=${sentinel || ''} stopVisible=${submitState.stopVisible} composerChars=${submitState.composerChars}`);
    log("Prompt sent, waiting for response...");
    let response;
    let responseTimedOut = false;
    let timeoutError = null;
    try {
      response = await waitForResponse(cdp, timeout, {
        sentinel,
        stablePolls,
        noActivate,
        inputCdp,
        log,
        baselineAssistantCount: assistantBaseline.assistantCount,
        activateTabForRecovery,
        heartbeatFile,
      });
    } catch (err) {
      if (!err.partialResponse?.text) {
        throw err;
      }
      response = err.partialResponse;
      responseTimedOut = true;
      timeoutError = err.message;
      log(`Response timed out; preserving partial assistant text (${response.text.length} chars)`);
    }
    const conversationUrl = await evaluate(cdp, "window.location.href").catch(() => null);
    log(`Response received (${response.text.length} chars)`);
    return {
      response: response.text,
      model: modelSelection.selected || "current",
      requestedModel: modelSelection.requested,
      selectedModel: modelSelection.selected,
      modelSelectionStatus: modelSelection.status,
      modelSelectionError: modelSelection.error,
      reasoning: reasoningSelection.selected || null,
      requestedReasoning: reasoningSelection.requested,
      selectedReasoning: reasoningSelection.selected,
      reasoningSelectionStatus: reasoningSelection.status,
      reasoningSelectionError: reasoningSelection.error,
      tabId,
      controlledTabId: tabId,
      conversationUrl,
      messageId: response.messageId,
      responseSource: response.source,
      sentinel,
      hasSentinel: response.hasSentinel,
      pageTextContainsSentinel: response.pageTextContainsSentinel === true,
      documentHiddenAtCompletion: response.documentHiddenAtCompletion === true,
      visibilityStateAtCompletion: response.visibilityStateAtCompletion || null,
      backgroundHiddenPolls: response.backgroundHiddenPolls || 0,
      backgroundPollCount: response.backgroundPollCount || 0,
      hiddenRecoveryUsed: response.hiddenRecoveryUsed === true,
      responseTimedOut,
      timeoutError,
      tookMs: Date.now() - startTime,
      activated: tabInfo.activated === true,
      tabWasCreated: tabInfo.tabWasCreated === true,
      noActivate: noActivate === true,
    };
  } finally {
    if (!keepTab) {
      await closeTab(tabId).catch(() => {});
    }
  }
}

module.exports = {
  query,
  extractAssistantResponse,
  hasRequiredCookies,
  CHATGPT_URL,
  assistantSnapshotExpression,
  assertReadyForNewPrompt,
  waitForSubmitAccepted,
  typePrompt,
  recoverCloudflareChallenge,
  attemptOptionalSelection,
  waitForResponse,
};
