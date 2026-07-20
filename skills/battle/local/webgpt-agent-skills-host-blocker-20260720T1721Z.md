# WebGPT Blocker: Agent-Skills Battle Receipt Review

**Timestamp**: 2026-07-20T17:21Z  
**Scope**: WebGPT UX acceptance for the agent-skills-hosted Battle receipt at
`http://127.0.0.1:3003/#battle/receipt?engine=pixi`.

## Proven Local State

- `curl http://127.0.0.1:3003/__host.json` returned:
  `host: agent-skills battle spectator`,
  `entry: skills/battle/spectator/src/main.tsx`.
- Fresh backend receipt:
  `skills/battle/local/adaptive-lineage-relive-20260720T144034Z/adaptive-lineage-qualification.json`
  reports `status: PASS`, `run_id: arena-adaptive-lineage-20260720T144034Z`,
  `battle_id: battle-004`, 4 primary SciLLM calls, 4 HTTP completions,
  4 red specimens, no budget overrun, and G2 Judge completion.
- Live-browser render proof:
  `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-assertions.json`
  reports `mocked:false`, `live:true`, screenshot bytes `254726`, and required
  text for `ADAPTIVE LINEAGE`, `LIVE: Qual PASS`, all four exploit names, and
  `G1-A Module Slip · selected G1`.

## WebGPT Attempts

1. `skills/battle/local/webgpt-design-review-20260720T1658Z/`
   - Receipt: `response.md.receipt.json`
   - Status: `submitted_to_chatgpt:true`
   - Failure: `response.md.meta.json` reports `proof_status:
     submitted_no_response_proof`, `failure: missing_sentinel`.
   - Tab `837359249` later still showed the `:3003` prompt with `Thinking`;
     no acceptance response was recoverable.

2. `skills/battle/local/webgpt-design-review-20260720T171624Z/`
   - Request: zip evidence bundle with screenshot and JSON proof.
   - Receipt: `response.receipt.json`
   - Status: `submitted_to_chatgpt:false`, `status: prepared_prompt`,
     requested tab `837359763`.
   - Preserved stderr: `submit.stderr.log`.
   - Failure signature: `ChatGPT did not accept submitted prompt: prompt
     remained in the composer after send`.

3. `skills/battle/local/webgpt-design-review-20260720T1721Z/`
   - Request: screenshot-only attachment plus inline local proof summary.
   - Receipt: `response.receipt.json`
   - Status: `submitted_to_chatgpt:false`, `status: prepared_prompt`,
     requested tab `837359766`.
   - Preserved stderr: `submit.stderr.log`.
   - Failure signature: `ChatGPT did not accept submitted prompt: prompt
     remained in the composer after send`.
   - Follow-up tab inspection showed the prompt still in the composer and the
     `Send prompt` button disabled.

4. Focused repair check:
   `skills/battle/local/webgpt-transport-sanity-20260720T1724Z/`
   - Request: text-only prompt, no attachment.
   - Receipt: `response.receipt.json`
   - Status: `submitted_to_chatgpt:true`, requested tab `837359769`.
   - Heartbeat: `phase: failed`, `page_state: stalled`, timeout remaining `0`.
   - Preserved stderr: `submit.stderr.log`.
   - Failure signature: `Response timeout; hidden_polls=143;
     last_visibility=hidden; document_hidden=true`.
   - Read-only tab inspection showed `Stop answering` still visible and no
     sentinel-bearing assistant response.

## Campaign Status

- `passed`: local backend receipt and local browser render proof.
- `failed`: WebGPT transport delivery for the agent-skills-host review.
- `blocked_by_systemic_failure`: further same-family Surf submits to new
  ChatGPT tabs until ChatGPT response generation recovers.
- `not_run`: final WebGPT acceptance for the agent-skills-hosted receipt.
- `active_family`: Surf `webgpt.submit` prompt delivery to ChatGPT.
- `latest_failure_signature`: `submitted_to_chatgpt:false`,
  `status: prepared_prompt`, prompt remains in composer, send disabled or not
  accepted for attachment-backed prompts; text-only prompt reaches
  `submitted_to_chatgpt:true` but stalls with `Stop answering` and no sentinel.

## Next Focused Repair Check

Do not rerun the broad WebGPT review first. First recover or wait out the
currently stalled ChatGPT response path, then run a tiny Surf text-only
`webgpt.submit` sentinel check in a fresh tab. Only after a text-only prompt
reaches `proof_status: response_proven` should the Battle review be retried.

This is not a Battle receipt regression. It is a WebGPT transport delivery
blocker after local Battle evidence already rendered from the agent-skills host.
