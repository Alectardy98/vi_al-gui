// Simulated protocol peer, not a substitute for physical WebHID acceptance.
import { readFileSync } from "node:fs";
export const fixture = JSON.parse(
  readFileSync(new URL("../fixtures/protocols.json", import.meta.url)),
);
const aw = JSON.parse(
  readFileSync(
    new URL(
      "../../../tests/alienware_aw768/fixtures/legacy-lighting.json",
      import.meta.url,
    ),
  ),
);
const prox = JSON.parse(
  readFileSync(new URL("../fixtures/pro-x-definition.json", import.meta.url)),
);
export async function mockKeyboard(page, kind = "my2k") {
  await page.addInitScript(
    ({ f, kind, aw, prox }) => {
      const unhex = (s) =>
        Uint8Array.from(s.match(/../g).map((x) => parseInt(x, 16)));
      const set16 = (a, i, v, le = false) => {
        a[i] = le ? v & 255 : v >>> 8;
        a[i + 1] = le ? v >>> 8 : v & 255;
      };
      const get16 = (a, i = 0, le = false) =>
        le ? a[i] | (a[i + 1] << 8) : (a[i] << 8) | a[i + 1];
      const set32 = (a, i, v, le = false) => {
        const d = new DataView(a.buffer);
        d.setUint32(i, v, le);
      };
      const crc32 = (a) => {
        let c = 0xffffffff;
        for (const v of a) {
          c ^= v;
          for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
        }
        return (c ^ 0xffffffff) >>> 0;
      };
      const ascii = (value) => new TextEncoder().encode(value);
      const fields = {
        touch: unhex(f.touch.raw),
        sleep: unhex(f.sleep.raw),
        locks: unhex(f.locks.raw),
        oled: unhex(f.oled.raw),
      };
      const revisions = { touch: 1, sleep: 1, locks: 1, game: 1, ec: 1 };
      const compressed = Uint8Array.from(
        atob(
          kind === "prox"
            ? prox.compressed
            : kind === "ec"
              ? f.ecCompressed
              : kind === "aw"
                ? f.awCompressed
                : kind === "core"
                  ? f.coreCompressed
                  : f.compressed,
        ),
        (c) => c.charCodeAt(0),
      );
      const rows = kind === "prox" ? 5 : kind === "ec" ? 6 : 3,
        cols = kind === "prox" ? 15 : kind === "ec" ? 16 : 5;
      const keymap = new Uint8Array(4 * rows * cols * 2);
      const macroBuffer = new Uint8Array(256);
      macroBuffer.set([...ascii("Hello"), 0, 1, 1, 4, 0]);
      const dynamic = new Map([
        [1, [4, 0, 0, 0, 200]],
        [3, [4, 5, 0, 0, 6]],
        [5, [4, 5, 65535, 0, 0, 0, 128]],
        [7, [4, 5, 0, 0]],
      ]);
      window.__qmkValues = { 7: 200, 21: 32768 };
      for (let i = 0; i < keymap.length; i += 2)
        set16(keymap, i, i === 0 ? 41 : 4 + ((i / 2) % 26));
      const gameKeys = [82, 81, 80, 79, 29, 27, 40, 44];
      let ani = [9, 0, 0],
        active = 1;
      let ecRecord = unhex(f.ec.record),
        press = 550,
        release = 500,
        overrides = Array(96).fill(0),
        rt = [0, 70, 70],
        ecState = 0,
        snapshot = 1;
      const resealEc = () => {
        set16(ecRecord, 1, press);
        set16(ecRecord, 3, release);
        ecRecord.set(overrides, 209);
        ecRecord.fill(0, 205, 209);
        const native = ecRecord.slice();
        for (const i of [
          1,
          3,
          5,
          ...Array.from({ length: 100 }, (_, i) => 9 + i * 2),
        ])
          [native[i], native[i + 1]] = [native[i + 1], native[i]];
        const crc = crc32(native);
        set16(ecRecord, 205, crc & 65535);
        set16(ecRecord, 207, crc >>> 16);
      };
      window.__hidWrites = [];
      window.__hidReplies = [];
      window.__ecPress = false;
      class Device extends EventTarget {
        vendorId = 0x4d58;
        productId = 0xf103;
        productName = "Simulated browser keyboard";
        opened = false;
        collections = [
          {
            usagePage: 0xff60,
            usage: 0x61,
            inputReports: [
              { reportId: 0, items: [{ reportSize: 8, reportCount: 32 }] },
            ],
            outputReports: [
              { reportId: 0, items: [{ reportSize: 8, reportCount: 32 }] },
            ],
          },
        ];
        async open() {
          this.opened = true;
        }
        async close() {
          this.opened = false;
        }
        async sendReport(id, input) {
          const q = new Uint8Array(input),
            r = q.slice();
          window.__hidWrites.push([...q]);
          if (q[0] === 1) {
            r[1] = 0;
            r[2] = 9;
          } else if (q[0] === 254) {
            r.fill(0);
            if (q[1] === 0) {
              r[0] = 6;
              r.set(
                unhex(
                  kind === "prox"
                    ? prox.uid
                    : kind === "ec"
                      ? "0ec173239f8f8f2c"
                      : kind === "aw"
                        ? "2945ce03248c2c0c"
                        : "0123456789abcdef",
                ),
                4,
              );
            }
            if (q[1] === 1) set32(r, 0, compressed.length, true);
            if (q[1] === 2) {
              const at = new DataView(q.buffer).getUint32(2, true) * 32;
              r.set(compressed.slice(at, at + 32));
              if (window.__corruptDefinition && at === 0) r[0] ^= 1;
            }
            if (q[1] === 5 || q[1] === 7) {
              r.fill(255);
              r[0] = 1;
              r[1] = 0;
            }
            if (kind === "core") {
              if (q[1] === 13) {
                if (q[2] === 0) r.set([1, 1, 1, 1]);
                else {
                  const read = q[2] % 2 ? q[2] : q[2] - 1;
                  const widths =
                    read === 5
                      ? [2, 2, 2, 1, 1, 1, 1]
                      : read === 7
                        ? [2, 2, 1, 1]
                        : [2, 2, 2, 2, 2];
                  if (!(q[2] % 2)) {
                    let offset = 4;
                    dynamic.set(
                      read,
                      widths.map((w) => {
                        const value =
                          w === 2 ? get16(q, offset, true) : q[offset];
                        offset += w;
                        return value;
                      }),
                    );
                  }
                  let offset = 1;
                  dynamic.get(read).forEach((v, i) => {
                    if (widths[i] === 2) set16(r, offset, v, true);
                    else r[offset] = v;
                    offset += widths[i];
                  });
                }
              }
              if (q[1] === 9) {
                r.fill(255);
                set16(r, 0, 7, true);
                set16(r, 2, 21, true);
              }
              if ([10, 11].includes(q[1])) {
                const id = get16(q, 2, true),
                  width = id === 21 ? 4 : 2;
                if (q[1] === 11)
                  window.__qmkValues[id] =
                    new DataView(q.buffer).getUint32(4, true) &
                    (width === 2 ? 65535 : 0xffffffff);
                if (width === 4) set32(r, 1, window.__qmkValues[id], true);
                else set16(r, 1, window.__qmkValues[id], true);
              }
            }
          } else if (q[0] === 12 && kind === "core") r[1] = 2;
          else if (q[0] === 13 && kind === "core") set16(r, 1, 256);
          else if (q[0] === 14 && kind === "core")
            r.set(macroBuffer.slice(get16(q, 1), get16(q, 1) + q[3]), 4);
          else if (q[0] === 15 && kind === "core")
            macroBuffer.set(q.slice(4, 4 + q[3]), get16(q, 1));
          else if (q[0] === 17) r[1] = 4;
          else if (q[0] === 18) {
            const offset = get16(q, 1);
            r.set(keymap.slice(offset, offset + q[3]), 4);
          } else if (q[0] === 5)
            keymap.set(q.slice(4, 6), ((q[1] * rows + q[2]) * cols + q[3]) * 2);
          else if (q[0] === 4)
            r.set(
              keymap.slice(
                ((q[1] * rows + q[2]) * cols + q[3]) * 2,
                ((q[1] * rows + q[2]) * cols + q[3]) * 2 + 2,
              ),
              4,
            );
          else if (q[0] === 2) {
            r.fill(0);
            r.set(q.slice(0, 2));
          } else if (q[0] === 253) {
            const channel = q[1],
              op = q[2];
            r.fill(0);
            r.set([253, channel, 170]);
            if ([235, 231, 233].includes(channel)) {
              r.set([q[3], op, q[4]], 3);
              const name = { 235: "touch", 231: "sleep", 233: "locks" }[
                channel
              ];
              if (op === 0) {
                if (channel === 235) {
                  r.set([...ascii("TCH2"), 16, 3, 1, 100, 50, 1], 6);
                  r.set([0, 100, 50, 1, 1], 24);
                }
                if (channel === 231)
                  r.set([...ascii("SLP1"), 16, 5, 120, 1, 0, 1], 6);
                if (channel === 233) {
                  r.set([...ascii("LKS2"), 128, 8, 5, 14, 5, 1], 6);
                  r[23] = 1;
                }
                set32(r, 16, revisions[name], true);
              } else if (channel === 233) {
                if (op === 1) {
                  r.set(q.slice(5, 7), 6);
                  r.set(fields.locks.slice(q[5], q[5] + q[6]), 8);
                }
                if (op === 3) fields.locks.set(q.slice(7, 7 + q[6]), q[5]);
                if (op === 4) revisions.locks++;
                if (op === 5) {
                  set32(r, 10, revisions.locks, true);
                  r.set(fields.locks.slice(124), 14);
                }
              } else {
                if (op === 1) {
                  r.set(fields[name], 8);
                  set32(r, 24, revisions[name], true);
                }
                if (op === 2) {
                  fields[name] = q.slice(9, 25);
                  revisions[name]++;
                  r.set(fields[name].slice(12), 12);
                  set32(r, 16, revisions[name], true);
                }
              }
            } else if (channel === 232) {
              r.set([1, op], 3);
              if (op === 0) {
                r.set([1, 31, 72, 40, 11, 5, 10], 5);
                set16(r, 12, 480, true);
                r[14] = 1;
              }
              if (op === 1) {
                const at = get16(q, 3, true),
                  n = Math.min(24, 480 - at);
                set16(r, 5, at, true);
                r[7] = n;
                r.set(fields.oled.slice(at, at + n), 8);
              }
              if (op === 3)
                fields.oled.set(q.slice(6, 6 + q[5]), get16(q, 3, true));
              if (op === 5) {
                r[5] = 2;
                r[13] = 1;
                r.set(fields.oled.slice(476), 8);
              }
            } else if (channel === 230) {
              r.set([1, op, q[4]], 3);
              if (op === 0) {
                r.set(ascii("GME1"), 8);
                r[28] = 28;
              }
              if (op === 6) {
                for (let i = 0; i < 8; i++)
                  gameKeys[i] = get16(q, 9 + i * 2, true);
                revisions.game++;
              }
              if ([5, 6].includes(op)) {
                gameKeys.forEach((key, i) => set16(r, 8 + i * 2, key, true));
                set32(r, 24, revisions.game, true);
              }
            } else if (channel === 237) {
              r.set([1, op, q[4]], 3);
              if (op === 0) {
                r.set(ascii("ANI1"), 6);
                r.set([1, 10, 1, 4], 10);
              }
              if (op === 1) {
                ani = [...q.slice(5, 8)];
                if (ani[0] === 9 && ani[1]) active = ani[1];
              }
              if (op === 2) {
                r[6] = 2;
                r.set([ani[0], 0, ani[1], 0, active, 3, 0, 0], 8);
              }
            } else if (channel === 75) {
              r.set([1, 0, 0, 2, 1], 3);
              set16(r, 8, 1000, true);
              set16(r, 10, 125, true);
            } else if (channel === 13) r[3] = 1;
            else if ([28, 66].includes(channel)) {
              r[3] = q[2];
              r[6] = 1;
            } else if (channel === 61) {
              r[4] = q[3] === 4 ? 200 : q[3] === 2 ? 100 : 128;
              r[5] = 64;
              r[6] = 200;
            }
          } else if (q[0] === 0xca) {
            const op = q[6],
              sequence = get16(q, 7),
              payload = q.slice(12, 12 + q[10]);
            let data = new Uint8Array();
            if (op === 0x10) {
              data = new Uint8Array(16);
              data.set([...ascii("QEC2"), 9]);
              set16(data, 5, 6);
              set16(data, 7, 16);
              set16(data, 9, 1023);
              data[11] = 1;
              set16(data, 12, 0xc6);
              data.set([5, 1], 14);
            }
            if (op === 0x2b) {
              data = new Uint8Array(20);
              set16(data, 0, 0xa996);
              set16(data, 2, 305);
              set16(data, 4, 1023);
              set32(data, 8, 65536);
              set32(data, 12, 131072);
              set16(data, 16, 1024);
              data.set([1, 1], 18);
            }
            if (op === 0x1c) data = ascii("EC42-test-v2.9");
            if (op === 0x14) data = Uint8Array.from([ecState, 0, 42, 0, 1, 0]);
            if ([0x1d, 0x16, 0x23].includes(op)) {
              const at = get16(payload, op === 0x23 ? 2 : 0),
                count = payload[op === 0x23 ? 4 : 2];
              data = new Uint8Array(3 + count);
              set16(data, 0, at);
              data[2] = count;
              data.set(ecRecord.slice(at, at + count), 3);
            }
            if ([0x29, 0x2c].includes(op)) {
              const index = get16(payload),
                percent = payload[2];
              if (op === 0x2c) {
                press =
                  percent === 99
                    ? 1022
                    : Math.floor((percent * 1023 + 50) / 100);
                release = Math.max(1, press - 50);
                overrides.fill(0);
              } else overrides[index] = percent;
              revisions.ec++;
              resealEc();
              data = new Uint8Array(2);
              set16(data, 0, revisions.ec);
            }
            if (op === 0x2a) {
              rt = [...payload.slice(0, 3)];
              revisions.ec++;
              data = new Uint8Array(2);
              set16(data, 0, revisions.ec);
            }
            if (op === 0x28) {
              const index = get16(payload);
              data = new Uint8Array(20);
              set16(data, 0, revisions.ec);
              set16(data, 6, press);
              set16(data, 8, release);
              data.set(rt, 10);
              data[13] = overrides[index] || 0;
              set16(data, 18, index);
            }
            if (op === 0x11) {
              data = new Uint8Array(8);
              set16(data, 0, snapshot++);
              set16(data, 6, 96);
            }
            if (op === 0x12) {
              const at = get16(payload, 2),
                count = payload[4];
              data = new Uint8Array(5 + count * 3);
              data.set(payload);
              for (let i = 0; i < count; i++) {
                set16(
                  data,
                  5 + i * 3,
                  window.__ecPress && at + i === 0 ? 700 : 40,
                );
                data[7 + i * 3] =
                  137 | (window.__ecPress && at + i === 0 ? 6 : 0);
              }
            }
            if (op === 0x13) {
              data = new Uint8Array(20);
              data.set(payload);
              [0, 900, press, release, 0, 1023, 900, 0].forEach((v, i) =>
                set16(data, 4 + i * 2, v),
              );
            }
            r.fill(0);
            r.set([0xca, 69, 67, 52, 50, 2, op]);
            set16(r, 7, sequence);
            r[10] = data.length;
            r[11] = 1;
            r.set(data, 12);
          }
          window.__hidReplies.push([...r]);
          setTimeout(() => {
            if (!this.opened) return;
            const event = new Event("inputreport");
            event.reportId = 0;
            event.data = new DataView(r.buffer);
            this.dispatchEvent(event);
          }, 0);
        }
      }
      const hid = new EventTarget();
      const device = new Device();
      class Lighting extends EventTarget {
        vendorId = 0x04f2;
        productId = 0x1666;
        opened = false;
        collections = [{ usagePage: 0xff00, usage: 1 }];
        records = aw.frames.map(unhex);
        async open() {
          this.opened = true;
        }
        async close() {
          this.opened = false;
        }
        async sendFeatureReport(id, q) {
          window.__awWrites.push(["feature", [...q]]);
          if (q[0] === 0x85)
            for (const raw of this.records)
              setTimeout(() => {
                const event = new Event("inputreport");
                event.reportId = 0;
                event.data = new DataView(raw.slice().buffer);
                this.dispatchEvent(event);
              }, 0);
        }
        async receiveFeatureReport() {
          const r = new Uint8Array(64);
          r.set([0x88, 0, 1]);
          return new DataView(r.buffer);
        }
        async sendReport(id, q) {
          window.__awWrites.push(["output", [...q]]);
          if (q[12] === 1) {
            const mask = get16(q, 14),
              index = this.records.findIndex(
                (r, i) => i >= 14 && i < 22 && get16(r, 14) === mask,
              );
            if (index >= 0) {
              const raw = q.slice();
              raw[0] = 0x85;
              raw[9] = 3 - raw[9];
              raw[12] = raw[13] = 0;
              this.records[index] = raw;
            }
          }
        }
      }
      window.__awWrites = [];
      const lighting = new Lighting();
      hid.getDevices = async () => [device];
      hid.requestDevice = async (options) =>
        options.filters.some((f) => f.vendorId === 0x04f2)
          ? [lighting]
          : [device];
      Object.defineProperty(navigator, "hid", {
        value: hid,
        configurable: true,
      });
    },
    { f: fixture, kind, aw, prox },
  );
}
