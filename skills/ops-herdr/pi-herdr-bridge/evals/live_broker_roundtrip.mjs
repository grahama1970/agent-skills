// Live e2e: register two clients on the REAL pi-intercom broker, send a
// message from one to the other, and require the listener to read it back.
// Touches no real agent session. Exits 0 with {"status":"PASS"} on success.
import { BrokerClient, brokerSocketPath } from "../broker.mjs";

const name = `bridge-eval-${process.pid}`;
const listener = new BrokerClient({ name });
const sender = new BrokerClient({ name: `${name}-sender` });

const received = new Promise((resolvePromise) => {
  listener.onInbound = (from, message) => resolvePromise({ from, message });
});

try {
  const listenerId = await listener.connect();
  await sender.connect();
  const sessions = await sender.listSessions();
  const peer = sessions.find((s) => s.id === listenerId);
  if (!peer) throw new Error(`listener ${listenerId} not in broker session list`);

  const text = `roundtrip-${Date.now()}`;
  const delivery = await sender.send(listenerId, text);
  const inbound = await Promise.race([
    received,
    new Promise((_, reject) => setTimeout(() => reject(new Error("no inbound message within 5s")), 5000)),
  ]);
  if (inbound.message.content.text !== text) {
    throw new Error(`readback mismatch: ${inbound.message.content.text}`);
  }
  console.log(JSON.stringify({
    status: "PASS",
    socket: brokerSocketPath(),
    listener_session_id: listenerId,
    delivery_result: delivery.type,
    readback_text: inbound.message.content.text,
    broker_received_at: inbound.message.brokerReceivedAt ?? null,
  }, null, 2));
  process.exit(0);
} catch (error) {
  console.log(JSON.stringify({ status: "FAIL", error: String(error) }));
  process.exit(1);
} finally {
  listener.close();
  sender.close();
}
