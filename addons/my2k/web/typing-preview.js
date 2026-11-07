// SPDX-License-Identifier: GPL-2.0-or-later
// Same QMK ASCII glyphs and 72x40 layout as oled_typing_preview.py.
import glyphs from "../../../web/src/data/typing-glyphs.json" with { type: "json" };
export function typingBitmap(label, history = "ABC", current = "D") {
  const bitmap = new Uint8Array(360);
  function glyph(char, x, y, scale = 1) {
    const code = char.charCodeAt(0);
    if (code < 32 || code > 126) return;
    for (let col = 0; col < 5; col++)
      for (let row = 0; row < 8; row++) {
        if (!(glyphs[(code - 32) * 6 + col] & (1 << row))) continue;
        for (let dx = 0; dx < scale; dx++)
          for (let dy = 0; dy < scale; dy++) {
            const px = x + col * scale + dx,
              py = y + row * scale + dy;
            if (px >= 0 && px < 72 && py >= 0 && py < 40)
              bitmap[Math.floor(py / 8) * 72 + px] |= 1 << (py % 8);
          }
      }
  }
  [...label.slice(0, 10)].forEach((c, i) => glyph(c, i * 6, 0));
  const tail = history.slice(-7);
  [...tail].forEach((c, i) => glyph(c, (7 - tail.length + i) * 6, 28));
  if (current) glyph(current[0], 44, 20, 2);
  return bitmap;
}
