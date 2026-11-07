import "./style.css";
import "./components.css";
import logo from "../assets/icons/256.png";
import { el, button, note, section } from "./ui.js";
import { rawInterface, RawHidTransport } from "./transport.js";
import { VialKeyboard } from "./keyboard.js";
import { catalogue } from "./keycodes.js";
import { demoKeyboard } from "./demo.js";
import {
  keymapPage,
  layoutPage,
  lightingPage,
  matrixPage,
  securityPage,
} from "./pages.js";
import { macroPage, dynamicPage, settingsPage } from "./advanced.js";

const addonModules = import.meta.glob("../addons/*/provider.js", {
  eager: true,
});
const addons = Object.values(addonModules).map((module) => module.default);
const state = {
  keyboard: null,
  pages: [],
  controller: null,
  operation: false,
  busy: false,
  devices: [],
};
const app = document.querySelector("#app");
const status = el("div", {
  class: "status",
  role: "status",
  "aria-label": "Keyboard status",
  "aria-live": "polite",
});
const content = el("main", { id: "content", tabIndex: -1 });
const nav = el("nav", { "aria-label": "Keyboard settings" });
const deviceSelect = el("select", {
  "aria-label": "Connected keyboard",
  onChange: async () => {
    const device = state.devices[+deviceSelect.value];
    if (device) await connect(device);
  },
});
deviceSelect.hidden = true;
const connectButton = button("Connect keyboard", chooseDevice, true);
const disconnectButton = button("Disconnect", () => disconnect());
disconnectButton.hidden = true;
const deviceName = el("strong", {}, "No keyboard connected");
const connection = el("span", { class: "connection-dot" });
app.append(
  el(
    "header",
    {},
    el(
      "a",
      { class: "brand", href: "./", "aria-label": "Vi_al home" },
      el("img", { src: logo, alt: "" }),
      el("span", {}, "Vi_al", el("small", {}, "1.0 · WEB")),
    ),
    el(
      "div",
      { class: "header-actions" },
      deviceSelect,
      connectButton,
      disconnectButton,
    ),
  ),
  el(
    "div",
    { class: "workspace" },
    el(
      "aside",
      {},
      el("div", { class: "device-info" }, connection, deviceName),
      nav,
      el(
        "div",
        { class: "sidebar-footer" },
        "YOUR KEYBOARD. YOUR WAY.",
        el(
          "a",
          {
            href: "https://github.com/Alectardy98/vi_al-gui",
            target: "_blank",
            rel: "noopener noreferrer",
          },
          "Source & desktop app ↗",
        ),
      ),
    ),
    el("div", { class: "page" }, status, content),
  ),
  el(
    "footer",
    {},
    "Runs locally in your browser · No account or server uploads",
    el("span", {}, "Vi_al / Vial · Open source"),
  ),
);

