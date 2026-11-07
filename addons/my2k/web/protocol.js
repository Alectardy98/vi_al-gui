// SPDX-License-Identifier: GPL-2.0-or-later
import {
  bytes,
  crcRecord,
  crc32,
  delay,
  dword,
  equal,
  integer,
  text,
  u16,
  u32,
  verifyCrc,
  word,
} from "../../../web/src/binary.js";

export function touchRecord(values) {
  const { mode, sensitivity, tap_jitter, left, right, tap } = values;
  integer(mode, 0, 1);
  integer(sensitivity, 1, 100);
  integer(tap_jitter, 0, 100);
  for (const key of [left, right, tap])
    if (
      !Number.isInteger(key) ||
      key < 0 ||
      key > 0x1fff ||
      !(
        key === 0 ||
        ((key & 255) >= 4 && (key & 255) <= 0xc2) ||
        ((key & 255) >= 0xcd && (key & 255) <= 0xe7)
      )
    )
      throw Error(
        "Touch controls require an ordinary keyboard, modifier, media or mouse key.",
      );
  return crcRecord(
    bytes(
      2,
      mode,
      sensitivity,
      tap_jitter,
      word(left, true),
      word(right, true),
      word(tap, true),
      0,
      0,
    ),
  );
}
export function decodeTouch(raw) {
  verifyCrc(raw);
  if (raw.length !== 16 || raw[0] !== 2)
    throw Error("Unsupported touch settings.");
  const values = {
    mode: raw[1],
    sensitivity: raw[2],
    tap_jitter: raw[3],
    left: u16(raw, 4, true),
    right: u16(raw, 6, true),
    tap: u16(raw, 8, true),
  };
  if (!equal(touchRecord(values), raw)) throw Error("Invalid touch settings.");
  return values;
}
export function sleepRecord({ enabled, minutes }) {
  integer(minutes, 5, 120, "Sleep timeout");
  return crcRecord(
    bytes(1, +!!enabled, word(minutes, true), [83, 76, 80, 49], [0, 0, 0, 0]),
  );
}
export function decodeSleep(raw) {
  verifyCrc(raw);
  const values = { enabled: !!raw[1], minutes: u16(raw, 2, true) };
  if (!equal(raw, sleepRecord(values))) throw Error("Invalid sleep settings.");
  return values;
}
const ascii = (value, max, multiline = false) => {
  if (
    typeof value !== "string" ||
    value.length > max ||
    !(multiline ? /^[\x20-\x7e\n]*$/ : /^[\x20-\x7e]*$/).test(value)
  )
    throw Error(
      `Use printable ASCII, up to ${max} characters${multiline ? " (line breaks allowed)" : ""}.`,
    );
  return new TextEncoder().encode(value);
};
export function oledRecord(values) {
  const message = ascii(values.message, 59, true),
    label = ascii(values.label, 10),
    font = ascii(values.font_family, 40);
  integer(values.font_size, 8, 38, "Font size");
  if (values.happy && values.clock)
    throw Error("Choose Happy or Clock, not both.");
  if (values.bitmap !== null && values.bitmap.length !== 360)
    throw Error("OLED bitmap must contain 360 bytes.");
  const raw = new Uint8Array(476);
  raw.set([
    1,
    +!!values.typing |
      (+!!values.happy << 1) |
      (values.bitmap !== null ? 4 : 0) |
      (+!!values.clock << 3),
    message.length,
    label.length,
  ]);
  raw.set(message, 4);
  raw.set(label, 64);
  raw.set([values.font_size, font.length], 74);
  raw.set(font, 76);
  if (values.bitmap !== null) raw.set(values.bitmap, 116);
  return crcRecord(raw);
}
export function decodeOled(raw) {
  verifyCrc(raw);
  if (
    raw.length !== 480 ||
    raw[0] !== 1 ||
    raw[1] & ~15 ||
    raw[2] > 59 ||
    raw[3] > 10 ||
    raw[75] > 40
  )
    throw Error("Invalid OLED configuration.");
  const result = {
    message: text(raw.slice(4, 4 + raw[2])),
    label: text(raw.slice(64, 64 + raw[3])),
    typing: !!(raw[1] & 1),
    happy: !!(raw[1] & 2),
    clock: !!(raw[1] & 8),
    font_family: text(raw.slice(76, 76 + raw[75])),
    font_size: raw[74],
    bitmap: raw[1] & 4 ? raw.slice(116, 476) : null,
  };
  if (!equal(oledRecord(result), raw))
    throw Error("Noncanonical OLED configuration.");
  return result;
}
export function lockRecord(values) {
  const raw = new Uint8Array(124);
  if (values.rules.length > 8 || values.fixed.length !== 5)
    throw Error("Lock Lights supports eight rules and five fixed indicators.");
  const color = (c) => {
    if (c.length !== 3) throw Error("Invalid RGB color.");
    c.forEach((n) => integer(n, 0, 255));
    return c;
  };
  raw.set([2, values.rules.length, +!!values.fallback_enabled]);
  raw.set(color(values.fallback), 4);
  values.rules.forEach((r, i) => {
    integer(r.trigger, 0, 4);
    integer(r.effect, 0, 4);
    integer(r.speed, 0, 15);
    if (r.trigger === 4) integer(r.layer, 1, 3);
    else if (r.layer !== 0)
      throw Error("Only layer triggers have a layer number.");
    raw.set(
      [r.trigger, +!!r.enabled, r.layer, r.effect, r.speed, ...color(r.color)],
      8 + i * 8,
    );
  });
  values.fixed.forEach((r, i) => {
    integer(r.effect, 0, 4);
    integer(r.speed, 0, 15);
    raw.set(
      [+!!r.enabled, r.effect, r.speed, ...color(r.color), 0, 0],
      72 + i * 8,
    );
  });
  return crcRecord(raw);
}
export function decodeLocks(raw) {
  verifyCrc(raw);
  if (raw.length !== 128 || raw[0] !== 2 || raw[1] > 8 || raw[2] > 1)
    throw Error("Unsupported Lock Lights format.");
  const result = {
    rules: [],
    fixed: [],
    fallback_enabled: !!raw[2],
    fallback: [...raw.slice(4, 7)],
  };
  for (let i = 0; i < raw[1]; i++) {
    const p = raw.slice(8 + i * 8, 16 + i * 8);
    result.rules.push({
      trigger: p[0],
      enabled: !!p[1],
      layer: p[2],
      effect: p[3],
      speed: p[4],
      color: [...p.slice(5)],
    });
  }
  for (let i = 0; i < 5; i++) {
    const p = raw.slice(72 + i * 8, 80 + i * 8);
    result.fixed.push({
      enabled: !!p[0],
      effect: p[1],
      speed: p[2],
      color: [...p.slice(3, 6)],
    });
  }
  if (!equal(lockRecord(result), raw))
    throw Error("Noncanonical Lock Lights configuration.");
  return result;
}
export class My2k {
  constructor(keyboard) {
    this.keyboard = keyboard;
    this.token = 0;
  }
  async amk(command, ...payload) {
    const r = await this.keyboard.request(253, command, payload);
    if (r[0] !== 253 || r[1] !== command || r[2] !== 170)
      throw Error(
        `Keyboard rejected AMK command ${command}. No write was retried.`,
      );
    return r;
  }
  async request(channel, version, op, payload = [], token = 0) {
    const r = await this.keyboard.request(
      253,
      channel,
      op,
      version,
      token,
      payload,
    );
    if (
      !equal(r.slice(0, 2), bytes(253, channel)) ||
      !equal(r.slice(3, 6), bytes(version, op, token))
    )
      throw Error("Unsupported firmware or mismatched settings response.");
    if (r[2] !== 170)
      throw Error(
        `Keyboard rejected settings request (${r[6]}). Unlock it, leave storage/game mode, and reload.`,
      );
    return r;
  }
  async touch() {
    const caps = await this.request(235, 2, 0);
    if (
      !equal(
        caps.slice(6, 16),
        bytes([84, 67, 72, 50], 16, 3, 1, 100, 50, 1),
      ) ||
      !equal(caps.slice(24, 28), bytes(0, 100, 50, 1))
    )
      throw Error("TCH2 firmware capabilities do not match.");
    const r = await this.request(235, 2, 1);
    return {
      values: decodeTouch(r.slice(8, 24)),
      revision: u32(r, 24, true),
      holdJitter: !!(caps[28] & 1),
    };
  }
  async setTouch(revision, values) {
    const raw = touchRecord(values);
    const token = (this.token = (this.token % 255) + 1);
    const ack = await this.request(
      235,
      2,
      2,
      bytes(dword(revision, true), raw),
      token,
    );
    const actual = await this.touch();
    if (
      actual.revision !== (revision + 1) >>> 0 ||
      !equal(touchRecord(actual.values), raw) ||
      !equal(ack.slice(12, 16), raw.slice(12))
    )
      throw Error("Touch acknowledgement/readback differs.");
    await this.waitSaved(async () => {
      const s = await this.request(235, 2, 3);
      return { pending: !!s[16], error: u32(s, 20, true) };
    });
    return actual;
  }
  async sleep() {
    const caps = await this.request(231, 1, 0);
    if (
      !equal(caps.slice(6, 13), bytes([83, 76, 80, 49], 16, 5, 120)) ||
      caps[15] !== 1
    )
      throw Error("SLP1 firmware capabilities do not match.");
    const r = await this.request(231, 1, 1);
    return { values: decodeSleep(r.slice(8, 24)), revision: u32(r, 24, true) };
  }
  async setSleep(revision, values) {
    const raw = sleepRecord(values),
      token = (this.token = (this.token % 255) + 1);
    const ack = await this.request(
        231,
        1,
        2,
        bytes(dword(revision, true), raw),
        token,
      ),
      actual = await this.sleep();
    if (
      actual.revision !== (revision + 1) >>> 0 ||
      !equal(sleepRecord(actual.values), raw) ||
      u32(ack, 16, true) !== actual.revision
    )
      throw Error("Sleep acknowledgement/readback differs.");
    await this.waitSaved(async () => {
      const r = await this.request(231, 1, 3);
      return { pending: !!r[20], error: u32(r, 24, true) };
    });
    return actual;
  }
  async waitSaved(status) {
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      const r = await status();
      if (r.error)
        throw Error("Settings changed in RAM but flash persistence failed.");
      if (!r.pending) return r;
      await delay(50);
    }
    throw Error(
      "Settings applied, but durable save is not yet confirmed. No update was repeated.",
    );
  }
  async oledRequest(op, payload = []) {
    const r = await this.keyboard.transport.request(
      bytes(253, 232, op, payload),
      { timeout: 6000 },
    );
    if (!equal(r.slice(0, 5), bytes(253, 232, 170, 1, op)))
      throw Error(
        "OLED update rejected: AUX unavailable, storage busy, or incompatible firmware.",
      );
    return r;
  }
  async oled() {
    const caps = await this.oledRequest(0);
    if (
      (caps[6] & 31) !== 31 ||
      !equal(caps.slice(7, 12), bytes(72, 40, 11, 5, 10)) ||
      u16(caps, 12, true) !== 480
    )
      throw Error("Unknown OLED geometry or schema.");
    const raw = new Uint8Array(480);
    for (let at = 0; at < 480; at += 24) {
      const n = Math.min(24, 480 - at),
        r = await this.oledRequest(1, word(at, true));
      if (u16(r, 5, true) !== at || r[7] !== n)
        throw Error("OLED readback offset mismatch.");
      raw.set(r.slice(8, 8 + n), at);
    }
    return {
      values: decodeOled(raw),
      persistent: !!caps[14],
      ready: !!caps[5],
    };
  }
  async oledApplied() {
    const deadline = Date.now() + 12000;
    while (Date.now() < deadline) {
      const r = await this.oledRequest(5);
      if (r[5] === 3)
        throw Error(`AUX rejected OLED update (${r[7]}). No save was retried.`);
      if (r[5] === 2) return r;
      await delay(40);
    }
    throw Error(
      "OLED completion is uncertain; inspect it before another save.",
    );
  }
  async setOled(values) {
    const raw = oledRecord(values);
    await this.oledRequest(2, [1]);
    for (let at = 0; at < 480; at += 24) {
      const part = raw.slice(at, at + 24);
      await this.oledRequest(3, bytes(word(at, true), part.length, part));
    }
    await this.oledRequest(4);
    const status = await this.oledApplied(),
      actual = await this.oled();
    if (
      !equal(status.slice(8, 12), raw.slice(476)) ||
      !equal(oledRecord(actual.values), raw)
    )
      throw Error("OLED acknowledgement/readback differs.");
    if (actual.persistent && (status[12] || !status[13]))
      throw Error("OLED applied, but persistent save has not been confirmed.");
    return actual;
  }
  async syncClock(date = new Date()) {
    await this.oledRequest(
      7,
      bytes(
        word(date.getFullYear(), true),
        date.getMonth() + 1,
        date.getDate(),
        ((date.getDay() + 6) % 7) + 1,
        date.getHours(),
        date.getMinutes(),
        date.getSeconds(),
      ),
    );
    await this.oledApplied();
  }
  async locks() {
    const caps = await this.request(233, 2, 0);
    if (
      !equal(caps.slice(6, 16), bytes([76, 75, 83, 50], 128, 8, 5, 14, 5, 1)) ||
      caps[23] !== 1
    )
      throw Error("LKS2 capabilities do not match.");
    const raw = new Uint8Array(128);
    for (let at = 0; at < 128; at += 24) {
      const n = Math.min(24, 128 - at),
        r = await this.request(233, 2, 1, [at, n]);
      if (r[6] !== at || r[7] !== n) throw Error("Lock Lights chunk mismatch.");
      raw.set(r.slice(8, 8 + n), at);
    }
    return { values: decodeLocks(raw), revision: u32(caps, 16, true) };
  }
  async setLocks(revision, values) {
    const raw = lockRecord(values),
      token = (this.token = (this.token % 255) + 1);
    await this.request(233, 2, 2, dword(revision, true), token);
    for (let at = 0; at < 128; at += 24) {
      const chunk = raw.slice(at, at + 24);
      await this.request(233, 2, 3, bytes(at, chunk.length, chunk), token);
    }
    await this.request(233, 2, 4, [], token);
    const s = await this.request(233, 2, 5),
      actual = await this.locks();
    if (
      u32(s, 10, true) !== (revision + 1) >>> 0 ||
      !equal(s.slice(14, 18), raw.slice(124)) ||
      !equal(lockRecord(actual.values), raw)
    )
      throw Error("Lock Lights readback differs.");
    await this.waitSaved(async () => {
      const r = await this.request(233, 2, 5);
      return { pending: !!r[8], error: !!r[9] || r[7] };
    });
    return actual;
  }
  async gaming(op = 0, game = 0, payload = []) {
    const r = await this.keyboard.request(253, 230, op, 1, game, payload);
    if (
      !equal(r.slice(0, 5), bytes(253, 230, 170, 1, op)) ||
      ([5, 6].includes(op) && r[5] !== game)
    )
      throw Error(
        "Gaming request rejected; exit storage/games, unlock the keyboard and reload.",
      );
    return r;
  }
  async gameKeys(game) {
    const r = await this.gaming(5, game);
    return {
      keys: Array.from({ length: 8 }, (_, i) => u16(r, 8 + i * 2, true)),
      revision: u32(r, 24, true),
    };
  }
  async setGameKeys(game, keys, revision) {
    if (
      keys.length !== 8 ||
      keys.some(
        (k) =>
          !Number.isInteger(k) ||
          !(
            k === 0 ||
            (k >= 4 && k <= 0x73) ||
            (k >= 0x87 && k <= 0xa4) ||
            (k >= 0xe0 && k <= 0xe7)
          ),
      )
    )
      throw Error("Choose eight ordinary keyboard keys, modifiers, or None.");
    const raw = bytes(...keys.map((k) => word(k, true)));
    const ack = await this.gaming(6, game, bytes(dword(revision, true), raw)),
      actual = await this.gameKeys(game);
    if (
      actual.revision !== (revision + 1) >>> 0 ||
      actual.keys.some((k, i) => k !== keys[i]) ||
      u32(ack, 24, true) !== actual.revision
    )
      throw Error("Gaming readback differs.");
    return actual;
  }
  async animation(op = 0, token = 0, payload = []) {
    return this.request(237, 1, op, payload, token);
  }
  async selectAnimation(action = 0, operation = 9) {
    const caps = await this.animation();
    if (
      text(caps.slice(6, 10)) !== "ANI1" ||
      !caps[10] ||
      caps[11] !== 10 ||
      caps[12] !== 1
    )
      throw Error("Animation AUX is not ready or unsupported.");
    const token = (this.token = (this.token % 255) + 1);
    await this.animation(1, token, [operation, action, 0]);
    const deadline = Date.now() + 8000;
    while (Date.now() < deadline) {
      const r = await this.animation(2, token);
      if (r[6] === 3) throw Error(`AUX animation command failed (${r[7]}).`);
      if (r[6] === 2) {
        const v = r.slice(8, 16);
        if (v[0] !== operation || v[2] !== action)
          throw Error("Animation acknowledgement differs.");
        return v;
      }
      if (r[6] !== 1) throw Error("Invalid animation command state.");
      await delay(30);
    }
    throw Error("Animation command timed out; it was not repeated.");
  }
}
