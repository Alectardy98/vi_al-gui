import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LeydenJar,
  C,
  GET,
  SET,
  profiles,
  supported,
  decodeDetails,
} from "../addons/leyden_jar/protocol.js";
import { createLeydenPeer } from "./helpers/leyden-peer.js";
const matches = (rows, cols) =>
  profiles.find((p) => p.rows === rows && p.cols === cols);
function fake(options = {}) {
  const rows = options.direct ? 9 : options.expanded ? 4 : 8,
    cols = options.direct
      ? 13
      : options.expanded
        ? 20
        : options.beamspring
          ? 12
          : 16;
  const peer = createLeydenPeer({ ...options, rows, cols });
  const keyboard = {
    ...matches(rows, cols),
    transport: {
      request: async (q) => peer.reply(q),
      batch: async (f) => f(),
      reports: { output: 0 },
      device: {
        sendReport: async (id, q) => {
          assert.equal(id, 0);
          peer.calls.push([...q]);
        },
      },
      fail: (e) => {
        peer.invalidated = e.message;
      },
    },
  };
  return { peer, keyboard };
}
test("profiles require exact UID, dimensions and a real device", () => {
  for (const p of profiles) {
    assert.ok(supported(p));
    assert.ok(!supported({ ...p, rows: p.rows + 1 }));
    assert.ok(!supported({ ...p, demo: true }));
  }
  assert.throws(
    () => new LeydenJar({ uid: "0000000000000000", rows: 8, cols: 16 }),
  );
});
test("connection is GET-only and never runs a sweep, disables typing or saves", async () => {
  const { peer, keyboard } = fake(),
    c = await new LeydenJar(keyboard).connect();
  assert.equal(c.persistent, true);
  assert.equal(c.bins.size, 144);
  assert.equal(c.enabled, true);
  assert.ok(peer.calls.every((q) => q[0] === GET));
  assert.ok(peer.calls.every((q) => q[1] !== C.detect));
  assert.deepEqual(peer.calls[0], [2, C.version, 0xc0, 0x21]);
});
test("both polarities, reversed maps, inactive pads and signal values", async () => {
  for (const beamspring of [false, true]) {
    const { peer, keyboard } = fake({
      beamspring,
      reverseCols: beamspring,
      reverseRows: !beamspring,
      unused: [[0, 0]],
    });
    const c = await new LeydenJar(keyboard).connect();
    peer.pressed.add("2:1");
    peer.pressed.add("0:0");
    const state = await c.keys();
    assert.deepEqual([...state.physical], ["2:1"]);
    assert.deepEqual([...state.logical], [beamspring ? "2:10" : "5:1"]);
    assert.equal(c.physicalPosition([...state.logical][0]), "2:1");
    const levels = await c.levels();
    assert.equal(levels.size, 144);
    assert.ok(levels.get("2:1") >= 0);
    assert.ok(!c.minimum.has("0:0"));
    assert.equal(c.maximum.get("2:1"), levels.get("2:1"));
  }
});
test("persistent trigger has one write, signed payload and independent readbacks", async () => {
  for (const beamspring of [false, true]) {
    const { peer, keyboard } = fake({ beamspring }),
      c = await new LeydenJar(keyboard).connect();
    const value = c.references[1] + (beamspring ? -22 : 22);
    await c.setThreshold(1, value);
    assert.equal(c.thresholds[1], value);
    assert.equal(c.saved[1], true);
    const writes = peer.calls.filter(
      (q) => q[0] === SET && q[1] === C.preference,
    );
    assert.equal(writes.length, 1);
    assert.deepEqual(
      writes[0].slice(4),
      beamspring ? [234, 255, 1] : [22, 0, 1],
    );
    await c.restoreDefaults();
    assert.ok(!c.saved.some(Boolean));
    assert.equal(c.thresholds[1], c.references[1] + c.defaults[1]);
  }
});
test("legacy calibrates in RAM; split 1.x does not invent the persistence extension", async () => {
  for (const options of [{ legacy: true }, { split: true }]) {
    const { peer, keyboard } = fake(options),
      c = await new LeydenJar(keyboard).connect();
    assert.equal(c.persistent, false);
    assert.equal(c.side, options.split ? "left" : null);
    await c.setThreshold(0, 440);
    assert.equal(c.thresholds[0], 440);
    await assert.rejects(() => c.restoreDefaults(), /does not support/);
    assert.ok(
      peer.calls.every(
        (q) => ![C.capabilities, C.preference, C.defaults].includes(q[1]),
      ),
    );
  }
});
test("3178 direct switch is a digital key with no invented analog position", async () => {
  const { peer, keyboard } = fake({ direct: true }),
    c = await new LeydenJar(keyboard).connect();
  peer.directPressed = true;
  const result = await c.keys();
  assert.ok(result.logical.has("8:12"));
  assert.equal(c.physicalPosition("8:12"), null);
  assert.deepEqual(c.details.directKey, [8, 12, 27]);
  assert.equal((await c.levels()).size, 128);
});
test("expanded 3276 reads four values in each of twenty columns", async () => {
  const { keyboard } = fake({ expanded: true }),
    c = await new LeydenJar(keyboard).connect();
  assert.equal(c.details.expandedColumns, true);
  assert.equal((await c.levels()).size, 80);
});
test("invalid dimensions, aliased maps, bad groups, out-of-range values are rejected", async () => {
  for (const fault of [
    "details",
    "mapping",
    "bins",
    "range",
    "short",
    "header",
    "reject",
  ]) {
    const { peer, keyboard } = fake();
    peer.fault = fault;
    await assert.rejects(() => new LeydenJar(keyboard).connect());
  }
  const { peer, keyboard } = fake(),
    c = await new LeydenJar(keyboard).connect();
  peer.fault = "levels";
  await assert.rejects(() => c.levels(), /Signal/);
});
test("invalid edits cause no write; failed writes/readbacks are never retried", async () => {
  const { peer, keyboard } = fake(),
    c = await new LeydenJar(keyboard).connect();
  const before = peer.calls.length;
  for (const [group, value] of [
    [-1, 420],
    [0, 1024],
    [0, 410],
    [2, 430],
  ])
    await assert.rejects(() => c.setThreshold(group, value));
  assert.equal(peer.calls.length, before);
  peer.fault = "readback";
  await assert.rejects(() => c.setThreshold(0, 440), /readback/);
  assert.equal(
    peer.calls.filter((q) => q[0] === SET && q[1] === C.preference).length,
    1,
  );
  peer.fault = "timeout";
  const n = peer.calls.length;
  await assert.rejects(() => c.setThreshold(0, 450), /timeout/);
  assert.equal(peer.calls.length, n + 1);
});
test("enable has acknowledgement/readback; restart actions send once without a reply", async () => {
  const { peer, keyboard } = fake(),
    c = await new LeydenJar(keyboard).connect();
  await c.setEnabled(false);
  assert.equal(c.enabled, false);
  await c.setEnabled(true);
  assert.equal(c.enabled, true);
  for (const command of [C.boot, C.reboot, C.erase]) {
    const n = peer.calls.length;
    await c.restart(command);
    assert.equal(peer.calls.length, n + 1);
    assert.equal(peer.calls.at(-1).length, 32);
    assert.deepEqual(peer.calls.at(-1).slice(0, 4), [3, command, 192, 33]);
  }
  assert.ok(peer.invalidated);
});
