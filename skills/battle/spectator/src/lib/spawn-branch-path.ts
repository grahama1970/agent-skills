import type { LineageSpawnBranch } from "./layout-lineage-rails";

/** Spawn-at-event branch: vertical at parent handoff, horizontal into child lane. */
export function spawnBranchPath(branch: LineageSpawnBranch) {
  return `M ${branch.x} ${branch.parentY} L ${branch.x} ${branch.childY} L ${branch.childEntryX} ${branch.childY}`;
}
