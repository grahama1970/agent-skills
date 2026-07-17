import { createHash } from 'node:crypto'
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs'
import { readdir, stat } from 'node:fs/promises'
import { basename, relative, resolve, sep } from 'node:path'
import type { DreamRunDetailResponse, HumanIdeaProjection, StoryboardConsumerProjection } from '../../contracts/src/index'
import { hydrateStoryboardConsumer } from './consumerContracts'
import { validateIdeaLineage } from './ideaLineage'
import { DreamPathPolicy } from './paths'
import { buildProviderReturnStage, projectStages } from './stages'

const ACTIVATION_RECEIPT_NAME = 'revision_activation_receipt.json'
const REQUIRED_ACTIVATION_FILES = [
  'revision_manifest',
  'artifact_index',
  'prepare_receipt',
  'verify_receipt',
  'local_active_pointer',
  'work_order',
  'queue_item',
  'queue_terminal_event',
] as const

type JsonRecord = Record<string, unknown>
type Qualification = DreamRunDetailResponse['revisionQualification']

async function listFiles(root: string, maxFiles = 4000): Promise<string[]> {
  const files: string[] = []
  async function visit(dir: string, depth: number): Promise<void> {
    if (depth > 7 || files.length >= maxFiles) return
    const entries = await readdir(dir, { withFileTypes: true }).catch(() => [])
    for (const entry of entries) {
      if (files.length >= maxFiles || entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') continue
      const path = resolve(dir, entry.name)
      if (entry.isDirectory()) await visit(path, depth + 1)
      else if (entry.isFile()) files.push(path)
    }
  }
  await visit(root, 0)
  return files
}

function readJson(path: string): JsonRecord | null {
  try { return JSON.parse(readFileSync(path, 'utf8')) as JsonRecord } catch { return null }
}

function record(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : null
}

function sha256File(path: string): string {
  return `sha256:${createHash('sha256').update(readFileSync(path)).digest('hex')}`
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value)
}

function sha256Json(value: unknown): string {
  return `sha256:${createHash('sha256').update(stableJson(value)).digest('hex')}`
}

function activePointerKey(runId: string): string {
  const digest = createHash('sha256').update(`persona-dream-active\0${runId}`).digest('hex')
  return `pd_active_${digest.slice(0, 48)}`
}

function assertInvariant(condition: unknown, code: string): asserts condition {
  if (!condition) throw new Error(code)
}

function safeReferencedFile(runRoot: string, value: unknown): string {
  const ref = record(value)
  assertInvariant(ref, 'BLOCKED_ACTIVATION_LOCAL_FILE_REF_INVALID')
  const relativePath = typeof ref.relative_path === 'string' ? ref.relative_path : ''
  const expectedSha256 = typeof ref.sha256 === 'string' ? ref.sha256 : ''
  assertInvariant(relativePath && !relativePath.startsWith('/') && !relativePath.split('/').includes('..'), 'BLOCKED_ACTIVATION_REFERENCED_PATH_ESCAPE')
  assertInvariant(/^sha256:[a-f0-9]{64}$/.test(expectedSha256), 'BLOCKED_ACTIVATION_REFERENCED_HASH_INVALID')
  const realRoot = realpathSync(runRoot)
  const candidate = resolve(realRoot, relativePath)
  assertInvariant(existsSync(candidate), 'BLOCKED_ACTIVATION_REFERENCED_FILE_MISSING')
  const real = realpathSync(candidate)
  const rel = relative(realRoot, real)
  assertInvariant(Boolean(rel) && rel !== '..' && !rel.startsWith(`..${sep}`), 'BLOCKED_ACTIVATION_REFERENCED_PATH_ESCAPE')
  assertInvariant(statSync(real).isFile(), 'BLOCKED_ACTIVATION_REFERENCED_FILE_NOT_REGULAR')
  assertInvariant(sha256File(real) === expectedSha256, 'BLOCKED_ACTIVATION_REFERENCED_HASH_MISMATCH')
  return real
}

function blockedQualification(blockers: string[], state: 'MISSING' | 'LEGACY_UNQUALIFIED' = 'LEGACY_UNQUALIFIED'): Qualification {
  return {
    state,
    status: 'BLOCKED_REVISION_NOT_QUALIFIED',
    blockers: [...new Set(blockers)],
    actualProviderCallAttempts: 0,
    providerReady: false,
    liveSubmitReady: false,
  }
}

