import { test } from "node:test";
import assert from "node:assert/strict";
import {
  catalogue,
  composeKeycode,
  keyLabel,
  parseKeycode,
} from "../src/keycodes.js";

function keyboard(version = 6, definition = {}) {
  const k = {
    version,
    definition,
    layers: 4,
    macroCount: 16,
    dynamic: { tapDance: 4, repeat: 0 },
  };
  k.catalogue = catalogue(k);
  return k;
}
test("native categories include complete key lists and firmware-bounded dynamic entries", () => {
  for (const version of [5, 6]) {
    const k = keyboard(version),
      rows = k.catalogue;
    assert.ok(rows.length > 120);
    for (const name of [
      "Basic",
      "ISO/JIS",
      "Layers",
      "Quantum",
      "Backlight",
      "Media & Mouse",
      "Tap Dance",
      "User",
      "Macro",
    ])
      assert.ok(
        rows.some((row) => row.categories.includes(name)),
        name,
      );
    assert.equal(
      rows.filter((row) => row.categories.includes("User")).length,
      16,
    );
    assert.equal(rows.filter((row) => /^TD\(/.test(row.id)).length, 4);
    assert.equal(rows.filter((row) => /^M\d+$/.test(row.id)).length, 16);
    assert.equal(
      rows.some((row) => row.id === "M16"),
      false,
    );
    assert.equal(parseKeycode(k, "TO(0)"), version === 6 ? 0x5200 : 0x5010);
    k.layers = 32;
    k.catalogue = catalogue(k);
    assert.equal(parseKeycode(k, "TO(31)"), version === 6 ? 0x521f : 0x501f);
  }
});
test("User tab presentation order never changes custom wire identities or aliases", () => {
  const k = keyboard(6, {
    customKeycodes: [
      {
        name: "FIRST",
        shortName: "First",
        title: "First action",
        displayOrder: 2,
      },
      { name: "SECOND", shortName: "Second", displayOrder: 0 },
      { name: "THIRD", shortName: "Third", displayOrder: 1 },
    ],
  });
  assert.deepEqual(
    k.catalogue
      .filter((row) => row.categories.includes("User"))
      .map((row) => [row.id, row.code]),
    [
      ["USER01", 0x7e01],
      ["USER02", 0x7e02],
      ["USER00", 0x7e00],
    ],
  );
  assert.equal(parseKeycode(k, "FIRST"), 0x7e00);
  assert.equal(parseKeycode(k, "USER01"), 0x7e01);
  assert.equal(keyLabel(k, 0x7e00), "First");
  assert.throws(() => keyboard(6, { customKeycodes: { length: 2 } }));
  assert.throws(() => keyboard(6, { customKeycodes: Array(257).fill({}) }));
});
test("modifier-tap and layer-tap expressions encode according to each Vial version", () => {
  for (const version of [5, 6]) {
    const k = keyboard(version);
    assert.equal(parseKeycode(k, "LCTL(KC_A)"), 0x0104);
    assert.equal(
      parseKeycode(k, "LCTL_T(KC_A)"),
      version === 6 ? 0x2104 : 0x6104,
    );
    assert.equal(parseKeycode(k, "LT(3,KC_SPACE)"), 0x432c);
    assert.equal(parseKeycode(k, "LT3(KC_SPC)"), 0x432c);
    assert.throws(() => parseKeycode(k, "LT(4,KC_A)"));
    assert.throws(() => parseKeycode(k, "LCTL(kc)"));
    assert.throws(() => parseKeycode(k, "LCTL(LT3(KC_A))"));
    assert.throws(() => parseKeycode(k, "65536"));
    assert.throws(() =>
      composeKeycode(
        k.catalogue.find((row) => row.id === "LCTL(kc)"),
        0x7e00,
      ),
    );
  }
});
test("optional Quantum, MIDI and layer features follow firmware capabilities", () => {
  const k = keyboard();
  assert.equal(
    k.catalogue.some((row) => row.id === "QK_CAPS_WORD_TOGGLE"),
    false,
  );
  assert.equal(
    k.catalogue.some((row) => row.categories.includes("MIDI")),
    false,
  );
  k.supportedFeatures = new Set(["caps_word", "layer_lock"]);
  k.definition.vial = { midi: "basic" };
  k.catalogue = catalogue(k);
  assert.ok(k.catalogue.some((row) => row.id === "QK_CAPS_WORD_TOGGLE"));
  assert.ok(k.catalogue.some((row) => row.id === "QK_LAYER_LOCK"));
  const basic = k.catalogue.filter((row) =>
    row.categories.includes("MIDI"),
  ).length;
  assert.ok(basic > 0);
  k.definition.vial.midi = "advanced";
  k.catalogue = catalogue(k);
  assert.ok(
    k.catalogue.filter((row) => row.categories.includes("MIDI")).length > basic,
  );
});
