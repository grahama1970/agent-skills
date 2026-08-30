#!/usr/bin/env node
import { createJiti } from 'jiti';

const jiti = createJiti(import.meta.url, { interopDefault: true });
const shared = jiti('../../guard-pipeline-shared.ts');

function assert(condition, message, details = {}) {
  if (!condition) {
    console.error(JSON.stringify({ ok: false, message, details }, null, 2));
    process.exit(1);
  }
}

shared.beginGuardTurn('root task requiring one shared retry ledger', 'interactive');
const shame = shared.claimGuardFollowUp({ guard: 'shame', messageId: 'assistant-message-1', assistantText: 'bad status', userText: 'root task requiring one shared retry ledger', reason: 'missing_status', maxRetries: 1 });
const researchSameMessage = shared.claimGuardFollowUp({ guard: 'research-routing', messageId: 'assistant-message-1', assistantText: 'bad status', userText: 'root task requiring one shared retry ledger', reason: 'missing_memory', maxRetries: 1 });
const obviousSameRoot = shared.claimGuardFollowUp({ guard: 'obvious-next-step', messageId: 'assistant-message-2', assistantText: 'not done: run eval', userText: 'root task requiring one shared retry ledger', reason: 'obvious_next_step', maxRetries: 1 });
const statusAfterFirstRoot = shared.guardPipelineStatus();

shared.beginGuardTurn('new root task allows a new shared retry', 'interactive');
const ralphNewRoot = shared.claimGuardFollowUp({ guard: 'ralph-wiggum', messageId: 'assistant-message-3', assistantText: 'done', userText: 'new root task allows a new shared retry', reason: 'self_verify', maxRetries: 2 });
const statusAfterSecondRoot = shared.guardPipelineStatus();

assert(shame.ok === true && shame.used === 1, 'first guard did not claim root retry', { shame });
assert(researchSameMessage.ok === false && researchSameMessage.reason === 'message_already_claimed', 'second guard on same message was not suppressed', { researchSameMessage });
assert(obviousSameRoot.ok === false && obviousSameRoot.reason === 'retry_budget_exhausted', 'second guard on same root bypassed retry budget', { obviousSameRoot, statusAfterFirstRoot });
assert(ralphNewRoot.ok === true && ralphNewRoot.used === 1, 'new root did not reset shared retry budget for Ralph', { ralphNewRoot, statusAfterSecondRoot });

console.log(JSON.stringify({
  ok: true,
  mode: 'guard-pipeline-shared-ledger',
  first_claim: shame.reason,
  same_message_suppression: researchSameMessage.reason,
  same_root_budget: obviousSameRoot.reason,
  new_root_claim: ralphNewRoot.reason,
  order: statusAfterSecondRoot.order,
}));
