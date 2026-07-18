// Barrel export for the Watch skill's UI package (GOAL gate G1).
// External shells (e.g. ux-lab) should mount Watch UI from here instead of
// keeping their own copies of these components.
export { WatchReportView, yoloLabelForOverlay, latestYoloLabelEventForTrack, yoloLabelFromEvent } from './components/WatchReportView'
export { WatchAgentPaneConverged } from './components/WatchAgentPaneConverged'
export { SharedChatShell } from './SharedChatShell'
export type { SharedChatShellProps, SharedChatAdapterOptions } from './SharedChatShell'
export * from './memory-turn'
