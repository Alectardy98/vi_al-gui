// SPDX-License-Identifier: GPL-3.0-or-later
// Native Leyden Jar protocol; selected Vial transport only, no private HID handle.
import profiles from "./profiles.json" with { type: "json" };
import { bytes, equal, integer, u16, u32, word } from "../../src/binary.js";
export { profiles };
export const supported = (k) =>
  !k.demo &&
  profiles.some(
    (p) => p.uid === k.uid && p.rows === k.rows && p.cols === k.cols,
  );
export const GET = 2,
  SET = 3;
export const C = Object.freeze({
  version: 0x81,
  details: 0x82,
  enable: 0x83,
  detect: 0x84,
  threshold: 0x85,
  levels: 0x86,
  scanLogical: 0x87,
  scanPhysical: 0x88,
  boot: 0x89,
  reboot: 0x8a,
  erase: 0x8b,
  logicalRow: 0x8c,
  physical: 0x8d,
  mapping: 0x8e,
  reference: 0x8f,
  bins: 0x90,
  side: 0x91,
  capabilities: 0x92,
  preference: 0x93,
  defaults: 0x94,
});
const atLeast = (v, w) =>
  v[0] > w[0] ||
  (v[0] === w[0] && (v[1] > w[1] || (v[1] === w[1] && v[2] >= w[2])));
const signed = (raw, at) =>
  new DataView(raw.buffer, raw.byteOffset, raw.byteLength).getInt16(at, true);
