const { insertPromptText } = require("./prompt-insert.cjs");
const GEMINI_TAB_URL = "https://gemini.google.com/";

const SELECTORS = {
  promptTextarea: 'rich-textarea textarea, rich-textarea div[contenteditable="true"], div[contenteditable="true"][aria-label*="Enter a prompt"], div[contenteditable="true"][data-placeholder*="Enter"], textarea[aria-label*="Enter a prompt"], textarea[placeholder*="Enter a prompt"]',
  sendButton: 'button[aria-label*="Send message"], button[aria-label*="Send"], button[mattooltip*="Send message"], button[mattooltip*="Send"], button.send-button.submit, button.send-button, button[data-test-id="send-button"], button[aria-label*="Submit"], button.submit:not([disabled])',
  stopButton: 'button[aria-label*="Stop response"], button[mattooltip*="Stop"], button[aria-label*="Stop"]',
  assistantMessage: 'message-content, .model-response-text, div[data-message-author="model"], div.markdown',
  conversationTurn: 'model-response, message-content, .conversation-container message-content',
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
    const ASSISTANT_SELECTOR = '${SELECTORS.assistantMessage}';
    const pageText = (document.body?.innerText || document.body?.textContent || '').trim();
    const findSentinel = (text) => {
      if (!SENTINEL || !text) return null;
      const variants = [SENTINEL, ...(SENTINEL.endsWith('>>>') ? [SENTINEL.slice(0, -1)] : [])];
      return variants.find((marker) => text.includes(marker)) || null;
    };
    const stopVisible = Boolean(document.querySelector(STOP_SELECTOR));
    const isUserNode = (node) => {
      if (!(node instanceof HTMLElement)) return true;
      if (node.closest([
        '[data-message-author-role="user"]',
        '[data-testid*="user"]',
        '[class*="user-message"]',
        '[class*="UserMessage"]',
        'user-query-content',
        '.user-query-container',
        '.query-content',
        '[id^="user-query-content-"]',
      ].join(', '))) return true;
      return false;
    };
    const nodes = Array.from(document.querySelectorAll(ASSISTANT_SELECTOR))
      .filter((node) => node instanceof HTMLElement && !isUserNode(node));
    let text = '';
    let source = 'page-text';
    if (nodes.length) {
      const candidates = nodes.map((node) => ({
        node,
        text: (node.innerText || node.textContent || '').trim(),
      })).filter((candidate) => candidate.text.length > 0);
      const selected = SENTINEL
        ? [...candidates].reverse().find((candidate) => candidate.text.includes(SENTINEL))
        : candidates[candidates.length - 1];
      if (selected) {
        text = selected.text;
        source = 'assistant-dom';
      }
    }
    if (!text) {
      const marker = 'Gemini said';
      const idx = pageText.lastIndexOf(marker);
      if (idx >= 0) {
        text = pageText.slice(idx + marker.length).trim();
        source = 'page-text-gemini-said';
      }
    }
    if (
      SENTINEL
      && source !== 'assistant-dom'
      && (
        text.includes('You said')
        || text.includes('Completion contract for browser automation:')
        || text.includes('At the very end of your final answer, print exactly:')
      )
    ) {
      text = '';
      source = 'page-text-contaminated';
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
      source,
      pageTextContainsSentinel,
      sentinelMatch,
    };
  })()`;
};

async function assistantSnapshot(cdp, sentinel, timeoutMs = 12000) {
  return withTimeout(
    evaluate(cdp, assistantSnapshotExpression(sentinel)),
    timeoutMs,
    "Gemini assistant DOM snapshot",
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

async function waitForPromptReady(cdp, timeoutMs = 45000) {
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

async function attachFile(cdp, inputCdp, filePath, log = () => {}) {
  const fs = require("fs");
  const path = require("path");
  const absolutePath = path.resolve(filePath);
  const name = path.basename(absolutePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`File not found: ${absolutePath}`);
  }

  // Wait for a file input to appear. Gemini lazily mounts the hidden
  // <input type="file"> when the composer attach button is interactable;
  // recent revs mount it unconditionally, but we poll defensively.
  const selectorJson = JSON.stringify(SELECTORS.fileInput);
  await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const uploadButton = Array.from(document.querySelectorAll('button, [role="button"]'))
        .find((el) => /upload|attach|add/i.test([
          el.getAttribute('aria-label') || '',
          el.getAttribute('title') || '',
          el.textContent || '',
        ].join(' ')));
      if (uploadButton) dispatchClickSequence(uploadButton);
      return Boolean(uploadButton);
    })()`,
  ).catch(() => false);
  const deadline = Date.now() + 10000;
  let found = false;
  let menuClicked = false;
  while (Date.now() < deadline) {
    const probe = await evaluate(
      cdp,
      `(() => {
        ${buildClickDispatcher()}
        if (document.querySelector(${selectorJson})) return true;
        if (!${JSON.stringify(menuClicked)}) {
          const item = Array.from(document.querySelectorAll([
            'button',
            '[role="menuitem"]',
            '[role="option"]',
            '.mat-mdc-menu-item',
            '.mat-mdc-option',
          ].join(', '))).find((el) => /upload|file|files|device/i.test([
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || '',
            el.textContent || '',
          ].join(' ')));
          if (item) {
            dispatchClickSequence(item);
            return 'menu-clicked';
          }
        }
        return false;
      })()`,
    );
    if (probe === true) {
      found = true;
      break;
    }
    if (probe === "menu-clicked") {
      menuClicked = true;
    }
    await delay(150);
  }
  if (!found) {
    throw new Error(
      "Gemini file input (input[type=\"file\"]) not present in the DOM; Gemini may have moved or hidden the attach control.",
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
    throw new Error("DOM.querySelector returned no nodeId for the Gemini file input");
  }
  await inputCdp("DOM.setFileInputFiles", {
    files: [absolutePath],
    nodeId: node.nodeId,
  });

  // Give Gemini a moment to process the file (it reads, hashes, sometimes
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
      return { attached: true, path: absolutePath, name, previewVisible: true };
    }
    await delay(250);
  }
  // No preview shown, but the input file was set. Proceed and report the
  // weaker metadata; gemini-submit.sh fails closed for attachment lanes unless
  // it can read back a visible attachment preview.
  log(`File attachment set (no preview detected within 20s; proceeding)`);
  return { attached: true, path: absolutePath, name, previewVisible: false };
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
  await insertPromptText(inputCdp, prompt);
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
  const promptSelectors = JSON.stringify(SELECTORS.promptTextarea.split(", ").map((s) => s.trim()));
  const sendSelectors = JSON.stringify(
    SELECTORS.sendButton.split(", ").map((s) => s.trim()).concat([
      'button[aria-label*="Send"]',
      'button[aria-label*="send"]',
      'button[data-test-id="send-button"]',
    ]),
  );
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    const result = await evaluate(
      cdp,
      `(() => {
        ${buildClickDispatcher()}
        const promptSelectors = ${promptSelectors};
        const sendSelectors = ${sendSelectors};
        let prompt = null;
        for (const selector of promptSelectors) {
          prompt = document.querySelector(selector);
          if (prompt) break;
        }
        const tryButton = (button) => {
          if (!button) return null;
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
          if (status === 'clicked') return 'clicked-global';
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
                if (status === 'clicked') return 'clicked-near';
                if (status === 'disabled') return 'disabled';
              }
            }
            node = node.parentElement;
          }
        }
        return 'missing';
      })()`
    );
    if (result === "clicked-global" || result === "clicked-near") return true;
    if (result === "disabled") {
      await delay(150);
      continue;
    }
    if (result === "missing") break;
    await delay(100);
  }

  await pressEnter(inputCdp);
  return true;
}

