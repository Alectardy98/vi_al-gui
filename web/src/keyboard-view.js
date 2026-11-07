import { el } from "./ui.js";
import { keyLabel } from "./keycodes.js";
import { keyBounds, keyOutline, placeLayout } from "./layout.js";

export function keyboardView(
  keyboard,
  { layer = 0, selected, onSelect, values, layoutChoices } = {},
) {
  const keys = layoutChoices
    ? placeLayout(keyboard.keys, layoutChoices)
    : keyboard.visibleKeys();
  if (!keys.length)
    return el(
      "p",
      { class: "notice" },
      "No physical keys match the selected layout options.",
    );
  const bounds = keys.map(keyBounds);
  const left = Math.min(...bounds.map((b) => b.left)),
    top = Math.min(...bounds.map((b) => b.top));
  const width = Math.max(...bounds.map((b) => b.right)) - left;
  const height = Math.max(...bounds.map((b) => b.bottom)) - top;
  const length = (n) => `calc(${n} * var(--key-unit))`;
  const canvas = el("div", {
    class: "keyboard",
    style: { width: length(width), height: length(height) },
  });
  canvas.style.setProperty(
    "--key-unit",
    `clamp(30px, calc((100cqw - 16px) / ${width}), 54px)`,
  );
  for (const key of keys) {
    const shape = keyOutline(key);
    const shaped =
      key.x2 ||
      key.y2 ||
      key.width2 !== key.width ||
      key.height2 !== key.height;
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
          left: length(shape.left - left),
          top: length(shape.top - top),
          width: `calc(${shape.width} * var(--key-unit) - 4px)`,
          height: `calc(${shape.height} * var(--key-unit) - 4px)`,
          transform: key.rotation_angle
            ? `rotate(${key.rotation_angle}deg)`
            : "",
          transformOrigin: `${length(key.rotation_x - shape.left)} ${length(key.rotation_y - shape.top)}`,
          clipPath:
            shaped && shape.connected
              ? `polygon(${shape.points.map(([x, y]) => `${(100 * (x - shape.left)) / shape.width}% ${(100 * (y - shape.top)) / shape.height}%`).join(", ")})`
              : "",
        },
        onClick: () => onSelect?.(key, keyId),
      },
      el(
        "span",
        {
          class: "keycap-label",
          style: {
            left: `${(100 * (key.x - shape.left)) / shape.width}%`,
            top: `${(100 * (key.y - shape.top)) / shape.height}%`,
            width: `${(100 * key.width) / shape.width}%`,
            height: `${(100 * key.height) / shape.height}%`,
          },
        },
        values?.(key) ?? keyLabel(keyboard, code),
      ),
    );
    canvas.append(cap);
  }
  return el("div", { class: "keyboard-scroll" }, canvas);
}
