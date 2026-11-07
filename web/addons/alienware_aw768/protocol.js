// SPDX-License-Identifier: GPL-2.0-or-later
import { bytes, delay, equal, integer, u16 } from "../../src/binary.js";
export const groups = [
  [2, "WASD"],
  [16, "Arrows"],
  [0xe000, "Number row"],
  [0x700, "Function row"],
  [32, "Numpad"],
  [0x1000, "Alien head"],
  [128, "Ambient"],
  [77, "Other keys"],
];
export const masks = [
  65535,
  65535,
  ...[0x2103, 0x4204, 0x8408, 0x810, 0x60, 0x1080],
  ...[0x2103, 0x4204, 0x8408, 0x810, 0x60, 0x1080],
  ...groups.map((g) => g[0]),
  ...groups.map((g) => g[0]),
];
export const uids = ["2945ce03248c2c0c", "a9ea250d225daaab"];
export function selector(command, profile = 0) {
  if (![5, 0x85, 0x88, 0x86].includes(command))
    throw Error("Unsupported AW768 lighting selector.");
  if (command === 0x88) {
    if (profile !== 0) throw Error("Status selector has no profile.");
  } else integer(profile, 1, 3, "Profile");
  const raw = new Uint8Array(64);
  raw.set([command, profile]);
  return raw;
}
export function parseSnapshot(profile, records) {
  if (records.length !== 30) throw Error("Incomplete AW768 readback.");
  records.forEach((r, i) => {
    if (
      r.length !== 64 ||
      r[0] !== 0x85 ||
      r[1] !== profile ||
      u16(r, 14) !== masks[i] ||
      r.slice(16).some(Boolean) ||
      r[9] > 3 ||
      r[10] > 10
    )
      throw Error("Unknown AW768 lighting record; writes are disabled.");
  });
  const legacy = records.every((r) => r[12] === 0 && r[13] === 0);
  const channels = [
    1,
    2,
    ...Array(6).fill(1),
    ...Array(6).fill(2),
    ...Array(8).fill(1),
    ...Array(8).fill(2),
  ];
  if (
    !legacy &&
    records.some((r, i) => r[12] !== channels[i] || ![1, 2, 3].includes(r[13]))
  )
    throw Error("Unknown AW768 channel layout.");
  return { profile, records, legacy };
}
export function lightingBatch(snapshot, changes) {
  const keys = [...changes.keys()];
  if (!keys.length || keys.some((k) => !groups.some((g) => g[0] === k)))
    throw Error("Choose a known lighting group.");
  const brightnesses = new Set([...changes.values()].map((s) => s.brightness));
  if (brightnesses.size !== 1) throw Error("AW768 brightness is shared.");
  const brightness = [...brightnesses][0];
  integer(brightness, 1, 10, "Brightness");
  const result = snapshot.records.slice(14, 22).map((record) => {
    const raw = record.slice(),
      setting = changes.get(u16(record, 14));
    raw[0] = 5;
    raw[10] = brightness;
    raw[12] = 1;
    if (raw[2] > 4)
      throw Error("Existing effect is unsupported; refusing a lossy rewrite.");
    if (snapshot.legacy) {
      raw[9] = 3 - raw[9];
      raw[13] = raw[2] === 3 ? 2 : raw[2] === 4 ? 3 : 1;
    }
    if (setting) {
      integer(setting.mode, 0, 4, "Effect");
      integer(setting.tempo, 0, 3, "Speed");
      if (setting.color.length !== 3) throw Error("Invalid RGB color.");
      setting.color.forEach((c) => integer(c, 0, 255, "Color"));
      raw[2] = setting.mode;
      raw.set(setting.color, 3);
      raw.set(setting.color2 ?? [0, 0, 0], 6);
      raw[9] = setting.tempo;
      raw[11] = 0;
      raw[13] = setting.mode === 3 ? 2 : setting.mode === 4 ? 3 : 1;
    }
    return raw;
  });
  return [
    ...result,
    ...result.map((raw) => {
      const p = raw.slice();
      p[2] = 255;
      p[12] = 2;
      return p;
    }),
  ];
}
export function macroPacket(profile, color) {
  integer(profile, 1, 3);
  if (color.length !== 3) throw Error("Invalid Macro color.");
  color.forEach((c) => integer(c, 0, 255));
  const raw = new Uint8Array(64);
  raw.set(bytes(6, profile, color, color, color));
  return raw;
}
export class Alienware {
  constructor(device) {
    if (
      device.vendorId !== 0x04f2 ||
      device.productId !== 0x1666 ||
      !device.collections.some((c) => c.usagePage === 0xff00 && c.usage === 1)
    )
      throw Error(
        "Choose the original AW768 lighting PCB (04F2:1666, vendor collection FF00/1).",
      );
    this.device = device;
    this.capture = null;
    this.onInput = (event) => {
      if (!this.capture || event.reportId !== 0) return;
      const raw = new Uint8Array(
        event.data.buffer,
        event.data.byteOffset,
        event.data.byteLength,
      ).slice();
      this.capture.frames.push(raw);
      if (this.capture.frames.length === 30) {
        const c = this.capture;
        this.capture = null;
        clearTimeout(c.timer);
        c.resolve(c.frames);
      }
    };
  }
  async open() {
    if (!this.device.opened) await this.device.open();
    this.device.addEventListener("inputreport", this.onInput);
    return this;
  }
  async close() {
    if (this.capture) {
      clearTimeout(this.capture.timer);
      this.capture.reject(Error("Lighting PCB disconnected."));
      this.capture = null;
    }
    this.device.removeEventListener("inputreport", this.onInput);
    if (this.device.opened) await this.device.close();
  }
  async feature(command, profile = 0) {
    await delay(10);
    await this.device.sendFeatureReport(0, selector(command, profile));
    await delay(10);
  }
  async profile() {
    await this.feature(0x88);
    const result = await this.device.receiveFeatureReport(0);
    const data = new Uint8Array(
      result.buffer,
      result.byteOffset,
      result.byteLength,
    );
    const raw = data.length === 65 && data[0] === 0 ? data.slice(1) : data;
    if (raw.length !== 64 || raw[0] !== 0x88)
      throw Error("Unexpected AW768 status response.");
    return integer(raw[2], 1, 3, "Active profile");
  }
  async load() {
    const profile = await this.profile();
    const frames = new Promise((resolve, reject) => {
      this.capture = {
        frames: [],
        resolve,
        reject,
        timer: setTimeout(() => {
          this.capture = null;
          reject(
            Error("AW768 readback timed out. Reconnect the lighting PCB."),
          );
        }, 3000),
      };
    });
    frames.catch(() => {});
    try {
      await this.feature(0x85, profile);
      return parseSnapshot(profile, await frames);
    } catch (e) {
      if (this.capture) {
        clearTimeout(this.capture.timer);
        this.capture = null;
      }
      throw e;
    }
  }
  async apply(changes, macro) {
    const before = await this.load(),
      packets = changes.size ? lightingBatch(before, changes) : [];
    if ((await this.profile()) !== before.profile)
      throw Error("Native lighting profile changed; reload first.");
    for (const packet of packets) {
      await this.feature(5, before.profile);
      await delay(10);
      await this.device.sendReport(0, packet);
      await delay(10);
    }
    if (macro) {
      await delay(10);
      await this.device.sendFeatureReport(
        0,
        macroPacket(before.profile, macro),
      );
      await delay(30);
    }
    await delay(100);
    const after = await this.load();
    if (after.profile !== before.profile)
      throw Error("Active native profile changed during save.");
    for (const [mask, setting] of changes) {
      const record = after.records
        .slice(14, 22)
        .find((r) => u16(r, 14) === mask);
      if (
        record[2] !== setting.mode ||
        !equal(record.slice(3, 6), setting.color) ||
        (after.legacy ? 3 - record[9] : record[9]) !== setting.tempo ||
        record[10] !== setting.brightness
      )
        throw Error("Lighting readback differs. Reload before trying again.");
    }
    return after;
  }
}
