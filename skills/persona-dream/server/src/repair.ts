import { createHash, randomUUID } from 'node:crypto'
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { dirname, resolve } from 'node:path'
import type {
  DreamRunDetailResponse,
  PersonaDreamRepairWorkOrder,
  RepairAttemptReceipt,
} from '../../contracts/src/index'

export interface TauRepairQueuePort {
  enqueue(workOrder: PersonaDreamRepairWorkOrder): Promise<{ queueReceiptPath: string; dagContractPath?: string }>
}

function writeJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
}

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>
}

export class FileTauRepairQueue implements TauRepairQueuePort {
  async enqueue(workOrder: PersonaDreamRepairWorkOrder): Promise<{ queueReceiptPath: string; dagContractPath: string }> {
    const tauRunRoot = resolve(workOrder.runRoot, '.persona-dream', 'repair', 'tau-runs', workOrder.workOrderId)
    const commandSpecsRoot = resolve(tauRunRoot, 'command-specs')
    const dagContractPath = resolve(tauRunRoot, 'dag-contract.json')
    const skillRoot = resolve(workOrder.runRoot, '..', '..')
    const repairScript = resolve(skillRoot, 'scripts', 'execute_local_pipeline_repair.py')
    const sourceManifest = resolve(workOrder.runRoot, 'repair_sources.v1.json')
    const workOrderPath = resolve(workOrder.runRoot, '.persona-dream', 'repair', 'work-orders', `${workOrder.workOrderId}.json`)
    const uvCommand = [
      'uv', 'run', '--project', skillRoot, 'python', repairScript,
    ]
    const installerSpecPath = resolve(commandSpecsRoot, 'repair-installer', 'tau-dispatch-command.json')
    const reviewerSpecPath = resolve(commandSpecsRoot, 'repair-reviewer', 'tau-dispatch-command.json')
    if (!existsSync(installerSpecPath)) writeJson(installerSpecPath, {
      command: [...uvCommand, 'install', '--work-order', workOrderPath, '--sources', sourceManifest, '--tau-handoff'],
      timeout_s: 300,
    })
    if (!existsSync(reviewerSpecPath)) writeJson(reviewerSpecPath, {
      command: [...uvCommand, 'review', '--work-order', workOrderPath, '--tau-handoff'],
      timeout_s: 300,
    })
    if (!existsSync(dagContractPath)) writeJson(dagContractPath, {
      schema: 'tau.dag_contract.v1',
      dag_id: `persona-dream-${workOrder.workOrderId}`,
      goal: {
        goal_id: `persona-dream-${workOrder.runId}-repair`,
        goal_version: 1,
        goal_hash: `sha256:${workOrder.dedupKey}`,
      },
      target: {
        repo: 'grahama1970/agent-skills',
        target: workOrder.runRoot,
        allowed_paths: [
          `${workOrder.runRoot}/.persona-dream/revisions/**`,
          `${workOrder.runRoot}/.persona-dream/repair/**`,
          `${workOrder.runRoot}/.persona-dream/state/**`,
        ],
      },
      entry_node: 'repair-installer',
      terminal_nodes: ['human'],
      limits: { resume: true, default_timeout_seconds: 300, max_total_attempts: 3 },
      nodes: [
        {
          id: 'repair-installer', agent: 'coder', executor: 'local', max_attempts: 1,
          command_spec: installerSpecPath,
          required_evidence: ['repair_revision_manifest'],
        },
        {
          id: 'repair-reviewer', agent: 'reviewer', executor: 'local', max_attempts: 1,
          command_spec: reviewerSpecPath,
          required_evidence: ['revision_promotion_receipt'],
        },
        { id: 'human', agent: 'human', executor: 'human' },
      ],
      edges: [
        { from: 'repair-installer', to: 'repair-reviewer' },
        { from: 'repair-reviewer', to: 'human' },
      ],
      required_evidence: ['repair_revision_manifest', 'revision_promotion_receipt'],
      fail_closed_on: [
        'goal_hash_mismatch', 'target_changed', 'unexpected_node', 'unexpected_edge',
        'missing_required_evidence', 'max_attempts_exceeded', 'malformed_handoff',
        'branch_target_divergence', 'branch_goal_hash_divergence',
      ],
    })
    const path = resolve(workOrder.runRoot, '.persona-dream', 'repair', 'tau-queue', `${workOrder.workOrderId}.json`)
    if (!existsSync(path)) writeJson(path, {
      schemaVersion: 'persona_dream.tau_repair_queue_item.v1',
      status: 'QUEUED',
      queuedAt: new Date().toISOString(),
      workOrderPath,
      dagContractPath,
      workOrder,
    })
    return { queueReceiptPath: path, dagContractPath }
  }
}

