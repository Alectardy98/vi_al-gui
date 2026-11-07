// SPDX-License-Identifier: GPL-2.0-or-later
import catalogues from "./data/keycodes.json" with { type: "json" };

export const keycodeCategories = [
  "Basic",
  "ISO/JIS",
  "Layers",
  "Quantum",
  "Backlight",
  "Media & Mouse",
  "MIDI",
  "Tap Dance",
  "User",
  "Macro",
];
export function catalogue(keyboard) {
  const version = keyboard.version === 6 ? "6" : "5";
  const encoding = catalogues.encodings[version];
  const features = new Set(keyboard.supportedFeatures ?? []);
  if (keyboard.version >= 5) features.add("persistent_default_layer");
  if (keyboard.dynamic?.repeat) features.add("repeat_key");
  const midi = keyboard.definition.vial?.midi;
  const rows = catalogues[version].filter(
    (row) =>
      (!row.feature || features.has(row.feature)) &&
      (!row.midi ||
        midi === "advanced" ||
        (midi === "basic" && row.midi === "basic")),
  );
  const add = (category, code, id, label, title = "", extra = {}) => {
    if (Number.isInteger(code) && code >= 0 && code <= 65535)
      rows.push({
        code,
        id,
        label,
        title,
        categories: [category],
        aliases: [],
        ...extra,
      });
  };
  const custom = keyboard.definition.customKeycodes;
  if (custom !== undefined && (!Array.isArray(custom) || custom.length > 256))
    throw Error(
      "Invalid custom keycode list; at most 256 entries are supported.",
    );
  const string = (value, fallback) =>
    typeof value === "string" && value.length ? value : fallback;
  const users = custom?.length
    ? custom
    : Array.from({ length: 16 }, (_, i) => ({
        name: `User ${i}`,
        shortName: `User ${i}`,
      }));
  const userRows = users.map((entry, i) => {
    const c = entry && typeof entry === "object" ? entry : {};
    const id = `USER${String(i).padStart(2, "0")}`;
    return {
      code: encoding.user + i,
      id,
      label: string(c.shortName, string(c.name, id)),
      title: string(c.title, string(c.name, `User keycode ${i}`)),
      categories: ["User"],
      aliases: typeof c.name === "string" ? [c.name] : [],
      order:
        Number.isInteger(c.displayOrder) &&
        c.displayOrder >= 0 &&
        c.displayOrder < users.length
          ? c.displayOrder
          : i,
    };
  });
  rows.push(...userRows.sort((a, b) => a.order - b.order));
  for (let layer = 0; layer < keyboard.layers; layer++) {
    for (const [name, base] of Object.entries(encoding.layers)) {
      if (
        base === null ||
        (name === "PDF" && !features.has("persistent_default_layer"))
      )
        continue;
      add(
        "Layers",
        base | layer,
        `${name}(${layer})`,
        `${name}(${layer})`,
        `${name}: layer ${layer}`,
      );
    }
    if (layer < 16)
      add(
        "Layers",
        encoding.layerTap + layer * 256,
        `LT${layer}(kc)`,
        `LT ${layer} (kc)`,
        `Tap a key; hold to activate layer ${layer}`,
        { masked: true },
      );
  }
  if (keyboard.layers >= 4) {
    add(
      "Layers",
      encoding.fn13,
      "FN_MO13",
      "Fn1 (Fn3)",
      "Activate layer 1; combine with Fn2 for layer 3",
    );
    add(
      "Layers",
      encoding.fn23,
      "FN_MO23",
      "Fn2 (Fn3)",
      "Activate layer 2; combine with Fn1 for layer 3",
    );
  }
  if (features.has("layer_lock"))
    add(
      "Layers",
      encoding.layerLock,
      "QK_LAYER_LOCK",
      "Layer Lock",
      "Lock the active layer",
      { aliases: ["QK_LLCK"] },
    );
  for (let i = 0; i < (keyboard.macroCount ?? 0); i++)
    add("Macro", encoding.macro + i, `M${i}`, `M${i}`, `Stored macro ${i}`);
  for (let i = 0; i < (keyboard.dynamic?.tapDance ?? 0); i++)
    add(
      "Tap Dance",
      encoding.tapDance + i,
      `TD(${i})`,
      `TD(${i})`,
      `Tap Dance entry ${i}`,
    );
  return rows;
}
export function keyLabel(keyboard, code) {
  const rows = keyboard.catalogue ?? [];
  const match = rows.find((row) => !row.masked && row.code === code);
  if (match) return match.label || match.id;
  const outer = rows.find((row) => row.masked && row.code === (code & 0xff00));
  if (outer) return outer.id.replace("kc", keyLabel(keyboard, code & 255));
  return `0x${code.toString(16).toUpperCase().padStart(4, "0")}`;
}
export function composeKeycode(wrapper, code) {
  if (!wrapper?.masked || !Number.isInteger(code) || code < 0 || code > 255)
    throw Error("Choose a basic keycode for the modifier or layer tap.");
  return wrapper.code | code;
}
export function parseKeycode(keyboard, value) {
  value = value.trim();
  const rows = keyboard.catalogue;
  const same = (a, b) => a.toLowerCase() === b.toLowerCase();
  const match =
    rows.find((row) => same(row.id, value)) ??
    rows.find((row) =>
      (row.aliases ?? []).some((alias) => same(alias, value)),
    ) ??
    rows.find((row) => same(row.label, value));
  if (match) {
    if (match.masked)
      throw Error(
        "Choose the inner keycode before assigning this modifier or layer tap.",
      );
    return match.code;
  }
  if (/^(0x[0-9a-f]{1,4}|\d{1,5})$/i.test(value)) {
    const code = Number(value);
    if (code <= 65535) return code;
  }
  const layer = value.match(/^LT\(\s*(\d+)\s*,\s*(.+)\)$/i);
  if (layer)
    return parseKeycode(keyboard, `LT${Number(layer[1])}(${layer[2]})`);
  const expression = value.match(/^([A-Z][A-Z_0-9]*)\(([^()]*)\)$/i);
  if (expression) {
    const wrapper = rows.find(
      (row) => row.masked && same(row.id, `${expression[1]}(kc)`),
    );
    if (wrapper)
      return composeKeycode(wrapper, parseKeycode(keyboard, expression[2]));
  }
  throw Error(
    "Choose a keycode, QMK name, supported modifier/layer-tap expression, or 16-bit value.",
  );
}
