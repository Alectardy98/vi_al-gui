// SPDX-License-Identifier: GPL-3.0-or-later
// Port of this add-on's EC42 v2.9 codec; field order and CRC are unchanged.
import {
  bytes,
  crc32,
  dword,
  equal,
  hex,
  integer,
  text,
  u16,
  u32,
  word,
  delay,
} from "../../src/binary.js";

export const profiles = [
  {
    name: "Matrix Astro ME EC Kit",
    uid: "0ec173239f8f8f2c",
    rows: 6,
    cols: 16,
    magic: 0xa996,
  },
  {
    name: "Cipulot EC Pro X",
    uid: "4d2d00bcadf8b927",
    rows: 5,
    cols: 15,
    magic: 0xa975,
  },
  {
    name: "MM Studio Class0413 EC",
    uid: "45464c4449414702",
    rows: 5,
    cols: 21,
    magic: 0xa105,
  },
  {
    name: "Cipulot Virgo EC",
    uid: "564952474f454301",
    rows: 6,
    cols: 18,
    magic: 0xa66c,
  },
];
const magic = Uint8Array.from([0xca, 69, 67, 52, 50, 2]);
export function encode(op, sequence, payload = []) {
  integer(op, 0x10, 0x2c, "EC42 operation");
  integer(sequence, 0, 65535);
  if (payload.length > 20) throw Error("EC42 payload exceeds 20 bytes.");
  const result = new Uint8Array(32);
  result.set(bytes(magic, op, word(sequence), 0, payload.length, 0, payload));
  return result;
}
export function decode(raw, op, sequence) {
  if (
    raw.length !== 32 ||
    !equal(raw.slice(0, 6), magic) ||
    raw[6] !== op ||
    u16(raw, 7) !== sequence ||
    raw[11] !== 1 ||
    raw[10] > 20 ||
    raw.slice(12 + raw[10]).some(Boolean)
  )
    throw Error("EC42 response identity, sequence or padding mismatch.");
  if (raw[9]) {
    const error = Error(
      `EC42 rejected this request (${raw[9]}). No request was retried.`,
    );
    error.confirmedResponse = true;
    throw error;
  }
  return raw.slice(12, 12 + raw[10]);
}
export function decodeRecord(raw, profile) {
  const cells = profile.rows * profile.cols,
    meta = 9 + 2 * cells;
  if (
    raw.length !== 17 + 3 * cells ||
    u16(raw, meta) !== profile.magic ||
    ![3, 0x42].includes(u16(raw, meta + 2))
  )
    throw Error("Wrong calibration record format or board.");
  const native = raw.slice();
  for (const start of [
    1,
    3,
    5,
    ...Array.from({ length: cells + 4 }, (_, i) => 9 + 2 * i),
  ]) {
    [native[start], native[start + 1]] = [native[start + 1], native[start]];
  }
  const expected = (u16(raw, meta + 4) | (u16(raw, meta + 6) << 16)) >>> 0;
  native.fill(0, meta + 4, meta + 8);
  if (
    crc32(native) !== expected ||
    raw[0] > 1 ||
    !(u16(raw, 3) > 0 && u16(raw, 3) < u16(raw, 1) && u16(raw, 1) < 1023) ||
    !raw[7] ||
    !raw[8]
  )
    throw Error("Invalid calibration record checksum or thresholds.");
  const overrides = raw.slice(meta + 8);
  for (let i = 0; i < cells; i++) {
    const value = u16(raw, 9 + 2 * i);
    if (
      overrides[i] > 99 ||
      value & 0x1c00 ||
      (value & 0x4000 && !(value & 1023)) ||
      (value & 0x8000 && (!(value & 0x4000) || value & 0x2000)) ||
      (!(value & 0x4000) && value & ~0x2000)
    )
      throw Error("Invalid calibration flags or override.");
  }
  return {
    raw,
    canonical: raw.slice(0, meta),
    overrides,
    packed: u16(raw, meta + 2) === 0x42,
  };
}
export const percentQ = (percent) =>
  percent === 99
    ? 1022
    : Math.floor((integer(percent, 1, 99) * 1023 + 50) / 100);
