type Entry = {
  id: string
  name: string
}

export function IndexDerivedQid({ entries }: { entries: Entry[] }) {
  return (
    <div>
      {entries.map((entry, index) => (
        <button
          key={entry.id}
          data-qid={`queue:item:select:${index}`}
          data-qs-action="QUEUE_SELECT"
          title={`Select ${entry.name}`}
          onClick={() => {}}
        >
          Select
        </button>
      ))}
    </div>
  )
}
