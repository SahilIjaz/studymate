/**
 * Minimal Server-Sent Events frame parser for `fetch` response bodies.
 *
 * The native EventSource only supports GET, and our question endpoint is a
 * POST with a JSON body, so frames are parsed by hand. Frames are separated
 * by a blank line; each has `event:` and `data:` lines. Multi-line `data:` is
 * joined with newlines per the spec.
 */

export type SSEFrame = { event: string; data: string };

export class SSEFrameParser {
  private buffer = "";

  push(chunk: string): SSEFrame[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const frames: SSEFrame[] = [];
    let index: number;
    while ((index = this.buffer.indexOf("\n\n")) !== -1) {
      const raw = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const frame = parseFrame(raw);
      if (frame) frames.push(frame);
    }
    return frames;
  }

  flush(): SSEFrame[] {
    const rest = this.buffer;
    this.buffer = "";
    const frame = rest.trim() ? parseFrame(rest) : null;
    return frame ? [frame] : [];
  }
}

function parseFrame(raw: string): SSEFrame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

export async function readSSE(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: SSEFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEFrameParser();
  const abort = () => reader.cancel().catch(() => undefined);
  signal?.addEventListener("abort", abort, { once: true });
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const frame of parser.push(decoder.decode(value, { stream: true }))) onFrame(frame);
    }
    for (const frame of parser.flush()) onFrame(frame);
  } finally {
    signal?.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
