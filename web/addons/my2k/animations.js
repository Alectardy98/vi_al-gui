// SPDX-License-Identifier: GPL-2.0-or-later
import { My2k } from "./protocol.js";
import { UsbFiles, parseCrs } from "./files.js";
import { bytes, dword, word } from "../../src/binary.js";
import {
  button,
  download,
  el,
  field,
  note,
  range,
  section,
  select,
} from "../../src/ui.js";

export async function convertGif(file, crop) {
  if (
    !globalThis.ImageDecoder ||
    !(await ImageDecoder.isTypeSupported(file.type))
  )
    throw Error(
      "GIF conversion requires ImageDecoder in a supported desktop browser. You can still upload an existing CRS file.",
    );
  if (file.size > 64 * 1024 * 1024) throw Error("Source GIF exceeds 64 MiB.");
  const decoder = new ImageDecoder({
    data: new Uint8Array(await file.arrayBuffer()),
    type: file.type,
  });
  try {
    await decoder.tracks.ready;
    const count = decoder.tracks.selectedTrack.frameCount;
    if (!count || count > 512)
      throw Error("MY-2K supports 1–512 frames per animation.");
    const offset = 20 + count * 2,
      raw = new Uint8Array(offset + count * 32768);
    raw.set(
      bytes(
        [65, 78, 73, 77],
        word(20, true),
        word(offset, true),
        dword(raw.length, true),
        word(128, true),
        word(128, true),
        word(2, true),
        word(count, true),
      ),
    );
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 128;
    const c = canvas.getContext("2d", { willReadFrequently: true });
    for (let frame = 0; frame < count; frame++) {
      const { image } = await decoder.decode({ frameIndex: frame });
      try {
        c.fillStyle = "#000";
        c.fillRect(0, 0, 128, 128);
        const width = image.displayWidth,
          height = image.displayHeight;
        if (crop) {
          const side = Math.min(width, height) * crop.size,
            x = (width - side) * crop.x,
            y = (height - side) * crop.y;
          c.drawImage(image, x, y, side, side, 0, 0, 128, 128);
        } else {
          const scale = Math.min(128 / width, 128 / height),
            w = width * scale,
            h = height * scale;
          c.drawImage(image, (128 - w) / 2, (128 - h) / 2, w, h);
        }
        raw.set(
          word(
            Math.min(
              65535,
              Math.max(1, Math.round((image.duration ?? 100000) / 1000)),
            ),
            true,
          ),
          20 + frame * 2,
        );
        const pixels = c.getImageData(0, 0, 128, 128).data,
          at = offset + frame * 32768;
        for (let i = 0; i < 16384; i++) {
          const value =
            ((pixels[i * 4] >>> 3) << 11) |
            ((pixels[i * 4 + 1] >>> 2) << 5) |
            (pixels[i * 4 + 2] >>> 3);
          raw[at + i * 2] = value >>> 8;
          raw[at + i * 2 + 1] = value & 255;
        }
      } finally {
        image.close();
      }
    }
    return raw;
  } finally {
    decoder.close();
  }
}
export function playCrs(canvas, raw, signal) {
  const movie = parseCrs(raw),
    c = canvas.getContext("2d"),
    image = c.createImageData(128, 128);
  let frame = 0,
    timer;
  const next = () => {
    if (signal.aborted) return;
    const at = movie.offset + frame * 32768;
    for (let i = 0; i < 16384; i++) {
      const rgb = (raw[at + i * 2] << 8) | raw[at + i * 2 + 1];
      image.data.set(
        [
          (((rgb >>> 11) & 31) * 255) / 31,
          (((rgb >>> 5) & 63) * 255) / 63,
          ((rgb & 31) * 255) / 31,
          255,
        ],
        i * 4,
      );
    }
    c.putImageData(image, 0, 0);
    const duration = Math.max(1000 / 60, movie.delays[frame] || 100);
    frame = (frame + 1) % movie.frames;
    timer = setTimeout(next, duration);
  };
  signal.addEventListener("abort", () => clearTimeout(timer), { once: true });
  next();
}
export async function connectFiles(ctx) {
  if (ctx.keyboard.files && !ctx.keyboard.files.uncertain)
    return ctx.keyboard.files;
  if (!navigator.usb)
    throw Error(
      "Animation transfers require WebUSB in desktop Chrome or Edge.",
    );
  const device = await navigator.usb.requestDevice({
    filters: [{ vendorId: 0x4d58, productId: 0xf103 }],
  });
  const client = new UsbFiles(device);
  try {
    await client.open();
    ctx.keyboard.files = client;
    return client;
  } catch (e) {
    await client.close().catch(() => {});
    throw e;
  }
}
export async function animationPage(container, ctx) {
  const client = new My2k(ctx.keyboard);
  let source = null,
    sourceUrl,
    converted,
    movie = null,
    infos = new Map(),
    cancel = false;
  const cache = (ctx.keyboard.previewCache ??= new Map());
  let previewController = new AbortController();
  const sourceImage = el("img", { alt: "Original GIF preview", hidden: true }),
    cropBox = el("div", { class: "crop-box" });
  const stage = el("div", { class: "gif-stage" }, sourceImage, cropBox),
    picker = el("input", {
      type: "file",
      accept: "image/gif,image/webp,.CRS",
      "aria-label": "Select GIF or CRS",
    });
  const mode = select(
    [
      [1, "Crop to fit"],
      [0, "Native size · fit with padding"],
    ],
    1,
  );
  const size = range("Crop size", 100, 10, 100),
    crop = { size: 1, x: 0.5, y: 0.5 };
  function updateCrop() {
    const w = sourceImage.clientWidth,
      h = sourceImage.clientHeight,
      side = Math.min(w, h) * crop.size;
    Object.assign(cropBox.style, {
      width: `${side}px`,
      height: `${side}px`,
      left: `${sourceImage.offsetLeft + (w - side) * crop.x}px`,
      top: `${sourceImage.offsetTop + (h - side) * crop.y}px`,
    });
    cropBox.hidden =
      !source || !+mode.value || source.name.toLowerCase().endsWith(".crs");
    converted = null;
  }
  size.input.addEventListener("input", () => {
    crop.size = +size.input.value / 100;
    updateCrop();
  });
  mode.addEventListener("change", updateCrop);
  const resize = new ResizeObserver(updateCrop);
  resize.observe(stage);
  let drag;
  cropBox.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, cx: crop.x, cy: crop.y };
    cropBox.setPointerCapture(e.pointerId);
  });
  cropBox.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const side =
      Math.min(sourceImage.clientWidth, sourceImage.clientHeight) * crop.size;
    crop.x = Math.max(
      0,
      Math.min(
        1,
        drag.cx +
          (e.clientX - drag.x) / Math.max(1, sourceImage.clientWidth - side),
      ),
    );
    crop.y = Math.max(
      0,
      Math.min(
        1,
        drag.cy +
          (e.clientY - drag.y) / Math.max(1, sourceImage.clientHeight - side),
      ),
    );
    updateCrop();
  });
  cropBox.addEventListener("pointerup", () => {
    drag = null;
  });
  cropBox.addEventListener("pointercancel", () => {
    drag = null;
  });
  const sourceStatus = el(
    "p",
    { class: "muted" },
    "Choose a GIF. It will be converted to 128×128 RGB565 at its original frame timing.",
  );
  picker.addEventListener("change", async () => {
    source = picker.files[0];
    converted = null;
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    if (!source) return;
    if (
      source.size > 64 * 1024 * 1024 ||
      (source.name.toLowerCase().endsWith(".crs") && source.size > 16778260)
    ) {
      ctx.notify(
        "The source exceeds the supported GIF or CRS size limit.",
        true,
      );
      source = null;
      picker.value = "";
      return;
    }
    if (source.name.toLowerCase().endsWith(".crs")) {
      sourceImage.hidden = true;
      cropBox.hidden = true;
      sourceStatus.textContent = `${source.name} · Ready to validate and transfer.`;
    } else {
      sourceUrl = URL.createObjectURL(source);
      sourceImage.src = sourceUrl;
      sourceImage.hidden = false;
      sourceImage.onload = updateCrop;
    }
  });
  async function convert() {
    if (!source) throw Error("Choose a source GIF or CRS file.");
    if (!converted)
      converted = source.name.toLowerCase().endsWith(".crs")
        ? new Uint8Array(await source.arrayBuffer())
        : await convertGif(source, +mode.value ? crop : null);
    const info = parseCrs(converted);
    sourceStatus.textContent = `${source.name} · ${info.frames} frames · ${(info.size / 1024).toFixed(0)} KiB · 128×128`;
    return converted;
  }
  const slotList = el("div", { class: "slot-list" }),
    slot = select(
      Array.from({ length: 10 }, (_, i) => [i + 1, `Slot ${i + 1}`]),
      1,
    );
  const screen = el("canvas", {
    width: 128,
    height: 128,
    class: "animation-preview",
  });
  const transferStatus = note(
    "Keyboard playback works over WebHID. Connect file access to load previews or transfer GIFs; no drive mounting is needed.",
  );
  const progress = el("progress", {
    max: 100,
    value: 0,
    "aria-label": "Transfer progress",
  });
  const cancelled = () => cancel || ctx.signal.aborted;
  const files = () => {
    const f = ctx.keyboard.files;
    if (!f || f.uncertain) throw Error("Connect keyboard file access first.");
    return f;
  };
  async function load() {
    const selection = await client.selectAnimation();
    infos = new Map();
    if (ctx.keyboard.files && !ctx.keyboard.files.uncertain)
      for (let i = 1; i <= 10; i++) infos.set(i, await files().info(i));
    slotList.replaceChildren(
      ...Array.from({ length: 10 }, (_, i) => {
        const number = i + 1,
          info = infos.get(number),
          occupied = !!(((selection[6] << 8) | selection[5]) & (1 << i));
        return button(
          `Slot ${number}${number === selection[4] ? " · playing" : ""}${info ? ` · ${(info.size / 1024).toFixed(0)} KiB` : occupied ? "" : " · empty"}`,
          () =>
            ctx.run(async () => {
              slot.value = number;
              const current = infos.get(number);
              if (!current)
                throw Error(
                  "Connect file access and choose a populated slot for its preview.",
                );
              cancel = false;
              const key =
                current.crc === null
                  ? null
                  : `${number}:${current.size}:${current.crc}`;
              const raw =
                key && cache.has(key)
                  ? cache.get(key)
                  : await files().read(
                      current,
                      (fraction) => {
                        progress.value = fraction * 100;
                      },
                      cancelled,
                    );
              if (key) cache.set(key, raw);
              previewController.abort();
              previewController = new AbortController();
              playCrs(screen, raw, previewController.signal);
              movie = raw;
            }, "Preview loaded."),
        );
      }),
    );
  }
  const connect = button(
    "Connect keyboard file access",
    async () => {
      try {
        await connectFiles(ctx);
        await ctx.run(load, "Animation slots loaded.");
      } catch (e) {
        ctx.notify(e.message, true);
      }
    },
    true,
  );
  const upload = button(
    "Save preview to slot",
    () =>
      ctx.run(async () => {
        const raw = await convert(),
          target = +slot.value,
          existing = await files().info(target);
        if (
          existing &&
          !confirm(
            `Replace animation in slot ${target}? The existing slot remains until the new upload commits.`,
          )
        )
          return;
        cancel = false;
        const started = performance.now();
        await files().upload(
          raw,
          target,
          !!existing,
          (fraction) => {
            progress.value = fraction * 100;
          },
          cancelled,
        );
        transferStatus.textContent = `Saved to anamations/animation_${String(target).padStart(2, "0")}.CRS · ${((performance.now() - started) / 1000).toFixed(2)} s · Stored CRC verified.`;
        await load();
      }, "Animation saved and verified."),
    true,
  );
  const cancelButton = button("Cancel transfer", () => {
    cancel = true;
  });
  cancelButton.className = "cancel-operation";
  const transfer = section(
    "Transfer GIF to keyboard",
    "Convert and save directly to one of the ten onboard slots.",
    field("Destination slot", slot),
    el(
      "div",
      { class: "toolbar" },
      upload,
      button("Clear slot", () =>
        ctx.run(async () => {
          const target = +slot.value;
          if (!confirm(`Clear slot ${target}?`)) return;
          await files().request(7, target);
          if (await files().info(target))
            throw Error("Slot still contains a file.");
          await load();
        }, "Slot cleared and read back."),
      ),
      button("Play selected slot on keyboard", () =>
        ctx.run(async () => {
          const r = await client.selectAnimation(+slot.value);
          if (r[4] !== +slot.value)
            throw Error("Animation selection readback differs.");
          await load();
        }, "Animation selection acknowledged."),
      ),
    ),
    progress,
    cancelButton,
    transferStatus,
  );
  container.append(
    el(
      "div",
      { class: "columns" },
      section(
        "GIF converter",
        "Preview the original GIF, crop a square, then convert it for the MY-2K.",
        picker,
        field("Sizing", mode),
        stage,
        size.node,
        sourceStatus,
        button("Convert and save to desktop", () =>
          ctx.run(
            async () =>
              download(
                "animation.CRS",
                await convert(),
                "application/octet-stream",
              ),
            "Converted file downloaded.",
          ),
        ),
      ),
      el(
        "div",
        {},
        section(
          "Files on keyboard",
          "Click a slot to load its preview.",
          connect,
          screen,
          slotList,
        ),
        transfer,
      ),
    ),
  );
  ctx.signal.addEventListener("abort", () => {
    cancel = true;
    previewController.abort();
    resize.disconnect();
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  });
  await load();
}
