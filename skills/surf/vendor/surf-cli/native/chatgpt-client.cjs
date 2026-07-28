const path = require("path");
const { abortableDelay, raceAbort, throwIfAborted } = require("./abort.cjs");
const { insertPromptText } = require("./prompt-insert.cjs");

const CHATGPT_URL = "https://chatgpt.com/";

const SELECTORS = {
  promptTextarea: '#prompt-textarea, [data-testid="composer-textarea"], textarea[name="prompt-textarea"], .ProseMirror, [contenteditable="true"][data-virtualkeyboard="true"]',
  sendButton: 'button[data-testid="send-button"], button[data-testid*="composer-send"], form button[type="submit"]',
  modelButton: '[data-testid="model-switcher-dropdown-button"]',
  reasoningButton: 'button[data-testid*="reason"], button[aria-label*="reason" i], button[aria-label*="thinking" i], button[aria-label*="effort" i]',
  menuContainer: '[role="menu"], [data-radix-collection-root]',
  menuItem: 'button, [role="menuitem"], [role="menuitemradio"], [data-testid*="model-switcher-"]',
  assistantMessage: '[data-message-author-role="assistant"], [data-turn="assistant"], [data-testid*="assistant-message"], [data-testid*="assistant-turn"], [data-testid*="assistant-response"]',
  assistantContent: '.markdown, [data-message-content], .prose, [class*="markdown"], [dir="auto"]',
  stopButton: '[data-testid="stop-button"], [data-testid*="stop"], button[aria-label*="Stop"], button[aria-label*="stop"]',
  finishedActions: 'button[data-testid="copy-turn-action-button"], button[data-testid="good-response-turn-action-button"], button[data-testid*="turn-action"], button[aria-label*="Copy"], button[aria-label*="copy"], button[aria-label*="Read aloud"], button[aria-label*="read aloud"]',
  conversationTurn: '[data-testid^="conversation-turn"], [data-testid*="conversation-turn"]',
  cloudflareScript: 'script[src*="/challenge-platform/"]',
};

