const CHATGPT_URL = "https://chatgpt.com/";

const SELECTORS = {
  promptTextarea: '#prompt-textarea, [data-testid="composer-textarea"], textarea[name="prompt-textarea"], .ProseMirror, [contenteditable="true"][data-virtualkeyboard="true"]',
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

async function wakeBackgroundTab(inputCdp, log) {
  if (!inputCdp) return;
  try {
    await inputCdp("Page.setWebLifecycleState", { state: "active" });
    log?.("Background tab lifecycle set to active for DOM polling");
  } catch (err) {
    log?.(`Page.setWebLifecycleState skipped: ${err?.message || err}`);
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
  const sessionCookie = cookies.find(
    (c) => c.name === "__Secure-next-auth.session-token" && c.value
  );
  return Boolean(sessionCookie);
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

const assistantSnapshotExpression = (sentinel) => {
  const sentinelLiteral = JSON.stringify(sentinel || null);
  return `(() => {
    const SENTINEL = ${sentinelLiteral};
    const CONVERSATION_SELECTOR = '${SELECTORS.conversationTurn}';
    const ASSISTANT_SELECTOR = '${SELECTORS.assistantMessage}';
    const STOP_SELECTOR = '${SELECTORS.stopButton}';
    const FINISHED_SELECTOR = '${SELECTORS.finishedActions}';
    const pageText = (document.body?.innerText || document.body?.textContent || '').trim();
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
    const turns = directAssistantTurns.length
      ? directAssistantTurns
      : Array.from(document.querySelectorAll(CONVERSATION_SELECTOR));
    let lastAssistantTurn = null;
    for (let i = turns.length - 1; i >= 0; i--) {
      if (isAssistantTurn(turns[i])) {
        lastAssistantTurn = turns[i];
        break;
      }
    }
    const sentinelVariants = SENTINEL
      ? [SENTINEL, ...(SENTINEL.endsWith('>>>') ? [SENTINEL.slice(0, -1)] : [])]
      : [];
    const findSentinel = (text) => sentinelVariants.find((marker) => text.includes(marker)) || null;
    const pageTextContainsSentinel = Boolean(SENTINEL && findSentinel(pageText));
    if (!lastAssistantTurn) {
      return {
        text: '',
        stopVisible: Boolean(document.querySelector(STOP_SELECTOR)),
        finished: false,
        source: 'no-assistant-turn',
        pageTextContainsSentinel,
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
    if (SENTINEL && sentinelMatch && sentinelMatch !== SENTINEL) {
      const idx = text.lastIndexOf(sentinelMatch);
      text = text.slice(0, idx) + SENTINEL + text.slice(idx + sentinelMatch.length);
    }
    const stopVisible = Boolean(document.querySelector(STOP_SELECTOR));
    const finished = Boolean(lastAssistantTurn.querySelector(FINISHED_SELECTOR));
    const messageId = messageRoot.getAttribute('data-message-id') || null;
    return { text, stopVisible, finished, messageId, turnIndex: turns.length - 1, source: 'assistant-dom', pageTextContainsSentinel, sentinelMatch };
  })()`;
};

async function assistantSnapshot(cdp, sentinel, timeoutMs = 12000) {
  return withTimeout(
    evaluate(cdp, assistantSnapshotExpression(sentinel)),
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
  const hasScript = await evaluate(
    cdp,
    `Boolean(document.querySelector('${SELECTORS.cloudflareScript}'))`
  );
  return hasScript;
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
  await inputCdp("Input.insertText", { text: prompt });
  await delay(300);
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

async function waitForResponse(cdp, timeoutMs = 2700000, options = {}) {
  const sentinel = options.sentinel || null;
  const noActivate = options.noActivate === true;
  const inputCdp = options.inputCdp || null;
  const log = options.log || (() => {});
  if (noActivate) {
    await wakeBackgroundTab(inputCdp, log);
  }
  const deadline = Date.now() + timeoutMs;
  let previousText = "";
  let stableCycles = 0;
  const requiredStableCycles = Number.isInteger(options.stablePolls) && options.stablePolls > 0
    ? options.stablePolls
    : 6;
  const minStableMs = 1200;
  let lastChangeAt = Date.now();
  let lastSnapshotError = null;
  while (Date.now() < deadline) {
    let snapshot;
    try {
      snapshot = await assistantSnapshot(cdp, sentinel);
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
    const currentText = snapshot.text || "";
    const currentLength = currentText.length;
    if (currentText !== previousText) {
      previousText = currentText;
      stableCycles = 0;
      lastChangeAt = Date.now();
    } else {
      stableCycles++;
    }
    const stableMs = Date.now() - lastChangeAt;
    const hasSentinel = sentinel ? ((snapshot.text || "").includes(sentinel) || Boolean(snapshot.sentinelMatch)) : true;
    const pageHasSentinel = sentinel ? snapshot.pageTextContainsSentinel === true : false;
    // Background/hidden tabs often keep [data-testid=stop-button] in the DOM until the tab
    // is focused, even after the assistant message is complete. In --no-activate mode we
    // trust a stable assistant sentinel (or page-level sentinel) instead of stop-button absence.
    const stopGateOk = !snapshot.stopVisible
      || (noActivate && hasSentinel && (snapshot.finished || pageHasSentinel));
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
        };
      }
    }
    await delay(400);
  }
  const detail = lastSnapshotError ? `; last snapshot error: ${lastSnapshotError.message}` : "";
  throw new Error(`Response timeout${detail}`);
}

async function extractAssistantResponse(options) {
  const {
    tabId,
    sentinel,
    cdpEvaluate,
    timeout = 12000,
  } = options;
  if (!tabId) {
    throw new Error("tabId required");
  }
  const cdp = (expr) => cdpEvaluate(tabId, expr);
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
  
  const cdp = (expr) => cdpEvaluate(tabId, expr);
  const inputCdp = (method, params) => cdpCommand(tabId, method, params);
  
  try {
    await waitForPageLoad(cdp);
    log("Page loaded");
    if (await isCloudflareBlocked(cdp)) {
      throw new Error("Cloudflare challenge detected - complete in browser");
    }
    const loginStatus = await checkLoginStatus(cdp);
    if (loginStatus.status !== 200 || loginStatus.hasLoginCta) {
      throw new Error("ChatGPT login required");
    }
    log("Login verified");
    const promptReady = await waitForPromptReady(cdp);
    if (!promptReady) {
      throw new Error("Prompt textarea not ready");
    }
    log("Prompt ready");
    if (model) {
      const selectedLabel = await selectModel(cdp, model);
      log(`Selected model: ${selectedLabel}`);
    }
    let selectedReasoning = null;
    if (reasoning) {
      selectedReasoning = await selectReasoning(cdp, reasoning);
      log(`Selected reasoning: ${selectedReasoning}`);
    }
    if (file) {
      await attachFile(cdp, inputCdp, file, log);
      log(`File attached: ${file}`);
    }
    await typePrompt(cdp, inputCdp, prompt);
    log("Prompt typed");
    await clickSend(cdp, inputCdp);
    log("Prompt sent, waiting for response...");
    const response = await waitForResponse(cdp, timeout, { sentinel, stablePolls, noActivate, inputCdp, log });
    const conversationUrl = await evaluate(cdp, "window.location.href").catch(() => null);
    log(`Response received (${response.text.length} chars)`);
    return {
      response: response.text,
      model: model || "current",
      reasoning: selectedReasoning || reasoning || null,
      tabId,
      controlledTabId: tabId,
      conversationUrl,
      messageId: response.messageId,
      responseSource: response.source,
      sentinel,
      hasSentinel: response.hasSentinel,
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

module.exports = { query, extractAssistantResponse, hasRequiredCookies, CHATGPT_URL };