export async function enqueueRepairCandidate(
  detail: DreamRunDetailResponse,
  queue: TauRepairQueuePort,
): Promise<{ workOrder: PersonaDreamRepairWorkOrder; workOrderPath: string; queueReceiptPath: string; reused: boolean }> {
  const candidate = detail.repairCandidate
  if (!candidate?.enqueueAllowed || !candidate.dedupKey) throw new Error('repair_candidate_not_enqueueable')
  if (detail.runKind !== 'active') throw new Error('repair_run_is_read_only')

  const repairRoot = resolve(detail.runRoot, '.persona-dream', 'repair')
  const leasePath = resolve(repairRoot, 'leases', `${candidate.dedupKey}.lease`)
  const workOrderId = `repair-${candidate.dedupKey.slice(0, 16)}`
  const workOrderPath = resolve(repairRoot, 'work-orders', `${workOrderId}.json`)
  mkdirSync(dirname(leasePath), { recursive: true })

  let reused = false
  try {
    mkdirSync(leasePath)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error
    reused = true
  }

  if (reused) {
    if (!existsSync(workOrderPath)) throw new Error('repair_lease_without_work_order')
    const workOrder = readJson(workOrderPath) as unknown as PersonaDreamRepairWorkOrder
    const queued = await queue.enqueue(workOrder)
    return { workOrder, workOrderPath, queueReceiptPath: queued.queueReceiptPath, reused: true }
  }

  const createdAt = new Date().toISOString()
  const workOrder: PersonaDreamRepairWorkOrder = {
    schemaVersion: 'persona_dream.repair_work_order.v1',
    workOrderId,
    dedupKey: candidate.dedupKey,
    runId: detail.runId,
    runRoot: detail.runRoot,
    sourceRevisionId: candidate.sourceRevisionId,
    targetRevisionId: `rev_repair_${candidate.dedupKey.slice(0, 12)}`,
    createdAt,
    detection: {
      earliestStalePhase: candidate.earliestRepairPhase,
      selectedThroughPhase: candidate.selectedThroughPhase,
      phaseRange: candidate.phaseRange,
      reasons: detail.earliestIssue?.reasons.map((code) => ({ phaseId: candidate.earliestRepairPhase, code })) ?? [],
    },
    policy: {
      maxAttemptsPerPhase: 3,
      forbiddenSideEffects: [
        'external_network',
        'public_media_publication',
        'paid_provider_call',
        'provider_submission',
        'human_acceptance_fabrication',
      ],
      stopBeforePhase: '11',
    },
    status: 'REQUESTED',
  }
  try {
    writeJson(workOrderPath, workOrder)
    writeJson(resolve(leasePath, 'lease.json'), {
      schemaVersion: 'persona_dream.repair_lease.v1',
      dedupKey: candidate.dedupKey,
      workOrderId,
      ownerId: `persona-dream-api-${process.pid}`,
      acquiredAt: createdAt,
      sourceRevisionId: candidate.sourceRevisionId,
    })
    const queued = await queue.enqueue(workOrder)
    return { workOrder, workOrderPath, queueReceiptPath: queued.queueReceiptPath, reused: false }
  } catch (error) {
    rmSync(leasePath, { recursive: true, force: true })
    throw error
  }
}

export function writeRepairAttempt(runRoot: string, receipt: RepairAttemptReceipt): string {
  if (receipt.attemptNumber < 1 || receipt.attemptNumber > 3) throw new Error('BLOCKED_REPAIR_MAX_ATTEMPTS')
  const path = resolve(
    runRoot,
    '.persona-dream',
    'repair',
    'attempts',
    receipt.workOrderId,
    receipt.phaseId,
    `attempt_${String(receipt.attemptNumber).padStart(2, '0')}.json`,
  )
  writeJson(path, receipt)
  return path
}

export function promoteRevision(options: {
  runRoot: string
  expectedSourceRevisionId: string
  targetRevisionId: string
  targetManifestPath: string
}): string {
  const stateRoot = resolve(options.runRoot, '.persona-dream', 'state')
  const pointerPath = resolve(stateRoot, 'active_revision.json')
  const lockPath = resolve(stateRoot, 'promotion.lock')
  mkdirSync(stateRoot, { recursive: true })
  mkdirSync(lockPath)
  try {
    const current = readJson(pointerPath)
    if (current.revisionId !== options.expectedSourceRevisionId) throw new Error('BLOCKED_REPAIR_PROMOTION_SOURCE_CHANGED')
    const target = readJson(options.targetManifestPath)
    if (target.revisionId !== options.targetRevisionId || target.status !== 'FROZEN_ALL_LOCAL_GATES_PASS') {
      throw new Error('BLOCKED_REPAIR_TARGET_REVISION_NOT_ACCEPTED')
    }
    const manifestSha256 = `sha256:${createHash('sha256').update(readFileSync(options.targetManifestPath)).digest('hex')}`
    const promotedAt = new Date().toISOString()
    const nextPointer = {
      schemaVersion: 'persona_dream.active_revision_pointer.v1',
      runId: current.runId,
      revisionId: options.targetRevisionId,
      revisionManifestSha256: manifestSha256,
      promotedAt,
    }
    const temporary = `${pointerPath}.${randomUUID()}.tmp`
    writeFileSync(temporary, `${JSON.stringify(nextPointer, null, 2)}\n`)
    renameSync(temporary, pointerPath)
    const receiptPath = resolve(stateRoot, `revision_promotion_${options.targetRevisionId}.json`)
    writeJson(receiptPath, {
      schemaVersion: 'persona_dream.revision_promotion_receipt.v1',
      status: 'PASS_REVISION_PROMOTION',
      expectedSourceRevisionId: options.expectedSourceRevisionId,
      targetRevisionId: options.targetRevisionId,
      targetManifestPath: options.targetManifestPath,
      targetManifestSha256: manifestSha256,
      promotedAt,
    })
    return receiptPath
  } finally {
    rmSync(lockPath, { recursive: true, force: true })
  }
}
