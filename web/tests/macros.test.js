import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeMacro, decodeMacro } from "../src/advanced.js";

test("macro text, taps, modifiers, delays and zero-low-byte extended keycodes round trip", () => {
  const actions = [
    { type: "text", value: "Hello" },
    { type: "down", value: 224 },
    { type: "tap", value: 4 },
    { type: "up", value: 224 },
    { type: "delay", value: 300 },
    { type: "tap", value: 0x7e00 },
  ];
  assert.deepEqual(decodeMacro(encodeMacro(actions, 6), 6), actions);
  assert.deepEqual(
    [...encodeMacro([{ type: "delay", value: 300 }], 6)],
    [1, 4, 46, 2],
  );
  assert.deepEqual(
    [...encodeMacro([{ type: "tap", value: 0x7e00 }], 6)],
    [1, 5, 0x7e, 0xff],
  );
});
test("reserved macro bytes, oversized delays and unsupported old formats are rejected", () => {
  assert.throws(() => encodeMacro([{ type: "text", value: "\0" }], 6));
  assert.throws(() => encodeMacro([{ type: "delay", value: 65025 }], 6));
  assert.throws(() => encodeMacro([{ type: "tap", value: 0x7e00 }], 4));
  assert.throws(() => decodeMacro(Uint8Array.from([1, 4, 1]), 6));
});
