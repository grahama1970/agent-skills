export function DuplicateLiteralQid() {
  return (
    <div>
      <button data-qid="queue:action:approve" data-qs-action="QUEUE_APPROVE_A" title="Approve A" onClick={() => {}}>
        Approve A
      </button>
      <button data-qid="queue:action:approve" data-qs-action="QUEUE_APPROVE_B" title="Approve B" onClick={() => {}}>
        Approve B
      </button>
    </div>
  )
}