export class EC42 {
  constructor(keyboard) {
    this.keyboard = keyboard;
    this.profile = profiles.find((p) => p.uid === keyboard.uid);
    this.sequence = 0;
    this.ready = false;
    if (!this.profile) throw Error("This keyboard is not an EC42 v2.9 target.");
    this.cells = this.profile.rows * this.profile.cols;
    this.size = 17 + 3 * this.cells;
  }
  async request(op, payload = []) {
    if (!this.ready && ![0x10, 0x1c, 0x2b].includes(op))
      throw Error("EC42 handshake is required.");
    const sequence = (this.sequence = (this.sequence + 1) & 65535);
    try {
      return decode(
        await this.keyboard.request(encode(op, sequence, payload)),
        op,
        sequence,
      );
    } catch (error) {
      if (!error.confirmedResponse) {
        this.ready = false;
        this.keyboard.transport.fail?.(error);
      }
      throw error;
    }
  }
  async identify() {
    this.ready = false;
    const id = await this.keyboard.request(254, 0);
    if (hex(id.slice(4, 12)) !== this.profile.uid)
      throw Error("Keyboard identity changed.");
    const h = await this.request(0x10),
      p = this.profile;
    if (
      h.length !== 16 ||
      text(h.slice(0, 4)) !== "QEC2" ||
      h[4] !== 9 ||
      u16(h, 5) !== p.rows ||
      u16(h, 7) !== p.cols ||
      u16(h, 9) !== 1023 ||
      h[11] !== 1 ||
      (u16(h, 12) & 0x46) !== 0x46 ||
      h[14] !== 5 ||
      h[15] !== 1
    )
      throw Error("EC42 v2.9 capabilities are required.");
    const d = await this.request(0x2b);
    if (
      d.length !== 20 ||
      u16(d) !== p.magic ||
      u16(d, 2) !== this.size ||
      u16(d, 4) !== 1023 ||
      u16(d, 6) >= 32 ||
      u32(d, 8) >= u32(d, 12) ||
      u32(d, 12) > u16(d, 16) * 1024 ||
      d[18] > 1 ||
      d[19] !== 1
    )
      throw Error("Invalid EC storage descriptor.");
    this.capabilities = u16(h, 12);
    this.storage = !!d[18];
    this.firmware = text(await this.request(0x1c));
    this.ready = true;
    return this;
  }
  async status() {
    const r = await this.request(0x14);
    if (
      r.length !== 6 ||
      ![0, 1, 3, 4, 5].includes(r[0]) ||
      r[3] > 3 ||
      r[4] > 1 ||
      r[5] > 1
    )
      throw Error("Invalid calibration status.");
    return r;
  }
  async record(op = 0x1d, session) {
    const raw = new Uint8Array(this.size);
    for (let offset = 0; offset < raw.length; offset += 17) {
      const n = Math.min(17, raw.length - offset),
        q = bytes(word(offset), n);
      const p = await this.request(
        op,
        session === undefined ? q : bytes(word(session), q),
      );
      if (p.length !== n + 3 || !equal(p.slice(0, 3), q))
        throw Error("Calibration record page mismatch.");
      raw.set(p.slice(3), offset);
    }
    if (op !== 0x16) decodeRecord(raw, this.profile);
    return raw;
  }
  async actuation(index = 65535) {
    const r = await this.request(0x28, word(index));
    if (
      r.length !== 20 ||
      r[4] > 4 ||
      r[5] > 1 ||
      r[10] > 1 ||
      r[13] > 99 ||
      u16(r, 18) !== index ||
      !(0 < u16(r, 8) && u16(r, 8) < u16(r, 6) && u16(r, 6) < 1023)
    )
      throw Error("Invalid actuation response.");
    return r;
  }
  async writable(idle = true) {
    await this.identify();
    const s = await this.status();
    if (!this.storage) throw Error("Keyboard settings storage is not ready.");
    if (idle && s[0]) throw Error("Finish or cancel calibration first.");
  }
  async setActuation(index, percent) {
    integer(index, 0, 65535);
    if (index !== 65535) integer(index, 0, this.cells - 1);
    integer(percent, index === 65535 ? 1 : 0, 99, "Actuation");
    await this.writable();
    const before = await this.actuation(index);
    const global = index === 65535;
    if (global && !(this.capabilities & 0x80))
      throw Error("Update EC firmware for atomic global actuation.");
    const ack = await this.request(
      global ? 0x2c : 0x29,
      bytes(word(index), percent, before.slice(0, 2)),
    );
    const actual = await this.actuation(index);
    if (
      !equal(ack, actual.slice(0, 2)) ||
      (global ? u16(actual, 6) !== percentQ(percent) : actual[13] !== percent)
    )
      throw Error("Actuation acknowledgement/readback differs.");
    if (
      global &&
      decodeRecord(await this.record(), this.profile).overrides.some(Boolean)
    )
      throw Error("Global actuation did not clear per-key overrides.");
    return actual;
  }
  async setRt(enabled, press, release) {
    integer(press, 1, 255);
    integer(release, 1, 255);
    await this.writable();
    const before = await this.actuation(),
      q = bytes(+enabled, press, release);
    const ack = await this.request(0x2a, bytes(q, before.slice(0, 2)));
    const actual = await this.actuation();
    if (!equal(ack, actual.slice(0, 2)) || !equal(actual.slice(10, 13), q))
      throw Error("Rapid Trigger readback differs.");
    return actual;
  }
  async snapshot(selected = null, details = true) {
    const latch = await this.request(0x11);
    if (latch.length !== 8 || !u16(latch) || u16(latch, 6) !== this.cells)
      throw Error("Invalid sensor latch.");
    const id = u16(latch),
      samples = [];
    for (let start = 0; start < this.cells; start += 5) {
      const n = Math.min(5, this.cells - start),
        q = bytes(word(id), word(start), n);
      const r = await this.request(0x12, q);
      if (r.length !== 5 + 3 * n || !equal(r.slice(0, 5), q))
        throw Error("Invalid sensor page.");
      for (let j = 0; j < n; j++) {
        const raw = u16(r, 5 + j * 3),
          flags = r[7 + j * 3];
        if (raw > 1023 || (flags & 0x70) > 0x40 || (flags && !(flags & 1)))
          throw Error("Invalid sensor data.");
        samples.push({
          raw,
          sampled: !!(flags & 1),
          active: !!(flags & 2),
          debounced: !!(flags & 4),
          enabled: !!(flags & 8),
          capture: (flags >> 4) & 7,
          qualified: !!(flags & 128),
        });
      }
    }
    const active = samples.findIndex((s) => s.active || s.debounced);
    this.selected = active >= 0 ? active : (selected ?? this.selected ?? 0);
    if (details) {
      const q = bytes(word(id), word(this.selected)),
        r = await this.request(0x13, q);
      if (r.length !== 20 || !equal(r.slice(0, 4), q))
        throw Error("Invalid sensor details.");
      [
        "baseline",
        "bottom",
        "press",
        "release",
        "minimum",
        "maximum",
        "peak",
        "extremum",
      ].forEach((key, i) => {
        samples[this.selected][key] = u16(r, 4 + i * 2);
      });
    }
    return samples;
  }
  async released() {
    if (
      (await this.snapshot(null, false)).some(
        (s) => s.sampled && (s.active || s.debounced),
      )
    )
      throw Error("Release every keyboard key before this operation.");
  }
  backup(raw) {
    let restorable = false;
    try {
      restorable = decodeRecord(raw, this.profile).packed;
    } catch {
      /* Preserve the raw recovery record even if currently invalid. */
    }
    return {
      format: "qmk-ec-backup-1",
      restorable,
      uid: this.profile.uid,
      serial: "",
      rows: this.profile.rows,
      cols: this.profile.cols,
      crc32: crc32(raw).toString(16),
      record: hex(raw),
    };
  }
  async start(saveBackup) {
    await this.writable();
    const actuation = await this.actuation();
    if (![0, 4].includes(actuation[4]))
      throw Error("Wait for actuation persistence before calibration.");
    await this.released();
    const backup = await this.record(0x16);
    await saveBackup(this.backup(backup));
    this.captureBase = await this.record();
    await this.released();
    const status = await this.status();
    const ack = await this.request(0x20, bytes(1, status[4]));
    const after = await this.status();
    if (
      ack.length !== 2 ||
      !u16(ack) ||
      after[0] !== 1 ||
      !equal(after.slice(1, 3), ack)
    )
      throw Error("Calibration start was not acknowledged.");
  }
  async cancel() {
    await this.writable(false);
    await this.request(0x20, [4]);
    if ((await this.status())[0] !== 0)
      throw Error("Calibration cancellation was not acknowledged.");
  }
  async review() {
    await this.writable(false);
    await this.request(0x20, [3]);
    const status = await this.status();
    if (status[0] !== 3) throw Error("Calibration is not in review state.");
    const session = u16(status, 1),
      proposed = await this.record(0x23, session),
      current = this.captureBase ?? (await this.record());
    const samples = await this.snapshot(null, false);
    let canApply = false;
    for (let i = 0; i < samples.length; i++) {
      if (!samples[i].sampled) continue;
      const value = u16(proposed, 9 + 2 * i),
        old = u16(current, 9 + 2 * i),
        state = samples[i].capture;
      if (
        (state === 1 && ((value & 0xc000) !== 0xc000 || !(value & 1023))) ||
        (state === 0 && value !== old) ||
        ([2, 3].includes(state) && value !== ((old & ~0x8000) | 0x2000))
      )
        throw Error("Capture flags do not match the firmware proposal.");
      canApply ||= state === 1;
    }
    if (canApply) await this.request(0x22, word(session));
    return { session, proposed, samples, canApply };
  }
  async apply(review) {
    await this.writable(false);
    const status = await this.status(),
      token = word(review.session);
    if (
      ![3, 4].includes(status[0]) ||
      u16(status, 1) !== review.session ||
      !review.canApply
    )
      throw Error("Review is stale or has no valid captures.");
    await this.released();
    await this.request(0x22, token);
    if (!equal(await this.record(0x23, review.session), review.proposed))
      throw Error("Calibration proposal changed.");
    await this.request(0x24, token);
    try {
      if (!equal(await this.request(0x15, [1]), review.proposed.slice(0, 9)))
        throw Error("Active calibration readback mismatch; not saved.");
      await delay(100);
      const samples = await this.snapshot(null, false);
      for (let i = 0; i < samples.length; i++) {
        const s = samples[i],
          v = u16(review.proposed, 9 + 2 * i);
        if (
          s.sampled &&
          (s.enabled !== !!(v & 0x8000) ||
            s.qualified !== !!(v & 0x4000) ||
            s.active ||
            s.debounced)
        )
          throw Error(
            "Released-key or active calibration verification failed; not saved.",
          );
      }
    } catch (error) {
      if (this.keyboard.transport.healthy) await this.request(0x20, [4]);
      throw error;
    }
    await this.request(0x25, token);
    const actual = decodeRecord(await this.record(0x16), this.profile),
      expected = decodeRecord(review.proposed, this.profile);
    if (
      !equal(actual.canonical, expected.canonical) ||
      !equal(actual.overrides, expected.overrides)
    )
      throw Error("Saved calibration differs from the reviewed record.");
  }
}
