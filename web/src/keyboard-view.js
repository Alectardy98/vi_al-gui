import { el } from "./ui.js";
import { keyLabel } from "./keycodes.js";

export function keyboardView(
  keyboard,
  { layer = 0, selected, onSelect, values } = {},
) {
  const keys = keyboard.visibleKeys();
  const unit = 54;
  const gap = 4;
  const left = Math.min(...keys.map((k) => k.x)),
    top = Math.min(...keys.map((k) => k.y));
  const width = Math.max(...keys.map((k) => k.x + k.width)) - left;
  const height = Math.max(...keys.map((k) => k.y + k.height)) - top;
  const canvas = el("div", {
    class: "keyboard",
    style: { width: `${width * unit}px`, height: `${height * unit}px` },
  });
  for (const key of keys) {
    const keyId =
      key.encoder !== null
        ? `e${key.encoder}:${key.direction}`
        : `${key.row}:${key.col}`;
    const code = keyboard.code(layer, key) ?? 0;
    const cap = el(
      "button",
      {
        type: "button",
        class: `keycap ${selected === keyId ? "selected" : ""}`,
        title:
          key.encoder !== null
            ? `Encoder ${key.encoder}, direction ${key.direction}`
            : `Row ${key.row}, column ${key.col} · ${keyLabel(keyboard, code)}`,
        "data-key": keyId,
        disabled: !onSelect,
        style: {
          left: `${(key.x - left) * unit}px`,
          top: `${(key.y - top) * unit}px`,
          width: `${key.width * unit - gap}px`,
          height: `${key.height * unit - gap}px`,
          transform: key.rotation_angle
            ? `rotate(${key.rotation_angle}deg)`
            : "",
          transformOrigin: `${(key.rotation_x - key.x) * unit}px ${(key.rotation_y - key.y) * unit}px`,
        },
        onClick: () => onSelect?.(key, keyId),
      },
      values?.(key) ?? keyLabel(keyboard, code),
    );
    canvas.append(cap);
  }
  return el("div", { class: "keyboard-scroll" }, canvas);
}
