/**
 * Tool-call hygiene for the zen adapter: the zen compat layer occasionally
 * streams a tool call with an empty id/name. The engine then fails with
 * UNKNOWN_TOOL, and the empty `tool_call_id` pollutes session history — the
 * Console rejects a repeated `tool_call_id: ""` as a duplicate on a later
 * turn. Two layers handle it.
 *
 * @module dsh-llm-opencode-zen/tool-call-guard
 */

import type { StreamChunk } from "@deepseek-ai/dsh-llm";

/** Drop tool-call blocks with an empty id or empty name before they reach
 * the engine (the engine would otherwise execute an empty tool name). */
export async function* dropEmptyToolCalls(
  src: AsyncIterable<StreamChunk>,
): AsyncIterable<StreamChunk> {
  let buf: StreamChunk[] | null = null;
  for await (const c of src) {
    if (c.type === "block-start" && c.blockType === "tool-call") {
      buf = [c];
      continue;
    }
    if (buf === null) {
      yield c;
      continue;
    }
    buf.push(c);
    if (c.type === "block-end") {
      const b = c.block;
      if (b.type === "tool-call" && b.id.length > 0 && b.name.length > 0)
        for (const x of buf) yield x;
      buf = null;
    }
  }
}

/** Backstop for ids replayed from a session cache (which bypasses the stream
 * filter): rewrite empty tool-call ids to deterministic unique values before
 * the request leaves. Assistant `tool_calls` are numbered first; tool result
 * messages reuse the same numbering in history order. */
export function normalizeToolCallIds(messages: unknown[]): void {
  let recovered = 0;
  for (const message of messages as { tool_calls?: { id?: string }[] }[]) {
    for (const call of message.tool_calls ?? []) {
      if (call.id !== undefined && call.id.length === 0)
        call.id = `call_recovered_${recovered++}`;
    }
  }
  recovered = 0;
  for (const message of messages as { tool_call_id?: string }[]) {
    if (message.tool_call_id !== undefined && message.tool_call_id.length === 0)
      message.tool_call_id = `call_recovered_${recovered++}`;
  }
}
