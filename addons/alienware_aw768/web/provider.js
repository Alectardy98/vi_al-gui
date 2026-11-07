// SPDX-License-Identifier: GPL-2.0-or-later
import { Alienware, groups, uids } from "./protocol.js";
import {
  button,
  el,
  field,
  note,
  range,
  section,
  select,
} from "../../../web/src/ui.js";
import { keyboardView } from "../../../web/src/keyboard-view.js";

async function render(container, ctx) {
  let client,
    snapshot,
    chosen = new Set([2]);
  const controls = el("div"),
    status = note(
      "Connect the original lighting PCB to load its saved settings.",
    );
  const connect = button(
    "Connect lighting PCB",
    async () => {
      try {
        const devices = await navigator.hid.requestDevice({
          filters: [
            {
              vendorId: 0x04f2,
              productId: 0x1666,
              usagePage: 0xff00,
              usage: 1,
            },
          ],
        });
        if (!devices[0] || ctx.signal.aborted) return;
        await ctx.run(async () => {
          if (client) await client.close();
          client = await new Alienware(devices[0]).open();
          snapshot = await client.load();
          status.textContent = `Native profile ${snapshot.profile} loaded · ${snapshot.legacy ? "Legacy" : "V0039"} controller.`;
          draw();
        }, "Native AW768 lighting settings loaded.");
      } catch (e) {
        ctx.notify(e.message, true);
      }
    },
    true,
  );
  ctx.signal.addEventListener("abort", () =>
    client?.close().catch(console.warn),
  );
  container.append(
    section(
      "AW768 lighting",
      "The original PCB is a separate USB device. Choose that PCB in the browser picker; browsers do not expose the internal hub topology.",
      connect,
      status,
    ),
    keyboardView(ctx.keyboard),
    controls,
  );
  function draw() {
    const first =
      snapshot.records
        .slice(14, 22)
        .find((r) => chosen.has((r[14] << 8) | r[15])) ?? snapshot.records[14];
    const color = el("input", {
      type: "color",
      value:
        "#" +
        [...first.slice(3, 6)]
          .map((x) => x.toString(16).padStart(2, "0"))
          .join(""),
    });
    const effect = select(
      [
        [0, "Color"],
        [1, "Pulse"],
        [2, "Breathing"],
        [3, "Morph"],
        [4, "Spectrum"],
      ],
      first[2],
    );
    const tempo = range(
      "Tempo",
      snapshot.legacy ? 3 - first[9] : first[9],
      0,
      3,
    );
    const brightness = range("Brightness", first[10] || 1, 1, 10);
    const zones = el("div", { class: "zone-grid" });
    for (const [mask, label] of [...groups, [0x10000, "Macro · X / M1–M5"]]) {
      const b = button(label, () => {
        if (chosen.has(mask)) chosen.delete(mask);
        else chosen.add(mask);
        b.classList.toggle("active", chosen.has(mask));
      });
      b.classList.toggle("active", chosen.has(mask));
      zones.append(b);
    }
    const save = button(
      "Save changes to keyboard",
      () =>
        ctx.run(async () => {
          if (!chosen.size) throw Error("Select one or more lighting groups.");
          const rgb = color.value
            .slice(1)
            .match(/../g)
            .map((x) => parseInt(x, 16));
          if (chosen.has(0x10000) && +effect.value !== 0)
            throw Error("The Macro zone supports solid color only.");
          const settings = new Map(
            [...chosen]
              .filter((x) => x !== 0x10000)
              .map((mask) => [
                mask,
                {
                  color: rgb,
                  mode: +effect.value,
                  tempo: +tempo.input.value,
                  brightness: +brightness.input.value,
                },
              ]),
          );
          snapshot = await client.apply(
            settings,
            chosen.has(0x10000) ? rgb : null,
          );
          status.textContent = chosen.has(0x10000)
            ? "Native groups verified. Macro color sent to all three native modes; this firmware may not support Macro color readback."
            : "Native lighting saved and read back.";
        }, "Native save sequence completed. See the readback status above."),
      true,
    );
    controls.replaceChildren(
      section(
        "Key groups",
        "Select the groups you want to change. Brightness is shared by the native profile.",
        zones,
        el(
          "div",
          { class: "toolbar" },
          button("Select all groups", () => {
            chosen = new Set([...groups.map((g) => g[0]), 0x10000]);
            draw();
          }),
          button("Clear selection", () => {
            chosen.clear();
            draw();
          }),
        ),
      ),
      section(
        "Lighting",
        "The native two-pass save sequence preserves the keyboard’s onboard profile.",
        el(
          "div",
          { class: "columns" },
          field("Color", color),
          field("Effect", effect),
          tempo.node,
          brightness.node,
        ),
        el(
          "div",
          { class: "toolbar" },
          save,
          button("Reload saved lighting", () =>
            ctx.run(async () => {
              snapshot = await client.load();
              draw();
            }, "Lighting read back."),
          ),
        ),
      ),
    );
  }
}
export default {
  id: "alienware_aw768",
  name: "AW768",
  supports: (keyboard) => uids.includes(keyboard.uid),
  pages: [{ id: "aw768-lighting", title: "AW768 lighting", render }],
};
