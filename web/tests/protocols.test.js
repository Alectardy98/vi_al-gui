import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bytes, crc32, hex } from "../src/binary.js";
import {
  VialKeyboard,
  parseDefinition,
  packOptions,
  optionValues,
} from "../src/keyboard.js";
import { catalogue, keyLabel } from "../src/keycodes.js";
import {
  touchRecord,
  decodeTouch,
  sleepRecord,
  decodeSleep,
  oledRecord,
  decodeOled,
  lockRecord,
  decodeLocks,
} from "../addons/my2k/protocol.js";
import { encode, decodeRecord, profiles } from "../addons/ec_42/protocol.js";
import {
  groups,
  lightingBatch,
  parseSnapshot,
  macroPacket,
} from "../addons/alienware_aw768/protocol.js";
import { typingBitmap } from "../addons/my2k/typing-preview.js";
const fixtures = JSON.parse(
  readFileSync(new URL("./fixtures/protocols.json", import.meta.url)),
);
const unhex = (value) => Uint8Array.from(Buffer.from(value, "hex"));

test("touch, sleep, OLED and Lock Lights bytes match the Python codecs exactly", () => {
  for (const [name, enc, dec] of [
    ["touch", touchRecord, decodeTouch],
    ["sleep", sleepRecord, decodeSleep],
    ["oled", oledRecord, decodeOled],
    ["locks", lockRecord, decodeLocks],
  ]) {
    const { values, raw } = fixtures[name];
    assert.equal(hex(enc(values)), raw, name);
    assert.deepEqual(dec(unhex(raw)), values, name);
    for (let i = 0; i < unhex(raw).length; i++) {
      const bad = unhex(raw);
      bad[i] ^= 1;
      assert.throws(() => dec(bad), `${name} byte ${i}`);
    }
  }
});
test("binary fields preserve nested byte arrays and reject truncation", () => {
  assert.deepEqual([...bytes(1, [2, [3]], bytes(4))], [1, 2, 3, 4]);
  assert.throws(() => bytes(256));
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
});
test("typing label preview matches the native fixed-font display pixel for pixel", () => {
  assert.equal(
    hex(typingBitmap(fixtures.typing.label)),
    fixtures.typing.bitmap,
  );
  assert.equal(typingBitmap("").length, 360);
});
test("EC42 request and CRC endianness match the existing firmware codec", () => {
  assert.equal(
    hex(encode(0x29, 123, bytes(0, 4, 37, 0, 9))),
    fixtures.ec.request,
  );
  const raw = unhex(fixtures.ec.record);
  assert.equal(decodeRecord(raw, profiles[0]).packed, true);
  for (let i = 0; i < raw.length; i++) {
    const bad = raw.slice();
    bad[i] ^= 1;
    assert.throws(() => decodeRecord(bad, profiles[0]));
  }
  assert.throws(() => decodeRecord(raw, profiles[1]));
});
test("AW768 complete save matches the captured Dell DLL packets", () => {
  const old = JSON.parse(
    readFileSync(
      new URL(
        "./fixtures/alienware_aw768/legacy-lighting.json",
        import.meta.url,
      ),
    ),
  );
  const golden = JSON.parse(
    readFileSync(
      new URL(
        "./fixtures/alienware_aw768/vendor-two-pass-red.json",
        import.meta.url,
      ),
    ),
  );
  const snapshot = parseSnapshot(1, old.frames.map(unhex));
  const changes = new Map(
    groups.map(([mask]) => [
      mask,
      { mode: 0, color: [255, 0, 0], tempo: 2, brightness: 10 },
    ]),
  );
  const packets = lightingBatch(snapshot, changes).map((p) => hex(bytes(0, p)));
  assert.deepEqual(packets, golden.groups);
  const macro = macroPacket(1, [0, 0, 255]);
  assert.deepEqual(
    [...macro.slice(0, 11)],
    [6, 1, 0, 0, 255, 0, 0, 255, 0, 0, 255],
  );
});
test("layout bounds, options and custom keycodes use real definition order", () => {
  const k = new VialKeyboard({});
  k.definition = fixtures.definition;
  k.version = 6;
  k.layers = 4;
  k.rows = 3;
  k.cols = 5;
  const keys = parseDefinition(k.definition);
  assert.equal(keys.length, 13);
  assert.equal(keys[5].width, 1.5);
  assert.throws(() =>
    parseDefinition({
      matrix: { rows: 1, cols: 1 },
      layouts: { keymap: [["2,1"]] },
    }),
  );
  const labels = ["Split", ["Layout", "A", "B", "C"]];
  assert.deepEqual(optionValues(labels, packOptions(labels, [1, 2])), [1, 2]);
  k.catalogue = catalogue(k);
  assert.equal(keyLabel(k, 0x7e00), "Storage");
  assert.equal(k.catalogue.find((r) => r.id === "MO(3)").code, 0x5223);
});
