// SPDX-License-Identifier: GPL-2.0-or-later
// AFB1/2/3/5/6/7 framing is shared with animation_fast_transport.py.
import {
  bytes,
  crc32,
  delay,
  dword,
  equal,
  integer,
  text,
  u16,
  u32,
} from "../../../web/src/binary.js";
import cp437 from "../../../web/src/data/cp437.json" with { type: "json" };
export function encodeRle(raw) {
  if (raw.length % 2) return raw;
  const out = [],
    count = raw.length / 2;
  let i = 0;
  const same = (a, b) =>
    raw[a * 2] === raw[b * 2] && raw[a * 2 + 1] === raw[b * 2 + 1];
  while (i < count) {
    let run = 1;
    while (run < 128 && i + run < count && same(i, i + run)) run++;
    if (run >= 3) {
      out.push(128 | (run - 1), raw[i * 2], raw[i * 2 + 1]);
      i += run;
      continue;
    }
    const start = i;
    i += run;
    while (i < count && i - start < 128) {
      run = 1;
      while (run < 3 && i + run < count && same(i, i + run)) run++;
      if (run >= 3) break;
      i += Math.min(run, 128 - (i - start));
    }
    out.push(i - start - 1, ...raw.slice(start * 2, i * 2));
  }
  return bytes(out);
}
export function parseCrs(raw) {
  if (
    raw.length < 20 ||
    text(raw.slice(0, 4)) !== "ANIM" ||
    u16(raw, 4, true) !== 20 ||
    u16(raw, 12, true) !== 128 ||
    u16(raw, 14, true) !== 128 ||
    u16(raw, 16, true) !== 2
  )
    throw Error("Choose a 128×128 RGB565 CRS animation.");
  const frames = u16(raw, 18, true),
    offset = u16(raw, 6, true),
    size = u32(raw, 8, true);
  if (
    !frames ||
    frames > 512 ||
    offset !== 20 + frames * 2 ||
    size !== offset + frames * 32768 ||
    raw.length !== size
  )
    throw Error("Invalid animation size, offsets or frame count.");
  return {
    frames,
    offset,
    size,
    delays: Array.from({ length: frames }, (_, i) =>
      u16(raw, 20 + i * 2, true),
    ),
  };
}
export class UsbFiles {
  constructor(device) {
    if (device.vendorId !== 0x4d58 || device.productId !== 0xf103)
      throw Error("Choose the connected MY-2K in normal keyboard mode.");
    this.device = device;
    this.token = 1;
    this.uncertain = false;
    this.bulk = null;
    this.blockSize = 4064;
    this.readSize = 4064;
    this.combined = false;
    this.framed = false;
  }
  async timed(promise, milliseconds = 20000) {
    let timer;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            this.uncertain = true;
            this.device.close().catch(() => {});
            reject(
              Error(
                "USB transfer timed out. Reconnect before inspecting the result. No write was repeated.",
              ),
            );
          }, milliseconds);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }
  async controlIn(request, length) {
    const r = await this.timed(
      this.device.controlTransferIn(
        {
          requestType: "vendor",
          recipient: "device",
          request,
          value: 0,
          index: 0,
        },
        length,
      ),
    );
    if (r.status !== "ok" || !r.data) throw Error("USB control read failed.");
    return new Uint8Array(
      r.data.buffer,
      r.data.byteOffset,
      r.data.byteLength,
    ).slice();
  }
  async open() {
    await this.device.open();
    const r = await this.request(0);
    if (r[6] !== 2 || r[16] !== 10)
      throw Error("Matching AFB Main/AUX firmware is required.");
    this.romLibrary = !!(r[22] & 32);
    this.gbcLibrary = !!(r[22] & 64);
    const signature = text(r.slice(12, 16)),
      limit = u16(r, 20, true);
    if (
      ["AFB3", "AFB5", "AFB6", "AFB7"].includes(signature) &&
      limit === 4096
    ) {
      const interfaces = this.device.configuration?.interfaces.filter((i) =>
        i.alternates.some(
          (a) =>
            a.interfaceClass === 255 &&
            a.interfaceSubclass === 0xaf &&
            a.interfaceProtocol === 3,
        ),
      );
      if (interfaces?.length !== 1)
        throw Error("Missing dedicated MY-2K animation interface.");
      const intf = interfaces[0],
        alt = intf.alternates.find(
          (a) =>
            a.interfaceClass === 255 &&
            a.interfaceSubclass === 0xaf &&
            a.interfaceProtocol === 3,
        );
      const out = alt.endpoints.filter(
          (e) => e.direction === "out" && e.type === "bulk",
        ),
        input = alt.endpoints.filter(
          (e) => e.direction === "in" && e.type === "bulk",
        );
      if (
        out.length !== 1 ||
        input.length !== 1 ||
        ![64, 512].includes(out[0].packetSize)
      )
        throw Error("Unsupported animation bulk endpoints.");
      await this.device.claimInterface(intf.interfaceNumber);
      if (intf.alternate.alternateSetting !== alt.alternateSetting)
        await this.device.selectAlternateInterface(
          intf.interfaceNumber,
          alt.alternateSetting,
        );
      this.bulk = {
        intf: intf.interfaceNumber,
        out: out[0].endpointNumber,
        input: input[0].endpointNumber,
        packet: out[0].packetSize,
      };
      this.blockSize = 4096;
      this.framed = ["AFB5", "AFB6", "AFB7"].includes(signature);
      this.combined = ["AFB6", "AFB7"].includes(signature);
      this.rle = signature === "AFB7";
      this.prefix = this.rle ? 4096 : 512;
      if (r[22] & 128 && r[23] & 1) this.readSize = 4096;
    } else if (!(
      (signature === "AFB1" && limit === 4064) ||
      (signature === "AFB2" && limit === 4096)
    ))
      throw Error("Unsupported AFB transfer capabilities.");
    return this;
  }
  async close() {
    this.uncertain = true;
    if (this.bulk && this.device.opened)
      await this.device.releaseInterface(this.bulk.intf).catch(() => {});
    if (this.device.opened) await this.device.close();
  }
  async bulkOut(data) {
    const r = await this.timed(this.device.transferOut(this.bulk.out, data));
    if (r.status !== "ok" || r.bytesWritten !== data.length)
      throw Error("Short animation bulk write.");
  }
  async request(
    op,
    slot = 0,
    offset = 0,
    data = new Uint8Array(),
    replace = false,
  ) {
    if (this.uncertain)
      throw Error(
        "Animation transfer is uncertain. Reconnect before another operation.",
      );
    integer(op, 0, 14);
    integer(slot, 0, 10);
    integer(offset, 0, 0xffffffff);
    if (
      ![0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14].includes(op) ||
      data.length > (op === 2 ? this.readSize : this.blockSize)
    )
      throw Error("Unsupported animation request or oversized data.");
    if (op === 3 && data.length !== 4)
      throw Error("Upload Begin requires CRC32.");
    const logical = data.length;
    let codec = false;
    if (op === 4 && this.rle && logical && !(logical % 2)) {
      const encoded = encodeRle(data);
      if (Math.ceil(encoded.length / 512) < Math.ceil(logical / 512)) {
        data = encoded;
        codec = true;
      }
    }
    const token = (this.token = (this.token % 255) + 1),
      header = new Uint8Array(32);
    header.set([253, 238, op, 2, token, slot, +!!replace, 0]);
    header.set(dword(offset, true), 8);
    header.set([data.length & 255, data.length >>> 8], 30);
    if (codec) {
      header[7] = 1;
      header.set([logical & 255, logical >>> 8], 28);
    }
    if (op === 3) header.set(data, 12);
    const q = [4, 12, 14].includes(op) ? bytes(header, data) : header;
    try {
      const framed = this.bulk && this.framed && [2, 4].includes(op);
      if (!framed) {
        const deadline = Date.now() + 3000;
        while (true) {
          const ready = await this.controlIn(0x62, 4);
          if (ready.length !== 4 || text(ready.slice(0, 3)) !== "AFB")
            throw Error("Invalid AFB readiness reply.");
          if (!ready[3]) break;
          if (![5, 6].includes(ready[3]) || Date.now() > deadline)
            throw Error("Another transfer owns the response buffer.");
          await delay(1);
        }
      }
      if (framed && this.combined) {
        await this.bulkOut(q);
        if (q.length < this.prefix && q.length % this.bulk.packet === 0)
          await this.bulkOut(new Uint8Array());
      } else if (framed) {
        await this.bulkOut(q.slice(0, 32));
        if (op === 4) await this.bulkOut(q.slice(32));
      } else if (this.bulk && op === 4) {
        const begin = await this.timed(
          this.device.controlTransferOut(
            {
              requestType: "vendor",
              recipient: "device",
              request: 0x63,
              value: q.length,
              index: 0,
            },
            new Uint8Array(),
          ),
        );
        if (begin.status !== "ok") throw Error("USB bulk prefix rejected.");
        await this.bulkOut(q);
      } else {
        const out = await this.timed(
          this.device.controlTransferOut(
            {
              requestType: "vendor",
              recipient: "device",
              request: 0x60,
              value: 0,
              index: 0,
            },
            q,
          ),
        );
        if (out.status !== "ok" || out.bytesWritten !== q.length)
          throw Error("Short animation control request.");
      }
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {
        let r;
        if (framed || (this.bulk && op === 4)) {
          const incoming = await this.timed(
            this.device.transferIn(
              this.bulk.input,
              32 + (op === 2 ? data.length : 0),
            ),
          );
          if (incoming.status !== "ok" || !incoming.data)
            throw Error("Animation bulk response failed.");
          r = new Uint8Array(
            incoming.data.buffer,
            incoming.data.byteOffset,
            incoming.data.byteLength,
          ).slice();
        } else r = await this.controlIn(0x61, 4096);
        if (
          r.length < 32 ||
          !equal(r.slice(0, 6), bytes(253, 238, 170, 2, op, token)) ||
          u16(r, 30, true) > this.readSize ||
          r.length !== 32 + u16(r, 30, true)
        )
          throw Error("Animation reply identity or length mismatch.");
        if (r[6] === 1) {
          await delay(1);
          continue;
        }
        if (r[6] === 6 && op === 1) return null;
        if (r[6] !== 2)
          throw Error(
            {
              4: "Storage is busy or in maintenance mode.",
              5: "AUX filesystem operation failed.",
              7: "Replacement was not authorized.",
              8: "Animation format or checksum verification failed.",
              9: "Interrupted transaction: inspect storage before retrying.",
              11: "Not enough free storage for a staged upload.",
            }[r[6]] ?? `Animation operation failed (${r[6]}).`,
          );
        return r;
      }
      throw Error("Animation completion timed out.");
    } catch (e) {
      this.uncertain = true;
      throw e;
    }
  }
  async info(slot) {
    const r = await this.request(1, slot);
    if (!r) return null;
    const size = u32(r, 8, true);
    integer(size, 32790, 16778260, "Stored animation size");
    return { slot, size, crc: r[7] & 1 ? u32(r, 16, true) : null };
  }
  async read(info, progress = () => {}, cancelled = () => false) {
    const raw = new Uint8Array(info.size);
    for (let at = 0; at < raw.length;) {
      if (cancelled()) throw Error("Preview download cancelled.");
      const n = Math.min(this.readSize, raw.length - at),
        r = await this.request(2, info.slot, at, new Uint8Array(n));
      if (u32(r, 8, true) !== at || u16(r, 30, true) !== n)
        throw Error("Preview offset or size mismatch.");
      raw.set(r.slice(32), at);
      at += n;
      progress(at / raw.length);
    }
    parseCrs(raw);
    if (info.crc !== null && crc32(raw) !== info.crc)
      throw Error("Stored preview CRC mismatch.");
    return raw;
  }
  async upload(
    raw,
    slot,
    replace,
    progress = () => {},
    cancelled = () => false,
  ) {
    parseCrs(raw);
    integer(slot, 1, 10);
    const checksum = crc32(raw);
    await this.request(
      3,
      slot,
      raw.length,
      bytes(dword(checksum, true)),
      replace,
    );
    let active = true;
    try {
      for (let at = 0; at < raw.length;) {
        if (cancelled())
          throw Error("Upload cancelled; the previous slot was retained.");
        const part = raw.slice(at, at + this.blockSize),
          r = await this.request(4, slot, at, part);
        at += part.length;
        if (u32(r, 8, true) !== at)
          throw Error("Upload acknowledgement offset mismatch.");
        progress(at / raw.length);
      }
      const committed = await this.request(5, slot);
      active = false;
      if (
        u32(committed, 8, true) !== raw.length ||
        u32(committed, 16, true) !== checksum
      )
        throw Error("Stored animation size or verification CRC differs.");
    } finally {
      if (active && !this.uncertain) await this.request(6, slot);
    }
  }
  async catalogue(gbc = false) {
    if (gbc ? !this.gbcLibrary : !this.romLibrary)
      throw Error("This AUX does not advertise the matching ROM catalogue.");
    const rows = [];
    let cursor = 0;
    for (let page = 0; page < 22; page++) {
      const reply = await this.request(gbc ? 13 : 11, 0, cursor),
        raw = reply.slice(32);
      if (
        raw.length < 16 ||
        text(raw.slice(0, 4)) !== (gbc ? "GRL1" : "NRL1") ||
        raw[4] !== 1 ||
        raw[5] !== 24 ||
        raw[6] > 24 ||
        raw.length !== 16 + 112 * raw[6]
      )
        throw Error("Invalid ROM catalogue header or length.");
      for (let i = 0; i < raw[6]; i++) {
        const entry = raw.slice(16 + i * 112, 16 + (i + 1) * 112),
          zero = entry.slice(16).indexOf(0);
        if (zero < 0 || entry[15] > 1)
          throw Error("Invalid ROM catalogue entry.");
        const name = [...entry.slice(16, 16 + zero)]
          .map((byte) => cp437[byte])
          .join("");
        if (rows.some((row) => row.name === name))
          throw Error("ROM catalogue changed while loading.");
        rows.push({
          name,
          size: u32(entry, 0, true),
          mapper: u16(entry, 12, true),
          error: entry[14],
          selected: !!entry[15],
        });
      }
      if (!(raw[7] & 1)) return { rows, truncated: !!(raw[7] & 2) };
      const next = u32(raw, 12, true);
      if (next <= cursor || next >= 512)
        throw Error("Invalid ROM catalogue cursor.");
      cursor = next;
    }
    throw Error("ROM catalogue exceeds the bounded directory limit.");
  }
  async selectRom(name, gbc = false) {
    if (
      typeof name !== "string" ||
      name.length > 95 ||
      /[\\/:\0]/.test(name) ||
      name.includes("..") ||
      !(gbc ? /\.(gb|gbc)$/i : /\.nes$/i).test(name)
    )
      throw Error("Invalid ROM filename.");
    const encoded = [...name].map((char) => cp437.indexOf(char));
    if (encoded.some((byte) => byte < 32))
      throw Error("ROM filename contains unsupported characters.");
    const r = await this.request(gbc ? 14 : 12, 0, 0, bytes(encoded, 0));
    if (r.length !== 40 || text(r.slice(32, 36)) !== (gbc ? "GRS1" : "NRS1"))
      throw Error("ROM selection acknowledgement mismatch.");
    const after = await this.catalogue(gbc);
    if (
      !after.rows.some((row) => row.name === name && row.selected && !row.error)
    )
      throw Error("Saved ROM selection readback differs.");
    return after;
  }
}