function normalizeProviderMessage(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function detectsConversationMaxLength(text) {
  const normalized = normalizeProviderMessage(text);
  if (!normalized) return false;
  const reachedLimit =
    normalized.includes("you've reached the maximum length for this conversation") ||
    normalized.includes("you have reached the maximum length for this conversation") ||
    normalized.includes("maximum length for this conversation");
  const newChatInstruction =
    normalized.includes("keep talking by starting a new chat") ||
    normalized.includes("start a new chat");
  return reachedLimit && newChatInstruction;
}

function detectsTooManyRequests(text) {
  const normalized = normalizeProviderMessage(text);
  if (!normalized) return false;
  const hasTitle =
    normalized.includes("too many requests") ||
    normalized.includes("you've hit your limit") ||
    normalized.includes("you have hit your limit");
  const hasThrottle =
    normalized.includes("you're making requests too quickly") ||
    normalized.includes("you are making requests too quickly") ||
    normalized.includes("temporarily limited access to your conversations") ||
    normalized.includes("please wait a few minutes before trying again") ||
    normalized.includes("please try again later");
  return hasTitle && hasThrottle;
}

function conversationMaxLengthError(state) {
  const error = new Error(
    "ChatGPT conversation reached maximum length; start a new chat is required"
  );
  error.code = "chatgpt_conversation_max_length";
  error.chatgptPageState = state || null;
  return error;
}

function tooManyRequestsError(state) {
  const error = new Error(
    "ChatGPT is rate limited: too many requests; wait before retrying"
  );
  error.code = "chatgpt_too_many_requests";
  error.chatgptPageState = state || null;
  return error;
}

function delay(ms, signal) {
  return abortableDelay(ms, signal);
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
  return cookies.some(
    (c) =>
      typeof c?.name === "string" &&
      Boolean(c.value) &&
      (c.name === "__Secure-next-auth.session-token" ||
        /^__Secure-next-auth\.session-token\.\d+$/.test(c.name))
  );
}

function cleanChatGPTResponseText(rawText) {
  if (!rawText) return "";

  const chromeLines = new Set([
    "copy",
    "good response",
    "bad response",
    "read aloud",
    "edit",
    "retry",
    "continue generating",
    "share",
  ]);

  const lines = [];
  let inCodeFence = false;

  for (const line of String(rawText).replace(/\r\n?/g, "\n").split("\n")) {
    const trimmed = line.trim();
    const isFenceLine = trimmed.startsWith("```");
    const normalizedLine = inCodeFence || isFenceLine ? line.replace(/[\t ]+$/g, "") : line;

    lines.push({
      text: normalizedLine,
      trimmed,
      isChrome: trimmed.length > 0 && chromeLines.has(trimmed.toLowerCase()),
      inCodeFence,
      isFenceLine,
    });

    if (isFenceLine) {
      inCodeFence = !inCodeFence;
    }
  }

  while (lines.length > 0 && lines[0].trimmed.length === 0) {
    lines.shift();
  }
  while (lines.length > 0 && lines[lines.length - 1].trimmed.length === 0) {
    lines.pop();
  }

  let trailingChromeStart = lines.length;
  while (trailingChromeStart > 0) {
    const line = lines[trailingChromeStart - 1];
    if (line.inCodeFence || line.isFenceLine || !line.isChrome) break;
    trailingChromeStart--;
  }

  const trailingChromeCount = lines.length - trailingChromeStart;
  if (trailingChromeCount >= 2) {
    lines.splice(trailingChromeStart);
  }

  while (lines.length > 0 && lines[0].trimmed.length === 0) {
    lines.shift();
  }
  while (lines.length > 0 && lines[lines.length - 1].trimmed.length === 0) {
    lines.pop();
  }

  return lines.map((line) => line.text).join("\n");
}

function extractLatestAssistantSnapshot(candidates) {
  if (!Array.isArray(candidates)) return null;

  let latestEmptyAssistant = null;

  for (let i = candidates.length - 1; i >= 0; i--) {
    const candidate = candidates[i];
    if (!candidate?.isAssistant) continue;

    const snapshot = {
      ...candidate,
      text: cleanChatGPTResponseText(candidate?.text || ""),
      turnIndex: i,
    };

    if (snapshot.text) {
      return snapshot;
    }

    if (!latestEmptyAssistant) {
      latestEmptyAssistant = snapshot;
    }
  }

  return latestEmptyAssistant;
}

function normalizeResponseSnapshot(rawSnapshot) {
  const candidates = rawSnapshot?.candidates;
  return {
    latestAssistant: extractLatestAssistantSnapshot(candidates),
    assistantCount: Array.isArray(candidates)
      ? candidates.filter((candidate) => candidate?.isAssistant).length
      : 0,
    stopVisible: Boolean(rawSnapshot?.stopVisible),
    pageText: rawSnapshot?.pageText || "",
    documentHidden: rawSnapshot?.documentHidden === true,
    visibilityState: rawSnapshot?.visibilityState || null,
  };
}

function isNewAssistantContent(
  latestAssistant,
  baselineAssistant,
  assistantCount = 0,
  baselineAssistantCount = 0
) {
  if (!latestAssistant) return false;
  if (!baselineAssistant) return true;
  if (latestAssistant.messageId && baselineAssistant.messageId) {
    if (latestAssistant.messageId !== baselineAssistant.messageId) {
      return true;
    }
  }

  const currentText = latestAssistant.text || "";
  const baselineText = baselineAssistant.text || "";

  if (assistantCount > baselineAssistantCount) {
    if (latestAssistant.turnIndex !== baselineAssistant.turnIndex) {
      return true;
    }
    if (currentText !== baselineText) {
      return true;
    }
    return false;
  }

  if (currentText !== baselineText) {
    return true;
  }
  return false;
}

function isChatGPTResponseComplete(snapshot, stableCycles, stableMs) {
  if (!snapshot?.text) return false;
  if (snapshot.stopVisible) return false;
  if (snapshot.hasFinishedActions) return true;
  return stableCycles >= 6 && stableMs >= 1200;
}

async function evaluate(cdp, expression, signal) {
  throwIfAborted(signal);
  const result = await cdp(expression);
  throwIfAborted(signal);
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

async function waitForPageLoad(cdp, timeoutMs = 45000, signal) {
  throwIfAborted(signal);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await evaluate(cdp, "document.readyState");
    if (ready === "complete" || ready === "interactive") {
      return;
    }
    await delay(100, signal);
  }
  throw new Error("Page did not load in time");
}

async function isCloudflareBlocked(cdp) {
  const title = await evaluate(cdp, "document.title.toLowerCase()");
  if (title && title.includes("just a moment")) return true;
  const state = await evaluate(
    cdp,
    `(() => {
      const text = String(document.body?.innerText || '').toLowerCase().replace(/\\s+/g, ' ');
      const hasChallengeScript = Boolean(document.querySelector('${SELECTORS.cloudflareScript}'));
      const hasChallengeText =
        text.includes('checking your browser') ||
        text.includes('verify you are human') ||
        text.includes('review the security of your connection') ||
        text.includes('needs to review the security') ||
        text.includes('cf-challenge') ||
        text.includes('cloudflare');
      const hasChatGptShell =
        text.includes('chatgpt') ||
        Boolean(document.querySelector('#prompt-textarea, [data-testid="composer-textarea"], [data-message-author-role]'));
      return { hasChallengeScript, hasChallengeText, hasVisibleChallenge: hasChallengeText, hasChatGptShell };
    })()`
  );
  return Boolean(state?.hasChallengeText || state?.hasVisibleChallenge) &&
    (state?.hasChatGptShell !== true || title.includes("just a moment"));
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
    `Cloudflare challenge persisted after ${maxReloads} automatic hard reload(s)`
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

async function waitForPromptReady(cdp, timeoutMs = 30000, signal) {
  throwIfAborted(signal);
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
    await delay(200, signal);
  }
  return false;
}

async function assertReadyForNewPrompt(cdp, signal) {
  throwIfAborted(signal);
  const state = await evaluate(
    cdp,
    `(() => {
      const STOP_SELECTOR = ${JSON.stringify(SELECTORS.stopButton)};
      const SEND_SELECTOR = ${JSON.stringify(SELECTORS.sendButton)};
      const PROMPT_SELECTOR = ${JSON.stringify(SELECTORS.promptTextarea)};
      const stop = document.querySelector(STOP_SELECTOR);
      const send = document.querySelector(SEND_SELECTOR);
      const prompt = document.querySelector(PROMPT_SELECTOR);
      const promptText = prompt ? (prompt.innerText || prompt.value || prompt.textContent || '').trim() : '';
      const pageText = document.body?.innerText || '';
      const visibleText = pageText.slice(-4000);
      const normalizeProviderMessage = (text) => String(text || '')
        .toLowerCase()
        .replace(/[\\u2018\\u2019]/g, "'")
        .replace(/\\s+/g, ' ')
        .trim();
      const detectsConversationMaxLength = (text) => {
        const normalized = normalizeProviderMessage(text);
        if (!normalized) return false;
        const reachedLimit = (
          normalized.includes("you've reached the maximum length for this conversation") ||
          normalized.includes('you have reached the maximum length for this conversation') ||
          normalized.includes('maximum length for this conversation')
        );
        const newChatInstruction = (
          normalized.includes('keep talking by starting a new chat') ||
          normalized.includes('start a new chat')
        );
        return reachedLimit && newChatInstruction;
      };
      const detectsTooManyRequests = (text) => {
        const normalized = normalizeProviderMessage(text);
        if (!normalized) return false;
        const hasTitle = (
          normalized.includes('too many requests') ||
          normalized.includes("you've hit your limit") ||
          normalized.includes('you have hit your limit')
        );
        const hasThrottle = (
          normalized.includes("you're making requests too quickly") ||
          normalized.includes('you are making requests too quickly') ||
          normalized.includes('temporarily limited access to your conversations') ||
          normalized.includes('please wait a few minutes before trying again') ||
          normalized.includes('please try again later')
        );
        return hasTitle && hasThrottle;
      };
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
        conversationMaxLengthDetected: detectsConversationMaxLength(pageText),
        conversationMaxLengthTail: detectsConversationMaxLength(pageText) ? visibleText : '',
        tooManyRequestsDetected: detectsTooManyRequests(pageText),
        tooManyRequestsTail: detectsTooManyRequests(pageText) ? visibleText : '',
        title: document.title || '',
        url: location.href || '',
      };
    })()`,
    signal
  );
  if (state?.conversationMaxLengthDetected) {
    throw conversationMaxLengthError(state);
  }
  if (state?.tooManyRequestsDetected) {
    throw tooManyRequestsError(state);
  }
  if (state?.stopVisible) {
    const error = new Error(
      "ChatGPT page is busy before submit: stop button is visible; wait, extract the existing response, or use a fresh reviewer tab"
    );
    error.chatgptPageState = state;
    throw error;
  }
  if (!state?.promptPresent) {
    const error = new Error("ChatGPT prompt composer not present before submit");
    error.chatgptPageState = state || null;
    throw error;
  }
  if (state?.promptChars > 0) {
    const error = new Error(
      "ChatGPT prompt composer is not empty before submit; clear the draft or use a fresh reviewer tab"
    );
    error.chatgptPageState = state;
    throw error;
  }
  return state;
}

function normalizeChatGPTModelChoice(desiredModel) {
  const normalized = String(desiredModel || "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

  if (["instant", "gpt53"].includes(normalized)) return "instant";
  if (["thinking", "gpt54thinking"].includes(normalized)) return "thinking";
  if (["pro", "gpt54pro"].includes(normalized)) return "pro";

  return normalized;
}

function resolveChatGPTModelMenuOption(items, desiredModel) {
  if (!Array.isArray(items)) return null;

  const targetModel = normalizeChatGPTModelChoice(desiredModel);

  return items.find((item) => {
    if (item?.role !== "menuitemradio") return false;
    if (typeof item?.testId !== "string" || !item.testId.startsWith("model-switcher-")) return false;

    const label = normalizeChatGPTModelChoice(item.label || "");
    const testId = normalizeChatGPTModelChoice(item.testId.replace(/^model-switcher-/, ""));
    return label === targetModel || testId === targetModel;
  }) || null;
}

async function selectModel(cdp, desiredModel, timeoutMs = 8000, signal) {
  throwIfAborted(signal);
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
  await delay(300, signal);

  const normalizedModel = normalizeChatGPTModelChoice(desiredModel);
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const result = await evaluate(
      cdp,
      `(() => {
        const menu = document.querySelector('[role="menu"][data-radix-menu-content]');
        if (!menu) {
          return { found: false, waiting: true };
        }

        return {
          found: true,
          items: Array.from(menu.children).map((item) => {
            const primary = item.querySelector?.('.min-w-0 > span');
            return {
              role: item.getAttribute?.('role') || null,
              label: (primary?.textContent || item.getAttribute?.('aria-label') || item.textContent || '').trim(),
              testId: item.getAttribute?.('data-testid') || null,
            };
          }),
        };
      })()`
    );

    if (result && result.found) {
      const match = resolveChatGPTModelMenuOption(result.items, normalizedModel);
      if (match) {
        await evaluate(
          cdp,
          `(() => {
            ${buildClickDispatcher()}
            const menu = document.querySelector('[role="menu"][data-radix-menu-content]');
            const item = menu?.querySelector('[data-testid="${match.testId}"]');
            if (item) dispatchClickSequence(item);
          })()`
        );
        await delay(200, signal);
        return match.label;
      }

      const available = Array.isArray(result.items)
        ? result.items
            .filter((item) => item?.role === "menuitemradio" && typeof item?.testId === "string" && item.testId.startsWith("model-switcher-"))
            .map((item) => item.label)
            .filter(Boolean)
            .join(", ")
        : "";
      throw new Error(
        available
          ? `Model not found: ${desiredModel}. Available: ${available}`
          : `Model not found: ${desiredModel}`
      );
    }

    await delay(100, signal);
  }

  throw new Error(`Model not found: ${desiredModel} (timeout)`);
}

async function selectReasoning(cdp, desiredReasoning, timeoutMs = 8000, signal) {
  throwIfAborted(signal);
  const normalizedReasoning = String(desiredReasoning || "").toLowerCase().replace(/[^a-z0-9]/g, "");
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
    })()`,
    signal
  );
  if (!clicked || !clicked.success) {
    throw new Error(`Reasoning selector button not found for: ${desiredReasoning}`);
  }
  await delay(300, signal);
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
    })()`,
    signal
  );
  if (!result || !result.success) {
    throw new Error(`Reasoning option not found: ${desiredReasoning}`);
  }
  return result.label;
}

