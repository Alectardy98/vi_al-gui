// SPDX-License-Identifier: GPL-3.0-or-later
import { EC42, decodeRecord, profiles } from "./protocol.js";
import { bytes, u16 } from "../../src/binary.js";
import {
  button,
  download,
  el,
  field,
  note,
  poll,
  range,
  section,
  toggle,
} from "../../src/ui.js";
import { keyboardView } from "../../src/keyboard-view.js";

async function client(ctx) {
  return new EC42(ctx.keyboard).identify();
}
async function actuationPage(container, ctx) {
  const ec = await client(ctx);
  let index = 65535;
  let current = await ec.actuation();
  const keyboard = el("div"),
    selectedLabel = el(
      "p",
      { class: "muted" },
      "Select a key for its independent actuation point.",
    );
  const global = range(
    "Global default",
    Math.round((u16(current, 6) * 100) / 1023),
    1,
    99,
    (value) =>
      ctx.run(async () => {
        current = await ec.setActuation(65535, value);
        global.set(value);
        perKey.set(value);
        if (index !== 65535) await loadKey(index);
      }, "Global actuation saved; all per-key overrides cleared."),
  );
  const perKey = range(
    "Per-key actuation",
    +global.input.value,
    1,
    99,
    (value) =>
      ctx.run(async () => {
        if (index === 65535) throw Error("Select a key first.");
        current = await ec.setActuation(index, value);
        perKey.set(current[13] || Math.round((u16(current, 6) * 100) / 1023));
      }, "Per-key actuation saved and read back."),
  );
  perKey.input.disabled = true;
  const renderKeyboard = () =>
    keyboard.replaceChildren(
      keyboardView(ctx.keyboard, {
        selected:
          index === 65535
            ? null
            : `${Math.floor(index / ec.profile.cols)}:${index % ec.profile.cols}`,
        onSelect: (key) => {
          if (key.row !== null)
            ctx.run(
              () => loadKey(key.row * ec.profile.cols + key.col),
              "Selected key settings loaded.",
            );
        },
      }),
    );
  async function loadKey(next) {
    index = next;
    current = await ec.actuation(index);
    perKey.input.disabled = false;
    perKey.set(current[13] || Math.round((u16(current, 6) * 100) / 1023));
    selectedLabel.textContent = `Row ${Math.floor(index / ec.profile.cols)}, column ${index % ec.profile.cols}${current[13] ? " · Per-key override" : " · Using global default"}`;
    renderKeyboard();
  }
  const rt = toggle("Dynamic Rapid Trigger", !!current[10]);
  const press = range("Press movement", current[11], 1, 255),
    release = range("Release movement", current[12], 1, 255);
  container.append(
    keyboard,
    section(
      "Actuation",
      "Moving Global default resets every key to the new global point. Moving Per-key changes only the selected key.",
      global.node,
      selectedLabel,
      perKey.node,
      button("Use global for selected key", () =>
        ctx.run(async () => {
          if (index === 65535) throw Error("Select a key first.");
          await ec.setActuation(index, 0);
          await loadKey(index);
        }, "Per-key override cleared."),
      ),
    ),
    section(
      "Dynamic Rapid Trigger",
      "A key releases when you move up, then triggers again when you move down. Smaller movement values are more sensitive.",
      rt.node,
      press.node,
      release.node,
      button(
        "Apply Rapid Trigger",
        () =>
          ctx.run(async () => {
            current = await ec.setRt(
              rt.input.checked,
              +press.input.value,
              +release.input.value,
            );
          }, "Rapid Trigger saved and verified."),
        true,
      ),
    ),
  );
  renderKeyboard();
}
async function sensorsPage(container, ctx) {
  const ec = await client(ctx),
    samples = [];
  const canvas = el("canvas", {
      width: 680,
      height: 300,
      class: "sensor-chart",
    }),
    graph = canvas.getContext("2d");
  const label = el(
    "p",
    { class: "muted" },
    "Press any key; the graph follows the active sensor automatically.",
  );
  const cells = Array.from({ length: ec.cells }, (_, i) =>
    el(
      "div",
      { class: "matrix-cell" },
      `${Math.floor(i / ec.profile.cols)},${i % ec.profile.cols}`,
    ),
  );
  const matrix = el(
    "div",
    {
      class: "matrix",
      style: {
        gridTemplateColumns: `repeat(${ec.profile.cols},minmax(20px,1fr))`,
      },
    },
    cells,
  );
  container.append(
    section(
      "Live sensors",
      "Live readings stay in memory only. No sensor history is saved or uploaded.",
      label,
      el("div", { class: "columns" }, canvas, matrix),
    ),
  );
  let lastIndex = null;
  poll(
    ctx.signal,
    async () => {
      try {
        const values = await ctx.read(() => ec.snapshot());
        if (ctx.signal.aborted || !values) return;
        const selected = ec.selected,
          sample = values[selected];
        if (selected !== lastIndex) {
          samples.length = 0;
          lastIndex = selected;
        }
        samples.push(sample.raw);
        if (samples.length > 180) samples.shift();
        cells.forEach((cell, i) => {
          cell.textContent = values[i].sampled ? values[i].raw : "—";
          cell.classList.toggle(
            "pressed",
            values[i].active || values[i].debounced,
          );
        });
        label.textContent = `Row ${Math.floor(selected / ec.profile.cols)}, column ${selected % ec.profile.cols} · Sensor ${sample.raw} · Press ${sample.press} · Release ${sample.release}`;
        graph.fillStyle = "#141019";
        graph.fillRect(0, 0, 680, 300);
        for (const [value, color, name] of [
          [sample.press, "#b58aff", "Press"],
          [sample.release, "#f1b36e", "Release"],
        ]) {
          const y = 285 - (value * 270) / 1023;
          graph.strokeStyle = color;
          graph.lineWidth = 2;
          graph.beginPath();
          graph.moveTo(0, y);
          graph.lineTo(680, y);
          graph.stroke();
          graph.fillStyle = color;
          graph.font = "13px sans-serif";
          graph.fillText(`${name} ${value}`, 8, Math.max(15, y - 6));
        }
        graph.strokeStyle = "#86dfb3";
        graph.lineWidth = 3;
        graph.beginPath();
        samples.forEach((v, i) => {
          const x = (i * 680) / 179,
            y = 285 - (v * 270) / 1023;
          i ? graph.lineTo(x, y) : graph.moveTo(x, y);
        });
        graph.stroke();
      } catch (e) {
        if (!ctx.signal.aborted) {
          label.textContent = e.message;
          ctx.notify(e.message, true);
        }
        throw e;
      }
    },
    60,
  );
}
async function calibrationPage(container, ctx) {
  const ec = await client(ctx);
  let record = await ec.record(),
    review = null,
    running = false,
    timer;
  const keyboard = el("div"),
    status = note(`EC42 ${ec.firmware} · Current stored calibration loaded.`);
  const rows = [];
  const table = el(
    "table",
    {},
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        ...["Position", "Stored EC", "Capture"].map((x) => el("th", {}, x)),
      ),
    ),
    el(
      "tbody",
      {},
      Array.from({ length: ec.cells }, (_, i) => {
        const stored = u16(record, 9 + 2 * i);
        const capture = el("td", {}, "—");
        rows.push(capture);
        return el(
          "tr",
          {},
          el(
            "td",
            {},
            `${Math.floor(i / ec.profile.cols)},${i % ec.profile.cols}`,
          ),
          el("td", {}, stored & 1023),
          capture,
        );
      }),
    ),
  );
  keyboard.append(keyboardView(ctx.keyboard));
  const save = button(
    "Save and apply",
    () =>
      ctx.run(async () => {
        if (!review) throw Error("Finish and review calibration first.");
        await ec.apply(review);
        review = null;
        save.disabled = true;
        status.textContent = "Calibration saved and verified.";
      }),
    true,
  );
  save.disabled = true;
  const tick = async () => {
    if (!running || ctx.signal.aborted) return;
    try {
      const values = await ctx.read(() => ec.snapshot(null, false));
      if (ctx.signal.aborted || !values) return;
      const caps = keyboard.querySelectorAll("[data-key]");
      values.forEach((s, i) => {
        rows[i].textContent = !s.sampled
          ? "Not fitted"
          : s.capture === 1
            ? "Captured"
            : s.capture > 1
              ? "Retry"
              : s.active
                ? "Held"
                : "Ready";
      });
      caps.forEach((cap) => {
        const [r, c] = cap.dataset.key.split(":").map(Number),
          s = values[r * ec.profile.cols + c];
        cap.classList.toggle("captured", s?.capture === 1);
        cap.classList.toggle("failed", s?.capture > 1);
        cap.classList.toggle("pressed", s?.active || s?.debounced);
      });
      if (running) timer = setTimeout(tick, 100);
    } catch (e) {
      running = false;
      status.textContent = e.message;
      ctx.notify(e.message, true);
    }
  };
  ctx.signal.addEventListener("abort", () => {
    running = false;
    clearTimeout(timer);
  });
  const start = button(
    "Start manual calibration",
    async () => {
      if (!window.showSaveFilePicker) {
        ctx.notify(
          "Manual calibration requires a browser with the Save File Picker API so the recovery backup can be confirmed before capture starts.",
          true,
        );
        return;
      }
      let file;
      try {
        file = await window.showSaveFilePicker({
          suggestedName: `EC42-${ec.profile.uid}-backup.json`,
          types: [
            {
              description: "EC42 recovery backup",
              accept: { "application/json": [".json"] },
            },
          ],
        });
      } catch (e) {
        if (e.name !== "AbortError") ctx.notify(e.message, true);
        return;
      }
      ctx.run(async () => {
        running = false;
        clearTimeout(timer);
        await ec.start(async (backup) => {
          const data = JSON.stringify(backup, null, 2),
            writer = await file.createWritable();
          try {
            await writer.write(data);
          } finally {
            await writer.close();
          }
          if ((await (await file.getFile()).text()) !== data)
            throw Error(
              "Recovery backup readback did not match. Calibration was not started.",
            );
        });
        review = null;
        save.disabled = true;
        running = true;
        status.textContent =
          "Capture active: press and hold each key fully, then release. Green = held, blue = captured, red = retry.";
        tick();
      }, "Manual calibration started; recovery backup saved.");
    },
    true,
  );
  const controls = section(
    "Manual calibration",
    "Release all keys before starting. A recovery backup is saved before capture begins.",
    status,
    el(
      "div",
      { class: "toolbar" },
      start,
      button("Finish and review", () =>
        ctx.run(async () => {
          running = false;
          clearTimeout(timer);
          review = await ec.review();
          review.samples.forEach((s, i) => {
            rows[i].textContent = !s.sampled
              ? "Not fitted"
              : (["Retained", "Captured", "Retry", "Invalid"][s.capture] ??
                "Unknown");
          });
          save.disabled = !review.canApply;
          status.textContent = review.canApply
            ? "Review ready. Save and apply commits the verified captures."
            : "No valid new captures. Cancel or restart calibration.";
        }, "Calibration review loaded."),
      ),
      button("Cancel calibration", () =>
        ctx.run(async () => {
          running = false;
          clearTimeout(timer);
          await ec.cancel();
          review = null;
          save.disabled = true;
          status.textContent = "Calibration cancelled.";
        }, "Calibration cancelled."),
      ),
      save,
    ),
    button("Export saved calibration", () =>
      ctx.run(
        async () =>
          download(
            "EC42-backup.json",
            JSON.stringify(ec.backup(await ec.record(0x16)), null, 2),
          ),
        "Recovery backup downloaded.",
      ),
    ),
  );
  container.append(
    el(
      "div",
      { class: "columns calibration" },
      el("div", {}, keyboard, controls),
      section(
        "Calibration positions",
        "Stored values and live capture results.",
        el("div", { class: "scroll-table" }, table),
      ),
    ),
  );
}
export default {
  id: "ec_42",
  name: "EC42",
  supports: (keyboard) =>
    profiles.some((profile) => profile.uid === keyboard.uid),
  pages: [
    { id: "ec-calibration", title: "Calibration", render: calibrationPage },
    { id: "ec-actuation", title: "Actuation", render: actuationPage },
    { id: "ec-sensors", title: "Live sensors", render: sensorsPage },
  ],
};
