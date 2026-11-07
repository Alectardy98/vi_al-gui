import {
  button,
  download,
  el,
  field,
  note,
  poll,
  section,
  select,
} from "./ui.js";
import { keyLabel } from "./keycodes.js";
import { keyboardView } from "./keyboard-view.js";
import { optionValues } from "./keyboard.js";
import { delay } from "./binary.js";
import { keycodePicker } from "./keycode-picker.js";

export function keymapPage(container, ctx) {
  const k = ctx.keyboard;
  let layer = 0,
    selected = null;
  const view = el("div"),
    selection = el(
      "p",
      { class: "muted" },
      "Select a key to change its assignment.",
    );
  const render = () =>
    view.replaceChildren(
      keyboardView(k, {
        layer,
        selected: selected?.id,
        onSelect: (key, id) => {
          selected = { key, id };
          selection.textContent = `Selected: ${keyLabel(k, k.code(layer, key))} · ${id}`;
          render();
          picker.refresh();
        },
      }),
    );
  const set = (code) =>
    ctx.run(
      async () => {
        if (!selected) throw Error("Select a keyboard key first.");
        const current = selected;
        const targetLayer = layer;
        await k.setKey(targetLayer, current.key, code);
        render();
        selection.textContent = `Saved: ${keyLabel(k, code)} · ${current.id}`;
      },
      k.demo
        ? "Demo key changed. No keyboard was written."
        : "Key assignment saved and read back.",
    );
  const picker = keycodePicker(k, {
    onChoose: set,
    hasSelection: () => !!selected,
    notify: ctx.notify,
  });
  const layerButtons = el(
    "div",
    { class: "segmented layers" },
    Array.from({ length: k.layers }, (_, index) => {
      const b = button(String(index), () => {
        layer = index;
        for (const child of layerButtons.children)
          child.classList.toggle("active", +child.textContent === layer);
        render();
      });
      b.classList.toggle("active", !index);
      return b;
    }),
  );
  container.append(
    section(
      "Keymap",
      "Select a physical key, then choose its new action. Changes are saved to the keyboard and read back.",
      el(
        "div",
        { class: "toolbar" },
        el("span", { class: "eyebrow" }, "LAYER"),
        layerButtons,
        button("Reload", () =>
          ctx.run(async () => {
            await k.reloadKeymap();
            render();
          }, "Keymap reloaded."),
        ),
        button("Export keymap", () =>
          ctx.run(
            async () =>
              download(
                "vi-al-keymap.json",
                JSON.stringify(await k.exportKeymap(), null, 2),
              ),
            "Keymap downloaded.",
          ),
        ),
      ),
      view,
    ),
    section("Keycodes", null, selection, picker.node),
  );
  render();
}

export function layoutPage(container, ctx) {
  const k = ctx.keyboard,
    labels = k.definition.layouts.labels ?? [],
    values = optionValues(labels, k.layoutOptions);
  if (!labels.length) {
    container.append(
      section(
        "Layout",
        "This keyboard has one fixed physical layout.",
        keyboardView(k),
      ),
    );
    return;
  }
  const preview = el("div");
  const renderPreview = () =>
    preview.replaceChildren(keyboardView(k, { layoutChoices: values }));
  const fields = labels.map((label, i) =>
    field(
      typeof label === "string" ? label : label[0],
      select(
        typeof label === "string"
          ? [
              [0, "Off"],
              [1, "On"],
            ]
          : label.slice(1).map((x, i) => [i, x]),
        values[i],
        (e) => {
          values[i] = +e.target.value;
          renderPreview();
        },
      ),
    ),
  );
  container.append(
    section(
      "Layout preview",
      "Preview physical options here. Apply layout saves them to the keyboard.",
      preview,
    ),
    section(
      "Physical layout",
      "Choose the actual switch layout fitted to your keyboard.",
      ...fields,
      button(
        "Apply layout",
        () =>
          ctx.run(async () => {
            await k.setOptions(values);
            ctx.openPage("layout");
          }, "Layout saved and verified."),
        true,
      ),
    ),
  );
  renderPreview();
}

export async function securityPage(container, ctx) {
  const k = ctx.keyboard;
  const status = await k.unlockStatus();
  const keys = [];
  for (let i = 2; i < 32; i += 2)
    if (status[i] !== 255 && status[i + 1] !== 255)
      keys.push(`${status[i]},${status[i + 1]}`);
  const message = el(
    "p",
    { class: "notice" },
    status[0] === 1
      ? "Keyboard is unlocked."
      : `Hold the unlock keys: ${keys.join(" · ")} (matrix row, column).`,
  );
  const unlock = button(
    "Start unlock",
    () =>
      ctx.run(async () => {
        if (k.demo) {
          ctx.notify("Demo keyboard is already unlocked.");
          return;
        }
        await k.request(254, 6);
        for (let i = 0; i < 80 && !ctx.signal.aborted; i++) {
          const r = await k.request(254, 7);
          if (r[0] === 1) {
            message.textContent = "Keyboard is unlocked.";
            return;
          }
          await delay(250);
        }
        throw Error(
          "Unlock did not finish. Hold the displayed keys and try again.",
        );
      }, "Unlock complete."),
    true,
  );
  container.append(
    section(
      "Keyboard security",
      "Use the firmware’s physical unlock sequence for protected operations.",
      message,
      el(
        "div",
        { class: "toolbar" },
        unlock,
        button("Lock keyboard", () =>
          ctx.run(async () => {
            await k.request(254, 8);
            ctx.openPage("security");
          }, "Keyboard locked."),
        ),
      ),
    ),
  );
}