function validateActivationChain(options: {
  runRoot: string
  evidenceRoot: string
  runId: string
  revisionId: string
  pointerPath: string
  pointer: JsonRecord | null
  fixtureRun: boolean
  humanIdea: HumanIdeaProjection
}): Qualification {
  const receiptPath = resolve(options.evidenceRoot, ACTIVATION_RECEIPT_NAME)
  if (!existsSync(receiptPath)) {
    return blockedQualification([
      'BLOCKED_REVISION_ACTIVATION_RECEIPT_MISSING',
      'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN',
      'BLOCKED_QUEUE_TERMINAL_STATE_UNPROVEN',
    ])
  }

  try {
    const receipt = readJson(receiptPath)
    assertInvariant(receipt, 'BLOCKED_REVISION_ACTIVATION_RECEIPT_INVALID')
    assertInvariant(receipt.schema === 'persona_dream.revision_activation_receipt.v1', 'BLOCKED_REVISION_ACTIVATION_RECEIPT_SCHEMA')
    assertInvariant(receipt.status === 'PASS_ACTIVE_CONSISTENT', 'BLOCKED_REVISION_ACTIVATION_RECEIPT_STATUS')
    assertInvariant(receipt.run_id === options.runId, 'BLOCKED_REVISION_ACTIVATION_RECEIPT_RUN_MISMATCH')
    assertInvariant(receipt.revision_id === options.revisionId, 'BLOCKED_REVISION_ACTIVATION_RECEIPT_REVISION_MISMATCH')
    assertInvariant(receipt.actual_provider_call_attempts === 0, 'BLOCKED_PROVIDER_REVISION_INVARIANT_UNPROVEN')
    assertInvariant(receipt.provider_live === false && receipt.paid_call_authorized === false && receipt.submitted === false, 'BLOCKED_PROVIDER_REVISION_INVARIANT_UNPROVEN')
    assertInvariant(receipt.provider_ready === false && receipt.live_submit_ready === false, 'BLOCKED_PROVIDER_REVISION_INVARIANT_UNPROVEN')
    if (!options.fixtureRun) {
      assertInvariant(receipt.mocked === false && receipt.live === true, 'BLOCKED_REVISION_ACTIVATION_NOT_LIVE')
    } else {
      assertInvariant(receipt.mocked === true && receipt.live === false, 'BLOCKED_REVISION_ACTIVATION_FIXTURE_CLASSIFICATION')
    }

    const localFiles = record(receipt.local_files)
    assertInvariant(localFiles, 'BLOCKED_ACTIVATION_LOCAL_FILES_MISSING')
    const resolved: Record<string, string> = {}
    for (const name of REQUIRED_ACTIVATION_FILES) {
      resolved[name] = safeReferencedFile(options.runRoot, localFiles[name])
    }

    assertInvariant(realpathSync(resolved.revision_manifest) === realpathSync(resolve(options.evidenceRoot, 'revision_manifest.json')), 'BLOCKED_REVISION_MANIFEST_REFERENCE_MISMATCH')
    assertInvariant(realpathSync(resolved.artifact_index) === realpathSync(resolve(options.evidenceRoot, 'revision_artifact_index.json')), 'BLOCKED_REVISION_ARTIFACT_INDEX_REFERENCE_MISMATCH')
    assertInvariant(realpathSync(resolved.prepare_receipt) === realpathSync(resolve(options.evidenceRoot, 'revision_memory_prepare_receipt.json')), 'BLOCKED_MEMORY_PREPARE_RECEIPT_REFERENCE_MISMATCH')
    assertInvariant(realpathSync(resolved.verify_receipt) === realpathSync(resolve(options.evidenceRoot, 'revision_memory_verify_receipt.json')), 'BLOCKED_MEMORY_VERIFY_RECEIPT_REFERENCE_MISMATCH')
    assertInvariant(realpathSync(resolved.local_active_pointer) === realpathSync(options.pointerPath), 'BLOCKED_LOCAL_ACTIVE_POINTER_REFERENCE_MISMATCH')

    const manifest = readJson(resolved.revision_manifest)
    const index = readJson(resolved.artifact_index)
    const prepare = readJson(resolved.prepare_receipt)
    const verify = readJson(resolved.verify_receipt)
    const localPointer = readJson(resolved.local_active_pointer)
    const workOrder = readJson(resolved.work_order)
    const queueItem = readJson(resolved.queue_item)
    const terminalEvent = readJson(resolved.queue_terminal_event)
    assertInvariant(manifest && index && prepare && verify && localPointer && workOrder && queueItem && terminalEvent, 'BLOCKED_ACTIVATION_REFERENCED_JSON_INVALID')

    const manifestSha256 = sha256File(resolved.revision_manifest)
    const indexSha256 = sha256File(resolved.artifact_index)
    const prepareSha256 = sha256File(resolved.prepare_receipt)
    const verifySha256 = sha256File(resolved.verify_receipt)
    const pointerSha256 = sha256File(resolved.local_active_pointer)
    const workOrderSha256 = sha256File(resolved.work_order)
    const queueItemSha256 = sha256File(resolved.queue_item)
    const terminalEventSha256 = sha256File(resolved.queue_terminal_event)
    const expectedTransactionId = `activation-${sha256Json({
        run_id: options.runId,
        revision_id: options.revisionId,
        source_revision_id: String(receipt.source_revision_id ?? ''),
        source_commit: String(receipt.source_commit ?? ''),
        revision_manifest_sha256: manifestSha256,
        artifact_index_sha256: indexSha256,
        prepare_receipt_sha256: prepareSha256,
        verify_receipt_sha256: verifySha256,
        local_active_pointer_sha256: pointerSha256,
        work_order_sha256: workOrderSha256,
        queue_item_sha256: queueItemSha256,
      }).slice('sha256:'.length, 'sha256:'.length + 32)}`

    assertInvariant(manifest.runId === options.runId && manifest.revisionId === options.revisionId, 'BLOCKED_REVISION_MANIFEST_IDENTITY')
    assertInvariant(index.run_id === options.runId && index.revision_id === options.revisionId, 'BLOCKED_REVISION_ARTIFACT_INDEX_IDENTITY')
    assertInvariant(options.pointer && localPointer.runId === options.runId && localPointer.revisionId === options.revisionId, 'BLOCKED_LOCAL_ACTIVE_POINTER_MISMATCH')
    assertInvariant(localPointer.revisionManifestSha256 === manifestSha256, 'BLOCKED_LOCAL_ACTIVE_POINTER_MANIFEST_MISMATCH')
    assertInvariant(localPointer.ideaId === options.humanIdea.ideaId && localPointer.ideaSha256 === options.humanIdea.ideaSha256, 'BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH')

    assertInvariant(prepare.schema === 'persona_dream.revision_memory_prepare_receipt.v1' && prepare.status === 'PASS_MEMORY_REVISION_PREPARED', 'BLOCKED_MEMORY_PREPARE_RECEIPT_INVALID')
    assertInvariant(verify.schema === 'persona_dream.revision_memory_verify_receipt.v1' && verify.status === 'PASS_MEMORY_REVISION_VERIFIED', 'BLOCKED_MEMORY_VERIFY_RECEIPT_INVALID')
    for (const value of [prepare, verify]) {
      assertInvariant(value.run_id === options.runId && value.revision_id === options.revisionId, 'BLOCKED_MEMORY_RECEIPT_IDENTITY_MISMATCH')
      assertInvariant(value.source_revision_id === receipt.source_revision_id && value.source_commit === receipt.source_commit, 'BLOCKED_MEMORY_RECEIPT_IDENTITY_MISMATCH')
      assertInvariant(value.runtime_release_id === receipt.runtime_release_id && value.memory_url === receipt.memory_url && value.collection === receipt.collection, 'BLOCKED_MEMORY_RECEIPT_IDENTITY_MISMATCH')
      assertInvariant(value.artifact_index_sha256 === indexSha256 && value.revision_manifest_sha256 === manifestSha256, 'BLOCKED_MEMORY_RECEIPT_HASH_CHAIN')
      assertInvariant(value.actual_provider_call_attempts === 0 && value.provider_live === false && value.paid_call_authorized === false && value.submitted === false, 'BLOCKED_PROVIDER_REVISION_INVARIANT_UNPROVEN')
      assertInvariant(value.mocked === receipt.mocked && value.live === receipt.live, 'BLOCKED_MEMORY_RECEIPT_EVIDENCE_CLASS')
    }
    assertInvariant(verify.prepare_receipt_sha256 === prepareSha256, 'BLOCKED_MEMORY_RECEIPT_HASH_CHAIN')
    const expectedCounts = { revision: 1, phase: 10, required_artifact: 16, total: 27 }
    const prepareRecords = record(prepare.records)
    const verifyRecords = record(verify.records)
    assertInvariant(prepareRecords && verifyRecords, 'BLOCKED_MEMORY_RECEIPT_RECORDS_MISSING')
    for (const counts of [prepareRecords.expected_counts, prepareRecords.returned_counts, verifyRecords.expected_counts, verifyRecords.before_counts, verifyRecords.after_counts]) {
      assertInvariant(stableJson(counts) === stableJson(expectedCounts), 'BLOCKED_MEMORY_RECEIPT_RECORD_COUNTS_MISMATCH')
    }
    assertInvariant(Array.isArray(prepareRecords.exact_keys) && prepareRecords.exact_keys.length === 27, 'BLOCKED_MEMORY_RECEIPT_EXACT_KEYS_MISMATCH')
    assertInvariant(stableJson(prepareRecords.exact_keys) === stableJson(verifyRecords.exact_keys), 'BLOCKED_MEMORY_RECEIPT_EXACT_KEYS_MISMATCH')
    const receiptChain = record(receipt.receipt_chain)
    assertInvariant(receiptChain?.prepare_status === 'PASS_MEMORY_REVISION_PREPARED' && receiptChain?.verify_status === 'PASS_MEMORY_REVISION_VERIFIED', 'BLOCKED_ACTIVATION_RECEIPT_CHAIN_MISMATCH')
    assertInvariant(receiptChain?.exact_record_count === 27 && receiptChain?.phase_record_count === 10 && receiptChain?.required_artifact_record_count === 16 && receiptChain?.semantic_pointer_count === 27, 'BLOCKED_ACTIVATION_RECEIPT_CHAIN_MISMATCH')
    const receiptHashValidation = record(receipt.hash_validation)
    const prepareHashValidation = record(prepare.hash_validation)
    const verifyHashValidation = record(verify.hash_validation)
    assertInvariant(receiptHashValidation && prepareHashValidation && verifyHashValidation, 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISSING')
    const indexedArtifactCount = Number(index.artifact_count ?? 0)
    assertInvariant(indexedArtifactCount > 0, 'BLOCKED_REVISION_ARTIFACT_COUNT_MISMATCH')
    for (const validation of [receiptHashValidation, prepareHashValidation, verifyHashValidation]) {
      assertInvariant(validation.artifact_count === indexedArtifactCount, 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISMATCH')
      assertInvariant(validation.recomputed_count === indexedArtifactCount && validation.matched_count === indexedArtifactCount, 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISMATCH')
      assertInvariant(validation.mismatch_count === 0 && validation.symlink_count === 0 && validation.escape_count === 0, 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISMATCH')
      assertInvariant(typeof validation.artifact_hash_manifest_sha256 === 'string' && /^sha256:[a-f0-9]{64}$/.test(validation.artifact_hash_manifest_sha256), 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISMATCH')
    }
    assertInvariant(receiptHashValidation.artifact_hash_manifest_sha256 === prepareHashValidation.artifact_hash_manifest_sha256 && receiptHashValidation.artifact_hash_manifest_sha256 === verifyHashValidation.artifact_hash_manifest_sha256, 'BLOCKED_REVISION_ACTIVATION_HASH_VALIDATION_MISMATCH')

    const verifySemantic = record(verify.semantic_sync)
    const semanticAfter = record(verifySemantic?.after)
    const semanticStates = record(semanticAfter?.states)
    const semanticRecall = record(verifySemantic?.recall)
    assertInvariant(semanticAfter?.pointer_count === 27 && semanticStates?.synced === 27, 'BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED')
    assertInvariant(typeof semanticRecall?.max_dense === 'number' && semanticRecall.max_dense > 0, 'BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED')

    assertInvariant(workOrder.schemaVersion === 'persona_dream.repair_work_order.v1' && workOrder.status === 'REQUESTED', 'BLOCKED_REPAIR_WORK_ORDER_INVALID')
    assertInvariant(workOrder.runId === options.runId && workOrder.targetRevisionId === options.revisionId, 'BLOCKED_REPAIR_WORK_ORDER_IDENTITY')
    assertInvariant(queueItem.schemaVersion === 'persona_dream.tau_repair_queue_item.v1' && queueItem.status === 'QUEUED', 'BLOCKED_REPAIR_QUEUE_STATE')
    const embeddedWorkOrder = record(queueItem.workOrder)
    assertInvariant(embeddedWorkOrder?.workOrderId === workOrder.workOrderId && embeddedWorkOrder?.targetRevisionId === options.revisionId, 'BLOCKED_REPAIR_QUEUE_IDENTITY')

    const transactionId = typeof receipt.activation_transaction_id === 'string' ? receipt.activation_transaction_id : ''
    assertInvariant(/^activation-[a-f0-9]{32}$/.test(transactionId), 'BLOCKED_REVISION_ACTIVATION_TRANSACTION_ID')
    assertInvariant(transactionId === expectedTransactionId, 'BLOCKED_REVISION_ACTIVATION_TRANSACTION_HASH_MISMATCH')
    assertInvariant(terminalEvent.schema === 'persona_dream.repair_queue_terminal_event.v1' && terminalEvent.status === 'COMPLETED', 'BLOCKED_QUEUE_TERMINAL_STATE_UNPROVEN')
    assertInvariant(terminalEvent.activation_transaction_id === transactionId, 'BLOCKED_QUEUE_TERMINAL_EVENT_MISMATCH')
    assertInvariant(terminalEvent.run_id === options.runId && terminalEvent.target_revision_id === options.revisionId, 'BLOCKED_QUEUE_TERMINAL_EVENT_MISMATCH')
    assertInvariant(terminalEvent.work_order_id === workOrder.workOrderId, 'BLOCKED_QUEUE_TERMINAL_EVENT_MISMATCH')
    assertInvariant(terminalEvent.prepare_receipt_sha256 === prepareSha256 && terminalEvent.verify_receipt_sha256 === verifySha256, 'BLOCKED_QUEUE_TERMINAL_EVENT_HASH_CHAIN')
    assertInvariant(terminalEvent.revision_manifest_sha256 === manifestSha256 && terminalEvent.artifact_index_sha256 === indexSha256, 'BLOCKED_QUEUE_TERMINAL_EVENT_HASH_CHAIN')
    assertInvariant(terminalEvent.local_active_pointer_sha256 === pointerSha256, 'BLOCKED_QUEUE_TERMINAL_EVENT_HASH_CHAIN')
    assertInvariant(terminalEvent.work_order_sha256 === workOrderSha256 && terminalEvent.queue_item_sha256 === queueItemSha256, 'BLOCKED_QUEUE_TERMINAL_EVENT_HASH_CHAIN')
    assertInvariant(terminalEvent.actual_provider_call_attempts === 0 && terminalEvent.provider_live === false && terminalEvent.paid_call_authorized === false && terminalEvent.submitted === false, 'BLOCKED_PROVIDER_REVISION_INVARIANT_UNPROVEN')

    const receiptQueue = record(receipt.queue)
    assertInvariant(receiptQueue?.work_order_id === workOrder.workOrderId && receiptQueue?.terminal_status === 'COMPLETED', 'BLOCKED_ACTIVATION_RECEIPT_QUEUE_MISMATCH')
    const receiptPointer = record(receipt.local_pointer)
    assertInvariant(receiptPointer?.run_id === options.runId && receiptPointer?.revision_id === options.revisionId, 'BLOCKED_ACTIVATION_RECEIPT_POINTER_MISMATCH')
    assertInvariant(receiptPointer?.revision_manifest_sha256 === manifestSha256, 'BLOCKED_ACTIVATION_RECEIPT_POINTER_MISMATCH')

    const memory = record(receipt.memory)
    assertInvariant(memory, 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
    assertInvariant(memory.active_revision_id === options.revisionId && memory.previous_revision_id === workOrder.sourceRevisionId, 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
    assertInvariant(memory.exact_reread_count === 1, 'BLOCKED_MEMORY_ACTIVE_POINTER_REREAD_COUNT')
    assertInvariant(memory.semantic_sync_state === 'synced', 'BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED')
    for (const field of ['active_pointer_key', 'qdrant_collection', 'qdrant_point_id', 'embedding_model', 'embedding_version', 'text_hash', 'document_contract_sha256']) {
      assertInvariant(typeof memory[field] === 'string' && String(memory[field]).length > 0, 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
    }
    const expectedActiveKey = activePointerKey(options.runId)
    assertInvariant(memory.active_pointer_key === expectedActiveKey, 'BLOCKED_MEMORY_ACTIVE_POINTER_KEY_MISMATCH')
    const runtimeReleaseId = String(receipt.runtime_release_id ?? '')
    const activatedAt = String(receipt.activated_at ?? '')
    const sourceCommit = String(receipt.source_commit ?? '')
    const sourceRevisionId = String(receipt.source_revision_id ?? '')
    assertInvariant(runtimeReleaseId.length > 0 && activatedAt.length > 0 && sourceCommit.length > 0 && sourceRevisionId.length > 0, 'BLOCKED_REVISION_ACTIVATION_RECEIPT_IDENTITY')
    const pointerContract: Record<string, unknown> = {
      _key: expectedActiveKey,
      schema: 'persona_dream.active_revision_pointer.v1',
      kind: 'persona_dream_active_revision_pointer',
      record_type: 'active_revision_pointer',
      project: 'persona-dream',
      run_id: options.runId,
      active_revision_id: options.revisionId,
      previous_revision_id: sourceRevisionId,
      idea_id: options.humanIdea.ideaId,
      idea_sha256: options.humanIdea.ideaSha256,
      source_commit: sourceCommit,
      runtime_release_id: runtimeReleaseId,
      lifecycle_state: 'ACTIVE',
      qualification_status: 'MEMORY_ACTIVE_POINTER_WRITTEN',
      activation_receipt_required: true,
      activation_receipt_relative_path: `.persona-dream/revisions/${options.revisionId}/${ACTIVATION_RECEIPT_NAME}`,
      activation_transaction_id: transactionId,
      revision_manifest_sha256: manifestSha256,
      artifact_index_sha256: indexSha256,
      local_active_pointer_sha256: pointerSha256,
      prepare_receipt_sha256: prepareSha256,
      verify_receipt_sha256: verifySha256,
      work_order_sha256: workOrderSha256,
      queue_item_sha256: queueItemSha256,
      queue_terminal_event_sha256: terminalEventSha256,
      activated_at: activatedAt,
      provider_live: false,
      paid_call_authorized: false,
      submitted: false,
      provider_ready: false,
      live_submit_ready: false,
      actual_provider_call_attempts: 0,
      scope: `persona-dream:${options.runId}:active-revision`,
      source: `persona-dream://${options.runId}/active-revision`,
      retrieval_text: `The active immutable Persona Dream revision for run ${options.runId} is ${options.revisionId}. Memory verification passed for Phase 01 through Phase 10, the historical repair work order reached a hash-bound terminal event, and provider calls remain disabled.`,
      tags: [
        'persona-dream',
        'active-revision-pointer',
        `run:${options.runId}`,
        `active-revision:${options.revisionId}`,
      ],
    }
    assertInvariant(memory.document_contract_sha256 === sha256Json(pointerContract), 'BLOCKED_MEMORY_ACTIVE_POINTER_CONTRACT_HASH_MISMATCH')
    const requests = record(memory.requests)
    const listBefore = record(requests?.list_before)
    const upsertRequest = record(requests?.upsert)
    const listAfter = record(requests?.list_after)
    for (const [name, evidence, endpoint] of [
      ['list_before', listBefore, '/list'],
      ['upsert', upsertRequest, '/upsert'],
      ['list_after', listAfter, '/list'],
    ] as const) {
      assertInvariant(evidence?.endpoint === endpoint, 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
      assertInvariant(typeof evidence?.status_code === 'number' && evidence.status_code >= 200 && evidence.status_code < 300, 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
      assertInvariant(typeof evidence?.request_payload_sha256 === 'string' && /^sha256:[a-f0-9]{64}$/.test(evidence.request_payload_sha256), 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
      assertInvariant(typeof evidence?.response_sha256 === 'string' && /^sha256:[a-f0-9]{64}$/.test(evidence.response_sha256), 'BLOCKED_MEMORY_ACTIVE_REVISION_UNPROVEN')
      assertInvariant(record(evidence?.returned_counts), `BLOCKED_MEMORY_ACTIVE_REVISION_${name.toUpperCase()}_COUNTS`)
    }
    const listAfterCounts = record(listAfter?.returned_counts)
    assertInvariant(listAfterCounts?.count === 1 && listAfterCounts?.total === 1, 'BLOCKED_MEMORY_ACTIVE_POINTER_REREAD_COUNT')
    const upsertCounts = record(upsertRequest?.returned_counts)
    assertInvariant(upsertCounts?.total === 1 && Number(upsertCounts?.inserted ?? 0) + Number(upsertCounts?.updated ?? 0) === 1, 'BLOCKED_MEMORY_ACTIVE_POINTER_UPSERT_COUNT')
    assertInvariant(terminalEvent.memory_active_pointer_key === memory.active_pointer_key, 'BLOCKED_MEMORY_ACTIVE_POINTER_HASH_CHAIN')

    const activationLocalFiles = record(receipt.local_files)
    const eventRef = record(activationLocalFiles?.queue_terminal_event)
    assertInvariant(eventRef?.sha256 === terminalEventSha256, 'BLOCKED_ACTIVATION_RECEIPT_LOCAL_FILES_MISMATCH')

    return {
      state: 'ACTIVE_CONSISTENT',
      status: 'PASS_ACTIVE_CONSISTENT',
      blockers: [],
      activationTransactionId: transactionId,
      activationReceiptPath: receiptPath,
      memoryActivePointerKey: String(memory.active_pointer_key),
      queueTerminalEventPath: resolved.queue_terminal_event,
      actualProviderCallAttempts: 0,
      providerReady: false,
      liveSubmitReady: false,
    }
  } catch (error) {
    const code = error instanceof Error && /^BLOCKED_[A-Z0-9_]+$/.test(error.message)
      ? error.message
      : 'BLOCKED_REVISION_ACTIVATION_RECEIPT_INVALID'
    return blockedQualification([code])
  }
}

export async function collectRuns(reportRoots: readonly string[], outputRoots: readonly string[]) {
  const runs: Array<Record<string, unknown>> = []
  for (const [source, roots] of [['report', reportRoots], ['output', outputRoots]] as const) {
    for (const root of roots) {
      const entries = await readdir(root, { withFileTypes: true }).catch(() => [])
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        const runRoot = resolve(root, entry.name)
        const statusPath = resolve(runRoot, 'status.json')
        const validationPath = resolve(runRoot, 'validation.json')
        const manifestPath = resolve(runRoot, 'manifest.json')
        if (![statusPath, validationPath, manifestPath, resolve(runRoot, 'report.html')].some(existsSync)) continue
        const statusDoc = readJson(statusPath)
        const validationDoc = readJson(validationPath)
        const statusPolicy = record(statusDoc?.policy)
        const providerCallAttempts = Number(validationDoc?.actual_provider_call_attempts ?? 0)
        const rawStatus = String(validationDoc?.status ?? statusDoc?.status ?? 'UNKNOWN')
        const stats = await Promise.all([statusPath, validationPath, manifestPath].map((path) => stat(path).catch(() => null)))
        const updatedAt = stats.find(Boolean)?.mtime.toISOString() ?? new Date(0).toISOString()
        runs.push({
          id: entry.name,
          title: entry.name.replace(/[-_]+/g, ' '),
          source,
          status: rawStatus,
          runRoot,
          reportPath: existsSync(resolve(runRoot, 'report.html')) ? resolve(runRoot, 'report.html') : undefined,
          reportUrl: existsSync(resolve(runRoot, 'report.html')) ? `/api/projects/dream/report?path=${encodeURIComponent(resolve(runRoot, 'report.html'))}` : undefined,
          statusPath: existsSync(statusPath) ? statusPath : undefined,
          validationPath: existsSync(validationPath) ? validationPath : undefined,
          manifestPath: existsSync(manifestPath) ? manifestPath : undefined,
          klingCalled: providerCallAttempts > 0 || statusPolicy?.kling_call_performed === true,
          paidCallAuthorized: statusPolicy?.paid_call_authorized === true,
          updatedAt,
        })
      }
    }
  }
  return runs.sort((a, b) => Date.parse(String(b.updatedAt)) - Date.parse(String(a.updatedAt))).slice(0, 40)
}

export async function buildRunDetail(policy: DreamPathPolicy, requestedRoot: string): Promise<DreamRunDetailResponse> {
  const runRoot = policy.resolveDirectory(requestedRoot)
  const revision = readJson(resolve(runRoot, 'dream_revision_manifest.v1.json'))
  const pointerPath = resolve(runRoot, '.persona-dream', 'state', 'active_revision.json')
  const pointer = readJson(pointerPath)
  const sourceRevisionId = typeof pointer?.revisionId === 'string'
    ? pointer.revisionId
    : typeof revision?.active_revision_id === 'string'
      ? revision.active_revision_id
      : ''
  const localRevisionRoot = sourceRevisionId
    ? resolve(runRoot, '.persona-dream', 'revisions', sourceRevisionId)
    : ''
  const evidenceRoot = localRevisionRoot && existsSync(localRevisionRoot)
    ? policy.resolveDirectory(realpathSync(localRevisionRoot))
    : runRoot
  let humanIdea: HumanIdeaProjection | undefined
  let ideaLineageBlocker: string | undefined
  if (sourceRevisionId && localRevisionRoot && existsSync(localRevisionRoot)) {
    try {
      humanIdea = validateIdeaLineage(evidenceRoot, basename(runRoot), sourceRevisionId)
    } catch {
      ideaLineageBlocker = 'BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH'
    }
  }
  const files = await listFiles(evidenceRoot)
  const projectedStages = projectStages(evidenceRoot, files, '10', sourceRevisionId || undefined)
  const runId = basename(runRoot)
  const fixtureRun = revision?.fixture === true
  const revisionQualification: DreamRunDetailResponse['revisionQualification'] = sourceRevisionId
    ? ideaLineageBlocker || !humanIdea
      ? blockedQualification(['BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH'])
      : validateActivationChain({
        runRoot,
        evidenceRoot,
        runId,
        revisionId: sourceRevisionId,
        pointerPath,
        pointer,
        fixtureRun,
        humanIdea,
      })
    : blockedQualification(['BLOCKED_ACTIVE_REVISION_MISSING'], 'MISSING')
  const stages = projectedStages.map((stage) => {
    if (revisionQualification.state === 'ACTIVE_CONSISTENT' || stage.effectiveState !== 'accepted_current') return stage
    return {
      ...stage,
      status: 'BLOCKED_REVISION_NOT_QUALIFIED',
      failureOrGap: 'The active revision has not passed Memory activation and repair-queue convergence.',
      acceptance: { ...stage.acceptance, state: 'blocked' as const },
      effectiveState: 'blocked_by_upstream' as const,
      lineage: {
        ...stage.lineage,
        state: 'stale' as const,
        staleReasons: [
          ...stage.lineage.staleReasons,
          { code: 'REVISION_QUALIFICATION_NOT_ACTIVE_CONSISTENT' },
        ],
      },
      repair: {
        ...stage.repair,
        eligible: false,
        reason: 'revision_activation_transaction_required',
      },
    }
  })
  const providerReturnStage = buildProviderReturnStage(runRoot, sourceRevisionId || undefined)
  if (providerReturnStage) stages.push(providerReturnStage)
  const earliest = stages.find((stage) => Number(stage.id) <= 10
    && ['missing', 'malformed', 'semantic_invalid', 'accepted_stale', 'blocked_current', 'blocked_stale'].includes(stage.effectiveState))
  const repairEnabled = Boolean(revision?.repair_enabled === true || revision?.pipeline_complete === true)
  const phaseRange = earliest ? stages.filter((stage) => Number(stage.id) >= Number(earliest.id) && Number(stage.id) <= 10).map((stage) => stage.id) : []
  const candidate = earliest && sourceRevisionId
    ? {
        sourceRevisionId,
        earliestRepairPhase: earliest.id,
        selectedThroughPhase: '10',
        phaseRange,
        dedupKey: String(earliest.repair.dedupKey ?? ''),
        enqueueAllowed: repairEnabled && earliest.repair.eligible,
        blockers: repairEnabled ? [] : ['REPAIR_NOT_ENABLED'],
      }
    : undefined
  let storyboard: StoryboardConsumerProjection | undefined
  if (sourceRevisionId) {
    const index = readJson(resolve(evidenceRoot, 'revision_artifact_index.json'))
    const artifacts = index?.artifacts && typeof index.artifacts === 'object' && !Array.isArray(index.artifacts)
      ? index.artifacts as Record<string, { relative_path: string; sha256: string; roles: string[] }>
      : null
    const packetEntry = artifacts?.storyboard_packet
    if (artifacts && packetEntry?.relative_path) {
      try {
        const revisionPolicy = new DreamPathPolicy([evidenceRoot])
        const packetPath = revisionPolicy.resolveFile(resolve(evidenceRoot, packetEntry.relative_path))
        const packet = readJson(packetPath)
        if (packet) {
          const hydrated = hydrateStoryboardConsumer(packet, { artifacts })
          const artifactUrl = (artifactId: string) => [
            '/api/projects/dream/runs',
            encodeURIComponent(runId),
            'revisions',
            encodeURIComponent(sourceRevisionId),
            'artifacts',
            encodeURIComponent(artifactId),
          ].join('/')
          storyboard = {
            contract: 'dream_storyboard_workspace_v1',
            revisionId: sourceRevisionId,
            packetArtifactId: 'storyboard_packet',
            packetUrl: artifactUrl('storyboard_packet'),
            panelCount: hydrated.panelCount,
            panels: hydrated.panelIds.map((panelId) => {
              const start = hydrated.frames.find((frame) => frame.panelId === panelId && frame.role === 'start_frame')
              const end = hydrated.frames.find((frame) => frame.panelId === panelId && frame.role === 'end_frame')
              if (!start || !end) throw new Error(`BLOCKED_ASSET_RESOLUTION:${panelId}`)
              return {
                panelId,
                startFrame: { artifactId: start.artifactId, sha256: start.sha256, url: artifactUrl(start.artifactId) },
                endFrame: { artifactId: end.artifactId, sha256: end.sha256, url: artifactUrl(end.artifactId) },
              }
            }),
          }
        }
      } catch {
        storyboard = undefined
      }
    }
  }
  return {
    schemaVersion: 'persona_dream.run_detail.v2',
    status: 'ok',
    mocked: false,
    live: false,
    runRoot,
    stageReportPath: existsSync(resolve(evidenceRoot, 'pipeline_stage_report.json')) ? resolve(evidenceRoot, 'pipeline_stage_report.json') : undefined,
    stages,
    sourceGroupedStages: [],
    runId,
    runKind: fixtureRun ? 'fixture' : revision?.historical === true ? 'historical' : 'active',
    repairEnabled,
    activeRevision: sourceRevisionId ? {
      revisionId: sourceRevisionId,
      manifestSha256: typeof pointer?.revisionManifestSha256 === 'string' ? pointer.revisionManifestSha256 : undefined,
    } : undefined,
    revisionQualification,
    consumers: humanIdea || storyboard ? { humanIdea, storyboard } : undefined,
    earliestIssue: earliest ? {
      phaseId: earliest.id,
      kind: earliest.evidence.state === 'malformed' || earliest.evidence.state === 'semantic_invalid' ? 'malformed' : 'missing',
      reasons: [...earliest.evidence.missingIds, ...earliest.evidence.malformedIds, ...earliest.evidence.semanticInvalidIds],
    } : undefined,
    repairCandidate: candidate,
  }
}
