import { afterEach, beforeEach, describe, expect, it } from "vitest";

declare const require: (moduleName: string) => any;

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { acquireBrowserLock, browserLockBlockerPayload, getBrowserLockDir } = require("../../native/browser-lock.cjs");

describe("browser lock", () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "surf-browser-lock-test-"));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it("creates and releases a per-socket lock", () => {
    const lock = acquireBrowserLock("/tmp/surf.sock", tempDir);
    const lockDir = getBrowserLockDir("/tmp/surf.sock", tempDir);

    expect(lock.lockDir).toBe(lockDir);
    expect(fs.existsSync(path.join(lockDir, "owner.json"))).toBe(true);

    lock.release();

    expect(fs.existsSync(lockDir)).toBe(false);
  });

  it("uses independent lock directories for different sockets", () => {
    const first = acquireBrowserLock("/tmp/surf-agent-a.sock", tempDir);
    const second = acquireBrowserLock("/tmp/surf-agent-b.sock", tempDir);

    expect(first.lockDir).not.toBe(second.lockDir);

    first.release();
    second.release();
  });

  it("removes stale locks owned by dead processes before acquiring", () => {
    const lockDir = getBrowserLockDir("/tmp/surf.sock", tempDir);
    fs.mkdirSync(lockDir);
    fs.writeFileSync(
      path.join(lockDir, "owner.json"),
      JSON.stringify({ pid: -1, token: "dead-owner", socketPath: "/tmp/surf.sock" }),
    );
    const staleTime = new Date(Date.now() - 60_000);
    fs.utimesSync(lockDir, staleTime, staleTime);

    const lock = acquireBrowserLock("/tmp/surf.sock", tempDir, { staleMs: 1 });

    expect(lock.lockDir).toBe(lockDir);
    expect(JSON.parse(fs.readFileSync(path.join(lockDir, "owner.json"), "utf8")).pid).toBe(
      process.pid,
    );

    lock.release();
  });

  it("does not steal an old lock from a live process", () => {
    const lockDir = getBrowserLockDir("/tmp/surf.sock", tempDir);
    fs.mkdirSync(lockDir);
    fs.writeFileSync(
      path.join(lockDir, "owner.json"),
      JSON.stringify({ pid: process.pid, token: "live-owner", socketPath: "/tmp/surf.sock" }),
    );
    const staleTime = new Date(Date.now() - 60_000);
    fs.utimesSync(lockDir, staleTime, staleTime);

    expect(() =>
      acquireBrowserLock("/tmp/surf.sock", tempDir, {
        timeoutMs: -1,
        staleMs: 1,
        sleep: () => undefined,
      }),
    ).toThrow("Timed out waiting for browser lock");
    expect(fs.existsSync(path.join(lockDir, "owner.json"))).toBe(true);
  });

  it("does not release a replacement lock owned by another process", () => {
    const first = acquireBrowserLock("/tmp/surf.sock", tempDir);
    const lockDir = first.lockDir;
    fs.rmSync(lockDir, { recursive: true, force: true });
    fs.mkdirSync(lockDir);
    fs.writeFileSync(
      path.join(lockDir, "owner.json"),
      JSON.stringify({ pid: process.pid, token: "replacement", socketPath: "/tmp/surf.sock" }),
    );

    first.release();

    expect(fs.existsSync(path.join(lockDir, "owner.json"))).toBe(true);
  });

  it("times out while a fresh lock is held", () => {
    const held = acquireBrowserLock("/tmp/surf.sock", tempDir);

    expect(() =>
      acquireBrowserLock("/tmp/surf.sock", tempDir, {
        timeoutMs: -1,
        staleMs: 60_000,
        sleep: () => undefined,
      }),
    ).toThrow(/Timed out waiting for browser lock.*owner_pid=.*owner_socket=.*lock_dir=.*Do not use --no-lock/s);

    held.release();
  });

  it("includes owner metadata when a live process holds the lock", () => {
    const lockDir = getBrowserLockDir("/tmp/surf.sock", tempDir);
    fs.mkdirSync(lockDir);
    fs.writeFileSync(
      path.join(lockDir, "owner.json"),
      JSON.stringify({
        pid: process.pid,
        token: "live-owner",
        socketPath: "unix:/tmp/surf.sock",
        createdAt: "2026-07-25T13:58:59.000Z",
      }),
    );

    expect(() =>
      acquireBrowserLock("/tmp/surf.sock", tempDir, {
        timeoutMs: -1,
        staleMs: 60_000,
        sleep: () => undefined,
      }),
    ).toThrow(
      /owner_pid=.*owner_created_at=2026-07-25T13:58:59.000Z owner_socket=unix:\/tmp\/surf.sock lock_dir=.*separate Surf socket\/profile/s,
    );
  });

  it("creates a first-class lock blocker payload with owner metadata", () => {
    const payload = browserLockBlockerPayload({
      owner: {
        pid: process.pid,
        socketPath: "unix:/tmp/surf.sock",
        createdAt: "2026-07-25T13:58:59.000Z",
        tool: "webgpt.submit",
      },
      lockDir: "/tmp/surf-lock-example",
      endpointKey: "unix:/tmp/surf.sock",
      timeoutMs: 60000,
    });

    expect(payload.schema).toBe("surf.browser_lock_blocker.v1");
    expect(payload.status).toBe("BLOCKED");
    expect(payload.blocker).toBe("surf_browser_lock_timeout");
    expect(payload.owner?.pid).toBe(process.pid);
    expect(payload.owner?.socket).toBe("unix:/tmp/surf.sock");
    expect(payload.owner?.tool).toBe("webgpt.submit");
    expect(payload.recovery.do_not_use_no_lock_for_browser_handlers).toBe(true);
  });
});
