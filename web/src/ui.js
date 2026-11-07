// SPDX-License-Identifier: GPL-2.0-or-later
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (key.startsWith("on"))
      node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "class") node.className = value;
    else if (key === "style") Object.assign(node.style, value);
    else if (key in node && !key.startsWith("aria") && key !== "list")
      node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined)
      node.append(
        child instanceof Node ? child : document.createTextNode(String(child)),
      );
  }
  return node;
}
export const button = (label, action, primary = false) =>
  el(
    "button",
    { type: "button", class: primary ? "primary" : "", onClick: action },
    label,
  );
export const note = (text, type = "") =>
  el("p", { class: `notice ${type}` }, text);
export const section = (title, description, ...children) =>
  el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "section-heading" },
      el("h2", {}, title),
      description ? el("p", {}, description) : null,
    ),
    ...children,
  );
export const field = (label, input, description) => {
  if (
    ["INPUT", "SELECT", "TEXTAREA"].includes(input.tagName) &&
    !input.hasAttribute("aria-label")
  )
    input.setAttribute("aria-label", label);
  return el(
    "label",
    { class: "field" },
    el("span", {}, label),
    input,
    description ? el("small", {}, description) : null,
  );
};
export function select(values, value, action) {
  return el(
    "select",
    { value, onChange: action },
    values.map(([id, label]) =>
      el(
        "option",
        { value: id, selected: String(id) === String(value) },
        label,
      ),
    ),
  );
}
export function range(label, value, min, max, action) {
  const output = el("output", {}, value);
  const input = el("input", {
    type: "range",
    min,
    max,
    value,
    "aria-label": label,
    onInput: () => {
      output.value = input.value;
    },
    onChange: () => action?.(+input.value),
  });
  return {
    node: field(label, el("div", { class: "slider-row" }, input, output)),
    input,
    output,
    set: (value) => {
      input.value = value;
      output.value = value;
    },
  };
}
export function toggle(label, checked, action) {
  const input = el("input", {
    type: "checkbox",
    checked,
    onChange: () => action?.(input.checked),
  });
  return {
    node: el("label", { class: "toggle" }, input, el("span", {}, label)),
    input,
  };
}
export function download(name, data, type = "application/json") {
  const link = el("a", {
    href: URL.createObjectURL(new Blob([data], { type })),
    download: name,
  });
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
export function poll(signal, action, interval = 100) {
  let timer;
  const tick = async () => {
    try {
      if (!signal.aborted) await action();
    } catch (error) {
      if (!signal.aborted) console.error(error);
      return;
    }
    if (!signal.aborted) timer = setTimeout(tick, interval);
  };
  signal.addEventListener("abort", () => clearTimeout(timer), { once: true });
  tick();
}
