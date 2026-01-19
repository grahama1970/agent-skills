/**
 * Rewind Hook - Git-based File Restoration for Pi Agent
 *
 * Compatible with pi-mono v0.25.x (uses available events: session, turn_start, turn_end, branch)
 *
 * Creates automatic git checkpoints at each turn, allowing you to:
 * - Restore files to any previous checkpoint
 * - Branch with code restoration options
 * - Undo accidental file changes
 *
 * Checkpoints are stored as git refs under refs/pi-checkpoints/<session-id>/
 *
 * Based on: https://github.com/nicobailon/pi-rewind-hook (adapted for 0.25.x)
 */

import type { HookAPI, BranchEvent, TurnStartEvent, TurnEndEvent, SessionEvent } from "@mariozechner/pi-coding-agent/hooks";

// Configuration
const MAX_CHECKPOINTS = 100;
const CHECKPOINT_REF_PREFIX = "refs/pi-checkpoints";
const SILENT_MODE = process.env.PI_REWIND_SILENT === "true";

interface Checkpoint {
  turnIndex: number;
  commitHash: string;
  timestamp: number;
  entryId?: string;
}

// Session state
let sessionId: string | null = null;
let checkpoints: Map<number, Checkpoint> = new Map();
let pendingWorktreeHash: string | null = null;
let lastUndoBackup: string | null = null;
let isGitRepo = false;

/**
 * Generate a unique session ID
 */
function generateSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
}

/**
 * Execute a git command and return stdout
 */
async function git(ctx: { exec: Function }, args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return ctx.exec("git", args);
}

/**
 * Check if we're in a git repository
 */
async function checkGitRepo(ctx: { exec: Function }): Promise<boolean> {
  const result = await git(ctx, ["rev-parse", "--is-inside-work-tree"]);
  return result.code === 0 && result.stdout.trim() === "true";
}

/**
 * Capture current worktree state as a commit (without affecting HEAD)
 */
async function captureWorktree(ctx: { exec: Function }): Promise<string | null> {
  try {
    // Check for changes (staged or unstaged)
    const status = await git(ctx, ["status", "--porcelain"]);
    if (status.code !== 0) return null;

    // Get current HEAD as parent
    const headResult = await git(ctx, ["rev-parse", "HEAD"]);
    if (headResult.code !== 0) return null;
    const parentCommit = headResult.stdout.trim();

    if (status.stdout.trim() === "") {
      // No changes, use current HEAD
      return parentCommit;
    }

    // Create a tree from the current worktree state
    // First, add all files to a temporary index
    const addResult = await git(ctx, ["add", "-A", "--intent-to-add"]);
    if (addResult.code !== 0) return null;

    // Write tree from index
    const writeTreeResult = await git(ctx, ["write-tree"]);
    if (writeTreeResult.code !== 0) return null;
    const treeHash = writeTreeResult.stdout.trim();

    // Create commit object (without updating HEAD)
    const commitResult = await git(ctx, [
      "commit-tree",
      treeHash,
      "-p",
      parentCommit,
      "-m",
      `Pi checkpoint ${new Date().toISOString()}`
    ]);
    if (commitResult.code !== 0) return null;

    // Reset index to HEAD (don't keep our temp staging)
    await git(ctx, ["reset", "HEAD"]);

    return commitResult.stdout.trim();
  } catch (e) {
    return null;
  }
}

/**
 * Save checkpoint as a git ref
 */
async function saveCheckpointRef(ctx: { exec: Function }, checkpoint: Checkpoint): Promise<boolean> {
  if (!sessionId) return false;

  const refName = `${CHECKPOINT_REF_PREFIX}/${sessionId}/turn-${checkpoint.turnIndex}`;
  const result = await git(ctx, ["update-ref", refName, checkpoint.commitHash]);
  return result.code === 0;
}

/**
 * Restore files from a checkpoint
 */
async function restoreFromCheckpoint(ctx: { exec: Function; ui: any }, checkpoint: Checkpoint): Promise<boolean> {
  try {
    // Create backup of current state first
    const backupHash = await captureWorktree(ctx);
    if (backupHash) {
      lastUndoBackup = backupHash;
    }

    // Checkout files from checkpoint (keep HEAD unchanged)
    const result = await git(ctx, ["checkout", checkpoint.commitHash, "--", "."]);
    if (result.code !== 0) {
      ctx.ui.notify(`Failed to restore files: ${result.stderr}`, "error");
      return false;
    }

    ctx.ui.notify(`Restored files to turn ${checkpoint.turnIndex} checkpoint`, "info");
    return true;
  } catch (e) {
    ctx.ui.notify(`Restore failed: ${e}`, "error");
    return false;
  }
}

/**
 * Undo last restore operation
 */
