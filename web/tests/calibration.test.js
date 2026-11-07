// Exercise calibration safety boundaries without accessing a physical keyboard.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { EC42, profiles } from "../addons/ec_42/protocol.js";
import { u16, word } from "../src/binary.js";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/protocols.json", import.meta.url)),
);
const raw = Uint8Array.from(Buffer.from(fixture.ec.record, "hex"));
function session() {
  const ec = new EC42({ uid: profiles[0].uid, transport: { healthy: true } });
  const calls = [];
  ec.writable = async () => {};
  ec.actuation = async () => new Uint8Array(20);
  ec.released = async () => {};
  ec.record = async () => raw.slice();
  ec.status = async () => Uint8Array.of(3, 0, 7, 0, 0, 0);
  ec.request = async (op, payload = []) => {
    calls.push([op, [...payload]]);
    return op === 0x15 ? raw.slice(0, 9) : word(7);
  };
  ec.snapshot = async () =>
    Array.from({ length: ec.cells }, (_, i) => {
      const value = u16(raw, 9 + 2 * i);
      return {
        sampled: true,
        enabled: !!(value & 0x8000),
        qualified: !!(value & 0x4000),
        active: false,
        debounced: false,
      };
    });
  return {
    ec,
    calls,
    review: { session: 7, proposed: raw.slice(), canApply: true },
  };
}
test("failed recovery-file save prevents calibration capture from starting", async () => {
  const { ec, calls } = session();
  await assert.rejects(
    ec.start(async () => {
      throw Error("Backup disk unavailable");
    }),
    /Backup disk/,
  );
  assert.deepEqual(calls, []);
});
test("a newly pressed key after backup prevents calibration capture", async () => {
  const { ec, calls } = session();
  let checks = 0,
    backedUp = false;
  ec.released = async () => {
    if (++checks === 2) throw Error("Release every key");
  };
  await assert.rejects(
    ec.start(async (backup) => {
      backedUp = backup.record === fixture.ec.record;
    }),
    /Release every key/,
  );
  assert.equal(backedUp, true);
  assert.deepEqual(calls, []);
});
test("stale calibration session and changed proposal cannot activate or save", async () => {
  const { ec, calls, review } = session();
  await assert.rejects(ec.apply({ ...review, session: 8 }), /stale/);
  assert.deepEqual(calls, []);
  ec.record = async () => {
    const changed = raw.slice();
    changed[9] ^= 1;
    return changed;
  };
  await assert.rejects(ec.apply(review), /proposal changed/);
  assert.deepEqual(
    calls.map(([op]) => op),
    [0x22],
  );
});
test("failed active readback cancels volatile calibration and never saves", async () => {
  const { ec, calls, review } = session();
  const request = ec.request;
  ec.request = async (op, payload) =>
    op === 0x15 ? new Uint8Array(9) : request(op, payload);
  await assert.rejects(ec.apply(review), /readback mismatch/);
  assert.deepEqual(calls, [
    [0x22, [0, 7]],
    [0x24, [0, 7]],
    [0x20, [4]],
  ]);
});
test("released-key verification failure cancels before persistent save", async () => {
  const { ec, calls, review } = session();
  const snapshot = ec.snapshot;
  ec.snapshot = async () => {
    const values = await snapshot();
    values[0].active = true;
    return values;
  };
  await assert.rejects(ec.apply(review), /Released-key/);
  assert.equal(
    calls.some(([op]) => op === 0x25),
    false,
  );
  assert.deepEqual(calls.at(-1), [0x20, [4]]);
});
test("verified calibration saves once and compares persistent record readback", async () => {
  const { ec, calls, review } = session();
  const records = [];
  ec.record = async (op) => {
    records.push(op);
    return raw.slice();
  };
  await ec.apply(review);
  assert.deepEqual(
    calls.map(([op]) => op),
    [0x22, 0x24, 0x15, 0x25],
  );
  assert.deepEqual(records, [0x23, 0x16]);
});
