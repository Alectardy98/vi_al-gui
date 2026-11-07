import { VialKeyboard, parseDefinition } from "./keyboard.js";
import { word } from "./binary.js";

export function demoKeyboard() {
  const keyboard = new VialKeyboard({ healthy: true, close: async () => {} });
  keyboard.demo = true;
  keyboard.version = 6;
  keyboard.layers = 4;
  keyboard.rows = 6;
  keyboard.cols = 16;
  keyboard.uid = "demo";
  keyboard.layoutOptions = 0;
  keyboard.encoderKeys = new Map();
  const rows = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1],
    [1.5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1.5, 1],
    [1.75, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.25],
    [2.25, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.75, 1],
    [1.25, 1.25, 1.25, 6.25, 1.25, 1.25, 1.25, 1, 1, 1],
  ];
  keyboard.definition = {
    name: "Vi_al demo keyboard",
    vendorId: "0x0000",
    productId: "0x0000",
    matrix: { rows: 6, cols: 16 },
    layouts: {
      keymap: rows.map((row, r) => row.flatMap((w, c) => [{ w }, `${r},${c}`])),
    },
  };
  keyboard.keys = parseDefinition(keyboard.definition);
  keyboard.keymap = new Uint8Array(4 * 6 * 16 * 2);
  const codes = [
    [41, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 72, 73],
    [53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 42, 76],
    [43, 20, 26, 8, 21, 23, 28, 24, 12, 18, 19, 47, 48, 49, 74],
    [57, 4, 22, 7, 9, 10, 11, 13, 14, 15, 51, 52, 40],
    [225, 29, 27, 6, 25, 5, 17, 16, 54, 55, 56, 229, 82],
    [224, 227, 226, 44, 230, 231, 0x5221, 80, 81, 79],
  ];
  for (let l = 0; l < 4; l++)
    codes.forEach((row, r) =>
      row.forEach((code, c) =>
        keyboard.keymap.set(word(l ? 1 : code), keyboard.keyOffset(l, r, c)),
      ),
    );
  keyboard.setKey = async (layer, key, code) =>
    keyboard.keymap.set(
      word(code),
      keyboard.keyOffset(layer, key.row, key.col),
    );
  keyboard.reloadKeymap = async () => {};
  keyboard.unlockStatus = async () =>
    Uint8Array.from([1, 0, ...Array(30).fill(255)]);
  keyboard.matrix = async () => Array(96).fill(false);
  keyboard.request = async () => {
    throw Error(
      "This operation needs a connected keyboard. Demo edits stay in this page only.",
    );
  };
  return keyboard;
}
