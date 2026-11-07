// SPDX-License-Identifier: GPL-2.0-or-later
import { button, el, field, note } from "./ui.js";
import { composeKeycode, keycodeCategories, parseKeycode } from "./keycodes.js";

export function keycodePicker(keyboard, { onChoose, hasSelection, notify }) {
  let active = "Basic",
    wrapper = null;
  const root = el("div", { class: "keycode-browser" });
  const tabs = el("div", {
    class: "keycode-tabs",
    role: "tablist",
    "aria-label": "Keycode categories",
  });
  const search = el("input", {
    type: "search",
    placeholder: "Search all keycodes, names and descriptions…",
    "aria-label": "Search keycodes",
  });
  const details = el(
    "div",
    { class: "keycode-description", "aria-live": "polite" },
    "Browse a category, then choose an action for the selected physical key.",
  );
  const builder = el("div"),
    panel = el("div", { role: "tabpanel", id: "keycode-panel", tabIndex: -1 });
  const choices = ["All", ...keycodeCategories, "Any"];
  const tabButtons = choices.map((name) => {
    const node = button(name, () => switchTab(name));
    node.setAttribute("role", "tab");
    node.id = `keycode-tab-${choices.indexOf(name)}`;
    node.setAttribute("aria-controls", "keycode-panel");
    node.addEventListener("keydown", (event) => {
      const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const index = choices.indexOf(active);
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? choices.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + choices.length) %
              choices.length;
      switchTab(choices[next]);
      tabButtons[next].focus();
    });
    return node;
  });
  tabs.append(...tabButtons);
  function switchTab(name) {
    active = name;
    wrapper = null;
    search.value = "";
    render();
  }
  function choose(row) {
    if (row.masked) {
      wrapper = row;
      active = "Basic";
      search.value = "";
      render();
    } else {
      const code = wrapper ? composeKeycode(wrapper, row.code) : row.code;
      wrapper = null;
      render();
      onChoose(code);
    }
  }
  function render() {
    tabButtons.forEach((node, i) => {
      const selected = choices[i] === active;
      node.classList.toggle("active", selected);
      node.setAttribute("aria-selected", String(selected));
      node.tabIndex = selected ? 0 : -1;
    });
    panel.setAttribute(
      "aria-labelledby",
      tabButtons[choices.indexOf(active)].id,
    );
    builder.replaceChildren();
    if (wrapper)
      builder.append(
        note(
          `${wrapper.id}: ${wrapper.title}. Choose its basic key below; nothing is saved until that key is chosen.`,
        ),
        button("Cancel combination", () => {
          wrapper = null;
          render();
        }),
      );
    if (active === "Any") {
      const input = el("input", {
        placeholder: "KC_A, LCTL(KC_A), LT(1,KC_SPC), USER00 or 0x0004",
        "aria-label": "Any keycode",
      });
      const assign = button(
        "Assign keycode",
        () => {
          try {
            onChoose(parseKeycode(keyboard, input.value));
          } catch (error) {
            notify(error.message, true);
          }
        },
        true,
      );
      assign.disabled = !hasSelection();
      panel.replaceChildren(
        field(
          "QMK keycode or 16-bit value",
          input,
          "Use a supported QMK name, custom name, modifier or layer-tap expression, decimal value or hexadecimal value.",
        ),
        assign,
      );
      return;
    }
    const query = search.value.trim().toLowerCase();
    const rows = keyboard.catalogue.filter(
      (row) =>
        (!wrapper || (!row.masked && row.code <= 255)) &&
        (query || active === "All" || row.categories?.includes(active)) &&
        (!query ||
          `${row.id} ${row.label} ${row.title} ${(row.aliases ?? []).join(" ")}`
            .toLowerCase()
            .includes(query)),
    );
    const grid = el("div", { class: "keycode-picker" });
    grid.append(
      ...rows.map((row) => {
        const text = row.label || (row.code === 0 ? "No action" : row.id);
        const description = `${row.id} · ${row.title || text}${row.masked ? " · Choose an inner key" : ""}`;
        const node = button(text, () => choose(row));
        node.title = description;
        node.dataset.keycode = row.id;
        node.disabled = !hasSelection();
        node.addEventListener("mouseenter", () => {
          details.textContent = description;
        });
        node.addEventListener("focus", () => {
          details.textContent = description;
        });
        return node;
      }),
    );
    const count = el(
      "p",
      { class: "muted keycode-count" },
      `${rows.length} ${query ? "matching " : ""}keycodes${wrapper ? " · choose the inner key" : ""}`,
    );
    panel.replaceChildren(
      count,
      rows.length
        ? grid
        : note(
            active === "User"
              ? "No custom keycodes were advertised by this keyboard."
              : active === "MIDI"
                ? "This keyboard does not advertise MIDI support."
                : query
                  ? "No matching keycodes."
                  : `This firmware does not advertise ${active} entries.`,
          ),
    );
  }
  search.addEventListener("input", () => {
    if (active === "Any") active = "All";
    render();
  });
  root.append(tabs, search, builder, panel, details);
  render();
  return { node: root, refresh: render };
}
