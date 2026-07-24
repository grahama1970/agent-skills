const KIMI_TAB_URL = "https://www.kimi.com/";

const SELECTORS = {
  promptTextarea: 'textarea[placeholder*="Ask anything"], textarea[placeholder*="follow-up"], textarea[placeholder*="Add a follow-up"], div[class*="editorContentEditable"], [contenteditable="true"][role="textbox"], [contenteditable="true"]',
  sendButton: '#send-button, button[id="send-button"], [class*="send-btn"], button[aria-label*="Send"], button[aria-label*="send"], button[type="submit"]:not([disabled])',
  stopButton: 'button[aria-label*="Stop"], button[aria-label*="Cancel"], button[aria-label*="stop"], button[aria-label*="Stop generation"]',
  assistantMessage: '[class*="markdown"], [class*="Markdown"], .markdown-body, .prose, [data-role="assistant"], article, [class*="assistant"]',
  conversationTurn: '[class*="message"], [class*="Message"], article',
  fileInput: 'input[type="file"]',
};

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
    const STOP_SELECTOR = '${SELECTORS.stopButton}';
    const pageText = (document.body?.innerText || document.body?.textContent || '').trim();
    const lowerPageText = pageText.toLowerCase();
    const providerBusy = (
      lowerPageText.includes('system is currently busy')
      || lowerPageText.includes('capacity is busy')
      || lowerPageText.includes('please try again later')
    );
    const findSentinel = (text) => {
      if (!SENTINEL || !text) return null;
      const variants = [SENTINEL, ...(SENTINEL.endsWith('>>>') ? [SENTINEL.slice(0, -1)] : [])];
      return variants.find((marker) => text.includes(marker)) || null;
    };
    const nodeText = (node) => {
      if (!(node instanceof HTMLElement)) return '';
      const contentRoot = node.matches('[class*="markdown"], .markdown-body, .prose')
        ? node
        : (node.querySelector('[class*="markdown"], .markdown-body, .prose') || node);
      return (contentRoot.innerText || contentRoot.textContent || '').trim();
    };
    const isExcluded = (node) => {
      if (!(node instanceof HTMLElement)) return true;
      if (node.closest('iframe')) return true;
      if (node.closest('.toolcall-content-text')) return true;
      const html = node.innerHTML || '';
      if (html.includes('<!DOCTYPE') || html.includes('<html') || html.includes('<script')) return true;
      const txt = nodeText(node);
      if (!txt) return true;
      if (txt.length > 20000) return true;
      return false;
    };
    const isThinkingNode = (node) => {
      if (!(node instanceof HTMLElement)) return true;
      const cls = (node.className && node.className.toString()) || '';
      if (/toolcall-content-text|think|reason|analysis|chain-of-thought|segment-assistant-actions/i.test(cls)) return true;
      const sample = nodeText(node).slice(0, 240);
      if (!sample) return true;
      if (/^The user wants me to/i.test(sample)) return true;
      if (/^Reply with only/i.test(sample)) return true;
      if (/^So the output should be:/i.test(sample)) return true;
      return false;
    };
    const candidateSelectors = [
      '.message-content .markdown',
      '.markdown-container:not(.toolcall-content-text)',
      '.markdown-container .markdown',
      '[class*="markdown"]',
      '[class*="Markdown"]',
      '.markdown-body',
      '.prose',
      '[data-role="assistant"]',
      '[data-message-role="assistant"]',
      '[class*="assistant-message"]',
      '[class*="bot-message"]',
    ];
    const seen = new Set();
    let nodes = [];
    for (const selector of candidateSelectors) {
      for (const node of Array.from(document.querySelectorAll(selector))) {
        if (!(node instanceof HTMLElement) || seen.has(node)) continue;
        seen.add(node);
        nodes.push(node);
      }
    }
    nodes = nodes.filter((node) => !isExcluded(node) && !isThinkingNode(node));
    const hasTerminalSentinel = (text) => {
      if (!SENTINEL || !text) return false;
      const idx = text.lastIndexOf(SENTINEL);
      if (idx < 0) return Boolean(findSentinel(text));
      return text.slice(idx + SENTINEL.length).trim().length === 0;
    };
    let last = null;
    if (SENTINEL) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const txt = nodeText(nodes[i]);
        if (hasTerminalSentinel(txt)) {
          last = nodes[i];
          break;
        }
      }
    }
    if (!last) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const txt = nodeText(nodes[i]);
        if (txt) {
          last = nodes[i];
          break;
        }
      }
    }
    const stopVisible = Boolean(document.querySelector(STOP_SELECTOR))
      || Boolean(document.querySelector('[class*="loading"]'))
      || Boolean(document.querySelector('[class*="typing"]'))
      || Boolean(document.querySelector('[aria-busy="true"]'));
    const lowerPageText = pageText.toLowerCase();
    const providerBusy = lowerPageText.includes('system is currently busy')
      || lowerPageText.includes('capacity is busy')
      || lowerPageText.includes('temporarily busy')
      || lowerPageText.includes('please try again later');
    let text = '';
    let source = 'page-text';
    if (last) {
      text = nodeText(last);
      source = 'assistant-dom';
    }
    const sentinelMatch = findSentinel(text);
    if (SENTINEL && sentinelMatch && sentinelMatch !== SENTINEL) {
      const idx = text.lastIndexOf(sentinelMatch);
      if (idx >= 0) {
        text = text.slice(0, idx) + SENTINEL + text.slice(idx + sentinelMatch.length);
      }
    }
    const pageTextContainsSentinel = Boolean(findSentinel(pageText));
    return {
      text,
      stopVisible,
      finished: !stopVisible && text.length > 0,
      providerBusy,
      source,
      pageTextContainsSentinel,
      sentinelMatch,
      providerBusy,
    };
  })()`;
};

async function assistantSnapshot(cdp, sentinel, timeoutMs = 12000) {
  return withTimeout(
    evaluate(cdp, assistantSnapshotExpression(sentinel)),
    timeoutMs,
    "Kimi assistant DOM snapshot",
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
    `Boolean(document.querySelector('${'script[src*="/challenge-platform/"]'}'))`
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

async function waitForPromptReady(cdp, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  const selectors = [
    'textarea[placeholder*="Ask anything"]',
    'textarea[placeholder*="follow-up"]',
    'div[class*="editorContentEditable"]',
    '[contenteditable="true"][role="textbox"]',
    '[contenteditable="true"]',
  ];
  while (Date.now() < deadline) {
    const found = await evaluate(
      cdp,
      `(() => {
        const selectors = ${JSON.stringify(selectors)};
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          if (node && !node.hasAttribute('disabled')) return true;
        }
        const body = (document.body?.innerText || '').toLowerCase();
        return body.includes('ask anything') || body.includes('follow-up');
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
  const encodedPrompt = JSON.stringify(prompt);
  const typed = await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const selectors = [
        'textarea[placeholder*="Ask anything"]',
        'textarea[placeholder*="follow-up"]',
        'textarea[placeholder*="Add a follow-up"]',
        'div[class*="editorContentEditable"]',
        '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]',
      ];
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node || node.hasAttribute('disabled')) continue;
        dispatchClickSequence(node);
        if (typeof node.focus === 'function') node.focus();
        if (node.tagName === 'TEXTAREA' || node.tagName === 'INPUT') {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
            || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          if (setter) setter.call(node, ${encodedPrompt});
          else node.value = ${encodedPrompt};
          node.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
          return { ok: true, mode: 'value' };
        }
        if (node.isContentEditable) {
          try {
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, ${encodedPrompt});
          } catch (e) {
            node.textContent = ${encodedPrompt};
          }
          node.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertText' }));
          return { ok: true, mode: 'contenteditable' };
        }
      }
      return { ok: false };
    })()`
  );
  if (!typed?.ok) {
    throw new Error("Failed to focus/type Kimi prompt composer");
  }
  await delay(300);
}

async function clickSend(cdp, inputCdp, prompt = "") {
  const promptNeedle = JSON.stringify((prompt || "").trim().slice(0, 120));
  const promptSelectors = JSON.stringify(SELECTORS.promptTextarea.split(", ").map((s) => s.trim()));
  const sendSelectors = JSON.stringify(
    [
      '.chat-input .send-button-container',
      '.chat-input [class*="send-button"]',
      ...SELECTORS.sendButton.split(", ").map((s) => s.trim()),
      'button[aria-label*="Send"]',
      'button[aria-label*="send"]',
      'button[data-test-id="send-button"]',
    ],
  );
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const result = await evaluate(
      cdp,
      `(() => {
        ${buildClickDispatcher()}
        const promptSelectors = ${promptSelectors};
        const sendSelectors = ${sendSelectors};
        const promptNeedle = ${promptNeedle};
        let prompt = null;
        for (const selector of promptSelectors) {
          prompt = document.querySelector(selector);
          if (prompt) break;
        }
        const composerText = () => {
          const composer = document.querySelector('.chat-input') || prompt;
          return (composer?.innerText || composer?.textContent || composer?.value || '').trim();
        };
        const submitted = () => {
          if (document.querySelector('${SELECTORS.stopButton}')) return true;
          if (!promptNeedle) return false;
          return !composerText().includes(promptNeedle);
        };
        const tryButton = (button) => {
          if (!button) return null;
          const rect = button.getBoundingClientRect();
          const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0
            && rect.top < window.innerHeight && rect.left < window.innerWidth;
          if (!visible) return null;
          const disabled = button.hasAttribute('disabled')
            || button.getAttribute('aria-disabled') === 'true'
            || button.getAttribute('data-disabled') === 'true';
          if (disabled) return 'disabled';
          dispatchClickSequence(button);
          return 'clicked';
        };
        for (const selector of sendSelectors) {
          const button = document.querySelector(selector);
          const status = tryButton(button);
          if (status === 'clicked') return submitted() ? 'submitted-global' : 'clicked-global';
          if (status === 'disabled') return 'disabled';
        }
        if (prompt) {
          let node = prompt;
          for (let depth = 0; depth < 10 && node; depth++) {
            const buttons = node.querySelectorAll ? Array.from(node.querySelectorAll('button')) : [];
            for (const button of buttons) {
              const aria = (button.getAttribute('aria-label') || '').toLowerCase();
              const label = (button.textContent || '').trim().toLowerCase();
              if (aria.includes('send') || label === 'send') {
                const status = tryButton(button);
                if (status === 'clicked') return submitted() ? 'submitted-near' : 'clicked-near';
                if (status === 'disabled') return 'disabled';
              }
            }
            node = node.parentElement;
          }
        }
        return 'missing';
      })()`
    );
    if (result === "submitted-global" || result === "submitted-near") return true;
    if (result === "clicked-global" || result === "clicked-near") {
      await delay(500);
      const submitted = await evaluate(
        cdp,
        `(() => {
          const needle = ${promptNeedle};
          if (document.querySelector('${SELECTORS.stopButton}')) return true;
          if (!needle) return false;
          const composer = document.querySelector('.chat-input')
            || document.querySelector(${JSON.stringify(SELECTORS.promptTextarea)});
          const text = (composer?.innerText || composer?.textContent || composer?.value || '').trim();
          return !text.includes(needle);
        })()`,
      ).catch(() => false);
      if (submitted) return true;
      continue;
    }
    if (result === "disabled") {
      await delay(150);
      continue;
    }
    if (result === "missing") break;
    await delay(100);
  }

  for (const modifiers of [2, 4, 8, 0]) {
    await inputCdp("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "Enter",
      code: "Enter",
      windowsVirtualKeyCode: 13,
      nativeVirtualKeyCode: 13,
      modifiers,
      text: modifiers ? undefined : "\r",
    });
    await inputCdp("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "Enter",
      code: "Enter",
      windowsVirtualKeyCode: 13,
      nativeVirtualKeyCode: 13,
      modifiers,
    });
    await delay(250);
    const generating = await evaluate(
      cdp,
      `(() => {
        const needle = ${promptNeedle};
        if (document.querySelector('${SELECTORS.stopButton}')) return true;
        if (!needle) return false;
        const composer = document.querySelector('.chat-input')
          || document.querySelector(${JSON.stringify(SELECTORS.promptTextarea)});
        const text = (composer?.innerText || composer?.textContent || composer?.value || '').trim();
        return !text.includes(needle);
      })()`,
    ).catch(() => false);
    if (generating) return true;
  }
  return true;
}

async function waitForResponse(cdp, timeoutMs = 2700000, options = {}) {
  const baselineText = options.baselineText || "";
  const sentinel = options.sentinel || null;
  const deadline = Date.now() + timeoutMs;
  let previousText = "";
  let stableCycles = 0;
  const requiredStableCycles = Number.isInteger(options.stablePolls) && options.stablePolls > 0
    ? options.stablePolls
    : 6;
  const minStableMs = 1200;
  let lastChangeAt = Date.now();
  let lastSnapshotError = null;
  let sawGenerating = false;
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
    if (snapshot.providerBusy) {
      throw new Error("Kimi provider capacity busy: system is currently busy; capacity is busy");
    }
    if (snapshot.stopVisible) {
      sawGenerating = true;
    }
    if (snapshot.providerBusy) {
      throw new Error("Kimi provider capacity busy: System is currently busy / Capacity is busy. Please try again later.");
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
    const hasSentinel = sentinel
      ? (((snapshot.text || "").includes(sentinel) || Boolean(snapshot.sentinelMatch)))
      : true;
    const assistantSource = snapshot.source === "assistant-dom";
    const changedFromBaseline = !baselineText || (currentText && currentText !== baselineText && !baselineText.includes(currentText));
    if (hasSentinel) {
      const stableEnough = stableCycles >= requiredStableCycles && stableMs >= minStableMs;
      const finishedVisible = snapshot.finished;
      const grewAfterBaseline = baselineText
        ? (currentLength > (baselineText.length + 5))
        : currentLength > 0;
      const sentinelFresh = Boolean(
        sentinel && hasSentinel && baselineText && !baselineText.includes(sentinel),
      );
      const responseComplete = sentinel
        ? (
          stableEnough
          && assistantSource
          && (
            sentinelFresh
            || (changedFromBaseline && (sawGenerating || grewAfterBaseline))
          )
        )
        : ((!snapshot.stopVisible || finishedVisible) && stableEnough);
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
  log("Starting Kimi tab query");
  const tabInfo = await createTab();
  const { tabId } = tabInfo;
  if (!tabId) {
    throw new Error("Failed to create Kimi tab");
  }
  log(`Created tab ${tabId}`);
  
  const cdp = (expr) => cdpEvaluate(tabId, expr);
  const inputCdp = (method, params) => cdpCommand(tabId, method, params);
  
  try {
    await waitForPageLoad(cdp);
    log("Page loaded");
    const promptReady = await waitForPromptReady(cdp);
    if (!promptReady) {
      throw new Error("Prompt textarea not ready");
    }
    log("Prompt ready");
    const baseline = await assistantSnapshot(cdp, null).catch(() => ({ text: "" }));
    await typePrompt(cdp, inputCdp, prompt);
    log("Prompt typed");
    await clickSend(cdp, inputCdp, prompt);
    log("Prompt sent, waiting for response...");
    const genDeadline = Date.now() + 20000;
    while (Date.now() < genDeadline) {
      const snap = await assistantSnapshot(cdp, null).catch(() => null);
      if (snap?.stopVisible) break;
      await delay(250);
    }
    const response = await waitForResponse(cdp, timeout, { sentinel, stablePolls, baselineText: baseline?.text || "" });
    const conversationUrl = await evaluate(cdp, "window.location.href").catch(() => null);
    log(`Response received (${response.text.length} chars)`);
    return {
      response: response.text,
      model: model || "current",
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

module.exports = { query, extractAssistantResponse, KIMI_TAB_URL };