async function attemptOptionalSelection(kind, requested, selectFn, log, recoverFn) {
  if (!requested) {
    return {
      requested: null,
      selected: null,
      status: "not_requested",
      error: null,
    };
  }
  try {
    const selected = await selectFn(requested);
    return {
      requested,
      selected: selected || requested,
      status: "selected",
      error: null,
    };
  } catch (err) {
    const message = err?.message || String(err);
    log?.(`${kind} selection unavailable for ${requested}; preserving current browser setting and continuing with current setting: ${message}`);
    if (typeof recoverFn === "function") {
      await recoverFn().catch(() => {});
    }
    return {
      requested,
      selected: null,
      status: "unavailable_using_current",
      error: message,
    };
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
    const CONVERSATION_SELECTOR = ${JSON.stringify(SELECTORS.conversationTurn)};
    const ASSISTANT_SELECTOR = ${JSON.stringify(SELECTORS.assistantMessage)};
    const CONTENT_SELECTORS = ${JSON.stringify(SELECTORS.assistantContent.split(", "))};
    const STOP_SELECTOR = ${JSON.stringify(SELECTORS.stopButton)};
    const FINISHED_SELECTOR = ${JSON.stringify(SELECTORS.finishedActions)};
    const pageText = document.body?.innerText || document.body?.textContent || '';
    const findSentinel = (text) => SENTINEL && String(text || '').includes(SENTINEL) ? SENTINEL : null;
    const conversationTurns = Array.from(document.querySelectorAll(CONVERSATION_SELECTOR));
    let assistantTurns = conversationTurns.filter((node) => {
      if (!(node instanceof HTMLElement)) return false;
      const role = (node.getAttribute('data-message-author-role') || '').toLowerCase();
      const turn = (node.getAttribute('data-turn') || '').toLowerCase();
      return role === 'assistant' || turn === 'assistant' || Boolean(node.querySelector(ASSISTANT_SELECTOR));
    });
    if (assistantTurns.length === 0) {
      assistantTurns = Array.from(document.querySelectorAll(ASSISTANT_SELECTOR));
    }
    const newAssistantTurns = assistantTurns.slice(BASELINE);
    let lastAssistantTurn = newAssistantTurns.length ? newAssistantTurns[newAssistantTurns.length - 1] : null;
    let baselineFallback = false;
    if (!lastAssistantTurn && SENTINEL && assistantTurns.length) {
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
    if (!lastAssistantTurn) {
      return {
        text: '',
        stopVisible: Boolean(document.querySelector(STOP_SELECTOR)),
        finished: false,
        source: 'awaiting-assistant-turn',
        pageTextContainsSentinel: false,
        documentHidden: document.hidden === true,
        visibilityState: document.visibilityState || null,
        baselineAssistantCount: BASELINE,
        newAssistantTurnCount: 0,
      };
    }
    const messageRoot = lastAssistantTurn.querySelector?.(ASSISTANT_SELECTOR) || lastAssistantTurn;
    let contentRoot = null;
    for (const selector of CONTENT_SELECTORS) {
      const match = selector === '[dir="auto"]'
        ? (messageRoot.matches?.(selector) ? messageRoot : null)
        : (messageRoot.matches?.(selector) ? messageRoot : messageRoot.querySelector?.(selector));
      if (match) {
        contentRoot = match;
        break;
      }
    }
    const contentText = ((contentRoot || messageRoot)?.innerText || (contentRoot || messageRoot)?.textContent || '').trim();
    const turnText = (messageRoot?.innerText || messageRoot?.textContent || '').trim();
    const contentSentinel = findSentinel(contentText);
    const turnSentinel = findSentinel(turnText);
    let text = SENTINEL && !contentSentinel && turnSentinel ? turnText : contentText;
    let source = baselineFallback ? 'assistant-dom-baseline-fallback' : 'assistant-dom';
    if (SENTINEL && findSentinel(turnText) && !findSentinel(text)) {
      const idx = turnText.lastIndexOf(SENTINEL);
      if (idx >= 0) {
        text = turnText.slice(Math.max(0, idx - 12000), idx + SENTINEL.length).trim();
        source = 'page-text-fallback';
      }
    }
    return {
      text,
      stopVisible: Boolean(document.querySelector(STOP_SELECTOR)),
      finished: Boolean(lastAssistantTurn.querySelector?.(FINISHED_SELECTOR)),
      messageId: messageRoot.getAttribute?.('data-message-id') || null,
      turnIndex: assistantTurns.length - 1,
      source,
      pageTextContainsSentinel: Boolean(SENTINEL && findSentinel(turnText || pageText)),
      sentinelMatch: findSentinel(text),
      documentHidden: document.hidden === true,
      visibilityState: document.visibilityState || null,
      baselineAssistantCount: BASELINE,
      newAssistantTurnCount: newAssistantTurns.length,
    };
  })()`;
};

async function typePrompt(cdp, inputCdp, prompt, signal) {
  throwIfAborted(signal);
  const selectors = JSON.stringify(SELECTORS.promptTextarea.split(", "));
  const encodedPrompt = JSON.stringify(prompt);
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
  await insertPromptText(inputCdp, prompt, signal);
  await delay(300, signal);
  const verified = await evaluate(
    cdp,
    `(() => {
      const selectors = ${selectors};
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node) continue;
        const text = node.innerText || node.value || node.textContent || '';
        if (text.trim().length > 0) return true;
      }
      return false;
    })()`
  );
  if (!verified) {
    await evaluate(
      cdp,
      `(() => {
        const editor = document.querySelector('#prompt-textarea');
        const fallback = document.querySelector('textarea[name="prompt-textarea"]');
        if (fallback) {
          fallback.value = ${encodedPrompt};
          fallback.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
        }
        if (editor) {
          editor.textContent = ${encodedPrompt};
          editor.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
        }
      })()`
    );
  }
}

async function clickSend(cdp, inputCdp, signal) {
  throwIfAborted(signal);
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
    await delay(100, signal);
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

async function waitForSubmitAccepted(cdp, prompt, timeoutMs = 10000, baseline = {}, signal) {
  throwIfAborted(signal);
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
      })()`,
      signal
    );
    const assistantAdvanced = Number(lastState?.assistantCount || 0) > baselineAssistantCount;
    const userTurnAdvanced = Number(lastState?.userCount || 0) > baselineUserCount && lastState?.lastUserContainsPrompt === true;
    if (lastState?.stopVisible || assistantAdvanced || userTurnAdvanced) {
      return { accepted: true, ...lastState };
    }
    await delay(200, signal);
  }
  const err = new Error("ChatGPT did not accept submitted prompt: prompt remained in the composer after send");
  err.chatgptSubmitState = lastState || null;
  throw err;
}