export async function matrixPage(container, ctx) {
  const k = ctx.keyboard;
  const cells = Array.from({ length: k.rows * k.cols }, (_, i) =>
    el(
      "div",
      { class: "matrix-cell" },
      `${Math.floor(i / k.cols)},${i % k.cols}`,
    ),
  );
  const status = note("Polling the keyboard matrix.");
  container.append(
    section(
      "Matrix tester",
      "Green cells are pressed. This reads the keyboard matrix without remapping any keys.",
      status,
      el(
        "div",
        {
          class: "matrix",
          style: {
            gridTemplateColumns: `repeat(${k.cols}, minmax(24px, 1fr))`,
          },
        },
        cells,
      ),
    ),
  );
  if ((await k.unlockStatus())[0] !== 1) {
    status.textContent =
      "Unlock the keyboard in Security before starting the matrix tester.";
    return;
  }
  poll(
    ctx.signal,
    async () => {
      try {
        const bits = await ctx.read(() => k.matrix());
        if (!ctx.signal.aborted && bits)
          cells.forEach((cell, i) => cell.classList.toggle("pressed", bits[i]));
      } catch (e) {
        status.textContent = e.message;
        throw e;
      }
    },
    70,
  );
}

export async function lightingPage(container, ctx) {
  const k = ctx.keyboard,
    kind = k.definition.lighting;
  if (
    ![
      "qmk_rgblight",
      "qmk_backlight",
      "qmk_backlight_rgblight",
      "vialrgb",
    ].includes(kind)
  ) {
    container.append(
      section(
        "Lighting",
        "This keyboard uses an add-on for its lighting controls.",
        note("Choose the keyboard’s lighting page in the sidebar."),
      ),
    );
    return;
  }
  const vial = kind === "vialrgb";
  const get = async (id) => (await k.request(8, id)).slice(2);
  const inputs = [];
  if (vial) {
    const info = await get(0x40);
    if (info[0] !== 1 || info[1] !== 0) throw Error("Unknown VialRGB version.");
    const r = await get(0x41);
    const mode = el("input", {
      type: "number",
      min: 0,
      max: 65535,
      value: r[0] | (r[1] << 8),
    });
    const speed = el("input", { type: "range", min: 0, max: 255, value: r[2] });
    const hsv = [r[3], r[4], r[5]].map((v, i) =>
      el("input", {
        type: "range",
        min: 0,
        max: i === 2 ? info[2] : 255,
        value: v,
      }),
    );
    container.append(
      section(
        "VialRGB",
        "Use the mode IDs supported by this firmware.",
        field("Effect ID", mode),
        field("Speed", speed),
        ...["Hue", "Saturation", "Brightness"].map((name, i) =>
          field(name, hsv[i]),
        ),
        button(
          "Apply and save",
          () =>
            ctx.run(async () => {
              const wanted = [
                +mode.value & 255,
                +mode.value >>> 8,
                +speed.value,
                ...hsv.map((x) => +x.value),
              ];
              await k.request(7, 0x41, wanted);
              const actual = await get(0x41);
              if (wanted.some((v, i) => actual[i] !== v))
                throw Error("Lighting readback differs.");
              await k.request(9);
            }),
          true,
        ),
      ),
    );
  } else {
    const ids = [];
    if (kind.includes("backlight"))
      ids.push([9, "Backlight brightness"], [10, "Backlight effect"]);
    if (kind.includes("rgblight"))
      ids.push(
        [128, "RGB brightness"],
        [129, "RGB effect"],
        [130, "RGB speed"],
      );
    for (const [id, name] of ids) {
      const input = el("input", {
        type: "number",
        min: 0,
        max: 255,
        value: (await get(id))[0],
      });
      inputs.push([id, input]);
      container.append(field(name, input));
    }
    container.append(
      button(
        "Apply and save lighting",
        () =>
          ctx.run(async () => {
            for (const [id, input] of inputs) {
              const value = +input.value;
              if (!Number.isInteger(value) || value < 0 || value > 255)
                throw Error("Choose a value from 0 to 255.");
              await k.request(7, id, value);
              if ((await get(id))[0] !== value)
                throw Error("Lighting readback differs.");
            }
            await k.request(9);
          }),
        true,
      ),
    );
  }
}
