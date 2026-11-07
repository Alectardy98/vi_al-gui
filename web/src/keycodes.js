import catalogues from "./data/keycodes.json" with { type: "json" };

export function catalogue(keyboard) {
  let rows = [...catalogues[keyboard.version === 6 ? "6" : "5"]];
  const custom = keyboard.definition.customKeycodes;
  if (custom?.length) {
    if (!Array.isArray(custom) || custom.length > 256)
      throw Error("Custom keycode list exceeds the supported range.");
    const base = keyboard.version === 6 ? 0x7e00 : 0x5f80;
    rows = rows.filter((r) => !/^USER\d+$/.test(r.id));
    rows.push(
      ...custom
        .map((c, i) => ({
          code: base + i,
          id: `USER${String(i).padStart(2, "0")}`,
          label: c.shortName ?? c.name ?? `User ${i}`,
          title: c.title ?? c.name ?? "",
          order: c.displayOrder ?? i,
        }))
        .sort((a, b) => a.order - b.order),
    );
  }
  const bases =
    keyboard.version === 6
      ? [0x5220, 0x5260, 0x5240, 0x5200, 0x5280]
      : [0x5100, 0x5300, 0x5200, 0x5000, 0x5400];
  for (let layer = 0; layer < keyboard.layers; layer++) {
    ["MO", "TG", "DF", "TO", "OSL"].forEach((name, i) =>
      rows.push({
        code: bases[i] + layer,
        id: `${name}(${layer})`,
        label: `${name}(${layer})`,
        title: `Layer ${layer}`,
      }),
    );
  }
  for (let i = 0; i < (keyboard.macroCount ?? 0); i++)
    rows.push({
      code: (keyboard.version === 6 ? 0x7700 : 0x5f12) + i,
      id: `M${i}`,
      label: `Macro ${i}`,
      title: "Stored macro",
    });
  for (let i = 0; i < (keyboard.dynamic?.tapDance ?? 0); i++)
    rows.push({
      code: 0x5700 + i,
      id: `TD(${i})`,
      label: `TD(${i})`,
      title: "Tap Dance",
    });
  return rows;
}
export function keyLabel(keyboard, code) {
  const match = keyboard.catalogue?.find((r) => r.code === code);
  return (
    match?.label ?? `0x${code.toString(16).toUpperCase().padStart(4, "0")}`
  );
}
export function parseKeycode(keyboard, value) {
  const match = keyboard.catalogue.find(
    (r) =>
      r.id.toLowerCase() === value.toLowerCase() ||
      r.label.toLowerCase() === value.toLowerCase(),
  );
  if (match) return match.code;
  if (/^(0x[0-9a-f]{1,4}|\d{1,5})$/i.test(value)) {
    const code = Number(value);
    if (code <= 65535) return code;
  }
  throw Error(
    "Choose a keycode from the list, a QMK name, or a 16-bit hexadecimal value.",
  );
}
