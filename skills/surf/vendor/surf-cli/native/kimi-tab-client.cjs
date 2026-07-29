const KIMI_TAB_URL = "https://www.kimi.com/";
const { insertPromptText } = require("./prompt-insert.cjs");

const SELECTORS = {
  promptTextarea: 'textarea[placeholder*="Ask anything"], textarea[placeholder*="follow-up"], textarea[placeholder*="Add a follow-up"], .chat-input-editor[role="textbox"], .chat-input-editor, div[class*="editorContentEditable"], [contenteditable="true"][role="textbox"], [contenteditable="true"]',
  sendButton: '#send-button, button[id="send-button"], [class*="send-btn"], [class*="send-button"], button[aria-label*="Send"], button[aria-label*="send"], button[type="submit"]:not([disabled])',
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

function textLooksKimiProviderBusy(text) {
  const lower = String(text || "").toLowerCase();
  return (
    lower.includes("system is currently busy")
    || lower.includes("please try again later") && (
      lower.includes("system is currently busy")
      || lower.includes("temporarily busy")
      || lower.includes("high demand")
    )
  );
}

async function setPromptInComposerDom(cdp, prompt) {
  const encodedPrompt = JSON.stringify(prompt);
  return await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      const prompt = ${encodedPrompt};
      const selectors = [
        '.chat-input-editor[role="textbox"]',
        '.chat-input-editor',
        'textarea[placeholder*="Ask anything"]',
        'textarea[placeholder*="follow-up"]',
        'textarea[placeholder*="Add a follow-up"]',
        'div[class*="editorContentEditable"]',
        '[role="textbox"]',
        '[contenteditable="true"]',
      ];
      const visible = (node) => {
        if (!node) return false;
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0
          && rect.height > 0
          && style.visibility !== 'hidden'
          && style.display !== 'none';
      };
      const textOf = (node) => node.innerText || node.textContent || node.value || '';
      const promptStart = prompt.slice(0, 80);
      const promptEnd = prompt.slice(-80);
      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        for (const node of nodes) {
          if (!visible(node) || node.hasAttribute('disabled')) continue;
          dispatchClickSequence(node);
          if (typeof node.focus === 'function') node.focus();
          if (node.tagName === 'TEXTAREA' || node.tagName === 'INPUT') {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
              || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
            if (setter) setter.call(node, '');
            else node.value = '';
            node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward' }));
            if (setter) setter.call(node, prompt);
            else node.value = prompt;
            node.dispatchEvent(new InputEvent('input', { bubbles: true, data: prompt, inputType: 'insertFromPaste' }));
          } else {
            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(node);
            selection.removeAllRanges();
            selection.addRange(range);
            document.execCommand('delete', false, null);
            const inserted = document.execCommand('insertText', false, prompt);
            if (!inserted || !textOf(node).includes(promptStart) || !textOf(node).includes(promptEnd)) {
              node.textContent = prompt;
              node.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, data: prompt, inputType: 'insertFromPaste' }));
              node.dispatchEvent(new InputEvent('input', { bubbles: true, data: prompt, inputType: 'insertFromPaste' }));
            }
          }
          const text = textOf(node);
          if (text.includes(promptStart) && text.includes(promptEnd)) {
            return { ok: true, selector, length: text.length, mode: 'dom_fallback' };
          }
        }
      }
      return { ok: false };
    })()`,
  );
}

const assistantSnapshotExpression = (sentinel) => {
  const sentinelLiteral = JSON.stringify(sentinel || null);
  return `(() => {
    const SENTINEL = ${sentinelLiteral};
    const STOP_SELECTOR = '${SELECTORS.stopButton}';
    const pageText = (document.body?.innerText || document.body?.textContent || '').trim();
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
    const lowerPageText = pageText.toLowerCase();
    const lowerResponseText = text.toLowerCase();
    const promptNeedle = 'if kimi provider capacity is busy';
    const promptEchoLooksBusy = lowerResponseText.includes(promptNeedle);
    const providerBusyInPage = lowerPageText.includes('system is currently busy')
      || lowerPageText.includes('please try again later') && (
        lowerPageText.includes('system is currently busy')
        || lowerPageText.includes('temporarily busy')
        || lowerPageText.includes('high demand')
      );
    const providerBusyInResponse = !promptEchoLooksBusy && (lowerResponseText.includes('system is currently busy')
      || lowerResponseText.includes('please try again later') && (
        lowerResponseText.includes('system is currently busy')
        || lowerResponseText.includes('temporarily busy')
        || lowerResponseText.includes('high demand')
      ));
    const promptSentinelIndex = SENTINEL ? pageText.lastIndexOf(SENTINEL) : -1;
    const busyMarkerIndex = Math.max(
      lowerPageText.lastIndexOf('system is currently busy'),
      lowerPageText.lastIndexOf('temporarily busy'),
      lowerPageText.lastIndexOf('please try again later'),
      lowerPageText.lastIndexOf('high demand'),
    );
    const providerBusyAfterPrompt = promptSentinelIndex >= 0 && busyMarkerIndex > promptSentinelIndex;
    return {
      text,
      stopVisible,
      finished: !stopVisible && text.length > 0,
      providerBusy: providerBusyInResponse,
      providerBusyInPage,
      providerBusyInResponse,
      providerBusyAfterPrompt,
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
    '.chat-input-editor[role="textbox"]',
    '.chat-input-editor',
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
        return false;
      })()`
    );
    if (found) return true;
    await delay(200);
  }
  return false;
}

function normalizePreferenceLabel(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function preferenceTargets(kind, requested) {
  const normalized = normalizePreferenceLabel(requested);
  if (kind === "model" && ["instant", "kimiinstant"].includes(normalized)) {
    return ["instant"];
  }
  if (kind === "reasoning" && ["high", "reasoninghigh", "thinkhigh", "thinkinghigh"].includes(normalized)) {
    return ["reasoninghigh", "thinkinghigh", "high"];
  }
  return [normalized].filter(Boolean);
}

async function selectPreference(cdp, kind, requested, timeoutMs = 8000) {
  const targets = preferenceTargets(kind, requested);
  if (targets.length === 0) {
    return { status: "skipped", requested: requested || null };
  }
  const result = await evaluate(
    cdp,
    `(async () => {
      ${buildClickDispatcher()}
      const kind = ${JSON.stringify(kind)};
      const requested = ${JSON.stringify(requested)};
      const targets = ${JSON.stringify(targets)};
      const timeoutMs = ${timeoutMs};
      const normalize = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const compactLabel = (el) => {
        const parts = [
          el.textContent || '',
          el.getAttribute?.('aria-label') || '',
          el.getAttribute?.('title') || '',
          el.getAttribute?.('data-testid') || '',
        ].map((part) => String(part || '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
        const label = [...new Set(parts)].join(' ').trim();
        if (!label || label.length > 160) return '';
        if (/[{}]|@keyframes|#/.test(label)) return '';
        return label;
      };
      const textOf = (el) => normalize([
        compactLabel(el),
        el.getAttribute?.('aria-label') || '',
        el.getAttribute?.('title') || '',
        el.getAttribute?.('data-testid') || '',
      ].join(' '));
      const wordCount = (label) => label.split(/\\s+/).filter(Boolean).length;
      const visible = (el) => {
        if (!(el instanceof HTMLElement)) return false;
        const style = getComputedStyle(el);
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number(style.opacity || '1') > 0
          && el.getBoundingClientRect().width > 0
          && el.getBoundingClientRect().height > 0;
      };
      const hasTarget = (el) => {
        const label = compactLabel(el);
        const text = textOf(el);
        if (!label || wordCount(label) > 4) return false;
        return targets.some((target) => {
          if (target === 'high') {
            return ['high', 'reasoninghigh', 'thinkinghigh'].includes(text);
          }
          return text === target || text.includes(target);
        });
      };
      const candidateLabels = (nodes) => {
        const labels = [];
        const seen = new Set();
        for (const node of nodes) {
          const label = compactLabel(node);
          if (!label || seen.has(label)) continue;
          seen.add(label);
          labels.push(label);
          if (labels.length >= 50) break;
        }
        return labels;
      };
      const buttonLike = () => Array.from(document.querySelectorAll(
        'button,[role="button"],[aria-haspopup="listbox"],[aria-haspopup="menu"],[data-state],[class*="model"],[class*="reason"],[class*="thinking"]'
      )).filter((el) => visible(el) && compactLabel(el));
      const selectable = () => Array.from(document.querySelectorAll(
        '[role="option"],[role="menuitem"],[role="menuitemradio"],li,button,[role="button"],div,span,p'
      )).filter((el) => visible(el) && compactLabel(el));
      const textNodeParents = () => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const out = [];
        const seen = new Set();
        let node;
        while ((node = walker.nextNode())) {
          const label = String(node.nodeValue || '').replace(/\\s+/g, ' ').trim();
          if (!label || label.length > 80) continue;
          const parent = node.parentElement;
          if (!parent || seen.has(parent) || !visible(parent)) continue;
          seen.add(parent);
          out.push(parent);
        }
        return out;
      };
      const clickNodeAndParents = (node) => {
        let current = node;
        for (let depth = 0; depth < 5 && current; depth++) {
          if (current instanceof HTMLElement && visible(current)) {
            dispatchClickSequence(current);
          }
          current = current.parentElement;
        }
      };
      const hoverNodeAndParents = (node) => {
        let current = node;
        for (let depth = 0; depth < 5 && current; depth++) {
          if (current instanceof HTMLElement && visible(current)) {
            const rect = current.getBoundingClientRect();
            const clientX = rect.left + Math.max(2, Math.min(rect.width - 2, rect.width * 0.85));
            const clientY = rect.top + Math.max(2, Math.min(rect.height - 2, rect.height / 2));
            for (const type of ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointermove', 'mousemove']) {
              const common = { bubbles: true, cancelable: true, view: window, clientX, clientY };
              let event;
              if (type.startsWith('pointer') && 'PointerEvent' in window) {
                event = new PointerEvent(type, { ...common, pointerId: 1, pointerType: 'mouse' });
              } else {
                event = new MouseEvent(type, common);
              }
              current.dispatchEvent(event);
            }
          }
          current = current.parentElement;
        }
      };
      const clickFirstReasoningSubmenu = async () => {
        if (kind !== 'reasoning') return null;
        const nodes = selectable().concat(textNodeParents());
        let submenu = nodes.find((el) => {
          const text = textOf(el);
          const label = compactLabel(el);
          return label && wordCount(label) <= 6 && (
            text.includes('thinkingeffort') || text.includes('reasoningeffort')
          );
        });
        if (!submenu) {
          submenu = nodes.find((el) => {
            const text = textOf(el);
            let parent = el.parentElement;
            let parentText = '';
            for (let depth = 0; depth < 5 && parent; depth++) {
              parentText += textOf(parent);
              parent = parent.parentElement;
            }
            return text === 'standard' && (
              parentText.includes('thinkingeffort') || parentText.includes('reasoningeffort')
            );
          });
        }
        if (!submenu) return null;
        hoverNodeAndParents(submenu);
        await new Promise(r => setTimeout(r, 350));
        clickNodeAndParents(submenu);
        hoverNodeAndParents(submenu);
        await new Promise(r => setTimeout(r, 350));
        return compactLabel(submenu);
      };
      const current = buttonLike().find(hasTarget);
      if (current && !current.getAttribute('aria-expanded')) {
        return { status: 'already_selected', requested, label: compactLabel(current) };
      }
      const submenuClicks = [];
      const openers = buttonLike()
        .filter((el) => {
          const text = textOf(el);
          if (kind === 'model') return text.includes('model') || text.includes('instant') || text.includes('kimi') || text.includes('k2') || text.includes('k3');
          return text.includes('reason') || text.includes('thinking') || text.includes('standard') || text.includes('high') || text.includes('low') || text.includes('auto');
        })
        .sort((a, b) => {
          const score = (el) => {
            const text = textOf(el);
            let total = 0;
            if (hasTarget(el)) total += 100;
            if (kind === 'model' && text.includes('k3')) total += 20;
            if (kind === 'model' && text.includes('model')) total += 10;
            if (kind === 'reasoning' && (text.includes('reason') || text.includes('thinking'))) total += 20;
            return -total;
          };
          return score(a) - score(b);
        });
      const deadline = Date.now() + timeoutMs;
      for (const opener of openers.slice(0, 8)) {
        dispatchClickSequence(opener);
        await new Promise(r => setTimeout(r, 250));
        const submenuLabel = await clickFirstReasoningSubmenu();
        if (submenuLabel) submenuClicks.push(submenuLabel);
        const openerDeadline = Math.min(deadline, Date.now() + 2500);
        while (Date.now() < openerDeadline) {
          const match = selectable().concat(textNodeParents()).find(hasTarget);
          if (match) {
            clickNodeAndParents(match);
            await new Promise(r => setTimeout(r, 300));
            return { status: 'selected', requested, label: compactLabel(match) };
          }
          await new Promise(r => setTimeout(r, 100));
        }
      }
      const buttons = buttonLike();
      const choices = selectable();
      const buttonLabels = candidateLabels(buttons);
      const selectableLabels = candidateLabels(choices);
      const allLabels = candidateLabels(selectable().concat(textNodeParents()));
      const interestingLabels = allLabels.filter((label) => /thinking|reasoning|standard|high|instant|k3/i.test(label)).slice(0, 80);
      return { status: 'not_found', requested, submenuClicks, buttonLabels, selectableLabels, interestingLabels };
    })()`
  );
  if (!result || result.status === "not_found") {
    const candidates = result ? `; candidates=${JSON.stringify({
      interesting: result.interestingLabels || [],
      submenuClicks: result.submenuClicks || [],
      buttons: result.buttonLabels || [],
      selectable: result.selectableLabels || [],
    }).slice(0, 4000)}` : "";
    throw new Error(`Kimi ${kind} option not confirmed: requested ${requested}${candidates}`);
  }
  return result;
}

async function attachFile(cdp, inputCdp, filePath, log = () => {}) {
  const fs = require("fs");
  const path = require("path");
  const absolutePath = path.resolve(filePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`File not found: ${absolutePath}`);
  }

  const openedToolkit = await evaluate(
    cdp,
    `(() => {
      ${buildClickDispatcher()}
      if (document.querySelector(${JSON.stringify(SELECTORS.fileInput)})) {
        return { inputPresent: true, clicked: false };
      }
      const selectors = [
        '.toolkit-trigger-btn',
        '[class*="toolkit-trigger"]',
        '[aria-label*="Attach"]',
        '[aria-label*="Upload"]',
        '[aria-label*="Add file"]',
        '[title*="Attach"]',
        '[title*="Upload"]',
        '[title*="Add file"]',
      ];
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (node && dispatchClickSequence(node)) {
          return { inputPresent: false, clicked: true, selector };
        }
      }
      return { inputPresent: false, clicked: false };
    })()`,
  );
  if (openedToolkit?.clicked) {
    log(`Opened Kimi attachment toolkit with ${openedToolkit.selector}`);
    await delay(500);
  }

  // Wait for Kimi's file input to appear. Kimi usually mounts it with the
  // composer toolkit popover; if it is absent, the caller must not send a
  // prompt that claims an attachment exists.
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
      "Kimi file input (input[type=\"file\"]) not present in the DOM; Kimi may require opening the attachment menu first.",
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
    throw new Error("DOM.querySelector returned no nodeId for the Kimi file input");
  }
  await inputCdp("DOM.setFileInputFiles", {
    files: [absolutePath],
    nodeId: node.nodeId,
  });

  // Give Kimi a moment to process the file (it reads, hashes, sometimes
  // uploads). If the attachment is not yet visible after a brief wait we
  // surface the failure so the caller can decide to retry rather than send
  // a prompt that references a missing attachment.
  const previewDeadline = Date.now() + 20000;
  while (Date.now() < previewDeadline) {
    const previewState = await evaluate(
      cdp,
      `(() => {
        const attachmentArea = document.querySelector('.chat-editor-attachment-area');
        const errorNode = attachmentArea?.querySelector(
          '.error, [class*="error"], .error-icon, [aria-label*="error" i]',
        );
        if (errorNode) return 'error';
        const loadingNode = attachmentArea?.querySelector(
          '.loading, [class*="loading"], [aria-busy="true"]',
        );
        if (loadingNode) return 'pending';
        const readyNode = attachmentArea?.querySelector(
          'img, [class*="file-item"], [class*="attachment-item"], [class*="preview"]',
        );
        if (readyNode) return 'visible';
        return 'pending';
      })()`,
    );
    if (previewState === "error") {
      throw new Error("Kimi attachment upload failed: preview entered error state");
    }
    if (previewState === "visible") {
      log(`File attachment preview visible`);
      return {
        attached: true,
        path: absolutePath,
        name: path.basename(absolutePath),
        previewVisible: true,
      };
    }
    await delay(250);
  }
  throw new Error("Kimi attachment upload did not become ready within 20s");
}


async function verifyPromptInComposer(cdp, prompt, timeoutMs = 4000) {
  const promptStart = JSON.stringify(String(prompt || "").slice(0, 80));
  const promptEnd = JSON.stringify(String(prompt || "").slice(-80));
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const verified = await evaluate(
      cdp,
      `(() => {
        const selectors = [
          '.chat-input-editor[role="textbox"]',
          '.chat-input-editor',
          'textarea[placeholder*="Ask anything"]',
          'textarea[placeholder*="follow-up"]',
          'textarea[placeholder*="Add a follow-up"]',
          'div[class*="editorContentEditable"]',
          '[role="textbox"]',
          '[contenteditable="true"]',
        ];
        const visible = (node) => {
          if (!node) return false;
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          return rect.width > 0
            && rect.height > 0
            && style.visibility !== 'hidden'
            && style.display !== 'none';
        };
        for (const selector of selectors) {
          const nodes = Array.from(document.querySelectorAll(selector));
          for (const node of nodes) {
            if (!visible(node)) continue;
            const text = node.innerText || node.textContent || node.value || '';
            if (text.includes(${promptStart}) && text.includes(${promptEnd})) {
              return { ok: true, selector, length: text.length };
            }
          }
        }
        return { ok: false };
      })()`,
    );
    if (verified?.ok) return verified;
    await delay(100);
  }
  return { ok: false };
}

async function clearFocusedEditor(inputCdp) {
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
}

async function clickComposerCenter(inputCdp, target) {
  if (!target || !Number.isFinite(target.x) || !Number.isFinite(target.y)) return;
  await inputCdp("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: target.x,
    y: target.y,
    button: "left",
    clickCount: 1,
  });
  await inputCdp("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: target.x,
    y: target.y,
    button: "left",
    clickCount: 1,
  });
  await delay(100);
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
        '.chat-input-editor[role="textbox"]',
        '.chat-input-editor',
        'div[class*="editorContentEditable"]',
        '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]',
      ];
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node || node.hasAttribute('disabled')) continue;
        dispatchClickSequence(node);
        if (typeof node.focus === 'function') node.focus();
        const rect = node.getBoundingClientRect();
        const target = rect.width > 0 && rect.height > 0
          ? { x: rect.left + Math.min(rect.width / 2, Math.max(12, rect.width - 12)), y: rect.top + Math.min(rect.height / 2, Math.max(12, rect.height - 12)) }
          : null;
        if (node.tagName === 'TEXTAREA' || node.tagName === 'INPUT') {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
            || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          if (setter) setter.call(node, ${encodedPrompt});
          else node.value = ${encodedPrompt};
          node.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${encodedPrompt}, inputType: 'insertFromPaste' }));
          return { ok: true, mode: 'value', target };
        }
        if (node.isContentEditable || node.getAttribute('role') === 'textbox' || String(node.className || '').includes('chat-input-editor')) {
          return { ok: true, mode: 'focused_editable', target };
        }
        if (node.getAttribute('role') === 'textbox' || String(node.className || '').includes('chat-input-editor')) {
          return { ok: true, mode: 'focused_custom_textbox', target };
        }
      }
      return { ok: false };
    })()`
  );
  if (!typed?.ok) {
    throw new Error("Failed to focus/type Kimi prompt composer");
  }
  if (typed.mode === "focused_editable") {
    await clickComposerCenter(inputCdp, typed.target);
    await clearFocusedEditor(inputCdp);
    await insertPromptText(inputCdp, prompt);
    let verified = await verifyPromptInComposer(cdp, prompt);
    if (!verified?.ok) {
      verified = await setPromptInComposerDom(cdp, prompt);
    }
    if (!verified?.ok) {
      throw new Error("Kimi prompt composer did not receive inserted text");
    }
  } else if (typed.mode === "value") {
    const verified = await verifyPromptInComposer(cdp, prompt);
    if (!verified?.ok) {
      throw new Error("Kimi textarea composer did not retain inserted text");
    }
  }
  await delay(300);
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
    if (result === "clicked-global" || result === "clicked-near") {
      const accepted = await waitForSubmissionAcceptance(cdp, promptSelectors, 2500);
      if (accepted) return true;
      break;
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
    if (await waitForSubmissionAcceptance(cdp, promptSelectors, 1200)) return true;
  }
  return false;
}

