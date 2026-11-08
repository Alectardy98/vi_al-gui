// SPDX-License-Identifier: GPL-2.0-or-later
// Original xwhatsit utility protocol + the desktop add-on's XCAL record.
import profiles from "./profiles.json" with { type: "json" };
import { bytes, equal, integer, u16, word, delay } from "../../src/binary.js";
export { profiles };
export const supported = (k) =>
  !k.demo &&
  profiles.some(
    (p) => p.uid === k.uid && p.rows === k.rows && p.cols === k.cols,
  );
export function crc8(data) {
  let crc = 0;
  for (const value of data) {
    crc ^= value;
    for (let i = 0; i < 8; i++) crc = ((crc << 1) ^ (crc & 128 ? 7 : 0)) & 255;
  }
  return crc;
}
export function encodeSettings(s, maxGroups = 15, dac = 4095) {
  integer(s.settle, 1, 32, "DAC settling time");
  integer(s.sample, 1, 32, "Sample timing");
  integer(s.groups, 1, maxGroups, "Calibration groups");
  integer(s.margin, 0, dac, "Threshold margin");
  const exponents = [s.initial, s.per_key].map((v) => {
    if (![1, 2, 4, 8, 16, 32].includes(v))
      throw Error("Averaging must be 1, 2, 4, 8, 16 or 32.");
    return Math.log2(v);
  });
  const raw = bytes(
    167,
    s.settle,
    s.sample,
    exponents[0] | (exponents[1] << 4),
    s.groups,
    word(s.margin, true),
  );
  return bytes(raw, crc8(raw));
}
export function decodeSettings(raw, maxGroups = 15, dac = 4095) {
  if (
    raw.length !== 8 ||
    raw[0] !== 167 ||
    crc8(raw.slice(0, 7)) !== raw[7] ||
    (raw[3] & 15) > 5 ||
    raw[3] >> 4 > 5
  )
    throw Error("Invalid calibration record or checksum.");
  const s = {
    settle: raw[1],
    sample: raw[2],
    initial: 2 ** (raw[3] & 15),
    per_key: 2 ** (raw[3] >> 4),
    groups: raw[4],
    margin: u16(raw, 5, true),
  };
  encodeSettings(s, maxGroups, dac);
  return s;
}
export class Xwhatsit {
  constructor(keyboard) {
    if (!supported(keyboard))
      throw Error("This keyboard has no verified xwhatsit profile.");
    this.keyboard = keyboard;
    this.rows = keyboard.rows;
    this.cols = keyboard.cols;
    this.rowBytes = this.cols > 16 ? 4 : this.cols > 8 ? 2 : 1;
    this.extension = false;
    this.lastPressed = new Set();
    this.activityAt = 0;
  }
  async exchange(op, payload = [], timeout = 2000) {
    if (payload.length > 29) throw Error("Utility payload exceeds 29 bytes.");
    const reply = await this.keyboard.transport.request(
      bytes(85, 170, op, payload),
      { timeout },
    );
    if (reply.length !== 32 || reply[0] !== 85 || reply[1] !== 170)
      throw Error(
        "Invalid xwhatsit reply. Close other keyboard tools and reconnect.",
      );
    if (reply[2] === 36)
      throw Error(
        "Release all keys before applying calibration. This command was not retried.",
      );
    if (reply[2] !== 34)
      throw Error(
        `Firmware rejected utility command 0x${op.toString(16)}. No command was retried.`,
      );
    return reply.slice(3);
  }
  async connect() {
    const v = await this.exchange(17);
    this.version = [v[0], v[1], u16(v, 2)];
    if (v[0] !== 2 || (v[1] === 0 && u16(v, 2) < 2))
      throw Error("Requires xwhatsit utility protocol 2.0.2 or newer.");
    const d = await this.exchange(26);
    if (d[0] !== this.cols || d[1] !== this.rows)
      throw Error("Utility matrix differs from Vial layout.");
    this.senseRows = d[9];
    this.dac = u16(d, 7, true);
    this.auto = !!d[6];
    if (
      this.senseRows < 1 ||
      this.senseRows > this.rows ||
      ![1023, 4095].includes(this.dac)
    )
      throw Error("Unsupported sensor matrix or DAC.");
    if (v[1] >= 1) {
      const caps = await this.exchange(48);
      if (
        !equal(caps.slice(0, 5), bytes(88, 67, 65, 76, 1)) ||
        caps[5] < 1 ||
        caps[5] > 15 ||
        u16(caps, 7, true) !== this.dac
      )
        throw Error("Unknown XCAL capability descriptor.");
      this.extension = true;
      this.maxGroups = caps[5];
      this.auto = !!(caps[6] & 1);
      this.debug = !!(caps[6] & 2);
      this.defaults = decodeSettings(
        caps.slice(9, 17),
        this.maxGroups,
        this.dac,
      );
      this.settings = await this.getSettings();
    }
    this.thresholds = await this.getThresholds();
    return this;
  }
  async getSettings() {
    if (!this.extension)
      throw Error(
        "Live settings require the optional XCAL firmware extension.",
      );
    return decodeSettings(
      (await this.exchange(49)).slice(0, 8),
      this.maxGroups,
      this.dac,
    );
  }
  async save(settings, defaults = false) {
    if (!this.extension) throw Error("Live settings require XCAL firmware.");
    const expected = encodeSettings(settings, this.maxGroups, this.dac);
    const reply = await this.exchange(
      defaults ? 51 : 50,
      defaults ? [] : expected,
      60000,
    );
    if (
      !equal(reply.slice(0, 8), expected) ||
      !equal(
        encodeSettings(await this.getSettings(), this.maxGroups, this.dac),
        expected,
      )
    )
      throw Error("Save acknowledgement/readback mismatch.");
    this.settings = { ...settings };
    this.thresholds = await this.getThresholds();
    return this.settings;
  }
  async getThresholds() {
    const result = new Map(),
      size = this.rowBytes * this.senseRows;
    let group = 0,
      count = 1;
    while (group < count) {
      const bitmap = new Uint8Array(size);
      let threshold = null,
        expectedCount = null;
      for (let offset = 0; offset < size; offset += 26) {
        const raw = await this.exchange(22, [group, offset]);
        count = raw[0];
        const value = u16(raw, 1, true);
        if (
          count > 15 ||
          value > this.dac ||
          (threshold !== null && value !== threshold) ||
          (expectedCount !== null && count !== expectedCount)
        )
          throw Error("Invalid or changing calibration thresholds.");
        threshold = value;
        expectedCount = count;
        bitmap.set(raw.slice(3, 3 + Math.min(26, size - offset)), offset);
      }
      for (let row = 0; row < this.senseRows; row++)
        for (let col = 0; col < this.cols; col++) {
          if (
            count === 0 ||
            bitmap[row * this.rowBytes + Math.floor(col / 8)] & (1 << col % 8)
          ) {
            const id = `${row}:${col}`;
            if (result.has(id))
              throw Error("A key belongs to multiple calibration groups.");
            result.set(id, { group, threshold, row, col });
          }
        }
      group++;
    }
    return result;
  }
  async keyState() {
    const k = this.keyboard;
    if (
      k.version >= 3 &&
      (Math.floor(this.cols / 8) + 1) * this.rows <= 28 &&
      (await k.unlockStatus())[0] === 1
    ) {
      const states = await k.matrix();
      return new Set(
        states.flatMap((active, i) =>
          active ? [`${Math.floor(i / this.cols)}:${i % this.cols}`] : [],
        ),
      );
    }
    const raw = new Uint8Array(this.rows * this.rowBytes);
    for (let offset = 0; offset < raw.length; offset += 29)
      raw.set(
        (await this.exchange(21, [offset])).slice(
          0,
          Math.min(29, raw.length - offset),
        ),
        offset,
      );
    const pressed = new Set();
    for (let row = 0; row < this.rows; row++)
      for (let col = 0; col < this.cols; col++)
        if (raw[row * this.rowBytes + Math.floor(col / 8)] & (1 << col % 8))
          pressed.add(`${row}:${col}`);
    return pressed;
  }
  async readSignal(id) {
    const [row, col] = id.split(":").map(Number);
    integer(row, 0, this.senseRows - 1, "Sensor row");
    integer(col, 0, this.cols - 1, "Sensor column");
    const value = u16(await this.exchange(25, [col, row, 1]), 0, true);
    if (value > this.dac) throw Error("Signal exceeds DAC range.");
    return value;
  }
  observe(pressed) {
    if (pressed.size || [...pressed].join() !== [...this.lastPressed].join())
      this.activityAt = performance.now();
    this.lastPressed = pressed;
    return !pressed.size && performance.now() - this.activityAt >= 350;
  }
  async frame(selected, background = []) {
    let pressed = await this.keyState();
    const first = [...pressed].find((id) => +id.split(":")[0] < this.senseRows);
    selected = first ?? selected;
    this.observe(pressed);
    const values = new Map();
    for (const [index, id] of [selected, ...background.slice(0, 3)].entries()) {
      if (!id || values.has(id)) continue;
      if (index) {
        pressed = await this.keyState();
        if (!this.observe(pressed)) break;
      }
      values.set(id, await this.readSignal(id));
      await delay(2);
    }
    return { selected, pressed, values };
  }
  async enterBootloader() {
    const t = this.keyboard.transport,
      packet = new Uint8Array(32);
    packet.set([85, 170, 18]);
    // Jump disconnects before an ACK: one queued send, no retry/response wait.
    await t.batch(() => t.device.sendReport(t.reports.output, packet));
  }
  async eraseEeprom() {
    await this.exchange(24, [], 15000);
  }
}
