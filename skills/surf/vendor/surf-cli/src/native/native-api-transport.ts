import { sendToNativeHost } from "./port-manager";

export interface ApiStreamCallbacks {
  onStart: (status: number, headers: Record<string, string>) => void;
  onChunk: (chunk: string) => void;
  onEnd: () => void;
  onError: (error: string) => void;
}

const streamCallbacks = new Map<string, ApiStreamCallbacks>();
let streamIdCounter = 0;

export function handleNativeApiResponse(msg: any): boolean {
  const { type, streamId } = msg;
  
  if (!streamId || !streamCallbacks.has(streamId)) {
    return false;
  }
  
  const callbacks = streamCallbacks.get(streamId)!;
  
  switch (type) {
    case "API_RESPONSE_START":
      callbacks.onStart(msg.status, msg.headers);
      return true;
    case "API_RESPONSE_CHUNK":
      callbacks.onChunk(msg.chunk);
      return true;
    case "API_RESPONSE_END":
      callbacks.onEnd();
      streamCallbacks.delete(streamId);
      return true;
    case "API_RESPONSE_ERROR":
      callbacks.onError(msg.error);
      streamCallbacks.delete(streamId);
      return true;
    default:
      return false;
  }
}

export async function nativeApiFetch(
  url: string,
  options: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
  },
  callbacks: ApiStreamCallbacks
): Promise<void> {
  const streamId = `stream_${++streamIdCounter}_${Date.now()}`;
  
  streamCallbacks.set(streamId, callbacks);
  
  try {
    await sendToNativeHost({
      type: "API_REQUEST",
      streamId,
      url,
      method: options.method || "POST",
      headers: options.headers || {},
      body: options.body,
    });
  } catch (err) {
    streamCallbacks.delete(streamId);
    callbacks.onError(err instanceof Error ? err.message : "Unknown error");
  }
}