async function readChatGPTResponseSnapshot(cdp) {
  return evaluate(
    cdp,
    `(() => {
      const scope = document.querySelector('main') || document;
      const CONVERSATION_SELECTOR = ${JSON.stringify(SELECTORS.conversationTurn)};
      const ASSISTANT_SELECTOR = ${JSON.stringify(SELECTORS.assistantMessage)};
      const CONTENT_SELECTORS = ${JSON.stringify(SELECTORS.assistantContent.split(", "))};
      const STOP_SELECTOR = ${JSON.stringify(SELECTORS.stopButton)};
      const FINISHED_SELECTOR = ${JSON.stringify(SELECTORS.finishedActions)};

      const toCandidate = (turnNode, messageRoot = null) => {
        const resolvedMessageRoot = messageRoot || (turnNode.matches?.(ASSISTANT_SELECTOR)
          ? turnNode
          : turnNode.querySelector(ASSISTANT_SELECTOR));
        const searchRoot = resolvedMessageRoot || turnNode;
        let contentRoot = null;

        for (const selector of CONTENT_SELECTORS) {
          const match = selector === '[dir="auto"]'
            ? (searchRoot.matches?.(selector) ? searchRoot : null)
            : (searchRoot.matches?.(selector) ? searchRoot : searchRoot.querySelector(selector));
          if (match) {
            contentRoot = match;
            break;
          }
        }

        const role =
          resolvedMessageRoot?.getAttribute('data-message-author-role') ||
          turnNode.getAttribute('data-message-author-role') ||
          null;
        const turn =
          resolvedMessageRoot?.getAttribute('data-turn') ||
          turnNode.getAttribute('data-turn') ||
          null;
        const isAssistant =
          role === 'assistant' ||
          turn === 'assistant' ||
          resolvedMessageRoot !== null;
        const text = (contentRoot || turnNode).innerText || (contentRoot || turnNode).textContent || '';
        const messageId =
          resolvedMessageRoot?.getAttribute('data-message-id') ||
          turnNode.getAttribute('data-message-id') ||
          null;
        const hasFinishedActions = Boolean(turnNode.querySelector(FINISHED_SELECTOR));

        return {
          role,
          turn,
          isAssistant,
          text,
          messageId,
          hasFinishedActions,
        };
      };

      let candidates = Array.from(scope.querySelectorAll(CONVERSATION_SELECTOR)).map((turnNode) =>
        toCandidate(turnNode)
      );

      if (candidates.length === 0) {
        candidates = Array.from(scope.querySelectorAll(ASSISTANT_SELECTOR)).map((messageRoot) =>
          toCandidate(messageRoot, messageRoot)
        );
      }

      return {
        candidates,
        stopVisible: Boolean(scope.querySelector(STOP_SELECTOR)),
        pageText: document.body?.innerText || '',
        documentHidden: document.hidden === true,
        visibilityState: document.visibilityState || null,
      };
    })()`
  );
}

