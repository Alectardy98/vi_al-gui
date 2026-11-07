// SPDX-License-Identifier: GPL-2.0-or-later
import qmkSettings from "./data/qmk_settings.json" with { type: "json" };
import { bytes, equal, integer, u16, word } from "./binary.js";
import {
  button,
  download,
  el,
  field,
  note,
  section,
  select,
  toggle,
} from "./ui.js";
import { keyLabel, parseKeycode } from "./keycodes.js";

export function encodeMacro(actions, version) {
  const chunks = [];
  for (const action of actions) {
    if (action.type === "text") {
      const text = new TextEncoder().encode(action.value);
      if (
        text.some(
          (b) => b === 0 || (version >= 2 ? b === 1 : [1, 2, 3].includes(b)),
        )
      )
        throw Error("Macro text contains a reserved control byte.");
      chunks.push(text);
    } else if (action.type === "delay") {
      if (version < 2)
        throw Error("Delay actions require Vial protocol 2 or later.");
      const value = integer(+action.value, 0, 65024, "Macro delay");
      chunks.push(bytes(1, 4, (value % 255) + 1, Math.floor(value / 255) + 1));
    } else {
      const base = { tap: 1, down: 2, up: 3 }[action.type];
      if (!base) throw Error("Unknown macro action.");
      let key = integer(+action.value, 1, 0xfeff, "Macro keycode");
      if (key > 255 && version < 5)
        throw Error("Extended macro keys require Vial protocol 5 or later.");
      const extended = key > 255;
      if (extended && !(key & 255)) key = 0xff00 | (key >>> 8);
      chunks.push(
        bytes(
          version >= 2 ? [1] : [],
          extended ? base + 4 : base,
          extended ? word(key, true) : [key],
        ),
      );
    }
  }
  return bytes(...chunks);
}
export function decodeMacro(raw, version) {
  const result = [];
  let i = 0,
    textBytes = [];
  const flush = () => {
    if (textBytes.length) {
      result.push({
        type: "text",
        value: new TextDecoder("utf-8", { fatal: true }).decode(
          bytes(textBytes),
        ),
      });
      textBytes = [];
    }
  };
  while (i < raw.length) {
    const isAction = version >= 2 ? raw[i] === 1 : [1, 2, 3].includes(raw[i]);
    if (!isAction) {
      textBytes.push(raw[i++]);
      continue;
    }
    flush();
    if (version >= 2) i++;
    const type = raw[i++];
    if (type === 4 && version >= 2) {
      if (i + 2 > raw.length || !raw[i] || !raw[i + 1])
        throw Error("Truncated macro delay.");
      result.push({
        type: "delay",
        value: raw[i] - 1 + (raw[i + 1] - 1) * 255,
      });
      i += 2;
    } else {
      const extended = type >= 5 && type <= 7,
        base = extended ? type - 4 : type;
      if (![1, 2, 3].includes(base) || i + (extended ? 2 : 1) > raw.length)
        throw Error(
          "Malformed macro action. Export a backup before editing it.",
        );
      let code = extended ? u16(raw, i, true) : raw[i];
      i += extended ? 2 : 1;
      if (code > 0xff00) code = (code & 255) << 8;
      result.push({
        type: { 1: "tap", 2: "down", 3: "up" }[base],
        value: code,
      });
    }
  }
  flush();
  return result;
}
async function readMacros(k) {
  const count = k.macroCount,
    size = k.macroMemory,
    parts = [];
  let zeros = 0;
  for (let offset = 0; offset < size && zeros < count; offset += 28) {
    const n = Math.min(28, size - offset),
      r = await k.request(14, word(offset), n);
    if (r[0] !== 14 || u16(r, 1) !== offset || r[3] !== n)
      throw Error("Macro response offset/length mismatch.");
    const chunk = r.slice(4, 4 + n);
    parts.push(chunk);
    zeros += chunk.filter((b) => !b).length;
  }
  const data = bytes(...parts),
    macros = [];
  let start = 0;
  for (let i = 0; i < data.length && macros.length < count; i++)
    if (!data[i]) {
      macros.push(data.slice(start, i));
      start = i + 1;
    }
  if (macros.length !== count)
    throw Error("Macro buffer does not contain all declared macros.");
  return macros;
}
export async function macroPage(container, ctx) {
  const k = ctx.keyboard;
  let macros = await readMacros(k),
    index = 0,
    actions = decodeMacro(macros[0], k.version);
  const editor = el("div"),
    choice = select(
      macros.map((_, i) => [i, `Macro ${i}`]),
      0,
      (e) => {
        try {
          index = +e.target.value;
          actions = decodeMacro(macros[index], k.version);
          draw();
        } catch (error) {
          ctx.notify(error.message, true);
        }
      },
    );
  function draw() {
    editor.replaceChildren(
      ...actions.map((action, i) => {
        const kind = select(
          [
            ["text", "Text"],
            ["tap", "Tap key"],
            ["down", "Key down"],
            ["up", "Key up"],
            ...(k.version >= 2 ? [["delay", "Delay · ms"]] : []),
          ],
          action.type,
          (e) => {
            action.type = e.target.value;
            action.value =
              action.type === "text" ? "" : action.type === "delay" ? 100 : 4;
            draw();
          },
        );
        const value = el("input", {
          value: ["text", "delay"].includes(action.type)
            ? action.value
            : keyLabel(k, action.value),
          "aria-label": `Macro action ${i + 1}`,
          onChange: (e) => {
            try {
              action.value =
                action.type === "text"
                  ? e.target.value
                  : action.type === "delay"
                    ? +e.target.value
                    : parseKeycode(k, e.target.value);
            } catch (error) {
              ctx.notify(error.message, true);
            }
          },
        });
        return el(
          "div",
          { class: "toolbar" },
          kind,
          value,
          button("↑", () => {
            if (i) {
              [actions[i], actions[i - 1]] = [actions[i - 1], actions[i]];
              draw();
            }
          }),
          button("Remove", () => {
            actions.splice(i, 1);
            draw();
          }),
        );
      }),
      button("Add action", () => {
        actions.push({ type: "text", value: "" });
        draw();
      }),
    );
  }
  container.append(
    section(
      "Macros",
      `${macros.length} macros · ${k.macroMemory} bytes available. Other macros are preserved byte for byte.`,
      field("Macro", choice),
      editor,
      el(
        "div",
        { class: "toolbar" },
        button(
          "Save macro",
          () =>
            ctx.run(async () => {
              if ((await k.unlockStatus())[0] !== 1)
                throw Error("Unlock the keyboard in Security first.");
              const updated = macros.slice();
              updated[index] = encodeMacro(actions, k.version);
              const raw = bytes(...updated.map((m) => bytes(m, 0)));
              if (raw.length > k.macroMemory)
                throw Error(
                  "Macro data exceeds the available EEPROM allocation.",
                );
              for (let offset = 0; offset < raw.length; offset += 28) {
                const part = raw.slice(offset, offset + 28);
                await k.request(15, word(offset), part.length, part);
              }
              const actual = await readMacros(k);
              if (actual.some((m, i) => !equal(m, updated[i])))
                throw Error(
                  "Macro readback differs. Export your backup before further edits.",
                );
              macros = actual;
            }),
          true,
        ),
        button("Export macro backup", () =>
          download(
            "vi-al-macros.json",
            JSON.stringify(
              {
                format: "vi-al-macros-1",
                uid: k.uid,
                macros: macros.map((m) => [...m]),
              },
              null,
              2,
            ),
          ),
        ),
      ),
    ),
  );
  draw();
}
const dynamicTypes = [
  {
    key: "tapDance",
    title: "Tap Dance",
    read: 1,
    write: 2,
    fields: [
      ["Tap", 2, "key"],
      ["Hold", 2, "key"],
      ["Double tap", 2, "key"],
      ["Tap and hold", 2, "key"],
      ["Tapping term · ms", 2, "number"],
    ],
  },
  {
    key: "combo",
    title: "Combos",
    read: 3,
    write: 4,
    fields: [
      ["Input 1", 2, "key"],
      ["Input 2", 2, "key"],
      ["Input 3", 2, "key"],
      ["Input 4", 2, "key"],
      ["Output", 2, "key"],
    ],
  },
  {
    key: "override",
    title: "Key overrides",
    read: 5,
    write: 6,
    fields: [
      ["Trigger", 2, "key"],
      ["Replacement", 2, "key"],
      ["Layer mask", 2, "number"],
      ["Required modifier mask", 1, "number"],
      ["Negative modifier mask", 1, "number"],
      ["Suppressed modifier mask", 1, "number"],
      ["Options · bit 7 enables", 1, "number"],
    ],
  },
  {
    key: "repeat",
    title: "Alternate repeat",
    read: 7,
    write: 8,
    fields: [
      ["Keycode", 2, "key"],
      ["Alternate keycode", 2, "key"],
      ["Allowed modifier mask", 1, "number"],
      ["Options", 1, "number"],
    ],
  },
];
export async function dynamicPage(container, ctx) {
  const k = ctx.keyboard,
    available = dynamicTypes.filter((t) => k.dynamic[t.key]);
  let kind = available[0],
    index = 0;
  const editor = el("div"),
    entry = select(
      Array.from({ length: k.dynamic[kind.key] }, (_, i) => [
        i,
        `${kind.title} ${i}`,
      ]),
      0,
      (e) => ctx.run(() => load(kind, +e.target.value), "Entry loaded."),
    );
  const type = select(
    available.map((t) => [t.key, t.title]),
    kind.key,
    (e) =>
      ctx.run(async () => {
        const selected = available.find((t) => t.key === e.target.value);
        entry.replaceChildren(
          ...Array.from({ length: k.dynamic[selected.key] }, (_, i) =>
            el("option", { value: i }, `${selected.title} ${i}`),
          ),
        );
        await load(selected, 0);
      }, "Entries loaded."),
  );
  async function get(t, at) {
    const r = await k.request(254, 13, t.read, at);
    if (r[0] !== 0) throw Error("Firmware rejected dynamic entry read.");
    const length = t.fields.reduce((n, f) => n + f[1], 0);
    return r.slice(1, 1 + length);
  }
  async function load(t, at) {
    kind = t;
    index = at;
    const raw = await get(t, at);
    let offset = 0;
    const fields = t.fields.map(([name, width, mode]) => {
      const value = width === 2 ? u16(raw, offset, true) : raw[offset];
      offset += width;
      const input = el("input", {
        value: mode === "key" ? keyLabel(k, value) : value,
        type: mode === "key" ? "text" : "number",
        min: 0,
        max: width === 2 ? 65535 : 255,
      });
      return { input, width, mode, node: field(name, input) };
    });
    editor.replaceChildren(
      section(
        t.title,
        "Values come from the device. Save verifies the resulting entry; no automatic write retries.",
        el(
          "div",
          { class: "columns" },
          fields.map((f) => f.node),
        ),
        button(
          "Save entry",
          () =>
            ctx.run(async () => {
              if ((await k.unlockStatus())[0] !== 1)
                throw Error("Unlock the keyboard in Security first.");
              const wanted = bytes(
                ...fields.map((f) => {
                  const value =
                    f.mode === "key"
                      ? parseKeycode(k, f.input.value)
                      : integer(+f.input.value, 0, f.width === 2 ? 65535 : 255);
                  return f.width === 2 ? word(value, true) : [value];
                }),
              );
              await k.request(254, 13, t.write, at, wanted);
              if (!equal(await get(t, at), wanted))
                throw Error("Dynamic entry readback differs.");
            }),
          true,
        ),
      ),
    );
  }
  container.append(
    el("div", { class: "toolbar" }, field("Kind", type), field("Entry", entry)),
    editor,
  );
  await load(kind, index);
}
export async function settingsPage(container, ctx) {
  const k = ctx.keyboard,
    supported = new Set();
  let cursor = 0;
  for (let page = 0; page < 256; page++) {
    const response = await k.request(254, 9, word(cursor, true));
    let max = cursor;
    for (let i = 0; i < 32; i += 2) {
      const id = u16(response, i, true);
      if (id !== 65535) supported.add(id);
      max = Math.max(max, id);
    }
    if (max === 65535) break;
    if (max <= cursor) throw Error("QMK settings pagination did not advance.");
    cursor = max;
    if (page === 255) throw Error("QMK settings list exceeds its bound.");
  }
  const values = new Map(),
    groups = new Map();
  for (const tab of qmkSettings.tabs)
    for (const f of tab.fields)
      if (supported.has(f.qsid)) {
        if (!groups.has(f.qsid)) groups.set(f.qsid, []);
        groups.get(f.qsid).push(f);
      }
  const get = async (id, width) => {
    const r = await k.request(254, 10, word(id, true));
    if (r[0]) throw Error(`Cannot read QMK setting ${id}.`);
    let value = 0;
    for (let i = 0; i < width; i++) value += r[1 + i] * 2 ** (8 * i);
    return value;
  };
  for (const [id, fields] of groups)
    values.set(id, await get(id, fields[0].width ?? 1));
  if (!values.size) {
    container.append(
      note("This firmware does not advertise any editable QMK settings."),
    );
    return;
  }
  const inputs = new Map();
  for (const tab of qmkSettings.tabs) {
    const fields = tab.fields.filter((f) => supported.has(f.qsid));
    if (!fields.length) continue;
    container.append(
      section(
        tab.name,
        "",
        ...fields.map((f) => {
          const current = values.get(f.qsid),
            input =
              f.type === "boolean"
                ? toggle(f.title, !!(current & (1 << (f.bit ?? 0)))).input
                : el("input", {
                    type: "number",
                    value: current,
                    min: f.min,
                    max: f.max,
                  });
          inputs.set(f, input);
          return f.type === "boolean"
            ? el("label", { class: "toggle" }, input, f.title)
            : field(f.title, input);
        }),
      ),
    );
  }
  container.append(
    button(
      "Apply QMK settings",
      () =>
        ctx.run(async () => {
          if ((await k.unlockStatus())[0] !== 1)
            throw Error("Unlock the keyboard in Security first.");
          for (const [id, fields] of groups) {
            let value = values.get(id);
            const width = fields[0].width ?? 1;
            for (const f of fields) {
              const input = inputs.get(f);
              if (f.type === "boolean") {
                const mask = 1 << (f.bit ?? 0);
                value = (value & ~mask) | (input.checked ? mask : 0);
              } else value = integer(+input.value, f.min, f.max, f.title);
            }
            value >>>= 0;
            if (value === values.get(id)) continue;
            const raw = Array.from(
              { length: width },
              (_, i) => Math.floor(value / 2 ** (8 * i)) & 255,
            );
            const r = await k.request(254, 11, word(id, true), raw);
            if (r[0] || (await get(id, width)) !== value)
              throw Error(`QMK setting ${id} did not verify.`);
            values.set(id, value);
          }
        }),
      true,
    ),
  );
}
