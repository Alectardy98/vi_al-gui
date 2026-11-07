import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { VialKeyboard, parseDefinition, packOptions } from "../src/keyboard.js";
import { keyBounds, keyOutline } from "../src/layout.js";

const boards = JSON.parse(
  readFileSync(new URL("./fixtures/zenithal-layouts.json", import.meta.url)),
);
for (const board of boards) {
  test(`KLE clusters and every Zenithal option match desktop Vial: ${board.source}`, () => {
    const k = new VialKeyboard({});
    k.definition = board.definition;
    k.keys = parseDefinition(board.definition);
    assert.deepEqual(
      k.keys.map((key) => [key.x, key.y]),
      board.rawCoordinates,
    );
    const source = JSON.stringify(k.keys);
    for (const layout of board.layouts) {
      k.layoutOptions = packOptions(
        board.definition.layouts.labels,
        layout.values,
      );
      const visible = k.visibleKeys();
      assert.equal(visible.length, layout.positions.length);
      for (const [row, col, x, y] of layout.positions) {
        const key = visible.find((key) => key.row === row && key.col === col);
        assert.ok(key, `Missing ${row}:${col} with ${layout.values}`);
        assert.ok(
          Math.abs(key.x - x) < 0.04 && Math.abs(key.y - y) < 0.04,
          `${row}:${col}: ${key.x},${key.y} vs desktop ${x},${y} with ${layout.values}`,
        );
      }
      assert.ok(
        Math.max(...visible.map((key) => keyBounds(key).bottom)) <= 5.04,
      );
      assert.ok(
        Math.max(...visible.map((key) => keyBounds(key).right)) <= 21.75,
      );
    }
    assert.equal(
      JSON.stringify(k.keys),
      source,
      "Selecting options must not mutate source geometry",
    );
  });
}
test("ISO Enter outline includes its full L-shaped area and rotated bounds", () => {
  const key = {
    x: 1,
    y: 0,
    width: 1,
    height: 2,
    x2: -1,
    y2: 1,
    width2: 2,
    height2: 1,
    rotation_angle: 0,
    rotation_x: 0,
    rotation_y: 0,
  };
  const shape = keyOutline(key);
  assert.equal(shape.connected, true);
  const area =
    Math.abs(
      shape.points.reduce((sum, a, i) => {
        const b = shape.points[(i + 1) % shape.points.length];
        return sum + a[0] * b[1] - b[0] * a[1];
      }, 0),
    ) / 2;
  assert.equal(area, 3);
  assert.deepEqual(keyBounds(key), { left: 0, top: 0, right: 2, bottom: 2 });
  const rotated = keyBounds({ ...key, rotation_angle: 90 });
  assert.ok(
    Math.abs(rotated.left + 2) < 1e-9 && Math.abs(rotated.bottom - 2) < 1e-9,
  );
});
