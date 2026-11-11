// SPDX-License-Identifier: GPL-3.0-or-later
import { LeydenJar, supported, C, position } from "./protocol.js";
import { button, el, note, poll, range, section } from "../../src/ui.js";
import { groupFor, reading, keyView, updateKeys, chart } from "./view.js";
import "./style.css";
const open = async (ctx) => new LeydenJar(ctx.keyboard).connect();
const emptyFrame = () => ({
  values: new Map(),
  logical: new Set(),
  physical: new Set(),
});
function sampling(ctx, client, live, consume) {
  let lastSweep = -Infinity,
    frame = emptyFrame();
  poll(
    ctx.signal,
    async () => {
      if (ctx.isBusy()) return;
      try {
        const next = await ctx.read(async () => {
          if (live() && performance.now() - lastSweep >= 400) {
            frame.values = await client.levels();
            lastSweep = performance.now();
            frame.sampleNumber = (frame.sampleNumber ?? 0) + 1;
          }
          const state = await client.keys();
          return { ...frame, ...state };
        });
        if (next && !ctx.signal.aborted) {
          frame = next;
          consume(frame);
        }
      } catch (e) {
        if (!ctx.signal.aborted) ctx.notify(e.message, true);
        throw e;
      }
    },
    70,
  );
}
function initialKey(client) {
  const first =
    client.keyboard
      .visibleKeys()
      .map((k) => position(k.row, k.col))
      .find((id) => groupFor(client, id) !== null) ??
    [...client.bins]
      .filter(([, bin]) => bin !== 255)
      .map(([id]) => client.logicalPosition(id))
      .find(Boolean);
  if (!first) throw Error("The controller reports no mapped analog keys.");
  return first;
}
async function generalPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  const d = client.details,
    tbody = el("tbody");
  const information = () => {
    const rows = [
      ["Native protocol", client.version.join(".")],
      ["Vial UID", ctx.keyboard.uid],
      ["QMK matrix", `${d.rows} × ${d.cols}`],
      ["Controller matrix", `${d.physicalRows} × ${d.physicalCols}`],
      ["Switch technology", d.technology ? "Beamspring" : "Model F"],
      [
        "Mapping format",
        ["Leyden Jar", "xwhatsit", "wcass"][client.mappingType],
      ],
      [
        "Logical → controller rows",
        client.rows.map((x) => (x === 255 ? "—" : x)).join(", "),
      ],
      [
        "Logical → controller columns",
        client.cols
          .slice(0, d.cols)
          .map((x) => (x === 255 ? "—" : x))
          .join(", "),
      ],
      ["Calibration groups", d.bins],
      ["Keyboard typing", client.enabled ? "Enabled" : "Disabled"],
      [
        "Calibration storage",
        client.persistent
          ? "Persistent offsets; automatic startup calibration"
          : "Temporary until restart",
      ],
    ];
    if (client.side) rows.push(["Split side", client.side]);
    if (d.directKey)
      rows.push([
        "Direct switch",
        `QMK ${d.directKey[0]}, ${d.directKey[1]} · GPIO${d.directKey[2]}`,
      ]);
    if (d.expandedColumns)
      rows.push(["Expanded scanner", "Four sense rows, twenty drive columns"]);
    tbody.replaceChildren(
      ...rows.map((row) => el("tr", {}, ...row.map((v) => el("td", {}, v)))),
    );
  };
  const enable = button("", () =>
    ctx.run(async () => {
      await client.setEnabled(!client.enabled);
      refresh();
    }, "Keyboard typing state verified by readback."),
  );
  const refresh = () => {
    information();
    enable.textContent = client.enabled ? "Disable typing" : "Enable typing";
    enable.setAttribute("aria-pressed", String(client.enabled));
  };
  refresh();
  const actions = section(
    "Keyboard controls",
    "Commands affect only this selected controller.",
    el(
      "div",
      { class: "leyden-actions" },
      enable,
      button("Reload information", () =>
        ctx.run(async () => {
          await client.refreshBins();
          client.enabled = await client.readEnabled();
          refresh();
        }, "Controller information reloaded."),
      ),
    ),
  );
  const restart = (label, command, warning) =>
    button(label, () => {
      if (globalThis.confirm(warning))
        ctx.run(
          () => client.restart(command),
          "Command sent; reconnect after the keyboard restarts.",
        );
    });
  actions.append(
    el(
      "div",
      { class: "leyden-actions" },
      restart(
        "Restart and recalibrate",
        C.reboot,
        "Release every key, then restart and measure new calibration references? Saved offsets and keymaps remain.",
      ),
      restart(
        "Bootloader",
        C.boot,
        "Restart the selected keyboard into its existing bootloader?",
      ),
      restart(
        "Clear EEPROM",
        C.erase,
        "Clear all QMK/Vial settings, keymaps, macros and calibration overrides on this keyboard?",
      ),
    ),
  );
  container.append(
    section(
      "Controller information",
      "Values read from the keyboard, not a guessed wiring table.",
      el("table", {}, tbody),
    ),
    actions,
  );
}
async function calibrationPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  let selected = initialKey(client),
    group = groupFor(client, selected),
    live = true,
    frame = emptyFrame();
  const view = el(
      "div",
      { class: "leyden-keyboard" },
      keyView(client, {
        selected,
        onSelect: (id) => {
          const bin = groupFor(client, id);
          if (bin === null) {
            ctx.notify("This position has no analog calibration group.");
            return;
          }
          selected = id;
          choose(bin);
        },
      }),
    ),
    selection = el("p", { class: "muted" }),
    tbody = el("tbody"),
    cells = [];
  for (let bin = 0; bin < client.details.bins; bin++) {
    const row = el(
      "tr",
      {},
      el(
        "td",
        {},
        button(`Group ${bin + 1}`, () => choose(bin)),
      ),
    );
    const values = Array.from({ length: 4 }, () => el("td"));
    row.append(...values);
    cells.push({ row, values });
    tbody.append(row);
  }
  const trigger = range(
    "Group trigger",
    client.thresholds[group] ?? 0,
    0,
    1023,
    (value) => edit(value),
  );
  const number = el("input", {
    type: "number",
    min: 0,
    max: 1023,
    value: client.thresholds[group] ?? 0,
    "aria-label": "Group trigger value",
    onInput: () => edit(Number(number.value)),
  });
  const edit = (value) => {
    trigger.set(value);
    number.value = value;
  };
  trigger.input.addEventListener("input", () => {
    number.value = trigger.input.value;
  });
  const apply = button(
    client.persistent ? "Apply and save" : "Apply to this group",
    () =>
      ctx.run(
        async () => {
          await client.setThreshold(group, Number(number.value));
          choose(group);
        },
        client.persistent
          ? "Saved offset and trigger verified by readback."
          : "Trigger verified. This firmware keeps it only until restart.",
      ),
    true,
  );
  const pause = button("Pause live readings", () => {
    live = !live;
    pause.textContent = live ? "Pause live readings" : "Resume live readings";
  });
  const defaults = button("Restore calibration defaults", () => {
    if (
      globalThis.confirm(
        "Restore only calibration offsets? Your Vial keymaps and macros stay unchanged.",
      )
    )
      ctx.run(async () => {
        await client.restoreDefaults();
        choose(group);
      }, "Calibration defaults verified; keymaps preserved.");
  });
  defaults.disabled = !client.persistent;
  const choose = (bin) => {
    group = bin;
    const ref = client.references[bin];
    const min = client.persistent && !client.details.technology ? ref + 1 : 0,
      max = client.persistent && client.details.technology ? ref - 1 : 1023;
    trigger.input.min = number.min = min;
    trigger.input.max = number.max = max;
    edit(client.thresholds[bin]);
    refresh();
  };
  const refresh = () => {
    updateKeys(view, client, frame, selected, group);
    const value = reading(client, frame.values, selected);
    selection.textContent = `Selected QMK ${selected.replace(":", ", ")} · Group ${group + 1} · Signal ${value ?? "—"} · Trigger ${client.thresholds[group]}`;
    for (let bin = 0; bin < cells.length; bin++) {
      const values = [...frame.values]
        .filter(([id]) => client.bins.get(id) === bin)
        .map(([, v]) => v);
      const items = [
        client.references[bin],
        client.thresholds[bin],
        values.length ? `${Math.min(...values)}–${Math.max(...values)}` : "—",
        client.persistent
          ? `${client.offsets[bin] > 0 ? "+" : ""}${client.offsets[bin]}${client.saved[bin] ? " saved" : " default"}`
          : "RAM only",
      ];
      cells[bin].values.forEach((cell, i) => {
        cell.textContent = items[i];
      });
      cells[bin].row.classList.toggle("selected", bin === group);
    }
  };
  const explanation = client.details.technology
    ? "Beamspring: a higher trigger is more sensitive."
    : "Model F: a lower trigger is more sensitive.";
  const controls = section(
    "Calibration group",
    `${explanation} This is an electrical DAC threshold, not travel distance. Click a key or group to select it.`,
    note("Editing does not change the keyboard until you click Apply."),
    trigger.node,
    number,
    el("div", { class: "leyden-actions" }, apply, defaults, pause),
  );
  if (!client.persistent)
    controls.append(
      note(
        "Legacy firmware: trigger changes are temporary until restart. Persistent controls require the firmware extension.",
      ),
    );
  const table = el(
    "table",
    {},
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        ...["Group", "Rest", "Trigger", "Live min–max", "Offset"].map((t) =>
          el("th", {}, t),
        ),
      ),
    ),
    tbody,
  );
  container.append(
    note(
      "Live sweeps temporarily use the controller's DAC and can delay keyboard scans. Pause live readings or leave this page for ordinary typing.",
    ),
    el(
      "div",
      { class: "columns calibration leyden-calibration" },
      el("div", {}, view, selection, controls),
      section(
        "Calibration groups",
        "Rest is the fixed startup reference. Live values update while measurements run.",
        table,
      ),
    ),
  );
  choose(group);
  sampling(
    ctx,
    client,
    () => live,
    (next) => {
      frame = next;
      refresh();
    },
  );
}
async function sensorsPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  let selected = initialKey(client),
    mode = "Keyboard",
    frame = emptyFrame(),
    previous = null,
    live = true,
    lastSample = null;
  const samples = [],
    view = el("div", { class: "leyden-keyboard" }),
    label = el("p", { class: "leyden-reading" }),
    canvas = el("canvas", {
      width: 1000,
      height: 300,
      class: "sensor-chart",
      "aria-label": "Live capacitive signal chart",
    });
  const select = (id) => {
    selected = id;
    refresh();
  };
  const render = () => {
    view.replaceChildren(keyView(client, { mode, selected, onSelect: select }));
  };
  const refresh = () => {
    if (selected !== previous) {
      samples.length = 0;
      previous = selected;
    }
    updateKeys(view, client, frame, selected, null, true);
    const bin = groupFor(client, selected),
      value = reading(client, frame.values, selected),
      p = client.physicalPosition(selected);
    const digital =
      client.details.directKey &&
      selected === position(...client.details.directKey.slice(0, 2));
    label.textContent = digital
      ? `QMK ${selected.replace(":", ", ")} · Digital switch · ${frame.logical.has(selected) ? "Held" : "Released"} · No DAC signal`
      : `QMK ${selected.replace(":", ", ")} · Signal ${value ?? "—"} · Trigger ${bin === null ? "—" : client.thresholds[bin]} · Min ${client.minimum.get(p) ?? "—"} / Max ${client.maximum.get(p) ?? "—"} · ${frame.logical.has(selected) ? "Held" : "Released"}`;
    chart(
      canvas,
      samples,
      bin === null ? null : client.thresholds[bin],
      bin === null ? null : client.references[bin],
    );
  };
  const buttons = ["Keyboard", "QMK matrix", "Controller matrix"].map((name) =>
    button(name, () => {
      mode = name;
      buttons.forEach((b, i) =>
        b.setAttribute(
          "aria-pressed",
          String(["Keyboard", "QMK matrix", "Controller matrix"][i] === mode),
        ),
      );
      render();
      refresh();
    }),
  );
  buttons[0].setAttribute("aria-pressed", "true");
  const pause = button("Pause live readings", () => {
    live = !live;
    pause.textContent = live ? "Pause live readings" : "Resume live readings";
  });
  container.append(
    section(
      "Live signal",
      "Press a key to follow it automatically. Graph history stays in RAM only.",
      label,
      canvas,
      el("div", { class: "leyden-actions" }, ...buttons, pause),
      view,
    ),
    note(
      "A full native level sweep temporarily blocks keyboard scanning. Pause measurements or leave Live sensors for normal typing.",
    ),
  );
  render();
  refresh();
  sampling(
    ctx,
    client,
    () => live,
    (next) => {
      frame = next;
      const held =
        [...frame.logical].find((id) => groupFor(client, id) !== null) ??
        [...frame.logical][0];
      if (held) selected = held;
      if (selected !== previous) {
        samples.length = 0;
        previous = selected;
      }
      const value = reading(client, frame.values, selected);
      if (live && Number.isFinite(value) && frame.sampleNumber !== lastSample) {
        samples.push(value);
        if (samples.length > 160) samples.shift();
        lastSample = frame.sampleNumber;
      }
      refresh();
    },
  );
}
export default {
  id: "leyden_jar",
  name: "Leyden Jar",
  supports: supported,
  pages: [
    { id: "leyden-general", title: "Controller", render: generalPage },
    { id: "leyden-calibration", title: "Calibration", render: calibrationPage },
    { id: "leyden-sensors", title: "Live sensors", render: sensorsPage },
  ],
};
