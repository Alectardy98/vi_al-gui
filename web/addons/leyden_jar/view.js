// SPDX-License-Identifier: GPL-3.0-or-later
import { el } from "../../src/ui.js";
import { keyboardView } from "../../src/keyboard-view.js";
import { position } from "./protocol.js";
export const physical = (client, id) => client.physicalPosition(id);
export function groupFor(client, id) {
  const p = physical(client, id),
    bin = p === null ? 255 : client.bins.get(p);
  return bin === 255 || bin === undefined ? null : bin;
}
export function reading(client, values, id) {
  const p = physical(client, id);
  return p === null ? null : (values.get(p) ?? null);
}
export function keyView(
  client,
  { mode = "Keyboard", selected, onSelect } = {},
) {
  const d = client.details;
  if (mode === "Keyboard")
    return keyboardView(client.keyboard, {
      selected,
      onSelect: (key) => onSelect(position(key.row, key.col)),
      values: (key) => `${key.row},${key.col}\n—`,
    });
  const controller = mode === "Controller matrix",
    rows = controller ? d.physicalRows : d.rows,
    cols = controller ? d.physicalCols : d.cols;
  const matrix = el("div", {
    class: "matrix leyden-matrix",
    style: { gridTemplateColumns: `repeat(${cols},minmax(30px,1fr))` },
  });
  for (let row = 0; row < rows; row++)
    for (let col = 0; col < cols; col++) {
      const p = position(row, col),
        id = controller ? client.logicalPosition(p) : p;
      const active =
        id !== null &&
        (groupFor(client, id) !== null ||
          (d.directKey && id === position(...d.directKey.slice(0, 2))));
      matrix.append(
        el(
          "button",
          {
            type: "button",
            class: "matrix-cell",
            disabled: !active,
            "data-key": id ?? "",
            "data-coordinate": p,
            onClick: () => onSelect(id),
          },
          `${row},${col}\n—`,
        ),
      );
    }
  return el("div", { class: "keyboard-scroll" }, matrix);
}
export function updateKeys(
  view,
  client,
  frame,
  selected,
  group = null,
  coordinates = false,
) {
  for (const key of view.querySelectorAll("[data-key]")) {
    const id = key.dataset.key,
      bin = groupFor(client, id),
      value = reading(client, frame.values, id);
    const digital =
      client.details.directKey &&
      id === position(...client.details.directKey.slice(0, 2));
    const label = key.querySelector(".keycap-label") ?? key;
    const coordinate = key.dataset.coordinate ?? id;
    label.textContent =
      (coordinates || key.dataset.coordinate
        ? coordinate.replace(":", ",") + "\n"
        : "") + (digital ? "Digital" : (value ?? "—"));
    key.classList.toggle("selected", id === selected);
    key.classList.toggle("pressed", frame.logical.has(id));
    key.classList.toggle("leyden-group", group !== null && bin === group);
    key.classList.toggle(
      "leyden-near",
      bin !== null &&
        value !== null &&
        Math.abs(value - client.thresholds[bin]) <= 3,
    );
    key.title = `QMK ${id.replace(":", ", ")} · ${digital ? "digital switch" : bin === null ? "unpopulated pad" : `controller ${physical(client, id)} · group ${bin + 1} · trigger ${client.thresholds[bin]}`}`;
  }
}
export function chart(canvas, samples, threshold, reference) {
  const g = canvas.getContext("2d"),
    w = canvas.width,
    h = canvas.height;
  g.fillStyle = "#18131f";
  g.fillRect(0, 0, w, h);
  const vals = [...samples, threshold, reference].filter(Number.isFinite);
  if (!vals.length) return;
  const low = Math.max(0, Math.min(...vals) - 12),
    high = Math.min(1023, Math.max(...vals) + 12),
    y = (v) => h - 26 - ((v - low) / Math.max(1, high - low)) * (h - 52);
  const line = (value, color, label) => {
    if (!Number.isFinite(value)) return;
    g.strokeStyle = color;
    g.lineWidth = 3;
    g.beginPath();
    g.moveTo(0, y(value));
    g.lineTo(w, y(value));
    g.stroke();
    g.fillStyle = color;
    g.font = "16px sans-serif";
    g.fillText(`${label} ${value}`, 12, Math.max(18, y(value) - 6));
  };
  line(reference, "#9d91ad", "Rest");
  line(threshold, "#ffcb70", "Trigger");
  g.strokeStyle = "#c7a1ff";
  g.lineWidth = 3;
  g.beginPath();
  samples.forEach((v, i) =>
    i ? g.lineTo((i * w) / 159, y(v)) : g.moveTo(0, y(v)),
  );
  g.stroke();
}
