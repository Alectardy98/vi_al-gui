import { test } from "node:test";
import assert from "node:assert/strict";
import {
  Xwhatsit,
  profiles,
  supported,
  encodeSettings,
  decodeSettings,
} from "../addons/xwhatsit/protocol.js";
import { bytes, word } from "../src/binary.js";
const settings = {
  settle: 8,
  sample: 3,
  initial: 16,
  per_key: 16,
  groups: 5,
  margin: 96,
};
function fake({
  legacy = false,
  cols = 16,
  rows = 8,
  held = false,
  badAck = false,
} = {}) {
  const profile = profiles.find((p) => p.rows === rows && p.cols === cols);
  let record = encodeSettings(settings),
    writes = [];
  const keyboard = {
    ...profile,
    version: 6,
    transport: {
      async request(packet) {
        const op = packet[2];
        writes.push([...packet]);
        let data,
          status = 34;
        if (op === 17) data = [2, legacy ? 0 : 1, 0, legacy ? 2 : 5];
        else if (op === 26) data = [cols, rows, 0, 0, 8, 3, 1, 255, 15, rows];
        else if (op === 48)
          data = bytes(
            88,
            67,
            65,
            76,
            1,
            9,
            3,
            word(4095, true),
            encodeSettings(settings),
          );
        else if (op === 49) data = record;
        else if (op === 50 || op === 51) {
          if (held) {
            status = 36;
            data = [];
          } else {
            record = op === 51 ? encodeSettings(settings) : packet.slice(3, 11);
            data = badAck ? new Uint8Array(8) : record;
          }
        } else if (op === 22) {
          const width = cols > 16 ? 4 : cols > 8 ? 2 : 1,
            bitmap = new Uint8Array(width * rows);
          bitmap.fill(255);
          data = bytes(
            1,
            word(680, true),
            bitmap.slice(packet[4], packet[4] + 26),
          );
        } else if (op === 25) {
          assert.equal(packet[5], 1);
          data = word(500, true);
        } else if (op === 21) data = new Uint8Array(29);
        else throw Error("Unexpected operation " + op);
        const raw = new Uint8Array(32);
        raw.set(bytes(85, 170, status, data));
        return raw;
      },
    },
    async unlockStatus() {
      return [1];
    },
    async matrix() {
      return Array(rows * cols).fill(false);
    },
  };
  return { keyboard, writes };
}
test("all 29 profiles require exact UID and matrix; demo never matches", () => {
  assert.equal(profiles.length, 29);
  assert.equal(new Set(profiles.slice(7).map((p) => p.uid)).size, 22);
  for (const p of profiles) {
    assert.ok(supported(p));
    assert.ok(!supported({ ...p, rows: p.rows + 1 }));
    assert.ok(!supported({ ...p, demo: true }));
  }
});
test("XCAL record matches desktop encoding and rejects invalid CRC/ranges", () => {
  const raw = encodeSettings(settings);
  assert.equal(Buffer.from(raw).toString("hex"), "a708034405600027");
  assert.deepEqual(decodeSettings(raw), settings);
  const bad = raw.slice();
  bad[1] ^= 1;
  assert.throws(() => decodeSettings(bad), /checksum/);
  for (const s of [
    { ...settings, initial: 3 },
    { ...settings, settle: 0 },
    { ...settings, margin: 4096 },
  ])
    assert.throws(() => encodeSettings(s));
});
test("connect, live save, defaults, separate readback; reads never save", async () => {
  const peer = fake(),
    c = await new Xwhatsit(peer.keyboard).connect();
  assert.equal(c.thresholds.size, 128);
  assert.equal(c.thresholds.get("0:0").threshold, 680);
  assert.equal(
    peer.writes.filter((q) => [50, 51, 24, 18].includes(q[2])).length,
    0,
  );
  const updated = { ...settings, margin: 100 };
  await c.save(updated);
  assert.deepEqual(await c.getSettings(), updated);
  await c.save(c.defaults, true);
  assert.deepEqual(c.settings, settings);
  assert.equal(peer.writes.filter((q) => q[2] === 50).length, 1);
  assert.equal(peer.writes.filter((q) => q[2] === 51).length, 1);
});
test("legacy firmware monitors but cannot change settings", async () => {
  const peer = fake({ legacy: true }),
    c = await new Xwhatsit(peer.keyboard).connect();
  assert.equal(c.extension, false);
  assert.equal(await c.readSignal("0:0"), 500);
  await assert.rejects(() => c.save(settings), /XCAL/);
  assert.ok(peer.writes.every((q) => ![48, 49, 50, 51].includes(q[2])));
});
test("held keys, mismatching ACK and transport failures never retry a write", async () => {
  for (const options of [{ held: true }, { badAck: true }]) {
    const peer = fake(options),
      c = await new Xwhatsit(peer.keyboard).connect();
    await assert.rejects(() => c.save(settings));
    assert.equal(peer.writes.filter((q) => q[2] === 50).length, 1);
  }
  const peer = fake(),
    c = await new Xwhatsit(peer.keyboard).connect();
  let calls = 0;
  c.keyboard.transport.request = async () => {
    calls++;
    throw Error("timeout");
  };
  await assert.rejects(() => c.save(settings), /timeout/);
  assert.equal(calls, 1);
});
test("wide and 16-row boards assemble complete threshold bitmaps", async () => {
  for (const dims of [
    { rows: 8, cols: 22 },
    { rows: 16, cols: 16 },
  ]) {
    const peer = fake(dims),
      c = await new Xwhatsit(peer.keyboard).connect();
    assert.equal(c.thresholds.size, dims.rows * dims.cols);
    assert.ok(peer.writes.filter((q) => q[2] === 22).length > 1);
  }
});
test("live held key overrides selection and suppresses background samples", async () => {
  const peer = fake(),
    c = await new Xwhatsit(peer.keyboard).connect();
  peer.keyboard.matrix = async () =>
    Array.from({ length: 128 }, (_, i) => i === 3);
  const result = await c.frame("0:0", ["0:1", "0:2", "0:4"]);
  assert.equal(result.selected, "0:3");
  assert.equal(result.values.size, 1);
  assert.equal(peer.writes.filter((q) => q[2] === 25).length, 1);
});