export const position = (row, col) => `${row}:${col}`;
export function decodeDetails(raw, version) {
  if (raw.length < 6) throw Error("Incomplete Leyden Jar details.");
  const [rows, cols, physicalRows, physicalCols, technology, bins] = raw;
  let directKey = null,
    expandedColumns = false;
  if (version[0] === 0 && atLeast(version, [0, 10, 1])) {
    if (raw[6] === 2 && atLeast(version, [0, 10, 2])) {
      if (
        raw.length < 12 ||
        !equal(raw.slice(0, 5), bytes(4, 20, 4, 20, 1)) ||
        !equal(raw.slice(10, 12), bytes(31, 32))
      )
        throw Error("Invalid expanded-column scanner descriptor.");
      expandedColumns = true;
    } else if (raw[6] === 1) {
      directKey = [...raw.slice(7, 10)];
      if (
        rows !== 9 ||
        directKey.length !== 3 ||
        directKey[0] !== 8 ||
        directKey[1] >= cols ||
        directKey[2] >= 30
      )
        throw Error("Invalid direct-switch descriptor.");
    } else if (raw[6] !== 0)
      throw Error("Unsupported direct-switch descriptor.");
  }
  if (
    rows < 1 ||
    rows > (directKey ? 9 : 8) ||
    cols < 1 ||
    cols > (expandedColumns ? 20 : 18) ||
    physicalRows !== (expandedColumns ? 4 : 8) ||
    !(expandedColumns ? [20] : [16, 18]).includes(physicalCols) ||
    ![0, 1].includes(technology) ||
    bins < 1 ||
    bins > 16
  )
    throw Error("Unsupported Leyden Jar matrix, technology or group count.");
  return {
    rows,
    cols,
    physicalRows,
    physicalCols,
    technology,
    bins,
    directKey,
    expandedColumns,
  };
}
export class LeydenJar {
  constructor(keyboard) {
    if (!supported(keyboard))
      throw Error(
        "This keyboard has no verified Leyden Jar UID and matrix profile.",
      );
    this.keyboard = keyboard;
    this.persistent = false;
    this.minimum = new Map();
    this.maximum = new Map();
  }
  async exchange(
    operation,
    command,
    payload = [],
    { timeout = 2500, reply = true } = {},
  ) {
    if (
      ![GET, SET].includes(operation) ||
      !Object.values(C).includes(command) ||
      payload.length > 28
    )
      throw Error("Invalid native Leyden Jar command or payload.");
    const request = bytes(operation, command, 0xc0, 0x21, payload),
      t = this.keyboard.transport;
    if (!reply) {
      const packet = new Uint8Array(32);
      packet.set(request);
      await t.batch(() => t.device.sendReport(t.reports.output, packet));
      t.fail?.(
        Error(
          "Restart command sent. Reconnect the keyboard before continuing.",
        ),
      );
      return;
    }
    const raw = await t.request(request, { timeout });
    if (raw.length !== 32 || !equal(raw.slice(1, 4), request.slice(1, 4)))
      throw Error(
        "Mismatched Leyden Jar reply. Close other keyboard tools and reconnect.",
      );
    if (raw[0] === 255)
      throw Error(
        `Firmware rejected Leyden Jar command 0x${command.toString(16)}. It was not retried.`,
      );
    if (raw[0] !== operation)
      throw Error("Unexpected Leyden Jar operation reply.");
    return raw.slice(4);
  }
  async connect() {
    const raw = await this.exchange(GET, C.version);
    this.version = [raw[0], raw[1], u16(raw, 2, true)];
    if (!atLeast(this.version, [0, 9, 1]) || this.version[0] >= 2)
      throw Error("Requires native Leyden Jar protocol 0.9.1 or 1.x.");
    this.details = decodeDetails(
      await this.exchange(GET, C.details),
      this.version,
    );
    const d = this.details;
    if (d.rows !== this.keyboard.rows || d.cols !== this.keyboard.cols)
      throw Error("Native matrix differs from the connected Vial definition.");
    const mapping = await this.exchange(GET, C.mapping);
    this.mappingType = mapping[0];
    this.cols = [...mapping.slice(1, 1 + d.physicalCols)];
    this.rows = [
      ...mapping.slice(1 + d.physicalCols, 1 + d.physicalCols + d.physicalRows),
    ];
    if (d.directKey) this.rows.push(255);
    if (![0, 1, 2].includes(this.mappingType))
      throw Error("Unknown native matrix mapping convention.");
    for (const [map, used, limit] of [
      [this.rows, d.rows, d.physicalRows],
      [this.cols, d.cols, d.physicalCols],
    ]) {
      const assigned = map.slice(0, used).filter((x) => x !== 255);
      if (
        assigned.some((x) => x >= limit) ||
        new Set(assigned).size !== assigned.length
      )
        throw Error("Invalid or aliased logical-to-controller mapping.");
    }
    this.enabled = await this.readEnabled();
    await this.refreshBins();
    if (this.version[0] === 0 && atLeast(this.version, [0, 10, 0])) {
      const caps = await this.exchange(GET, C.capabilities);
      if (
        caps[0] !== 1 ||
        (caps[1] & 3) !== 3 ||
        caps[2] < d.bins ||
        caps[2] > 16
      )
        throw Error("Unsupported persistent calibration capabilities.");
      this.persistent = true;
      await this.refreshPreferences();
    }
    this.side = null;
    if (this.version[0] === 1) {
      const side = (await this.exchange(GET, C.side))[0];
      if (![0, 1].includes(side)) throw Error("Invalid split-controller side.");
      this.side = side ? "left" : "right";
    }
    return this;
  }
  async readThreshold(bin) {
    integer(bin, 0, this.details.bins - 1, "Calibration group");
    const raw = await this.exchange(GET, C.threshold, word(bin, true));
    if (u16(raw, 0, true) !== bin)
      throw Error("Threshold reply belongs to another group.");
    return integer(u16(raw, 2, true), 0, 1023, "DAC trigger");
  }
  async refreshBins() {
    const thresholds = [],
      references = [],
      bins = new Map(),
      d = this.details;
    for (let bin = 0; bin < d.bins; bin++) {
      thresholds.push(await this.readThreshold(bin));
      const raw = await this.exchange(GET, C.reference, word(bin, true));
      if (u16(raw, 0, true) !== bin)
        throw Error("Reference reply belongs to another group.");
      references.push(integer(u16(raw, 2, true), 0, 1023, "Startup reference"));
    }
    for (let col = 0; col < d.physicalCols; col++) {
      const raw = await this.exchange(GET, C.bins, word(col, true));
      if (u16(raw, 0, true) !== col)
        throw Error("Group reply belongs to another column.");
      for (let row = 0; row < d.physicalRows; row++) {
        const bin = raw[2 + row];
        if (bin !== 255 && bin >= d.bins)
          throw Error("Invalid calibration group assignment.");
        bins.set(position(row, col), bin);
      }
    }
    this.thresholds = thresholds;
    this.references = references;
    this.bins = bins;
    if (this.persistent) await this.refreshPreferences();
  }
  async refreshPreferences() {
    const offsets = [],
      defaults = [],
      saved = [];
    for (let bin = 0; bin < this.details.bins; bin++) {
      const raw = await this.exchange(GET, C.preference, word(bin, true));
      const offset = signed(raw, 2),
        defaultOffset = signed(raw, 4);
      if (
        u16(raw, 0, true) !== bin ||
        ![0, 1].includes(raw[6]) ||
        [offset, defaultOffset].some((x) => x === 0 || Math.abs(x) > 1023)
      )
        throw Error("Invalid saved calibration preference.");
      offsets.push(offset);
      defaults.push(defaultOffset);
      saved.push(!!raw[6]);
    }
    this.offsets = offsets;
    this.defaults = defaults;
    this.saved = saved;
  }
  async setThreshold(bin, value) {
    integer(bin, 0, this.details.bins - 1, "Calibration group");
    integer(value, 0, 1023, "DAC trigger");
    if (this.persistent) {
      const offset = value - this.references[bin];
      if (this.details.technology ? offset >= 0 : offset <= 0)
        throw Error(
          "Trigger must stay below Rest for Beamspring, or above Rest for Model F.",
        );
      await this.exchange(
        SET,
        C.preference,
        bytes(word(offset & 65535, true), bin),
      );
      await this.refreshPreferences();
      if (this.offsets[bin] !== offset || !this.saved[bin])
        throw Error("Saved offset readback does not match.");
    } else await this.exchange(SET, C.threshold, bytes(word(value, true), bin));
    const actual = await this.readThreshold(bin);
    if (actual !== value)
      throw Error("Trigger readback does not match the requested value.");
    this.thresholds[bin] = actual;
    this.resetExtrema();
    return actual;
  }
  async restoreDefaults() {
    if (!this.persistent)
      throw Error("Firmware does not support persistent calibration defaults.");
    await this.exchange(SET, C.defaults);
    await this.refreshBins();
    if (
      this.saved.some(Boolean) ||
      this.thresholds.some(
        (t, i) => t !== this.references[i] + this.defaults[i],
      )
    )
      throw Error("Calibration default readback could not be verified.");
    this.resetExtrema();
    return this.thresholds;
  }
  async readEnabled() {
    const state = (await this.exchange(GET, C.enable))[0];
    if (![0, 1].includes(state)) throw Error("Invalid keyboard output state.");
    return !!state;
  }
  async setEnabled(enabled) {
    if (typeof enabled !== "boolean")
      throw Error("Expected a keyboard enable state.");
    await this.exchange(SET, C.enable, [+enabled]);
    this.enabled = await this.readEnabled();
    if (this.enabled !== enabled)
      throw Error("Keyboard output readback does not match.");
    return this.enabled;
  }
  physicalPosition(id) {
    if (typeof id !== "string") return null;
    const [row, col] = id.split(":").map(Number),
      d = this.details;
    if (
      !Number.isInteger(row) ||
      !Number.isInteger(col) ||
      row < 0 ||
      col < 0 ||
      row >= d.rows ||
      col >= d.cols
    )
      return null;
    const mapped = [this.rows[row], this.cols[col]];
    return mapped.includes(255) ? null : position(...mapped);
  }
  logicalPosition(id) {
    const [row, col] = id.split(":").map(Number),
      r = this.rows.slice(0, this.details.rows).indexOf(row),
      c = this.cols.slice(0, this.details.cols).indexOf(col);
    return r < 0 || c < 0 ? null : position(r, c);
  }
  async keys() {
    const d = this.details,
      physical = new Set(),
      logical = new Set();
    await this.exchange(SET, C.scanPhysical);
    const raw = await this.exchange(GET, C.physical);
    for (let col = 0; col < d.physicalCols; col++)
      for (let row = 0; row < d.physicalRows; row++) {
        const id = position(row, col);
        if (
          this.bins.get(id) !== 255 &&
          !!(raw[col] & (1 << row)) !== !!d.technology
        ) {
          physical.add(id);
          const key = this.logicalPosition(id);
          if (key) logical.add(key);
        }
      }
    if (d.directKey) {
      const [row, col] = d.directKey;
      await this.exchange(SET, C.scanLogical);
      const state = await this.exchange(GET, C.logicalRow, word(row, true));
      if (u16(state, 0, true) !== row || u32(state, 4, true) >>> d.cols)
        throw Error("Invalid direct-switch row snapshot.");
      if (u32(state, 4, true) & (1 << col)) logical.add(position(row, col));
    }
    return { logical, physical };
  }
  async levels() {
    await this.exchange(SET, C.detect, [], { timeout: 20000 });
    const result = new Map(),
      d = this.details;
    for (let col = 0; col < d.physicalCols; col++) {
      const raw = await this.exchange(GET, C.levels, word(col, true));
      if (u16(raw, 0, true) !== col)
        throw Error("Signal reply belongs to another column.");
      for (let row = 0; row < d.physicalRows; row++) {
        const id = position(row, col),
          value = integer(u16(raw, 2 + 2 * row, true), 0, 1023, "Signal");
        result.set(id, value);
        if (this.bins.get(id) !== 255) {
          this.minimum.set(id, Math.min(this.minimum.get(id) ?? value, value));
          this.maximum.set(id, Math.max(this.maximum.get(id) ?? value, value));
        }
      }
    }
    return result;
  }
  resetExtrema() {
    this.minimum.clear();
    this.maximum.clear();
  }
  async restart(command) {
    if (![C.boot, C.reboot, C.erase].includes(command))
      throw Error("Invalid restart action.");
    await this.exchange(SET, command, [], { reply: false });
  }
}
