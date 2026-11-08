// SPDX-License-Identifier: GPL-2.0-or-later
import { Xwhatsit, supported } from "./protocol.js";
import { button, el, note, poll, range, section } from "../../src/ui.js";
import { keyboardView } from "../../src/keyboard-view.js";

const fields = [
  [
    "settle",
    "DAC settling time",
    "µs",
    1,
    32,
    "Wait after changing the sensing threshold. More time can stabilize readings but slows each scan.",
  ],
  [
    "sample",
    "Sample timing",
    "steps",
    1,
    32,
    "When to sample each capacitive signal. Changes can shift readings; the keyboard recalibrates when saved. These are sampling steps, not milliseconds.",
  ],
  [
    "initial",
    "Startup averaging",
    "samples",
    0,
    5,
    "Repeated measurements for the starting signal range. More samples reduce noise but make startup calibration longer.",
  ],
  [
    "per_key",
    "Per-key averaging",
    "samples",
    0,
    5,
    "Repeated measurements of each key during automatic calibration. More samples take longer.",
  ],
  [
    "groups",
    "Calibration groups",
    "groups",
    1,
    15,
    "Keys with similar released signals share a threshold. More groups account for key differences with extra scan work.",
  ],
  [
    "margin",
    "Threshold margin",
    "DAC counts",
    0,
    4095,
    "Gap from the released signal to the threshold. Larger values need more signal change and reduce false triggers; too large can miss presses. This is not distance in millimeters.",
  ],
];
const open = async (ctx) => new Xwhatsit(ctx.keyboard).connect();
async function calibrationPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  let selected = client.thresholds.keys().next().value,
    next = 0;
  const readings = new Map(),
    view = el("div"),
    selection = el(
      "p",
      { class: "muted" },
      "Press a key to follow its live signal.",
    );
  const render = () =>
    view.replaceChildren(
      keyboardView(ctx.keyboard, {
        selected,
        onSelect: (key) => {
          const id = `${key.row}:${key.col}`;
          if (client.thresholds.has(id)) {
            selected = id;
            render();
          }
        },
        values: (key) => readings.get(`${key.row}:${key.col}`) ?? "—",
      }),
    );
  render();
  const tbody = el("tbody"),
    table = el(
      "table",
      {},
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          ["Position", "Signal", "Threshold", "Group"].map((t) =>
            el("th", {}, t),
          ),
        ),
      ),
      tbody,
    );
  const refreshTable = () =>
    tbody.replaceChildren(
      ...[...client.thresholds].map(([id, v]) =>
        el(
          "tr",
          {},
          [
            id.replace(":", ", "),
            readings.get(id) ?? "—",
            v.threshold,
            v.group + 1,
          ].map((t) => el("td", {}, t)),
        ),
      ),
    );
  refreshTable();
  const controls = section(
    "Automatic calibration · saved automatically",
    "Release all keys while applying. Startup calibration uses saved tuning. Changes save when a slider is released.",
  );
  const widgets = {};
  const setControls = () => {
    for (const [name, , unit] of fields) {
      const v = client.settings[name];
      widgets[name].set(
        ["initial", "per_key"].includes(name) ? Math.log2(v) : v,
      );
      widgets[name].output.value = `${v} ${unit}`;
    }
  };
  const restore = button("Restore calibration defaults", () =>
    ctx.run(async () => {
      await client.save(client.defaults, true);
      setControls();
      refreshTable();
    }, "Calibration defaults restored; keymaps preserved."),
  );
  restore.disabled = !client.extension;
  controls.append(el("div", { class: "xwhatsit-actions" }, restore));
  for (const [name, label, unit, min, maximum, description] of fields) {
    const average = ["initial", "per_key"].includes(name),
      max =
        name === "groups"
          ? (client.maxGroups ?? maximum)
          : name === "margin"
            ? client.dac
            : maximum;
    const value = client.settings?.[name] ?? min;
    const control = range(
      label,
      average ? Math.log2(value) : value,
      min,
      max,
      (newValue) => {
        const settings = {
          ...client.settings,
          [name]: average ? 2 ** newValue : newValue,
        };
        ctx.run(async () => {
          try {
            await client.save(settings);
            refreshTable();
          } finally {
            setControls();
          }
        }, "Calibration saved and verified by readback.");
      },
    );
    control.input.disabled = !client.extension;
    control.input.addEventListener("input", () => {
      control.output.value = `${average ? 2 ** +control.input.value : control.input.value} ${unit}`;
    });
    controls.append(
      el(
        "div",
        { class: "xwhatsit-setting" },
        control.node,
        el("p", { class: "muted" }, description),
      ),
    );
    widgets[name] = control;
  }
  if (client.extension) setControls();
  else
    controls.append(
      note(
        "Monitoring works with this firmware. Adjustable persistent settings require the optional XCAL firmware extension.",
      ),
    );
  container.append(
    note(
      `Automatic calibration ${client.auto ? "enabled" : "disabled"} · Utility ${client.version.join(".")} · DAC 0–${client.dac}`,
    ),
    el(
      "div",
      { class: "columns calibration" },
      el("div", {}, view, selection, controls),
      section(
        "Position / calibration values",
        "Thresholds are read from the keyboard. Signal values refresh in rotation.",
        el("div", { class: "scroll-table" }, table),
      ),
    ),
  );
  poll(
    ctx.signal,
    async () => {
      if (ctx.isBusy()) return;
      const positions = [...client.thresholds.keys()],
        background = Array.from(
          { length: 3 },
          () => positions[next++ % positions.length],
        );
      const frame = await ctx.read(() => client.frame(selected, background));
      if (!frame || ctx.signal.aborted) return;
      if (frame.selected !== selected) {
        selected = frame.selected;
        render();
      }
      for (const [id, value] of frame.values) readings.set(id, value);
      for (const cap of view.querySelectorAll(".keycap")) {
        cap.classList.toggle("pressed", frame.pressed.has(cap.dataset.key));
        cap.querySelector(".keycap-label").textContent =
          readings.get(cap.dataset.key) ?? "—";
      }
      selection.textContent = `Following ${selected?.replace(":", ", ")} · ${readings.size} / ${client.thresholds.size} calibration positions sampled`;
      refreshTable();
    },
    90,
  );
}
async function sensorsPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  let selected = client.thresholds.keys().next().value,
    previous = null;
  const samples = [],
    label = el(
      "p",
      { class: "muted" },
      "Press a key; the graph follows the active sensor automatically.",
    );
  const canvas = el("canvas", {
      width: 1000,
      height: 330,
      class: "sensor-chart",
      "aria-label": "Live capacitive signal chart",
    }),
    graph = canvas.getContext("2d");
  const cells = new Map(),
    matrix = el("div", {
      class: "matrix",
      style: { gridTemplateColumns: `repeat(${client.cols},minmax(20px,1fr))` },
    });
  for (let r = 0; r < client.rows; r++)
    for (let c = 0; c < client.cols; c++) {
      const id = `${r}:${c}`,
        cell = el("div", { class: "matrix-cell" }, id);
      cells.set(id, cell);
      matrix.append(cell);
    }
  container.append(
    section(
      "Live sensors",
      "Live values only. No sensor log is saved.",
      label,
      canvas,
      matrix,
    ),
  );
  poll(
    ctx.signal,
    async () => {
      if (ctx.isBusy()) return;
      const frame = await ctx.read(() => client.frame(selected));
      if (!frame || ctx.signal.aborted) return;
      selected = frame.selected;
      if (previous !== selected) {
        samples.length = 0;
        previous = selected;
      }
      const value = frame.values.get(selected);
      if (value === undefined) return;
      samples.push(value);
      if (samples.length > 180) samples.shift();
      const threshold = client.thresholds.get(selected)?.threshold;
      label.textContent = `Row / column ${selected.replace(":", ", ")} · Signal ${value} · Threshold ${threshold ?? "—"} · ${frame.pressed.has(selected) ? "Held" : "Released"}`;
      for (const [id, cell] of cells) {
        cell.classList.toggle("pressed", frame.pressed.has(id));
        if (id === selected) cell.textContent = `${id} · ${value}`;
      }
      const low = Math.max(0, Math.min(...samples, threshold ?? value) - 30),
        high = Math.min(
          client.dac,
          Math.max(...samples, threshold ?? value) + 30,
        );
      const y = (v) => 310 - ((v - low) / Math.max(1, high - low)) * 280;
      graph.fillStyle = "#18131f";
      graph.fillRect(0, 0, 1000, 330);
      if (threshold !== undefined) {
        graph.strokeStyle = "#ffcb70";
        graph.lineWidth = 3;
        graph.beginPath();
        graph.moveTo(0, y(threshold));
        graph.lineTo(1000, y(threshold));
        graph.stroke();
      }
      graph.strokeStyle = "#bc91f0";
      graph.lineWidth = 3;
      graph.beginPath();
      samples.forEach((v, i) =>
        i ? graph.lineTo((i * 1000) / 179, y(v)) : graph.moveTo(0, y(v)),
      );
      graph.stroke();
    },
    50,
  );
}
async function generalPage(container, ctx) {
  const client = await open(ctx);
  if (ctx.signal.aborted) return;
  container.append(
    section(
      "Keyboard recovery",
      "These actions affect the selected keyboard only.",
      note(
        "Erase EEPROM clears keymaps, macros and calibration overrides. Reconnect afterward. Restore calibration defaults on the Calibration page preserves keymaps.",
      ),
      button("Erase EEPROM", () => {
        if (
          globalThis.confirm(
            "Erase all EEPROM on this keyboard? Reconnect afterward to initialize defaults.",
          )
        )
          ctx.run(
            () => client.eraseEeprom(),
            "EEPROM cleared. Reconnect the keyboard.",
          );
      }),
      button("Bootloader", () => {
        if (
          globalThis.confirm(
            "Restart this keyboard into its existing bootloader?",
          )
        )
          ctx.run(
            () => client.enterBootloader(),
            "Bootloader command sent. USB disconnect is expected.",
          );
      }),
    ),
  );
}
export default {
  id: "xwhatsit",
  name: "xwhatsit",
  supports: supported,
  pages: [
    {
      id: "xwhatsit-calibration",
      title: "Calibration",
      render: calibrationPage,
    },
    { id: "xwhatsit-sensors", title: "Live sensors", render: sensorsPage },
    { id: "xwhatsit-general", title: "General", render: generalPage },
  ],
};
