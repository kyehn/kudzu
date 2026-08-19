// Regression test for dropEmptyToolCalls: tool-call blocks with an empty id
// or empty name must never reach the engine (they pollute history with a
// `tool_call_id: ""` the Console rejects as a duplicate on a later turn).
import assert from "node:assert/strict";
import test from "node:test";
import {
  dropEmptyToolCalls,
  normalizeToolCallIds,
} from "../lib/tool-call-guard.js";

function callChunks(index, { id, name, args = "{}" }) {
  const pieces = [args.slice(0, 2), args.slice(2)];
  return [
    { type: "block-start", index, blockType: "tool-call" },
    { type: "tool-call-delta", index, id, name, argumentsDelta: pieces[0] },
    { type: "tool-call-delta", index, id, name, argumentsDelta: pieces[1] },
    {
      type: "block-end",
      index,
      block: { type: "tool-call", id, name, arguments: args },
    },
  ];
}

async function collect(stream) {
  const out = [];
  for await (const c of dropEmptyToolCalls(stream)) out.push(c);
  return out;
}

test("passes through valid tool-call blocks", async () => {
  const input = [
    { type: "block-start", index: 0, blockType: "reasoning" },
    { type: "reasoning-delta", index: 0, text: "think" },
    {
      type: "block-end",
      index: 0,
      block: { type: "reasoning", text: "think" },
    },
    ...callChunks(1, { id: "call_1", name: "bash" }),
  ];
  const out = await collect(input);
  assert.equal(
    out.filter((c) => c.type === "block-end" && c.block.type === "tool-call")
      .length,
    1,
  );
});

test("drops tool-call blocks with empty id", async () => {
  const out = await collect(callChunks(1, { id: "", name: "bash" }));
  assert.equal(out.length, 0);
});

test("drops tool-call blocks with empty name", async () => {
  const out = await collect(callChunks(1, { id: "call_1", name: "" }));
  assert.equal(out.length, 0);
});

test("keeps sibling blocks around a dropped tool-call", async () => {
  const input = [
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text: "hi" },
    { type: "block-end", index: 0, block: { type: "text", text: "hi" } },
    ...callChunks(1, { id: "", name: "" }),
    ...callChunks(2, { id: "call_2", name: "bash", args: '{"x":1}' }),
  ];
  const out = await collect(input);
  assert.equal(out[0].type, "block-start");
  assert.equal(out[out.length - 1].type, "block-end");
  const ends = out.filter((c) => c.type === "block-end");
  assert.equal(ends.length, 2);
  assert.equal(ends[1].block.type, "tool-call");
  assert.equal(ends[1].block.id, "call_2");
});

test("normalizes empty tool-call ids in an outgoing request", () => {
  const messages = [
    { role: "assistant", tool_calls: [{ id: "", function: { name: "bash" } }] },
    { role: "tool", tool_call_id: "" },
    {
      role: "assistant",
      tool_calls: [
        { id: "", function: { name: "bash" } },
        { id: "call_1", function: { name: "ls" } },
        { id: "", function: { name: "cat" } },
      ],
    },
    { role: "tool", tool_call_id: "" },
    { role: "tool", tool_call_id: "call_1" },
    { role: "tool", tool_call_id: "" },
  ];
  normalizeToolCallIds(messages);
  const ids = messages.flatMap((m) =>
    m.tool_call_id !== undefined
      ? [m.tool_call_id]
      : (m.tool_calls ?? []).map((t) => t.id),
  );
  assert.deepEqual(ids, [
    "call_recovered_0",
    "call_recovered_0",
    "call_recovered_1",
    "call_1",
    "call_recovered_2",
    "call_recovered_1",
    "call_1",
    "call_recovered_2",
  ]);
});
