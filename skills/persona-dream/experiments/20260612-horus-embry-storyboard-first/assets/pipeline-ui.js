(function () {
  'use strict';

  /**
   * Promote anti-hallucination gate definition blocks from red alerts to
   * neutral info accordions. Actual failure/blocked status messages stay red.
   */
  function upgradeGateDefinitions() {
    document.querySelectorAll('.status-alert, .status').forEach((el) => {
      const t = el.textContent || '';
      const lower = t.toLowerCase();

      if (/phase gate:/i.test(t)) {
        el.classList.remove('status-alert');
        if (/\b(fail|blocked|lie_not|missing dedicated|not live|remains blocked)\b/i.test(lower)) {
          el.classList.add('phase-gate-blocked');
        } else if (/\b(warn|review|stale|quarantine|partial|reconciled)\b/i.test(lower)) {
          el.classList.add('phase-gate-warn');
        } else if (/\b(complete|pass|proven|safe to proceed|recorded)\b/i.test(lower)) {
          el.classList.add('phase-gate-pass');
        } else {
          el.classList.add('status-note');
        }
        return;
      }

      if (/anti-hallucination gate|foreground prop behavior gate/i.test(t)) {
        convertToGateDefinition(el);
        return;
      }

      if (/live kling execution is/i.test(lower) && /blocked/i.test(lower)) {
        el.classList.remove('status');
        el.classList.add('status-blocked');
      }
    });
  }

  function convertToGateDefinition(el) {
    const html = el.innerHTML;
    const match = html.match(/^(<strong>[^<]+(?:anti-hallucination gate|prop behavior gate)[^<]*<\/strong>)(?:\s*|:\s*)(.*)$/i);
    if (!match) return;

    const summaryHtml = match[1];
    const bodyHtml = match[2].trim();
    const section = el.closest('section.pipeline-phase, section.card, section');
    const failed = section ? /\bbadge-fail\b|\bbadge-bad\b|\bFAIL\b|\bBlocked\b/.test(section.innerHTML) : false;

    const details = document.createElement('details');
    details.className = 'gate-definition' + (failed ? ' is-failed' : '');
    if (failed) details.open = true;

    const summary = document.createElement('summary');
    summary.innerHTML = summaryHtml;

    const body = document.createElement('div');
    body.className = 'gate-definition-body';
    body.innerHTML = bodyHtml || '';

    details.appendChild(summary);
    details.appendChild(body);
    el.replaceWith(details);
  }

  function openPanelLedgerFromHash() {
    const hash = window.location.hash || '';
    const match = hash.match(/^#panel-interaction-ledger-(\d+)$/);
    if (!match) return;
    const details = document.getElementById(`panel-interaction-ledger-${match[1]}`);
    if (!details) return;
    details.open = true;
    details.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function openPanelContractFromHash() {
    const hash = window.location.hash || '';
    const match = hash.match(/^#errata-panel-(\d+)-interaction-contract$/);
    if (!match) return;
    const details = document.getElementById(`errata-panel-${match[1]}-interaction-contract`);
    if (!details) return;
    details.open = true;
    details.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function initPanelLedgerLinks() {
    document.querySelectorAll('.panel-ledger-link').forEach((link) => {
      link.addEventListener('click', (event) => {
        const href = link.getAttribute('href') || '';
        const match = href.match(/^#panel-interaction-ledger-(\d+)$/);
        if (!match) return;
        const details = document.getElementById(`panel-interaction-ledger-${match[1]}`);
        if (!details) return;
        event.preventDefault();
        details.open = true;
        history.pushState(null, '', href);
        details.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    });
  }

  function initPanelContractLinks() {
    document.querySelectorAll('.panel-contract-pointer a[href^="#errata-panel-"]').forEach((link) => {
      link.addEventListener('click', (event) => {
        const href = link.getAttribute('href') || '';
        const match = href.match(/^#errata-panel-(\d+)-interaction-contract$/);
        if (!match) return;
        const details = document.getElementById(`errata-panel-${match[1]}-interaction-contract`);
        if (!details) return;
        event.preventDefault();
        details.open = true;
        history.pushState(null, '', href);
        details.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    });
  }


  function showCopyBundleToast(message, kind) {
    let toast = document.getElementById('pipeline-copy-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'pipeline-copy-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = 'pipeline-copy-toast' + (kind ? ' is-' + kind : '');
    toast.hidden = false;
    clearTimeout(showCopyBundleToast._timer);
    showCopyBundleToast._timer = setTimeout(() => {
      toast.hidden = true;
    }, 2600);
  }

  async function copyContactSheetBundle(button) {
    const absPath = button.getAttribute('data-bundle-path') || '';
    const href = button.getAttribute('data-bundle-href') || '';
    if (!absPath) {
      showCopyBundleToast('Recreate bundle missing', 'error');
      return;
    }

    const endpoints = [
      'http://127.0.0.1:8893/clipboard/file',
      'http://127.0.0.1:8892/api/clipboard/file',
    ];

    button.disabled = true;
    button.classList.remove('copied', 'failed');

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: absPath, target: 'kde' }),
        });
        if (!response.ok) {
          continue;
        }
        button.classList.add('copied');
        showCopyBundleToast(button.dataset.sheetStem && button.dataset.sheetStem.startsWith('panel_') ? 'Panel recreate bundle copied to clipboard' : 'Recreate bundle copied to clipboard', 'success');
        button.disabled = false;
        return;
      } catch (_error) {
        /* try next endpoint */
      }
    }

    if (href) {
      const link = document.createElement('a');
      link.href = href;
      link.download = '';
      document.body.appendChild(link);
      link.click();
      link.remove();
      button.classList.add('failed');
      showCopyBundleToast('Clipboard bridge offline — downloaded bundle instead', 'warn');
    } else {
      button.classList.add('failed');
      showCopyBundleToast('Clipboard bridge offline', 'error');
    }
    button.disabled = false;
  }

  async function regenerateFromBundle(button) {
    const absPath = button.getAttribute('data-bundle-path') || '';
    const kind = button.getAttribute('data-regenerate-kind') || '';
    const runRoot = button.getAttribute('data-run-root') || '';
    if (!absPath || !kind) {
      showCopyBundleToast('Recreate bundle missing', 'error');
      return;
    }
    const endpoints = ['http://127.0.0.1:8893/regenerate/run'];
    button.disabled = true;
    button.classList.remove('done', 'failed');
    button.classList.add('running');
    showCopyBundleToast('Regenerating ' + (kind === 'panel' ? 'panel' : 'contact sheet') + '…', 'warn');
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind, bundle: absPath, run_root: runRoot || undefined }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
          const detail = (payload.stderr || payload.stdout || 'regenerate failed').trim();
          throw new Error(detail.slice(0, 240));
        }
        button.classList.add('done');
        showCopyBundleToast('Regeneration finished — reload report to see updates', 'success');
        button.disabled = false;
        button.classList.remove('running');
        return;
      } catch (error) {
        showCopyBundleToast(String(error.message || error), 'error');
      }
    }
    button.classList.add('failed');
    button.disabled = false;
    button.classList.remove('running');
  }

  function initContactSheetRegenerateButtons() {
    document.querySelectorAll('.contact-sheet-regenerate-bundle').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        regenerateFromBundle(button);
      });
    });
  }

  function initContactSheetCopyButtons() {
    document.querySelectorAll('.contact-sheet-copy-bundle').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        copyContactSheetBundle(button);
      });
    });
  }

  upgradeGateDefinitions();
  initPanelLedgerLinks();
  initPanelContractLinks();
  initContactSheetCopyButtons();
  initContactSheetRegenerateButtons();
  window.addEventListener('hashchange', () => {
    openPanelLedgerFromHash();
    openPanelContractFromHash();
  });
  openPanelLedgerFromHash();
  openPanelContractFromHash();
})();