async function pressEnter(inputCdp) {
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
}

async function waitForSubmitAccepted(cdp, prompt, baselineUrl, timeoutMs = 10000) {
  const promptStart = JSON.stringify(prompt.slice(0, Math.min(prompt.length, 160)));
  const promptEnd = JSON.stringify(prompt.slice(Math.max(0, prompt.length - 160)));
  const expectedBaselineUrl = JSON.stringify(baselineUrl || "");
  const promptSelectors = JSON.stringify(SELECTORS.promptTextarea.split(", ").map((item) => item.trim()));
  const deadline = Date.now() + timeoutMs;
  let lastState = null;
  while (Date.now() < deadline) {
    lastState = await evaluate(
      cdp,
      `(() => {
        const promptStart = ${promptStart};
        const promptEnd = ${promptEnd};
        const baselineUrl = ${expectedBaselineUrl};
        const promptSelectors = ${promptSelectors};
        let composer = null;
        for (const selector of promptSelectors) {
          composer = document.querySelector(selector);
          if (composer) break;
        }
        const composerText = composer ? (composer.innerText || composer.value || composer.textContent || '') : '';
        const userTurns = Array.from(document.querySelectorAll([
          '[data-message-author-role="user"]',
          '[data-testid*="user"]',
          '[class*="user-message"]',
          '[class*="UserMessage"]',
          'user-query-content',
          '.user-query-container',
          '.query-content',
          '[id^="user-query-content-"]',
        ].join(', ')));
        const lastUser = userTurns.length ? userTurns[userTurns.length - 1] : null;
        const lastUserText = lastUser ? (lastUser.innerText || lastUser.textContent || '') : '';
        return {
          stopVisible: Boolean(document.querySelector('${SELECTORS.stopButton}')),
          composerChars: composerText.length,
          composerStillContainsPrompt: Boolean(
            composerText && composerText.includes(promptStart) && composerText.includes(promptEnd)
          ),
          lastUserContainsPrompt: Boolean(
            lastUserText && lastUserText.includes(promptStart) && lastUserText.includes(promptEnd)
          ),
          currentUrl: location.href,
          urlChanged: Boolean(baselineUrl && location.href !== baselineUrl),
        };
      })()`,
    );
    if (
      lastState?.stopVisible
      || lastState?.lastUserContainsPrompt
      || (lastState?.urlChanged && lastState?.composerChars === 0)
    ) {
      return { accepted: true, ...lastState };
    }
    await delay(200);
  }
  const error = new Error("Gemini did not accept submitted prompt: prompt remained in the composer after send");
  error.geminiSubmitState = lastState || null;
  throw error;
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
    if (snapshot.stopVisible) {
      sawGenerating = true;
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
    const hasSentinel = sentinel ? (snapshot.text || "").includes(sentinel) : true;
    const assistantSource = snapshot.source === "assistant-dom" || snapshot.source === "page-text-gemini-said";
    const changedFromBaseline = !baselineText
      || (currentText && currentText !== baselineText && !baselineText.includes(currentText));
    const sentinelFresh = Boolean(
      sentinel && hasSentinel && baselineText && !baselineText.includes(sentinel),
    );
    const stableEnough = stableCycles >= requiredStableCycles && stableMs >= minStableMs;
    const grewAfterBaseline = baselineText
      ? (currentLength > (baselineText.length + 5))
      : currentLength > 0;
    const stableResponseWithoutSentinel = Boolean(
      sentinel
      && !hasSentinel
      && options.submissionAccepted === true
      && stableEnough
      && stableMs >= 5000
      && assistantSource
      && changedFromBaseline
      && grewAfterBaseline
      && !snapshot.stopVisible
    );
    if (hasSentinel || stableResponseWithoutSentinel) {
      const finishedVisible = snapshot.finished;
      const responseComplete = sentinel
        ? (
          stableResponseWithoutSentinel
          || (
            stableEnough
            && assistantSource
            && (
              sentinelFresh
              || (changedFromBaseline && sawGenerating && grewAfterBaseline)
            )
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
          stableResponseWithoutSentinel,
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
  log("Starting Gemini tab query");
  const tabInfo = await createTab();
  const { tabId } = tabInfo;
  if (!tabId) {
    throw new Error("Failed to create Gemini tab");
  }
  log(`Created tab ${tabId}`);
  
  const cdp = (expr) => cdpEvaluate(tabId, expr);
  const inputCdp = (method, params) => cdpCommand(tabId, method, params);
  let attachment = null;
  
  try {
    await waitForPageLoad(cdp);
    log("Page loaded");
    const promptReady = await waitForPromptReady(cdp);
    if (!promptReady) {
      throw new Error("Prompt textarea not ready");
    }
    log("Prompt ready");
    const baseline = await assistantSnapshot(cdp, null).catch(() => ({ text: "" }));
    if (file) {
      attachment = await attachFile(cdp, inputCdp, file, log);
      log(`File attached: ${file}`);
    }
    const baselineUrl = await evaluate(cdp, "window.location.href").catch(() => "");
    const attachment = file ? await attachFile(cdp, inputCdp, file, log) : null;
    if (attachment?.attached) {
      log(`Attached file ${attachment.name}`);
    }
    await typePrompt(cdp, inputCdp, prompt);
    log("Prompt typed");
    await clickSend(cdp, inputCdp);
    let submitState;
    try {
      submitState = await waitForSubmitAccepted(cdp, prompt, baselineUrl, 6000);
    } catch (error) {
      log(`Send click was not accepted; pressing Enter on the controlled tab: ${error.message}`);
      await pressEnter(inputCdp);
      submitState = await waitForSubmitAccepted(cdp, prompt, baselineUrl, 10000);
    }
    log(`Prompt accepted: stopVisible=${submitState.stopVisible} composerChars=${submitState.composerChars}`);
    log("Prompt sent, waiting for response...");
    const genDeadline = Date.now() + 20000;
    while (Date.now() < genDeadline) {
      const snap = await assistantSnapshot(cdp, null).catch(() => null);
      if (snap?.stopVisible) break;
      await delay(250);
    }
    const response = await waitForResponse(cdp, timeout, {
      sentinel,
      stablePolls,
      baselineText: baseline?.text || "",
      submissionAccepted: submitState?.accepted === true,
    });
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
      stableResponseWithoutSentinel: response.stableResponseWithoutSentinel === true,
      tookMs: Date.now() - startTime,
      activated: tabInfo.activated === true,
      tabWasCreated: tabInfo.tabWasCreated === true,
      noActivate: noActivate === true,
      attachment,
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
  assistantSnapshotExpression,
  GEMINI_TAB_URL,
};
