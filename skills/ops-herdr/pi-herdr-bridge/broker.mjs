// Minimal pi-intercom broker client (protocol observed from
// nicobailon/pi-intercom broker/{framing,paths,protocol}.ts, MIT).
// Transport: unix socket ~/.pi/agent/intercom/broker.sock,
// frames: 4-byte big-endian length + JSON payload.
import net from "node:net";
import { join } from "node:path";
import { homedir } from "node:os";

const MAX_FRAME_BYTES = 1024 * 1024;

export function brokerSocketPath(env = process.env) {
  const agentDir = env.PI_CODING_AGENT_DIR?.trim() || join(homedir(), ".pi/agent");
  return join(agentDir, "intercom", "broker.sock");
}

export function encodeFrame(msg) {
  const json = JSON.stringify(msg);
  const payloadLength = Buffer.byteLength(json, "utf-8");
  const frame = Buffer.allocUnsafe(4 + payloadLength);
  frame.writeUInt32BE(payloadLength, 0);
  frame.write(json, 4, payloadLength, "utf-8");
  return frame;
}

export function createFrameReader(onMessage, onError, maxFrameBytes = MAX_FRAME_BYTES) {
  let buffer = Buffer.alloc(0);
  return (data) => {
    buffer = Buffer.concat([buffer, data]);
    while (buffer.length >= 4) {
      const payloadLength = buffer.readUInt32BE(0);
      if (payloadLength > maxFrameBytes) {
        onError(new Error(`frame length ${payloadLength} exceeds maximum ${maxFrameBytes}`));
        return;
      }
      if (buffer.length < 4 + payloadLength) return;
      const payload = buffer.subarray(4, 4 + payloadLength);
      buffer = buffer.subarray(4 + payloadLength);
      let msg;
      try {
        msg = JSON.parse(payload.toString("utf-8"));
      } catch (error) {
        onError(new Error(`unparseable broker frame: ${error.message}`));
        return;
      }
      onMessage(msg);
    }
  };
}

export class BrokerClient {
  constructor({ socketPath = brokerSocketPath(), name, cwd = process.cwd(), model = "external-bridge" } = {}) {
    this.socketPath = socketPath;
    this.name = name;
    this.cwd = cwd;
    this.model = model;
    this.sessionId = null;
    this.socket = null;
    this.pending = new Map(); // requestId -> resolver for `sessions`
    this.deliveryWaiters = new Map(); // messageId -> resolver
    this.onInbound = null; // (from, message) => void
    this.registeredResolve = null;
  }

  connect(timeoutMs = 5000) {
    return new Promise((resolvePromise, reject) => {
      const socket = net.connect(this.socketPath);
      this.socket = socket;
      const timer = setTimeout(() => {
        socket.destroy();
        reject(new Error(`broker connect/register timeout after ${timeoutMs}ms at ${this.socketPath}`));
      }, timeoutMs);
      const reader = createFrameReader(
        (msg) => this.#handle(msg),
        (error) => {
          clearTimeout(timer);
          socket.destroy();
          reject(error);
        },
      );
      socket.on("data", reader);
      socket.on("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      socket.on("connect", () => {
        this.registeredResolve = (sessionId) => {
          clearTimeout(timer);
          resolvePromise(sessionId);
        };
        const now = Date.now();
        this.#write({
          type: "register",
          session: {
            cwd: this.cwd,
            model: this.model,
            pid: process.pid,
            startedAt: now,
            lastActivity: now,
            ...(this.name ? { name: this.name } : {}),
            status: "external-bridge",
          },
        });
      });
    });
  }

  #write(msg) {
    this.socket.write(encodeFrame(msg));
  }

  #handle(msg) {
    if (!msg || typeof msg !== "object") return;
    switch (msg.type) {
      case "registered":
        this.sessionId = msg.sessionId;
        if (this.registeredResolve) {
          this.registeredResolve(msg.sessionId);
          this.registeredResolve = null;
        }
        break;
      case "sessions": {
        const resolver = this.pending.get(msg.requestId);
        if (resolver) {
          this.pending.delete(msg.requestId);
          resolver(msg.sessions);
        }
        break;
      }
      case "delivered":
      case "delivery_failed": {
        const waiter = this.deliveryWaiters.get(msg.messageId);
        if (waiter) {
          this.deliveryWaiters.delete(msg.messageId);
          waiter(msg);
        }
        break;
      }
      case "message":
        if (this.onInbound) this.onInbound(msg.from, msg.message);
        break;
      default:
        break;
    }
  }

  listSessions(timeoutMs = 5000) {
    const requestId = `req-${Date.now()}-${process.pid}`;
    return new Promise((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error(`broker list timeout after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(requestId, (sessions) => {
        clearTimeout(timer);
        resolvePromise(sessions);
      });
      this.#write({ type: "list", requestId });
    });
  }

  send(to, text, { replyTo, expectsReply, timeoutMs = 10000 } = {}) {
    const messageId = `bridge-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
    const message = {
      id: messageId,
      timestamp: Date.now(),
      ...(replyTo ? { replyTo } : {}),
      ...(expectsReply !== undefined ? { expectsReply } : {}),
      content: { text },
    };
    return new Promise((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.deliveryWaiters.delete(messageId);
        reject(new Error(`broker delivery result timeout after ${timeoutMs}ms for ${messageId}`));
      }, timeoutMs);
      this.deliveryWaiters.set(messageId, (result) => {
        clearTimeout(timer);
        resolvePromise(result);
      });
      this.#write({ type: "send", to, message });
    });
  }

  close() {
    if (this.socket) {
      try {
        this.#write({ type: "unregister" });
      } catch {
        // socket already gone; close proceeds
      }
      this.socket.end();
      this.socket.destroy();
      this.socket = null;
    }
  }
}