function notify(message, error = false) {
  status.textContent = message;
  status.classList.toggle("error", error);
}
function setBusy(busy) {
  state.busy = busy;
  connectButton.disabled = busy;
  deviceSelect.disabled = busy;
  nav.classList.toggle("busy", busy);
}
async function disconnect() {
  state.controller?.abort();
  state.controller = null;
  const old = state.keyboard;
  state.keyboard = null;
  state.operation = false;
  content.classList.remove("working");
  if (old) {
    try {
      if (old.files) await old.files.close();
      await old.transport.close();
    } catch (e) {
      console.warn(e);
    }
  }
  disconnectButton.hidden = true;
  connectButton.hidden = false;
  connection.className = "connection-dot";
  deviceName.textContent = "No keyboard connected";
  nav.replaceChildren();
  state.pages = [];
  welcome();
}
function welcome() {
  content.replaceChildren(
    el(
      "section",
      { class: "welcome" },
      el(
        "div",
        { class: "hero-mark" },
        el("img", { src: logo, alt: "Vi_al purple logo" }),
      ),
      el(
        "span",
        { class: "eyebrow" },
        "THE KEYBOARD CONFIGURATOR, IN YOUR BROWSER",
      ),
      el("h1", {}, "Make every key", el("br"), el("em", {}, "your own.")),
      el(
        "p",
        { class: "lead" },
        "Your layout, lighting and keyboard controls. Connect a Vial keyboard and configure it directly—no installation needed.",
      ),
      el(
        "div",
        { class: "hero-actions" },
        button("Connect your keyboard", chooseDevice, true),
        button("Explore demo", () => activate(demoKeyboard())),
      ),
      el(
        "p",
        { class: "muted browser-support" },
        globalThis.isSecureContext && navigator.hid
          ? "Use Chrome or Edge on desktop. Close other keyboard configurators before connecting."
          : "WebHID requires a compatible desktop browser and HTTPS (or localhost). Demo mode remains available.",
      ),
      el(
        "div",
        { class: "feature-grid" },
        section(
          "01 / BASED ON VIAL WEB",
          "Every key. Every layer.",
          el(
            "p",
            {},
            "Read your keyboard’s actual layout and save verified key assignments.",
          ),
        ),
        section(
          "02 / CUSTOM ADD-ON SUPPORT",
          "Built for your board.",
          el(
            "p",
            {},
            "Add a browser add-on in web/addons/<id>/, then rebuild and publish the site. Its controls appear automatically for matching keyboards. EC42, MY-2K and Alienware are already included.",
          ),
        ),
        section(
          "03 / LOCAL",
          "Your settings stay yours.",
          el(
            "p",
            {},
            "Communication goes directly from this browser to your USB device.",
          ),
        ),
      ),
    ),
  );
}
async function refreshDevices() {
  state.devices = navigator.hid
    ? (await navigator.hid.getDevices()).filter(rawInterface)
    : [];
  deviceSelect.replaceChildren(
    el("option", { value: "" }, "Previously approved keyboards"),
    ...state.devices.map((device, i) =>
      el(
        "option",
        { value: i },
        device.productName ||
          `USB ${device.vendorId.toString(16)}:${device.productId.toString(16)}`,
      ),
    ),
  );
  deviceSelect.hidden = !state.devices.length;
  const selected = state.devices.indexOf(state.keyboard?.transport.device);
  deviceSelect.value = selected >= 0 ? String(selected) : "";
}
async function chooseDevice() {
  if (state.busy) return;
  if (!globalThis.isSecureContext || !navigator.hid) {
    notify(
      "WebHID is unavailable. Open this page over HTTPS in desktop Chrome or Edge.",
      true,
    );
    return;
  }
  try {
    const devices = await navigator.hid.requestDevice({
      filters: [{ usagePage: 0xff60, usage: 0x61 }],
    });
    if (devices[0]) await connect(devices[0]);
    await refreshDevices();
  } catch (e) {
    notify(e.message, true);
  }
}
async function connect(device) {
  if (state.busy) return;
  await disconnect();
  setBusy(true);
  notify("Opening keyboard…");
  let transport;
  try {
    transport = await new RawHidTransport(device).open();
    const keyboard = await new VialKeyboard(transport).load(notify);
    await activate(keyboard);
  } catch (e) {
    if (transport) await transport.close().catch(() => {});
    notify(e.message, true);
  } finally {
    setBusy(false);
  }
}
async function activate(keyboard) {
  if (state.keyboard && state.keyboard !== keyboard) await disconnect();
  state.keyboard = keyboard;
  keyboard.catalogue = catalogue(keyboard);
  deviceName.textContent =
    keyboard.definition.name ??
    keyboard.transport.device?.productName ??
    "Vial keyboard";
  connection.className = `connection-dot ${keyboard.demo ? "demo" : "connected"}`;
  disconnectButton.hidden = false;
  connectButton.hidden = true;
  state.pages = [
    { id: "keymap", title: "Keymap", render: keymapPage },
    { id: "layout", title: "Layout", render: layoutPage },
    { id: "lighting", title: "Lighting", render: lightingPage },
  ];
  if (keyboard.macroCount)
    state.pages.push({ id: "macros", title: "Macros", render: macroPage });
  if (Object.values(keyboard.dynamic ?? {}).some(Boolean))
    state.pages.push({
      id: "dynamic",
      title: "Tap Dance & more",
      render: dynamicPage,
    });
  if (!keyboard.demo && keyboard.version >= 4)
    state.pages.push({
      id: "settings",
      title: "QMK settings",
      render: settingsPage,
    });
  for (const addon of addons)
    if (addon.supports(keyboard)) {
      for (const page of addon.pages)
        state.pages.push({ ...page, addon: addon.name });
    }
  state.pages.push(
    { id: "security", title: "Security", render: securityPage },
    { id: "matrix", title: "Matrix tester", render: matrixPage },
  );
  let clockStatus = "";
  for (const addon of addons)
    if (addon.supports(keyboard) && addon.onConnect) {
      try {
        await addon.onConnect(keyboard);
      } catch (e) {
        clockStatus = ` · Clock sync failed: ${e.message}`;
      }
    }
  notify(
    keyboard.demo
      ? "DEMO MODE · No keyboard is connected. Changes affect this page only."
      : `Connected · Vial ${keyboard.version} · ${keyboard.layers} layers · UID ${keyboard.uid}${clockStatus}`,
    !!clockStatus,
  );
  openPage("keymap");
}
async function openPage(id) {
  if (state.operation) {
    notify("Wait for the current keyboard operation to finish.");
    return;
  }
  const page = state.pages.find((p) => p.id === id);
  if (!page || !state.keyboard) return;
  state.controller?.abort();
  state.controller = new AbortController();
  const keyboard = state.keyboard;
  const serialize = (task) => {
    const next = (keyboard.operationQueue ?? Promise.resolve()).then(task);
    keyboard.operationQueue = next.catch(() => {});
    return next;
  };
  const ctx = {
    keyboard,
    signal: state.controller.signal,
    notify,
    openPage: (id) => {
      if (state.operation) ctx.nextPage = id;
      else openPage(id);
    },
    read: (task) =>
      serialize(() => {
        if (!ctx.signal.aborted) return task();
      }),
    isBusy: () => state.operation,
    run: async (task, message = "Saved and verified on keyboard.") => {
      if (state.operation || ctx.signal.aborted) return;
      state.operation = true;
      notify("Working…");
      content.classList.add("working");
      try {
        await serialize(() => {
          if (!ctx.signal.aborted) return task();
        });
        if (!ctx.signal.aborted) notify(message);
      } catch (e) {
        if (!ctx.signal.aborted) notify(e.message, true);
      } finally {
        if (state.keyboard === keyboard) {
          state.operation = false;
          content.classList.remove("working");
          if (ctx.nextPage) openPage(ctx.nextPage);
        }
      }
    },
  };
  nav.replaceChildren(
    ...state.pages.map((p) =>
      el(
        "button",
        {
          class: p.id === id ? "active" : "",
          type: "button",
          "aria-label": p.title,
          onClick: () => openPage(p.id),
        },
        el("span", {}, p.title),
        p.addon ? el("small", {}, p.addon) : null,
      ),
    ),
  );
  content.replaceChildren(
    el(
      "div",
      { class: "page-heading" },
      el(
        "div",
        {},
        el("span", { class: "eyebrow" }, page.addon ?? "KEYBOARD"),
        el("h1", {}, page.title),
      ),
      el(
        "span",
        { class: "badge" },
        state.keyboard.demo ? "DEMO" : "CONNECTED",
      ),
    ),
  );
  const body = el("div", { class: "page-body" });
  content.append(body);
  try {
    await serialize(() => {
      if (!ctx.signal.aborted) return page.render(body, ctx);
    });
  } catch (e) {
    if (!ctx.signal.aborted) body.replaceChildren(note(e.message, "error"));
  }
}
navigator.hid?.addEventListener("disconnect", (event) => {
  if (state.keyboard?.transport.device === event.device) {
    disconnect();
    notify("Keyboard disconnected.");
  }
  refreshDevices().catch((e) => console.warn(e));
});
navigator.hid?.addEventListener("connect", () =>
  refreshDevices().catch((e) => console.warn(e)),
);
welcome();
refreshDevices().catch((e) => notify(e.message, true));
