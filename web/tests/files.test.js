import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bytes, crc32, dword, hex, u16, u32, word } from "../src/binary.js";
import { UsbFiles, parseCrs, encodeRle } from "../../addons/my2k/web/files.js";
const f = JSON.parse(
  readFileSync(new URL("./fixtures/protocols.json", import.meta.url)),
);
const unhex = (s) => Uint8Array.from(Buffer.from(s, "hex"));
function crs() {
  const raw = new Uint8Array(32790);
  raw.set(
    bytes(
      [65, 78, 73, 77],
      word(20, true),
      word(22, true),
      dword(raw.length, true),
      word(128, true),
      word(128, true),
      word(2, true),
      word(1, true),
      word(50, true),
    ),
  );
  return raw;
}
test("RLE matches desktop output and preserves opaque RGB565 words", () => {
  for (const row of f.rle)
    assert.equal(hex(encodeRle(unhex(row.raw))), row.encoded);
});
test("CRS validation rejects bad headers, dimensions, frame counts and sizes", () => {
  assert.equal(parseCrs(crs()).frames, 1);
  for (const index of [0, 4, 6, 8, 12, 14, 16, 18]) {
    const bad = crs();
    bad[index] ^= 1;
    assert.throws(() => parseCrs(bad));
  }
  assert.throws(() => parseCrs(crs().slice(0, -1)));
});
class UsbPeer {
  vendorId = 0x4d58;
  productId = 0xf103;
  opened = false;
  store = null;
  input = null;
  outputs = [];
  stall = false;
  configuration = {
    interfaces: [
      {
        interfaceNumber: 4,
        alternate: { alternateSetting: 0 },
        alternates: [
          {
            alternateSetting: 0,
            interfaceClass: 255,
            interfaceSubclass: 0xaf,
            interfaceProtocol: 3,
            endpoints: [
              {
                endpointNumber: 5,
                direction: "out",
                type: "bulk",
                packetSize: 512,
              },
              {
                endpointNumber: 5,
                direction: "in",
                type: "bulk",
                packetSize: 512,
              },
            ],
          },
        ],
      },
    ],
  };
  async open() {
    this.opened = true;
  }
  async close() {
    this.opened = false;
  }
  async claimInterface(number) {
    assert.equal(number, 4);
  }
  async releaseInterface(number) {
    assert.equal(number, 4);
  }
  async controlTransferIn(setup) {
    assert.equal(setup.requestType, "vendor");
    assert.equal(setup.recipient, "device");
    const raw = setup.request === 0x62 ? bytes(65, 70, 66, 0) : this.input;
    return {
      status: "ok",
      data: new DataView(raw.buffer, raw.byteOffset, raw.byteLength),
    };
  }
  process(raw) {
    const op = raw[2],
      token = raw[4],
      slot = raw[5],
      offset = u32(raw, 8, true);
    let data = new Uint8Array();
    const header = new Uint8Array(32);
    header.set([253, 238, 170, 2, op, token, 2]);
    if (op === 0) {
      header.set([65, 70, 66, 55], 12);
      header[16] = 10;
      header.set(word(4096, true), 20);
      header[22] = 0xe0;
      header[23] = 1;
    }
    if (op === 1) {
      if (!this.store) header[6] = 6;
      else {
        header[7] = 1;
        header.set(dword(this.store.length, true), 8);
        header.set(dword(crc32(this.store), true), 16);
      }
    }
    if (op === 3) this.store = new Uint8Array(offset);
    if (op === 4) {
      const payload = raw.slice(32);
      let decoded = payload;
      if (raw[7]) {
        const out = [];
        let at = 0;
        while (at < payload.length) {
          const tag = payload[at++],
            n = (tag & 127) + 1;
          if (tag & 128) {
            const pixel = payload.slice(at, at + 2);
            at += 2;
            for (let i = 0; i < n; i++) out.push(...pixel);
          } else {
            out.push(...payload.slice(at, at + n * 2));
            at += n * 2;
          }
        }
        decoded = bytes(out);
        assert.equal(decoded.length, u16(raw, 28, true));
      }
      this.store.set(decoded, offset);
      header.set(dword(offset + decoded.length, true), 8);
    }
    if (op === 5) {
      header.set(dword(this.store.length, true), 8);
      header.set(dword(crc32(this.store), true), 16);
    }
    if (op === 2) {
      data = this.store.slice(offset, offset + u16(raw, 30, true));
      header.set(dword(offset, true), 8);
    }
    if (op === 7) this.store = null;
    header.set(word(data.length, true), 30);
    this.input = bytes(header, data);
  }
  async controlTransferOut(setup, data) {
    assert.equal(setup.request, 0x60);
    this.outputs.push(data.slice());
    this.process(data);
    return { status: this.stall ? "stall" : "ok", bytesWritten: data.length };
  }
  async transferOut(endpoint, data) {
    assert.equal(endpoint, 5);
    if (data.length) {
      this.outputs.push(data.slice());
      this.process(data);
    }
    return { status: this.stall ? "stall" : "ok", bytesWritten: data.length };
  }
  async transferIn(endpoint) {
    assert.equal(endpoint, 5);
    return { status: "ok", data: new DataView(this.input.buffer) };
  }
}
test("AFB7 negotiation, compressed upload, stored CRC, download and clear round trip", async () => {
  const peer = new UsbPeer(),
    files = await new UsbFiles(peer).open(),
    raw = crs();
  await files.upload(raw, 2, false);
  const info = await files.info(2);
  assert.equal(info.size, raw.length);
  assert.equal(info.crc, crc32(raw));
  assert.deepEqual(await files.read(info), raw);
  assert.ok(peer.outputs.some((q) => q[2] === 4 && q[7] === 1));
  await files.request(7, 2);
  assert.equal(await files.info(2), null);
  await files.close();
  assert.equal(peer.opened, false);
});
test("failed USB mutation is never replayed and prevents subsequent commands", async () => {
  const peer = new UsbPeer(),
    files = await new UsbFiles(peer).open();
  peer.stall = true;
  const count = peer.outputs.length;
  await assert.rejects(files.request(7, 1));
  await assert.rejects(files.request(7, 1));
  assert.equal(peer.outputs.length, count + 1);
  await files.close();
});