function normalizeDirectAssistantSnapshot(rawValue) {
  if (!rawValue || typeof rawValue !== "object") return null;
  const text = cleanChatGPTResponseText(rawValue.text || "");
  return {
    ...rawValue,
    text,
    stopVisible: Boolean(rawValue.stopVisible),
    finished: rawValue.finished === true || rawValue.hasFinishedActions === true,
    pageTextContainsSentinel: rawValue.pageTextContainsSentinel === true,
    documentHidden: rawValue.documentHidden === true,
    visibilityState: rawValue.visibilityState || null,
    source: rawValue.source || "assistant-dom",
  };
}

async function readDirectAssistantSnapshot(cdp, sentinel, signal) {
  const value = await evaluate(
    cdp,
    `(() => {
      const pageText = document.body?.innerText || '';
      return {
        text: '',
        pageTextContainsSentinel: ${JSON.stringify(Boolean(sentinel))} ? pageText.includes(${JSON.stringify(sentinel || "")}) : false,
        documentHidden: document.hidden === true,
        visibilityState: document.visibilityState || null,
        source: 'page-state'
      };
    })()`,
    signal
  );
  return normalizeDirectAssistantSnapshot(value);
}

async function waitForSentinelResponse(cdp, timeoutMs = 2700000, options = {}, signal) {
  throwIfAborted(signal);
  const sentinel = options.sentinel || null;
  const deadline = Date.now() + timeoutMs;
  const requiredStableCycles =
    Number.isInteger(options.stablePolls) && options.stablePolls > 0
      ? options.stablePolls
      : 6;
  const minStableMs = 1200;
  const stableStallMs = Number.parseInt(process.env.SURF_WEBGPT_STABLE_STALL_MS || "0", 10);
  let previousText = "";
  let stableCycles = 0;
  let lastChangeAt = Date.now();
  let lastNonEmptySnapshot = null;
  let pollCount = 0;

  while (Date.now() < deadline) {
    pollCount++;
    let snapshot = null;
    try {
      const raw = await readChatGPTResponseSnapshot(cdp);
      if (raw && typeof raw === "object" && typeof raw.text === "string" && !Array.isArray(raw.candidates)) {
        snapshot = normalizeDirectAssistantSnapshot(raw);
      } else {
        const normalized = normalizeResponseSnapshot(raw);
        const latest = normalized.latestAssistant;
        snapshot = {
          text: latest?.text || "",
          messageId: latest?.messageId || null,
          turnIndex: latest?.turnIndex,
          stopVisible: normalized.stopVisible === true,
          finished: latest?.hasFinishedActions === true || normalized.stopVisible !== true,
          source: latest?.source || "assistant-dom",
          pageTextContainsSentinel: sentinel ? String(normalized.pageText || "").includes(sentinel) : false,
          documentHidden: normalized.documentHidden === true,
          visibilityState: normalized.visibilityState || null,
          conversationMaxLengthDetected: detectsConversationMaxLength(normalized.pageText || ""),
          tooManyRequestsDetected: detectsTooManyRequests(normalized.pageText || ""),
        };
      }
    } catch (_error) {
      snapshot = await readDirectAssistantSnapshot(cdp, sentinel, signal).catch(() => null);
    }

    if (!snapshot) {
      await delay(400, signal);
      continue;
    }
    if (snapshot.conversationMaxLengthDetected === true || detectsConversationMaxLength(snapshot.text)) {
      throw conversationMaxLengthError(snapshot);
    }
    if (snapshot.tooManyRequestsDetected === true || detectsTooManyRequests(snapshot.text)) {
      throw tooManyRequestsError(snapshot);
    }

    const currentText = snapshot.text || "";
    if (currentText) {
      lastNonEmptySnapshot = { ...snapshot };
    }
    if (currentText !== previousText) {
      previousText = currentText;
      stableCycles = 0;
      lastChangeAt = Date.now();
    } else if (currentText) {
      stableCycles++;
    } else {
      stableCycles = 0;
      lastChangeAt = Date.now();
    }

    const stableMs = Date.now() - lastChangeAt;
    const hasSentinel = sentinel
      ? currentText.includes(sentinel) || snapshot.sentinelMatch === sentinel
      : true;

    if (
      sentinel &&
      stableStallMs > 0 &&
      currentText &&
      !hasSentinel &&
      stableCycles >= requiredStableCycles &&
      stableMs >= stableStallMs
    ) {
      const error = new Error(`Stable assistant response stalled without sentinel after ${stableMs}ms`);
      error.code = "stable_response_without_sentinel";
      error.partialResponse = {
        text: currentText,
        messageId: snapshot.messageId || null,
        turnIndex: snapshot.turnIndex,
        sentinel,
        hasSentinel: false,
        source: snapshot.source || "assistant-dom",
        stableResponseWithoutSentinel: true,
        stableStallMs: stableMs,
        pageTextContainsSentinel: snapshot.pageTextContainsSentinel === true,
        documentHiddenAtCompletion: snapshot.documentHidden === true,
        visibilityStateAtCompletion: snapshot.visibilityState || null,
        backgroundHiddenPolls: snapshot.documentHidden === true ? pollCount : 0,
        backgroundPollCount: pollCount,
        hiddenRecoveryUsed: false,
      };
      throw error;
    }

    const stableEnough = stableCycles >= requiredStableCycles && stableMs >= minStableMs;
    const stopGateOk = !snapshot.stopVisible || (sentinel && hasSentinel);
    if (currentText && hasSentinel && stopGateOk && (sentinel ? stableEnough : snapshot.finished || stableEnough)) {
      return {
        text: currentText,
        messageId: snapshot.messageId || null,
        turnIndex: snapshot.turnIndex,
        sentinel,
        hasSentinel,
        source: snapshot.source || "assistant-dom",
        pageTextContainsSentinel: snapshot.pageTextContainsSentinel === true,
        documentHiddenAtCompletion: snapshot.documentHidden === true,
        visibilityStateAtCompletion: snapshot.visibilityState || null,
        backgroundHiddenPolls: snapshot.documentHidden === true ? pollCount : 0,
        backgroundPollCount: pollCount,
        hiddenRecoveryUsed: false,
      };
    }

    await delay(400, signal);
  }

  const error = new Error("Response timeout");
  if (lastNonEmptySnapshot?.text) {
    error.partialResponse = {
      text: lastNonEmptySnapshot.text,
      messageId: lastNonEmptySnapshot.messageId || null,
      turnIndex: lastNonEmptySnapshot.turnIndex,
      sentinel,
      hasSentinel: sentinel ? lastNonEmptySnapshot.text.includes(sentinel) : true,
      source: lastNonEmptySnapshot.source || "assistant-dom",
      pageTextContainsSentinel: lastNonEmptySnapshot.pageTextContainsSentinel === true,
      documentHiddenAtCompletion: lastNonEmptySnapshot.documentHidden === true,
      visibilityStateAtCompletion: lastNonEmptySnapshot.visibilityState || null,
      backgroundHiddenPolls: 0,
      backgroundPollCount: pollCount,
      hiddenRecoveryUsed: false,
    };
  }
  throw error;
}

