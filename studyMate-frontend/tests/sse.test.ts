import { describe, expect, it } from "vitest";
import { readSSE, SSEFrameParser } from "@/lib/sse";

describe("SSEFrameParser", () => {
  it("parses complete frames and keeps partial ones buffered", () => {
    const parser = new SSEFrameParser();
    expect(parser.push('event: meta\ndata: {"a":1}\n\nevent: delta\ndata: {"text":"hel')).toEqual([
      { event: "meta", data: '{"a":1}' },
    ]);
    expect(parser.push('lo"}\n\n')).toEqual([{ event: "delta", data: '{"text":"hello"}' }]);
    expect(parser.flush()).toEqual([]);
  });

  it("joins multi-line data, ignores comments and CRLF", () => {
    const parser = new SSEFrameParser();
    const frames = parser.push(": keepalive\r\nevent: delta\r\ndata: line one\r\ndata: line two\r\n\r\n");
    expect(frames).toEqual([{ event: "delta", data: "line one\nline two" }]);
  });

  it("defaults the event name to message and flushes a trailing frame", () => {
    const parser = new SSEFrameParser();
    expect(parser.push("data: x")).toEqual([]);
    expect(parser.flush()).toEqual([{ event: "message", data: "x" }]);
  });
});

describe("readSSE", () => {
  it("reads frames from a byte stream split at arbitrary boundaries", async () => {
    const encoder = new TextEncoder();
    const text = 'event: sources\ndata: {"sources":[]}\n\nevent: delta\ndata: {"text":"héllo"}\n\nevent: done\ndata: {}\n\n';
    const bytes = encoder.encode(text);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
        controller.close();
      },
    });
    const seen: string[] = [];
    await readSSE(stream, (frame) => seen.push(`${frame.event}:${frame.data}`));
    expect(seen).toEqual(['sources:{"sources":[]}', 'delta:{"text":"héllo"}', "done:{}"]);
  });
});