async function undoRestore(ctx: { exec: Function; ui: any }): Promise<boolean> {
  if (!lastUndoBackup) {
    ctx.ui.notify("No restore to undo", "warning");
    return false;
  }

  const result = await git(ctx, ["checkout", lastUndoBackup, "--", "."]);
  if (result.code === 0) {
    ctx.ui.notify("Undo successful - files restored to previous state", "info");
    lastUndoBackup = null;
    return true;
  }

  ctx.ui.notify(`Undo failed: ${result.stderr}`, "error");
  return false;
}

/**
 * Prune old checkpoints to stay under limit
 */
async function pruneCheckpoints(ctx: { exec: Function }): Promise<void> {
  if (!sessionId || checkpoints.size <= MAX_CHECKPOINTS) return;

  // Sort by turn index, remove oldest
  const sorted = Array.from(checkpoints.entries()).sort((a, b) => a[0] - b[0]);
  const toRemove = sorted.slice(0, checkpoints.size - MAX_CHECKPOINTS);

  for (const [turnIndex] of toRemove) {
    const refName = `${CHECKPOINT_REF_PREFIX}/${sessionId}/turn-${turnIndex}`;
    await git(ctx, ["update-ref", "-d", refName]);
    checkpoints.delete(turnIndex);
  }
}

/**
 * List available checkpoints for UI
 */
function getCheckpointOptions(): string[] {
  const options: string[] = [];
  const sorted = Array.from(checkpoints.entries()).sort((a, b) => b[0] - a[0]); // Newest first

  for (const [turnIndex, cp] of sorted.slice(0, 10)) {
    const time = new Date(cp.timestamp).toLocaleTimeString();
    options.push(`Turn ${turnIndex} (${time})`);
  }

  return options;
}

export default function (pi: HookAPI) {
  // Session start: Initialize state
  pi.on("session", async (event: SessionEvent, ctx) => {
    if (event.reason !== "start") return;

    // Check if we're in a git repo
    isGitRepo = await checkGitRepo(ctx);
    if (!isGitRepo) return;

    // Generate new session ID
    sessionId = generateSessionId();
    checkpoints.clear();
    lastUndoBackup = null;

    if (!SILENT_MODE) {
      ctx.ui.notify(`Rewind enabled (session: ${sessionId.substring(0, 8)})`, "info");
    }
  });

  // Turn start: Capture worktree state before agent acts
  pi.on("turn_start", async (event: TurnStartEvent, ctx) => {
    if (!isGitRepo || !sessionId) return;

    // Capture current state before the turn
    pendingWorktreeHash = await captureWorktree(ctx);
  });

  // Turn end: Save checkpoint with the captured state
  pi.on("turn_end", async (event: TurnEndEvent, ctx) => {
    if (!isGitRepo || !sessionId || !pendingWorktreeHash) return;

    const checkpoint: Checkpoint = {
      turnIndex: event.turnIndex,
      commitHash: pendingWorktreeHash,
      timestamp: Date.now()
    };

    checkpoints.set(event.turnIndex, checkpoint);
    await saveCheckpointRef(ctx, checkpoint);
    await pruneCheckpoints(ctx);

    pendingWorktreeHash = null;

    if (!SILENT_MODE && event.turnIndex % 5 === 0) {
      ctx.ui.notify(`Checkpoint ${event.turnIndex} saved`, "info");
    }
  });

  // Branch: Offer restore options
  pi.on("branch", async (event: BranchEvent, ctx) => {
    if (!isGitRepo || !sessionId || !ctx.hasUI) return;
    if (checkpoints.size === 0) return;

    const options = [
      "Keep current files (conversation only)",
      "Restore files to branch point",
      ...getCheckpointOptions().map((o) => `Restore to: ${o}`),
      ...(lastUndoBackup ? ["Undo last restore"] : [])
    ];

    const choice = await ctx.ui.select("Rewind Options", options);

    if (!choice) return; // Cancelled

    if (choice === "Keep current files (conversation only)") {
      return { skipConversationRestore: false };
    }

    if (choice === "Restore files to branch point") {
      const targetCheckpoint = checkpoints.get(event.targetTurnIndex);
      if (targetCheckpoint) {
        await restoreFromCheckpoint(ctx, targetCheckpoint);
      }
      return { skipConversationRestore: false };
    }

    if (choice === "Undo last restore") {
      await undoRestore(ctx);
      return { skipConversationRestore: true };
    }

    // Restore to specific checkpoint
    const match = choice.match(/Turn (\d+)/);
    if (match) {
      const turnIndex = parseInt(match[1], 10);
      const checkpoint = checkpoints.get(turnIndex);
      if (checkpoint) {
        await restoreFromCheckpoint(ctx, checkpoint);
      }
    }

    return { skipConversationRestore: false };
  });
}
