// SPDX-License-Identifier: GPL-2.0-or-later
import { My2k, lockRecord, oledRecord } from "./protocol.js";
import { bytes, equal, integer, u16, u32 } from "../../../web/src/binary.js";
import {
  button,
  el,
  field,
  note,
  range,
  section,
  select,
  toggle,
} from "../../../web/src/ui.js";
import { keyLabel, parseKeycode } from "../../../web/src/keycodes.js";
import { animationPage, connectFiles } from "./animations.js";
import { typingBitmap } from "./typing-preview.js";

const rgbHex = (color) =>
  "#" + color.map((x) => x.toString(16).padStart(2, "0")).join("");
const colorBytes = (input) =>
  input.value
    .slice(1)
    .match(/../g)
    .map((x) => parseInt(x, 16));
const effects = [
  "Solid color",
  "Blink",
  "Breathing",
  "Pulse",
  "Rainbow cycle",
].map((name, id) => [id, name]);
export function keyInput(ctx, value, label) {
  const list = `keys-${Math.random().toString(16).slice(2)}`;
  const input = el("input", {
    value: keyLabel(ctx.keyboard, value),
    list,
    "aria-label": label,
  });
  const options = el(
    "datalist",
    { id: list },
    ctx.keyboard.catalogue
      .filter((k) => k.code <= 0x1fff)
      .map((k) => el("option", { value: k.id }, k.label)),
  );
  return {
    input,
    node: field(label, el("div", {}, input, options)),
    value: () => parseKeycode(ctx.keyboard, input.value.trim()),
  };
}
async function touchPage(container, ctx) {
  const client = new My2k(ctx.keyboard);
  let actual = await client.touch();
  const mode = select(
    [
      [0, "Hold"],
      [1, "Slider"],
    ],
    actual.values.mode,
  );
  const left = keyInput(ctx, actual.values.left, "Left"),
    right = keyInput(ctx, actual.values.right, "Right"),
    tap = keyInput(ctx, actual.values.tap, "Tap");
  const sensitivity = range("Sensitivity", actual.values.sensitivity, 1, 100),
    jitter = range("Tap jitter threshold", actual.values.tap_jitter, 0, 100);
  container.append(
    section(
      "Touch bar",
      "Hold repeats the side action while touched. Slider turns a swipe into repeated key presses; a tap uses the separate Tap action.",
      field("Mode", mode),
      el("div", { class: "columns" }, left.node, right.node),
      tap.node,
      sensitivity.node,
      jitter.node,
      note(
        actual.holdJitter
          ? "Tap jitter applies to Hold and Slider modes."
          : "This firmware applies tap jitter to Slider mode only.",
      ),
      button(
        "Apply touch settings",
        () =>
          ctx.run(async () => {
            actual = await client.setTouch(actual.revision, {
              mode: +mode.value,
              sensitivity: +sensitivity.input.value,
              tap_jitter: +jitter.input.value,
              left: left.value(),
              right: right.value(),
              tap: tap.value(),
            });
          }),
        true,
      ),
    ),
  );
}
function drawBitmap(canvas, bitmap) {
  const c = canvas.getContext("2d"),
    image = c.createImageData(72, 40);
  for (let y = 0; y < 40; y++)
    for (let x = 0; x < 72; x++) {
      const v = bitmap?.[Math.floor(y / 8) * 72 + x] & (1 << (y % 8)) ? 244 : 8,
        at = (y * 72 + x) * 4;
      image.data.set([v, v, v, 255], at);
    }
  c.putImageData(image, 0, 0);
}
function renderMessage(message, family, size) {
  const canvas = document.createElement("canvas");
  canvas.width = 72;
  canvas.height = 40;
  const c = canvas.getContext("2d");
  c.fillStyle = "#000";
  c.fillRect(0, 0, 72, 40);
  c.fillStyle = "#fff";
  c.font = `${size}px "${family}", monospace`;
  c.textBaseline = "top";
  let line = "",
    y = 0;
  for (const char of message) {
    if (char === "\n" || (line && c.measureText(line + char).width > 72)) {
      c.fillText(line, 0, y);
      y += +size;
      line = "";
    }
    if (char !== "\n") line += char;
  }
  c.fillText(line, 0, y);
  const pixels = c.getImageData(0, 0, 72, 40).data,
    result = new Uint8Array(360);
  for (let yy = 0; yy < 40; yy++)
    for (let x = 0; x < 72; x++)
      if (pixels[(yy * 72 + x) * 4] >= 128)
        result[Math.floor(yy / 8) * 72 + x] |= 1 << (yy % 8);
  return result;
}
async function oledPage(container, ctx) {
  const client = new My2k(ctx.keyboard);
  let actual = await client.oled(),
    bitmap = actual.values.bitmap;
  const message = el("textarea", {
    rows: 4,
    maxLength: 59,
    value: actual.values.message,
    "aria-label": "Idle message",
  });
  const label = el("input", {
    value: actual.values.label,
    maxLength: 10,
    "aria-label": "Typing label",
  });
  const families = [
    ...new Set([
      actual.values.font_family,
      "DejaVu Sans Mono",
      "monospace",
      "sans-serif",
      "serif",
    ]),
  ];
  const font = select(
      families.map((x) => [x, x]),
      actual.values.font_family,
    ),
    size = el("input", {
      type: "number",
      min: 8,
      max: 38,
      value: actual.values.font_size,
    });
  const typing = toggle("Enable Typing Mode", actual.values.typing);
  const override = select(
    [
      [0, "Saved message"],
      [1, "Happy Mode Override"],
      [2, "Clock Mode Override"],
    ],
    actual.values.happy ? 1 : actual.values.clock ? 2 : 0,
  );
  const preview = el("canvas", {
    width: 72,
    height: 40,
    class: "oled-preview",
    "aria-label": "Screen Saver preview",
  });
  const typingPreview = el("canvas", {
    width: 72,
    height: 40,
    class: "oled-preview",
    "aria-label": "Typing Mode preview",
  });
  let changedMessage = false;
  const update = () => {
    changedMessage = true;
    try {
      bitmap = renderMessage(message.value, font.value, +size.value);
      drawBitmap(preview, bitmap);
    } catch (e) {
      ctx.notify(e.message, true);
    }
  };
  for (const input of [message, font, size])
    input.addEventListener("input", update);
  label.addEventListener("input", () =>
    drawBitmap(typingPreview, typingBitmap(label.value)),
  );
  drawBitmap(typingPreview, typingBitmap(label.value));
  drawBitmap(
    preview,
    bitmap ?? renderMessage(message.value, font.value, +size.value),
  );
  const syncKey = `vi_al.web.clock.${ctx.keyboard.uid}`;
  const sync = toggle(
    "Sync date & time on connect",
    localStorage.getItem(syncKey) === "1",
    (value) => localStorage.setItem(syncKey, value ? "1" : "0"),
  );
  const apply = button(
    "Apply changes",
    () =>
      ctx.run(
        async () => {
          const wanted = {
            message: message.value,
            label: label.value,
            typing: typing.input.checked,
            happy: +override.value === 1,
            clock: +override.value === 2,
            font_family: font.value,
            font_size: +size.value,
            bitmap: changedMessage ? bitmap : actual.values.bitmap,
          };
          oledRecord(wanted);
          actual = await client.setOled(wanted);
          changedMessage = false;
        },
        actual.persistent
          ? "OLED configuration persisted and read back."
          : "OLED configuration applied and read back; firmware reports session-only settings.",
      ),
    true,
  );
  container.append(
    note(
      "Changes apply only when you press Apply changes. No keyboard writes happen while editing.",
    ),
    el(
      "div",
      { class: "toolbar" },
      apply,
      button("Sync date & time", () =>
        ctx.run(
          () => client.syncClock(),
          "Time synchronized; the current display mode will resume.",
        ),
      ),
      sync.node,
    ),
    el(
      "div",
      { class: "columns" },
      section(
        "Screen Saver",
        "Saved idle message and its monochrome bitmap.",
        field("Message · maximum 59 ASCII characters", message),
        el(
          "div",
          { class: "columns" },
          field("Font", font),
          field("Size", size),
        ),
        preview,
      ),
      section(
        "Typing Mode",
        "Typing has priority over the message and idle overrides.",
        typing.node,
        field("Corner label · maximum 10 ASCII characters", label),
        note(
          "The typing label uses the firmware’s fixed 6×8 font. It has no independent font or size setting.",
        ),
        typingPreview,
      ),
    ),
    section(
      "Idle override",
      "Enabling an override replaces the message when you are not typing.",
      field("Screen Saver mode", override),
    ),
    button("Reload from keyboard", () => ctx.openPage("my2k-oled")),
  );
}
async function locksPage(container, ctx) {
  const client = new My2k(ctx.keyboard);
  let actual = await client.locks();
  const editor = el("div");
  const fixedNames = [
    "Under Cap · Scroll Lock",
    "Under Cap · Caps Lock",
    "Under Cap · Num Lock",
    "100NG · Caps Lock",
    "100NG · Num Lock",
  ];
  function rowControls(item, onRemove) {
    const enabled = toggle("Enabled", item.enabled, (v) => {
      item.enabled = v;
    });
    const color = el("input", {
      type: "color",
      value: rgbHex(item.color),
      onInput: (event) => {
        item.color = colorBytes(event.target);
      },
    });
    const effect = select(effects, item.effect, (e) => {
      item.effect = +e.target.value;
    });
    const speed = range("Speed", item.speed, 0, 15, (value) => {
      item.speed = value;
    });
    return el(
      "div",
      {},
      el(
        "div",
        { class: "toolbar" },
        enabled.node,
        color,
        effect,
        onRemove ? button("Remove rule", onRemove) : null,
      ),
      speed.node,
    );
  }
  function draw() {
    const values = actual.values;
    const fixed = el(
      "div",
      { class: "columns" },
      values.fixed.map((item, i) =>
        section(fixedNames[i], "", rowControls(item)),
      ),
    );
    const rules = values.rules.map((item, i) => {
      const triggerId = item.trigger === 4 ? item.layer + 3 : item.trigger;
      const trigger = select(
        [
          [0, "None"],
          [1, "Caps Lock"],
          [2, "Num Lock"],
          [3, "Scroll Lock"],
          [4, "Layer 1"],
          [5, "Layer 2"],
          [6, "Layer 3"],
        ],
        triggerId,
        (e) => {
          const value = +e.target.value;
          item.trigger = value >= 4 ? 4 : value;
          item.layer = value >= 4 ? value - 3 : 0;
        },
      );
      return section(
        `Rule ${i + 1}`,
        "",
        field("Trigger", trigger),
        rowControls(item, () => {
          values.rules.splice(i, 1);
          draw();
        }),
        el(
          "div",
          { class: "toolbar" },
          button("Move up", () => {
            if (i) {
              [values.rules[i], values.rules[i - 1]] = [
                values.rules[i - 1],
                values.rules[i],
              ];
              draw();
            }
          }),
          button("Move down", () => {
            if (i < values.rules.length - 1) {
              [values.rules[i], values.rules[i + 1]] = [
                values.rules[i + 1],
                values.rules[i],
              ];
              draw();
            }
          }),
        ),
      );
    });
    const fallback = toggle(
      "Use fallback color when no rule matches",
      values.fallback_enabled,
      (value) => {
        values.fallback_enabled = value;
      },
    );
    const fallbackColor = el("input", {
      type: "color",
      value: rgbHex(values.fallback),
      onInput: (e) => {
        values.fallback = colorBytes(e.target);
      },
    });
    editor.replaceChildren(
      fixed,
      section(
        "LED Square",
        "First matching enabled rule wins. With no match, LED Square follows its base RGB-strip behavior unless a fallback is enabled.",
        ...rules,
        el(
          "div",
          { class: "toolbar" },
          button("Add rule", () => {
            if (values.rules.length >= 8) {
              ctx.notify("At most eight rules are supported.", true);
              return;
            }
            values.rules.push({
              trigger: 0,
              layer: 0,
              enabled: true,
              effect: 0,
              speed: 8,
              color: [255, 255, 255],
            });
            draw();
          }),
          fallback.node,
          fallbackColor,
        ),
      ),
    );
  }
  container.append(
    note(
      "Edit the rules, then Apply. The five fixed hardware assignments remain unchanged.",
    ),
    button(
      "Apply Lock Lights",
      () =>
        ctx.run(async () => {
          lockRecord(actual.values);
          actual = await client.setLocks(actual.revision, actual.values);
          draw();
        }),
      true,
    ),
    editor,
  );
  draw();
}
function rgbFeature(keyboard, name) {
  return keyboard.definition.amkFeature?.find(
    (f) => typeof f === "object" && f[name],
  )?.[name];
}
function rgbPage(type) {
  return async (container, ctx) => {
    const client = new My2k(ctx.keyboard),
      feature = rgbFeature(ctx.keyboard, type === 1 ? "rgb_strip" : "rgb_grid");
    if (!feature)
      throw Error(
        "The keyboard definition does not advertise this RGB region.",
      );
    const regions = feature[type === 1 ? "strips" : "grids"],
      list = el("div", { class: "zone-grid" }),
      controls = el("div");
    let chosen = 0;
    const getParam = async (param, i) => client.amk(61, type, param, i);
    async function load(index) {
      chosen = index;
      const [info, color, speed, bright] = await Promise.all([
        client.amk(type === 1 ? 28 : 66, index),
        getParam(0, index),
        getParam(2, index),
        getParam(4, index),
      ]);
      const value = el("input", {
        type: "color",
        value: rgbHex([...color.slice(4, 7)]),
      });
      const effect = select(
        feature.effects.map((x, id) => [id, x.split("/")[0]]),
        info[6],
      );
      const speedInput = range("Speed", speed[4], 0, 255),
        brightness = range("Brightness", bright[4], 0, 255);
      controls.replaceChildren(
        section(
          regions[index].name.split("/")[0],
          "Base-layer appearance. Lock Lights supplies matching modifier/layer overrides.",
          field("Color", value),
          field("Effect", effect),
          speedInput.node,
          brightness.node,
          button(
            "Apply region",
            () =>
              ctx.run(async () => {
                const rgb = colorBytes(value);
                for (const [param, data] of [
                  [0, rgb],
                  [2, [+speedInput.input.value]],
                  [4, [+brightness.input.value]],
                ]) {
                  await client.amk(62, type, param, index, data);
                  const actual = await getParam(param, index);
                  if (!equal(actual.slice(4, 4 + data.length), bytes(data)))
                    throw Error("RGB parameter readback differs.");
                }
                await client.amk(type === 1 ? 32 : 68, index, +effect.value);
                const read = await client.amk(type === 1 ? 28 : 66, index);
                if (read[6] !== +effect.value)
                  throw Error("RGB effect readback differs.");
              }),
            true,
          ),
        ),
      );
      for (const b of list.children)
        b.classList.toggle("active", +b.dataset.index === chosen);
    }
    regions.forEach((region, index) => {
      const b = button(region.name.split("/")[0], () =>
        ctx.run(() => load(index), "RGB settings loaded."),
      );
      b.dataset.index = index;
      list.append(b);
    });
    container.append(
      section(
        type === 1 ? "RGB Strips" : "RGB Grid",
        "Choose the physical lighting region to configure.",
        list,
      ),
      controls,
    );
    await load(0);
  };
}
async function generalPage(container, ctx) {
  const client = new My2k(ctx.keyboard);
  let sleep = await client.sleep();
  const enabled = toggle("Enable visual sleep", sleep.values.enabled),
    timeout = range("Sleep timeout · minutes", sleep.values.minutes, 5, 120);
  const perf = await client.amk(75);
  if (
    perf[3] !== 1 ||
    ![0, 1].includes(perf[4]) ||
    ![0, 1, 255].includes(perf[5])
  )
    throw Error("Unsupported input-performance schema.");
  const mode = select(
    [
      [0, "Standard · 1,000 Hz"],
      [1, "High Performance · 8,000 Hz interval"],
    ],
    perf[4],
  );
  const status = note(
    `Active USB interval: ${u16(perf, 8, true)} µs · Target matrix scan: ${u16(perf, 10, true)} µs${perf[6] & 64 ? " · Storage override active" : ""}`,
  );
  const nkro = toggle("N-key rollover", !!(await client.amk(13))[3]);
  container.append(
    section(
      "USB performance",
      "Changing USB mode restarts Main. Reconnect in the browser afterwards. An 8,000 Hz interval does not by itself prove 8,000 distinct input reports per second.",
      status,
      field("Mode", mode),
      button(
        "Apply & restart",
        () =>
          ctx.run(async () => {
            if (
              !confirm(
                "Save this USB mode and restart the keyboard? Reconnect to the website after enumeration.",
              )
            )
              return;
            const r = await client.amk(76, +mode.value);
            if (r[3] !== 1 || r[4] !== +mode.value || u32(r, 20, true))
              throw Error("Performance mode was not acknowledged.");
          }, "Mode acknowledged. Reconnect and verify its active interval."),
        true,
      ),
    ),
    section(
      "Keyboard input",
      "NKRO changes apply to Main.",
      nkro.node,
      button("Apply NKRO", () =>
        ctx.run(async () => {
          await client.amk(14, +nkro.input.checked);
          if (!!(await client.amk(13))[3] !== nkro.input.checked)
            throw Error("NKRO readback differs.");
        }),
      ),
    ),
    section(
      "Display test",
      "Show or exit the native transfer/FPS test without changing animation files.",
      el(
        "div",
        { class: "toolbar" },
        button("Show display test", () =>
          ctx.run(() => client.selectAnimation(1, 12), "Display test started."),
        ),
        button("Return to animation", () =>
          ctx.run(() => client.selectAnimation(0, 12), "Animation restored."),
        ),
      ),
    ),
    section(
      "Sleep",
      "RGB and both displays sleep after inactivity. The keyboard keeps typing and one ordinary key wakes the visuals.",
      enabled.node,
      timeout.node,
      button(
        "Apply sleep settings",
        () =>
          ctx.run(async () => {
            sleep = await client.setSleep(sleep.revision, {
              enabled: enabled.input.checked,
              minutes: +timeout.input.value,
            });
          }),
        true,
      ),
    ),
  );
}
async function gamingPage(container, ctx) {
  const client = new My2k(ctx.keyboard),
    caps = await client.gaming();
  if (String.fromCharCode(...caps.slice(8, 12)) !== "GME1" || !(caps[28] & 8))
    throw Error("Game control mapping needs matching Main firmware.");
  const controls = el("div");
  let game = 1;
  const choices = select(
    [
      [1, "NES"],
      ...(caps[28] & 16 ? [[3, "Game Boy Color"]] : []),
      ...(caps[28] & 4 ? [[2, "Doom"]] : []),
    ],
    1,
    (e) => ctx.run(() => load(+e.target.value), "Game bindings loaded."),
  );
  container.append(
    section(
      "Gaming",
      "Game controls are stored on the keyboard. Use the corresponding physical custom keycode to start or exit a game.",
      caps[27]
        ? note(
            "NES, GBC and Doom require Standard / 1K mode. Switch USB mode in General before launching a game.",
          )
        : null,
      field("Game", choices),
    ),
    controls,
  );
  async function load(next) {
    game = next;
    let actual = await client.gameKeys(game);
    const labels =
      game === 2
        ? [
            "Forward",
            "Back",
            "Turn left",
            "Turn right",
            "Fire",
            "Use",
            "Run",
            "Escape",
          ]
        : ["Up", "Down", "Left", "Right", "A", "B", "Select", "Start"];
    const fields = actual.keys.map((key, i) => keyInput(ctx, key, labels[i]));
    controls.replaceChildren(
      section(
        "Controls",
        "Ordinary keyboard keys and modifiers only. Editing this form does not launch a game.",
        el(
          "div",
          { class: "columns" },
          fields.map((f) => f.node),
        ),
        button(
          "Save game controls",
          () =>
            ctx.run(async () => {
              actual = await client.setGameKeys(
                game,
                fields.map((f) => f.value()),
                actual.revision,
              );
            }),
          true,
        ),
      ),
    );
    if (game !== 2) {
      const gbc = game === 3,
        catalogue = el("div");
      async function showLibrary() {
        const { rows, truncated } = await ctx.keyboard.files.catalogue(gbc);
        const selectRom = select(
          rows.map((row, i) => [
            i,
            `${row.name}${row.selected ? " · selected" : ""}${row.error ? ` · Unsupported (${row.error})` : ""}`,
          ]),
          Math.max(
            0,
            rows.findIndex((row) => row.selected),
          ),
        );
        catalogue.replaceChildren(
          rows.length
            ? field("ROM on keyboard", selectRom)
            : note(
                "No ROMs were found in the corresponding keyboard storage folder.",
              ),
          truncated ? note("The catalogue reached its directory limit.") : null,
          rows.length
            ? button(
                "Use selected ROM",
                () =>
                  ctx.run(async () => {
                    const selected = rows[+selectRom.value];
                    if (!selected || selected.error)
                      throw Error("Choose a supported ROM.");
                    await ctx.keyboard.files.selectRom(selected.name, gbc);
                    await showLibrary();
                  }, "ROM selected, persisted and read back."),
                true,
              )
            : null,
        );
      }
      const connect = button("Connect ROM file access", async () => {
        try {
          await connectFiles(ctx);
          await ctx.run(showLibrary, "ROM catalogue loaded.");
        } catch (e) {
          ctx.notify(e.message, true);
        }
      });
      controls.append(
        section(
          "ROM library",
          "ROM files stay on the keyboard. Connecting uses its dedicated WebUSB file interface.",
          connect,
          catalogue,
        ),
      );
      if (ctx.keyboard.files && !ctx.keyboard.files.uncertain)
        await showLibrary();
    }
  }
  await load(1);
}
export default {
  id: "my2k",
  name: "MY-2K",
  supports: (keyboard) =>
    /MY.?2K|100NG/i.test(keyboard.definition.name ?? "") &&
    keyboard.definition.inputPerformance?.version === 1,
  onConnect: async (keyboard) => {
    if (localStorage.getItem(`vi_al.web.clock.${keyboard.uid}`) === "1")
      await new My2k(keyboard).syncClock();
  },
  pages: [
    { id: "my2k-strips", title: "RGB Strips", render: rgbPage(1) },
    { id: "my2k-grid", title: "RGB Grid", render: rgbPage(3) },
    { id: "my2k-locks", title: "Lock Lights", render: locksPage },
    { id: "my2k-touch", title: "Touch bar", render: touchPage },
    { id: "my2k-gaming", title: "Gaming", render: gamingPage },
    { id: "my2k-general", title: "General", render: generalPage },
    { id: "my2k-oled", title: "Auxiliary Display", render: oledPage },
    { id: "my2k-animations", title: "Animations", render: animationPage },
  ],
};