async function waitForResponse(
  cdp,
  timeoutMs = 2700000,
  baselineAssistant,
  baselineAssistantCount,
  signal
) {
  if (
    baselineAssistant &&
    typeof baselineAssistant === "object" &&
    !("text" in baselineAssistant) &&
    (baselineAssistant.sentinel || baselineAssistant.stablePolls || baselineAssistant.noActivate)
  ) {
    return waitForSentinelResponse(cdp, timeoutMs, baselineAssistant, signal);
  }
  throwIfAborted(signal);
  const deadline = Date.now() + timeoutMs;
  let previousText = "";
  let stableCycles = 0;
  let lastChangeAt = Date.now();

  previousText = baselineAssistant?.text || "";
  lastChangeAt = Date.now();

  while (Date.now() < deadline) {
    const snapshot = await readChatGPTResponseSnapshot(cdp);

    if (!snapshot) {
      await delay(400, signal);
      continue;
    }

    const { latestAssistant, assistantCount, stopVisible } = normalizeResponseSnapshot(snapshot);
    const currentText = latestAssistant?.text || "";
    const hasNewAssistantContent = isNewAssistantContent(
      latestAssistant,
      baselineAssistant,
      assistantCount,
      baselineAssistantCount
    );

    if (!hasNewAssistantContent) {
      await delay(400, signal);
      continue;
    }

    if (currentText !== previousText) {
      previousText = currentText;
      stableCycles = 0;
      lastChangeAt = Date.now();
    } else if (currentText) {
      stableCycles++;
    } else {
      stableCycles = 0;
      lastChangeAt = Date.now();
    }

    const stableMs = Date.now() - lastChangeAt;
    const completionSnapshot = latestAssistant
      ? { ...latestAssistant, stopVisible }
      : { text: "", stopVisible, hasFinishedActions: false };

    if (isChatGPTResponseComplete(completionSnapshot, stableCycles, stableMs)) {
      return {
        text: latestAssistant.text,
        messageId: latestAssistant.messageId,
        turnIndex: latestAssistant.turnIndex,
      };
    }

    await delay(400, signal);
  }

  throw new Error("Response timeout");
}

