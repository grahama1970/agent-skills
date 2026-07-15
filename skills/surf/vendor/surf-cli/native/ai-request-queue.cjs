class KeyedRequestQueue {
  constructor(delayMs = 0) {
    this.delayMs = delayMs;
    this.queues = new Map();
    this.activeKeys = new Set();
  }

  enqueue(key, handler) {
    const queueKey = String(key || "global");
    return new Promise((resolve, reject) => {
      const queue = this.queues.get(queueKey) || [];
      queue.push({ handler, resolve, reject });
      this.queues.set(queueKey, queue);
      this.process(queueKey);
    });
  }

  async process(key) {
    const queue = this.queues.get(key);
    if (this.activeKeys.has(key) || !queue?.length) return;
    this.activeKeys.add(key);
    const { handler, resolve, reject } = queue.shift();
    try {
      resolve(await handler());
    } catch (error) {
      reject(error);
    } finally {
      this.activeKeys.delete(key);
      if (!queue.length) this.queues.delete(key);
      setTimeout(() => this.process(key), this.delayMs);
    }
  }
}

module.exports = { KeyedRequestQueue };
