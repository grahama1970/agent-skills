const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const DEFAULT_STALE_MS = 30000;
const DEFAULT_TIMEOUT_MS = 60000;
const DEFAULT_MIN_WAIT_MS = 50;
const DEFAULT_MAX_WAIT_MS = 1000;

function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function getBrowserLockDir(endpointKey, tempDir) {
  const hash = crypto.createHash("sha256").update(endpointKey).digest("hex").slice(0, 16);
  return path.join(tempDir, `surf-lock-${hash}`);
}

function createToken() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return crypto.randomBytes(16).toString("hex");
}

function readLockOwner(lockDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(lockDir, "owner.json"), "utf8"));
  } catch (error) {
    if (error && (error.code === "ENOENT" || error instanceof SyntaxError)) return null;
    throw error;
  }
}

function isProcessAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return Boolean(error && error.code === "EPERM");
  }
}

function writeLockOwner(lockDir, socketPath, token) {
  fs.writeFileSync(
    path.join(lockDir, "owner.json"),
    JSON.stringify({ pid: process.pid, token, socketPath, createdAt: new Date().toISOString() }),
  );
}

function removeLockDir(lockDir) {
  fs.rmSync(lockDir, { recursive: true, force: true });
}

function getLockTimestamp(lockDir, owner) {
  const target = owner ? path.join(lockDir, "owner.json") : lockDir;
  try {
    return fs.statSync(target).mtimeMs;
  } catch (error) {
    if (error && error.code === "ENOENT") return 0;
    throw error;
  }
}

function ownerMatches(left, right) {
  if (!left && !right) return true;
  return Boolean(left && right && left.token && left.token === right.token);
}

function formatLockOwner(owner, lockDir) {
  if (!owner) return `owner=unknown lockDir=${lockDir}`;
  const fields = [
    `owner_pid=${owner.pid ?? "unknown"}`,
    `owner_created_at=${owner.createdAt ?? "unknown"}`,
    `owner_socket=${owner.socketPath ?? "unknown"}`,
    `lock_dir=${lockDir}`,
  ];
  if (owner.tool) fields.push(`owner_tool=${owner.tool}`);
  if (owner.command) fields.push(`owner_command=${owner.command}`);
  return fields.join(" ");
}

function browserLockBlockerPayload({ owner, lockDir, endpointKey, timeoutMs }) {
  return {
    schema: "surf.browser_lock_blocker.v1",
    status: "BLOCKED",
    blocker: "surf_browser_lock_timeout",
    reason: "Timed out waiting for the per-socket Surf browser lock.",
    timeout_ms: timeoutMs,
    lock_dir: lockDir,
    endpoint_key: endpointKey,
    owner: owner
      ? {
          pid: owner.pid ?? null,
          created_at: owner.createdAt ?? null,
          socket: owner.socketPath ?? null,
          tool: owner.tool ?? null,
          command: owner.command ?? null,
        }
      : null,
    recovery: {
      do_not_use_no_lock_for_browser_handlers: true,
      next_command: "wait for the owner process to finish or run this lane through a separate Surf socket/profile",
    },
  };
}

function createBrowserLockTimeoutError({ owner, lockDir, endpointKey, timeoutMs }) {
  const payload = browserLockBlockerPayload({ owner, lockDir, endpointKey, timeoutMs });
  const error = new Error(
    `Timed out waiting for browser lock after ${Math.round(timeoutMs / 1000)}s. ${formatLockOwner(owner, lockDir)}. Do not use --no-lock for browser-handler submits; wait for the owner or use a separate Surf socket/profile.`,
  );
  error.code = "SURF_BROWSER_LOCK_TIMEOUT";
  error.surfLockBlocker = payload;
  return error;
}

function tryCreateStaleClaim(lockDir, staleMs, now = Date.now()) {
  const claimDir = path.join(lockDir, "stale-claim");
  try {
    fs.mkdirSync(claimDir);
    return claimDir;
  } catch (error) {
    if (!error || error.code !== "EEXIST") throw error;
    try {
      if (now - fs.statSync(claimDir).mtimeMs > staleMs) {
        fs.rmSync(claimDir, { recursive: true, force: true });
      }
    } catch (claimError) {
      if (!claimError || claimError.code !== "ENOENT") throw claimError;
    }
    return null;
  }
}

function claimAndRemoveStaleLock(lockDir, staleMs, now = Date.now()) {
  let lockStats;
  try {
    lockStats = fs.statSync(lockDir);
  } catch (error) {
    if (error && error.code === "ENOENT") return false;
    throw error;
  }

  const inspectedOwner = readLockOwner(lockDir);
  if (inspectedOwner && isProcessAlive(inspectedOwner.pid)) return false;
  if (now - getLockTimestamp(lockDir, inspectedOwner) <= staleMs) return false;

  const claimDir = tryCreateStaleClaim(lockDir, staleMs, now);
  if (!claimDir) return false;

  try {
    const currentOwner = readLockOwner(lockDir);
    if (!ownerMatches(inspectedOwner, currentOwner)) return false;
    if (currentOwner && isProcessAlive(currentOwner.pid)) return false;
    if (!currentOwner && Date.now() - lockStats.mtimeMs <= staleMs) return false;

    removeLockDir(lockDir);
    return true;
  } finally {
    try {
      fs.rmSync(claimDir, { recursive: true, force: true });
    } catch {}
  }
}

function acquireBrowserLock(socketPath, tempDir, options = {}) {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const staleMs = options.staleMs ?? DEFAULT_STALE_MS;
  const sleep = options.sleep ?? sleepSync;
  const lockDir = getBrowserLockDir(socketPath, tempDir);
  const startedAt = Date.now();
  let waitMs = options.minWaitMs ?? DEFAULT_MIN_WAIT_MS;
  const maxWaitMs = options.maxWaitMs ?? DEFAULT_MAX_WAIT_MS;

  while (true) {
    const token = createToken();
    try {
      fs.mkdirSync(lockDir, { recursive: false, mode: 0o700 });
      try {
        writeLockOwner(lockDir, socketPath, token);
      } catch (error) {
        removeLockDir(lockDir);
        throw error;
      }
      let released = false;
      return {
        lockDir,
        release() {
          if (released) return;
          released = true;
          const owner = readLockOwner(lockDir);
          if (owner && owner.token === token) removeLockDir(lockDir);
        },
      };
    } catch (error) {
      if (!error || error.code !== "EEXIST") throw error;
    }

    if (claimAndRemoveStaleLock(lockDir, staleMs)) continue;

    if (Date.now() - startedAt >= timeoutMs) {
      const owner = readLockOwner(lockDir);
      throw createBrowserLockTimeoutError({ owner, lockDir, endpointKey: socketPath, timeoutMs });
    }

    sleep(waitMs);
    waitMs = Math.min(Math.round(waitMs * 1.5), maxWaitMs);
  }
}

module.exports = {
  DEFAULT_STALE_MS,
  DEFAULT_TIMEOUT_MS,
  acquireBrowserLock,
  browserLockBlockerPayload,
  getBrowserLockDir,
};