async function extractAssistantResponse(options) {
  const {
    tabId,
    sentinel,
    timeout = 12000,
    wait = false,
    stablePolls,
    noActivate,
    cdpEvaluate,
    signal,
  } = options;
  if (!tabId) throw new Error("--tab-id required");
  if (!cdpEvaluate) throw new Error("cdpEvaluate callback required");
  throwIfAborted(signal);
  const cdp = (expr) => raceAbort(() => cdpEvaluate(tabId, expr), signal);

  let cloudflareBlocked = false;
  try {
    cloudflareBlocked = await isCloudflareBlocked(cdp);
  } catch (_error) {
    cloudflareBlocked = false;
  }
  if (cloudflareBlocked) {
    throw new Error("Cloudflare challenge detected - complete in browser");
  }

  if (wait || sentinel) {
    const response = await waitForResponse(
      cdp,
      timeout,
      { sentinel, stablePolls, noActivate },
      undefined,
      signal
    );
    return {
      response: response.text,
      tabId,
      controlledTabId: tabId,
      messageId: response.messageId || null,
      responseSource: response.source || "assistant-dom",
      sentinel,
      hasSentinel: response.hasSentinel === true || (sentinel ? response.text.includes(sentinel) : true),
      pageTextContainsSentinel: response.pageTextContainsSentinel === true,
      stopVisible: response.stopVisible === true,
      finished: true,
      turnIndex: response.turnIndex,
      documentHiddenAtCompletion: response.documentHiddenAtCompletion === true,
      visibilityStateAtCompletion: response.visibilityStateAtCompletion || null,
      backgroundHiddenPolls: response.backgroundHiddenPolls || 0,
      backgroundPollCount: response.backgroundPollCount || 0,
      hiddenRecoveryUsed: response.hiddenRecoveryUsed === true,
    };
  }

  const snapshot = normalizeResponseSnapshot(await readChatGPTResponseSnapshot(cdp));
  const latest = snapshot.latestAssistant;
  const text = latest?.text || "";
  return {
    response: text,
    tabId,
    controlledTabId: tabId,
    messageId: latest?.messageId || null,
    responseSource: latest?.source || "assistant-dom",
    sentinel,
    hasSentinel: sentinel ? text.includes(sentinel) : Boolean(text),
    pageTextContainsSentinel: false,
    stopVisible: snapshot.stopVisible === true,
    finished: Boolean(text) && snapshot.stopVisible !== true,
    turnIndex: latest?.turnIndex,
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
    uploadFile,
    log = () => {},
    signal,
  } = options;
  throwIfAborted(signal);
  const guardedUploadFile = uploadFile
    ? (...args) => raceAbort(() => uploadFile(...args), signal)
    : uploadFile;
  const startTime = Date.now();
  log("Starting ChatGPT query");
  const { cookies } = await raceAbort(getCookies, signal);
  if (!hasRequiredCookies(cookies)) {
    throw new Error("ChatGPT login required");
  }
  log(`Got ${cookies.length} cookies`);
  const tabInfo = await raceAbort(createTab, signal);
  const { tabId } = tabInfo;
  if (!tabId) {
    throw new Error("Failed to create ChatGPT tab");
  }
  log(`${tabInfo.reused ? "Using" : "Created"} tab ${tabId}`);

  const cdp = (expr) => raceAbort(() => cdpEvaluate(tabId, expr), signal);
  const inputCdp = (method, params, timeoutMs) => raceAbort(() => cdpCommand(tabId, method, params, timeoutMs), signal);

  try {
    await waitForPageLoad(cdp, 45000, signal);
    log("Page loaded");
    await recoverCloudflareChallenge(cdp, inputCdp, log, { signal });
    const loginStatus = await checkLoginStatus(cdp);
    if (loginStatus.status === 0) {
      throw new Error(
        loginStatus.error
          ? `ChatGPT login check failed: ${loginStatus.error}`
          : "ChatGPT login check failed"
      );
    }
    if (loginStatus.status !== 200 || loginStatus.hasLoginCta) {
      throw new Error("ChatGPT login required");
    }
    log("Login verified");
    const promptReady = await waitForPromptReady(cdp, 30000, signal);
    if (!promptReady) {
      throw new Error("Prompt textarea not ready");
    }
    await assertReadyForNewPrompt(cdp, signal);
    log("Prompt ready");
    const modelSelection = await attemptOptionalSelection(
      "Model",
      model,
      (value) => selectModel(cdp, value, 8000, signal),
      log,
      () => inputCdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 })
    );
    const reasoningSelection = await attemptOptionalSelection(
      "Reasoning",
      reasoning,
      (value) => selectReasoning(cdp, value, 8000, signal),
      log,
      () => inputCdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 })
    );
    if (file) {
      if (!uploadFile) {
        throw new Error("ChatGPT file upload unavailable: native host did not provide upload callback");
      }
      const files = Array.isArray(file) ? file : [file];
      const absFiles = files.map((filePath) => path.resolve(process.cwd(), filePath));
      log(`Uploading ${absFiles.length} file(s) to ChatGPT...`);
      const uploadResult = await guardedUploadFile(tabId, absFiles);
      if (uploadResult?.error) {
        throw new Error(`ChatGPT file upload failed: ${uploadResult.error}`);
      }
      if (!uploadResult?.success) {
        throw new Error("ChatGPT file upload failed: upload did not report success");
      }
      log("File uploaded, waiting for ChatGPT attachment processing...");
      await delay(1500, signal);
    }
    await typePrompt(cdp, inputCdp, prompt, signal);
    log("Prompt typed");
    const baseline = normalizeResponseSnapshot(await readChatGPTResponseSnapshot(cdp));
    await clickSend(cdp, inputCdp, signal);
    const submitState = await waitForSubmitAccepted(cdp, prompt, 10000, baseline, signal);
    log(`Prompt accepted: sentinel=${sentinel || ""} stopVisible=${submitState.stopVisible} composerChars=${submitState.composerChars}`);
    log("Prompt sent, waiting for response...");
    let response;
    let responseTimedOut = false;
    let timeoutError = null;
    try {
      response = await waitForResponse(
        cdp,
        timeout,
        sentinel || stablePolls || noActivate
          ? { sentinel, stablePolls, noActivate, heartbeatFile }
          : baseline.latestAssistant,
        baseline.assistantCount,
        signal
      );
    } catch (err) {
      if (!err.partialResponse?.text) {
        throw err;
      }
      response = err.partialResponse;
      responseTimedOut = true;
      timeoutError = err.message;
      if (err.code === "stable_response_without_sentinel") {
        log(`Response stabilized without sentinel; preserving assistant text (${response.text.length} chars)`);
      } else {
        log(`Response timed out; preserving partial assistant text (${response.text.length} chars)`);
      }
    }
    const conversationUrl = await evaluate(cdp, "window.location.href", signal).catch(() => null);
    log(`Response received (${response.text.length} chars)`);
    return {
      response: response.text,
      model: modelSelection.selected || model || "current",
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
      messageId: response.messageId || null,
      responseSource: response.source || "assistant-dom",
      sentinel: sentinel || null,
      hasSentinel: response.hasSentinel === true || (sentinel ? response.text.includes(sentinel) : true),
      pageTextContainsSentinel: response.pageTextContainsSentinel === true,
      documentHiddenAtCompletion: response.documentHiddenAtCompletion === true,
      visibilityStateAtCompletion: response.visibilityStateAtCompletion || null,
      backgroundHiddenPolls: response.backgroundHiddenPolls || 0,
      backgroundPollCount: response.backgroundPollCount || 0,
      hiddenRecoveryUsed: response.hiddenRecoveryUsed === true,
      stableResponseWithoutSentinel: response.stableResponseWithoutSentinel === true,
      stableStallMs: response.stableStallMs || null,
      responseTimedOut,
      timeoutError,
      tookMs: Date.now() - startTime,
      activated: tabInfo.activated === true,
      tabWasCreated: tabInfo.tabWasCreated === true,
      noActivate: noActivate === true,
    };
  } finally {
    if (!keepTab) {
      try {
        await closeTab(tabId);
      } catch (error) {
        log(`Failed to close ChatGPT tab ${tabId}: ${error?.message || error}`);
      }
    }
  }
}

module.exports = {
  query,
  extractAssistantResponse,
  hasRequiredCookies,
  cleanChatGPTResponseText,
  extractLatestAssistantSnapshot,
  normalizeChatGPTModelChoice,
  resolveChatGPTModelMenuOption,
  isNewAssistantContent,
  isChatGPTResponseComplete,
  assistantSnapshotExpression,
  assertReadyForNewPrompt,
  waitForSubmitAccepted,
  typePrompt,
  recoverCloudflareChallenge,
  attemptOptionalSelection,
  waitForResponse,
  detectsConversationMaxLength,
  detectsTooManyRequests,
  CHATGPT_URL,
};
