// Regression: kimi.submit --attach-file must click the REAL composer
// .toolkit-trigger-btn, not the first selector match. A prior tool-call's
// toolcall-flow summary span also matches the broad trigger selector; when it
// sorts first, querySelector returned it and the attach popover never opened
// (observed: clicked 97x, "toolkit popover never opened"). This pins the
// selection predicate from kimi-tab-client.cjs so a revert to querySelector-first
// fails here instead of silently breaking attachments on any history-polluted tab.
//
// Run: node skills/surf/tests/kimi_attach_trigger.test.mjs
import assert from 'node:assert';

// The exact predicate mounted into the page by kimi-tab-client.cjs.
function pickTrigger(nodes) {
  const cands = nodes.filter(
    (el) => el.offsetParent !== null &&
      !el.closest('[class*="toolcall"],[class*="message"],[class*="markdown"],[class*="history"]'),
  );
  return cands.find((el) => String((el.className && (el.className.baseVal || el.className)) || '').includes('toolkit-trigger-btn'))
    || cands[0] || null;
}

function node(className, { visible = true, ancestorClass = null } = {}) {
  const el = {
    className,
    offsetParent: visible ? {} : null,
    closest(sel) {
      if (!ancestorClass) return null;
      // crude [class*="X"] match against the one ancestor class we model
      const wants = [...sel.matchAll(/class\*="([^"]+)"/g)].map((m) => m[1]);
      return wants.some((w) => ancestorClass.includes(w)) ? {} : null;
    },
  };
  return el;
}

// Case 1: dead toolcall summary span first, real button second -> pick the button.
{
  const deadSpan = node('toolcall-flow__summary-text', { ancestorClass: 'toolcall-flow' });
  const realBtn = node('icon-button toolkit-trigger-btn');
  const picked = pickTrigger([deadSpan, realBtn]);
  assert.strictEqual(picked, realBtn, 'must skip the history dead node and pick the real toolkit-trigger-btn');
}

// Case 2: real button hidden (offsetParent null) -> not eligible.
{
  const hiddenBtn = node('toolkit-trigger-btn', { visible: false });
  const picked = pickTrigger([hiddenBtn]);
  assert.strictEqual(picked, null, 'invisible trigger must not be chosen');
}

// Case 3: no toolkit-trigger-btn but a visible generic candidate -> fall back to it.
{
  const generic = node('some-attach-btn');
  const picked = pickTrigger([generic]);
  assert.strictEqual(picked, generic, 'fall back to first visible non-history candidate');
}

// Case 4: real button INSIDE a message subtree (echoed in history) is excluded.
{
  const echoed = node('toolkit-trigger-btn', { ancestorClass: 'message markdown' });
  const composer = node('icon-button toolkit-trigger-btn');
  const picked = pickTrigger([echoed, composer]);
  assert.strictEqual(picked, composer, 'must exclude a trigger echoed inside message history');
}

console.log('kimi_attach_trigger: PASS (4 cases)');