async function waitForSubmissionAcceptance(cdp, promptSelectors, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const accepted = await evaluate(
      cdp,
      `(() => {
        const promptSelectors = ${promptSelectors};
        let prompt = null;
        for (const selector of promptSelectors) {
          prompt = document.querySelector(selector);
          if (prompt) break;
        }
        const promptText = (prompt?.innerText || prompt?.textContent || prompt?.value || '').trim();
        const generating = Boolean(document.querySelector('${SELECTORS.stopButton}'));
        return generating || promptText.length === 0;
      })()`,
    ).catch(() => false);
    if (accepted) return true;
    await delay(150);
  }
  return false;
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
    const hasSentinel = sentinel
      ? (((snapshot.text || "").includes(sentinel) || Boolean(snapshot.sentinelMatch)))
      : true;
    const assistantSource = snapshot.source === "assistant-dom";
    const changedFromBaseline = !baselineText || (currentText && currentText !== baselineText && !baselineText.includes(currentText));
    if (shouldAbortForProviderBusy(snapshot, baselineText, hasSentinel)) {
      throw new Error("Kimi provider capacity busy: system is currently busy; capacity is busy");
    }
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

function shouldAbortForProviderBusy(snapshot, baselineText = "", hasSentinel = false) {
  if (!snapshot || hasSentinel) return false;
  if (snapshot.providerBusyAfterPrompt === true) return true;
  if (snapshot.providerBusyInResponse !== true) return false;
  const currentText = snapshot.text || "";
  const changedFromBaseline = !baselineText || (currentText && currentText !== baselineText && !baselineText.includes(currentText));
  return Boolean(changedFromBaseline);
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
  log("Starting Kimi tab query");
  const tabInfo = await createTab();
  const { tabId } = tabInfo;
  if (!tabId) {
    throw new Error("Failed to create Kimi tab");
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
    const modelSelection = model ? await selectPreference(cdp, "model", model) : { status: "skipped" };
    if (model) log(`Kimi model selection: ${modelSelection.status} ${modelSelection.label || model}`);
    const reasoningSelection = reasoning ? await selectPreference(cdp, "reasoning", reasoning) : { status: "skipped" };
    if (reasoning) log(`Kimi reasoning selection: ${reasoningSelection.status} ${reasoningSelection.label || reasoning}`);
    const baseline = await assistantSnapshot(cdp, null).catch(() => ({ text: "" }));
    if (file) {
      attachment = await attachFile(cdp, inputCdp, file, log);
      log(`File attached: ${file}`);
    }
    await typePrompt(cdp, inputCdp, prompt);
    log("Prompt typed");
    const submitted = await clickSend(cdp, inputCdp);
    if (!submitted) {
      throw new Error("Kimi prompt submission was not accepted: composer still contains draft");
    }
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
      model: modelSelection?.label || model || "current",
      requestedModel: model || null,
      reasoning: reasoningSelection?.label || reasoning || null,
      requestedReasoning: reasoning || null,
      modelSelectionStatus: modelSelection?.status || null,
      reasoningSelectionStatus: reasoningSelection?.status || null,
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
      attachment,
    };
  } finally {
    if (!keepTab) {
      await closeTab(tabId).catch(() => {});
    }
  }
}

module.exports = { query, extractAssistantResponse, KIMI_TAB_URL, preferenceTargets, shouldAbortForProviderBusy, textLooksKimiProviderBusy };
