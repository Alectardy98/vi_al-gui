// SPDX-License-Identifier: GPL-2.0-or-later
import xz from "xz-decompress";
import { deserializeLayout, placeLayout } from "./layout.js";
import { bytes, dword, equal, hex, integer, u16, u32, word } from "./binary.js";
const { XzReadableStream } = xz;

export function parseDefinition(definition) {
  const { rows, cols } = definition.matrix ?? {};
  integer(rows, 1, 32, "Matrix rows");
  integer(cols, 1, 32, "Matrix columns");
  if (!Array.isArray(definition.layouts?.keymap))
    throw Error("The keyboard did not provide a physical layout.");
  const keys = deserializeLayout(definition.layouts.keymap).map((key) => {
    if (
      ![
        key.x,
        key.y,
        key.width,
        key.height,
        key.x2,
        key.y2,
        key.width2,
        key.height2,
        key.rotation_angle,
        key.rotation_x,
        key.rotation_y,
      ].every(Number.isFinite) ||
      Math.abs(key.x) > 100 ||
      Math.abs(key.y) > 100 ||
      key.width <= 0 ||
      key.width > 24 ||
      key.height <= 0 ||
      key.height > 24 ||
      key.width2 <= 0 ||
      key.width2 > 24 ||
      key.height2 <= 0 ||
      key.height2 > 24 ||
      Math.abs(key.x2) > 24 ||
      Math.abs(key.y2) > 24 ||
      Math.abs(key.rotation_x) > 100 ||
      Math.abs(key.rotation_y) > 100 ||
      Math.abs(key.rotation_angle) > 360
    )
      throw Error("Keyboard geometry is outside supported bounds.");
    const coord = key.labels[0]?.match(/^\s*(\d+)\s*,\s*(\d+)\s*$/);
    const option = key.labels[8]?.match(/^\s*(\d+)\s*,\s*(\d+)\s*$/);
    const encoder = key.labels[4] === "e";
    if (coord && !encoder && (+coord[1] >= rows || +coord[2] >= cols))
      throw Error("Layout key is outside its matrix.");
    return {
      ...key,
      row: coord && !encoder ? +coord[1] : null,
      col: coord && !encoder ? +coord[2] : null,
      encoder: encoder && coord ? +coord[1] : null,
      direction: encoder && coord ? +coord[2] : null,
      option: option ? [+option[1], +option[2]] : null,
    };
  });
  if (keys.length > 1024) throw Error("Physical layout is too large.");
  return keys;
}
export function optionValues(labels, packed) {
  const values = Array(labels?.length ?? 0).fill(0);
  let shift = 0;
  for (let i = values.length - 1; i >= 0; i--) {
    const bits =
      typeof labels[i] === "string"
        ? 1
        : Math.max(1, Math.ceil(Math.log2(labels[i].length - 1)));
    if (shift + bits > 32) throw Error("Layout options exceed 32 bits.");
    values[i] = (packed >>> shift) & (2 ** bits - 1);
    shift += bits;
  }
  return values;
}
export function packOptions(labels, values) {
  let result = 0,
    shift = 0;
  for (let i = labels.length - 1; i >= 0; i--) {
    const choices = typeof labels[i] === "string" ? 2 : labels[i].length - 1;
    integer(values[i], 0, choices - 1, "Layout option");
    const bits = Math.max(1, Math.ceil(Math.log2(choices)));
    if (shift + bits > 32) throw Error("Layout options exceed 32 bits.");
    result = (result | (values[i] << shift)) >>> 0;
    shift += bits;
  }
  return result;
}
export class VialKeyboard {
  constructor(transport) {
    this.transport = transport;
    this.definition = null;
    this.uid = "";
    this.layer = 0;
  }
  request(...data) {
    return this.transport.request(bytes(...data));
  }
  async load(progress = () => {}) {
    const via = await this.request(1);
    this.viaVersion = u16(via, 1);
    if (this.viaVersion !== 9)
      throw Error(
        `Unsupported VIA protocol ${this.viaVersion}; this client requires Vial firmware.`,
      );
    const identity = await this.request(254, 0);
    this.version = u32(identity, 0, true);
    this.uid = hex(identity.slice(4, 12));
    integer(this.version, 0, 6, "Vial protocol");
    if (identity.slice(4, 12).every((x) => x === 0))
      throw Error(
        "No Vial identity. VIA-only definitions are not supported yet.",
      );
    const size = u32(await this.request(254, 1), 0, true);
    integer(size, 1, 131072, "Compressed definition size");
    const compressed = new Uint8Array(size);
    for (let offset = 0; offset < size; offset += 32) {
      const chunk = await this.request(254, 2, dword(offset / 32, true));
      compressed.set(chunk.slice(0, Math.min(32, size - offset)), offset);
      progress(
        `Reading keyboard definition · ${Math.round((100 * Math.min(offset + 32, size)) / size)}%`,
      );
    }
    const stream = new XzReadableStream(new Blob([compressed]).stream());
    const reader = stream.getReader();
    let length = 0;
    const chunks = [];
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        length += value.length;
        if (length > 2 * 1024 * 1024) {
          await reader.cancel();
          throw Error("Expanded keyboard definition exceeds 2 MiB.");
        }
        chunks.push(value);
      }
    } catch (error) {
      throw Error(
        `Cannot decode the keyboard definition (${error.message}). Close desktop Vi_al and other keyboard configurators, then disconnect and reconnect this page. No settings were changed.`,
        { cause: error },
      );
    } finally {
      reader.releaseLock();
    }
    this.definition = JSON.parse(new TextDecoder().decode(bytes(...chunks)));
    this.keys = parseDefinition(this.definition);
    this.rows = this.definition.matrix.rows;
    this.cols = this.definition.matrix.cols;
    this.layers = (await this.request(17))[1];
    integer(this.layers, 1, 32, "Layer count");
    this.layoutOptions = u32(await this.request(2, 2), 2);
    await this.reloadKeymap(progress);
    this.macroCount = (await this.request(12))[1];
    this.macroMemory = u16(await this.request(13), 1);
    integer(this.macroCount, 0, 128, "Macro count");
    this.dynamic = { tapDance: 0, combo: 0, override: 0, repeat: 0 };
    this.supportedFeatures = new Set();
    if (this.version >= 4) {
      const counts = await this.request(254, 13, 0);
      ["tapDance", "combo", "override", "repeat"].forEach((key, i) => {
        this.dynamic[key] = counts[i];
      });
      if (counts[31] & 1) this.supportedFeatures.add("caps_word");
      if (counts[31] & 2) this.supportedFeatures.add("layer_lock");
    }
    return this;
  }
  async reloadKeymap(progress = () => {}) {
    const size = this.layers * this.rows * this.cols * 2;
    integer(size, 2, 65536, "Keymap size");
    const buffer = new Uint8Array(size);
    for (let offset = 0; offset < size; offset += 28) {
      const count = Math.min(28, size - offset);
      const response = await this.request(18, word(offset), count);
      if (
        response[0] !== 18 ||
        u16(response, 1) !== offset ||
        response[3] !== count
      )
        throw Error("Keymap response does not match its request.");
      buffer.set(response.slice(4, 4 + count), offset);
      progress(
        `Reading keymap · ${Math.round((100 * Math.min(offset + count, size)) / size)}%`,
      );
    }
    this.keymap = buffer;
    this.encoderKeys = new Map();
    for (const index of new Set(
      this.keys.filter((k) => k.encoder !== null).map((k) => k.encoder),
    )) {
      for (let layer = 0; layer < this.layers; layer++) {
        const r = await this.request(254, 3, layer, index);
        this.encoderKeys.set(`${layer}:${index}:0`, u16(r));
        this.encoderKeys.set(`${layer}:${index}:1`, u16(r, 2));
      }
    }
  }
  keyOffset(layer, row, col) {
    integer(layer, 0, this.layers - 1, "Layer");
    integer(row, 0, this.rows - 1, "Row");
    integer(col, 0, this.cols - 1, "Column");
    return 2 * ((layer * this.rows + row) * this.cols + col);
  }
  code(layer, key) {
    return key.encoder !== null
      ? this.encoderKeys.get(`${layer}:${key.encoder}:${key.direction}`)
      : u16(this.keymap, this.keyOffset(layer, key.row, key.col));
  }
  async setKey(layer, key, code) {
    integer(code, 0, 65535, "Keycode");
    if (key.encoder !== null) {
      await this.request(254, 4, layer, key.encoder, key.direction, word(code));
      const r = await this.request(254, 3, layer, key.encoder);
      if (u16(r, key.direction * 2) !== code)
        throw Error("Encoder readback differs; no write was retried.");
      this.encoderKeys.set(`${layer}:${key.encoder}:${key.direction}`, code);
    } else {
      const offset = this.keyOffset(layer, key.row, key.col);
      await this.request(5, layer, key.row, key.col, word(code));
      const read = await this.request(4, layer, key.row, key.col);
      if (read[0] !== 4 || u16(read, 4) !== code)
        throw Error("Keycode readback differs; no write was retried.");
      this.keymap.set(word(code), offset);
    }
  }
  async setOptions(values) {
    const packed = packOptions(this.definition.layouts.labels ?? [], values);
    await this.request(3, 2, dword(packed));
    const actual = u32(await this.request(2, 2), 2);
    if (actual !== packed) throw Error("Layout option readback differs.");
    this.layoutOptions = actual;
  }
  visibleKeys() {
    const options = optionValues(
      this.definition.layouts.labels,
      this.layoutOptions,
    );
    return placeLayout(this.keys, options);
  }
  async unlockStatus() {
    return this.request(254, 5);
  }
  async matrix() {
    if (this.version < 3 || (await this.unlockStatus())[0] !== 1)
      throw Error("Unlock the keyboard before reading its matrix.");
    const r = await this.request(2, 3);
    const width = Math.ceil(this.cols / 8);
    if (this.rows * width > 30)
      throw Error("Matrix is too large for this protocol.");
    return Array.from({ length: this.rows * this.cols }, (_, i) => {
      const row = Math.floor(i / this.cols),
        col = i % this.cols;
      return !!(
        r[2 + row * width + width - 1 - Math.floor(col / 8)] &
        (1 << (col % 8))
      );
    });
  }
  async exportKeymap() {
    await this.reloadKeymap();
    return {
      format: "vi-al-web-keymap-1",
      uid: this.uid,
      rows: this.rows,
      cols: this.cols,
      layers: this.layers,
      layoutOptions: this.layoutOptions,
      keymap: [...this.keymap],
      encoders: Object.fromEntries(this.encoderKeys),
    };
  }
}
