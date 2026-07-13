import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { qualifyRevisionLocally } from '../server/src/qualification'

function argument(name: string): string {
  const index = process.argv.indexOf(name)
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing_argument:${name}`)
  return process.argv[index + 1]
}

async function main() {
  const runId = argument('--run-id')
  const revisionId = argument('--revision-id')
  const revisionRoot = resolve(argument('--revision-root'))
  const outputRoot = resolve(argument('--output-dir'))
  const { readModelReceipt, consumerReceipt } = await qualifyRevisionLocally(runId, revisionId, revisionRoot)
  mkdirSync(outputRoot, { recursive: true })
  writeFileSync(resolve(outputRoot, 'revision_read_model_validation_receipt.json'), `${JSON.stringify(readModelReceipt, null, 2)}\n`)
  writeFileSync(resolve(outputRoot, 'revision_consumer_validation_receipt.json'), `${JSON.stringify(consumerReceipt, null, 2)}\n`)
  const status = readModelReceipt.status === 'PASS_REVISION_READ_MODEL' && consumerReceipt.status === 'PASS_REVISION_CONSUMER_HYDRATION'
    ? 'BLOCKED_MEMORY_QUALIFICATION_REQUIRED'
    : 'BLOCKED_LOCAL_QUALIFICATION'
  const qualification = {
    schema: 'persona_dream.revision_qualification_receipt.v1', status, run_id: runId, revision_id: revisionId,
    local_read_model_passed: readModelReceipt.status === 'PASS_REVISION_READ_MODEL',
    consumer_hydration_passed: consumerReceipt.status === 'PASS_REVISION_CONSUMER_HYDRATION',
    memory_prepare_passed: false, memory_validation_passed: false, graph_sync_passed: false, qdrant_sync_passed: false,
    active_consistent: false, provider_ready: false, live_submit_ready: false, paid_call_authorized: false,
    submitted: false, actual_provider_call_attempts: 0, mocked: false, live: false,
  }
  writeFileSync(resolve(outputRoot, 'revision_qualification_receipt.json'), `${JSON.stringify(qualification, null, 2)}\n`)
  console.log(JSON.stringify({ readModelReceipt, consumerReceipt, qualification }, null, 2))
}

void main()
