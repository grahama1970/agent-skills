// Draggable split handle between workspace panes (user spec): wide invisible
// grab zone, hover/drag highlight, indicator dots.

export function ResizeHandle({
  pane,
  isDragging,
  onMouseDown,
  onDoubleClick,
}: {
  pane: string
  isDragging: boolean
  onMouseDown: (event: React.MouseEvent) => void
  onDoubleClick?: () => void
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${pane} pane`}
      data-qid={`deck:resize:${pane}`}
      title={`Drag to resize the ${pane} pane · double-click to reset width`}
      onMouseDown={onMouseDown}
      onDoubleClick={onDoubleClick}
      className={`group relative z-20 h-full w-1.5 flex-shrink-0 cursor-col-resize select-none transition-colors ${
        isDragging ? 'bg-cyan-500' : 'bg-slate-800/60 hover:bg-cyan-500/80'
      }`}
    >
      <div className="absolute inset-y-0 -left-1 -right-1 z-30" />
      <div className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <span className="h-0.5 w-0.5 rounded-full bg-slate-200" />
        <span className="h-0.5 w-0.5 rounded-full bg-slate-200" />
        <span className="h-0.5 w-0.5 rounded-full bg-slate-200" />
      </div>
    </div>
  )
}
