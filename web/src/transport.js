// SPDX-License-Identifier: GPL-2.0-or-later
const reportBytes = (report) =>
  report.items.reduce((total, i) => total + i.reportSize * i.reportCount, 0) /
  8;
export function rawInterface(device) {
  for (const c of device.collections ?? []) {
    if (c.usagePage !== 0xff60 || c.usage !== 0x61) continue;
    const output = c.outputReports?.find((r) => reportBytes(r) === 32);
    const input = c.inputReports?.find((r) => reportBytes(r) === 32);
    if (output && input)
      return { output: output.reportId, input: input.reportId };
  }
  return null;
}

export class RawHidTransport {
  constructor(device, { timeout = 1500 } = {}) {
    this.device = device;
    this.timeout = timeout;
    this.queue = Promise.resolve();
    this.generation = 0;
    this.pending = null;
    this.healthy = false;
    this.reports = rawInterface(device);
    if (!this.reports)
      throw Error(
        "Select the Vial configuration interface (vendor usage FF60/61, 32-byte reports).",
      );
    this.onInput = (event) => {
      if (event.reportId !== this.reports.input || !this.pending) return;
      const data = new Uint8Array(
        event.data.buffer,
        event.data.byteOffset,
        event.data.byteLength,
      ).slice();
      if (data.length !== 32) {
        this.fail(Error("Short HID response; reconnect before continuing."));
        return;
      }
      const pending = this.pending;
      this.pending = null;
      pending.resolve(data);
    };
  }
  async open() {
    if (!this.device.opened) await this.device.open();
    this.device.addEventListener("inputreport", this.onInput);
    this.healthy = true;
    return this;
  }
  fail(error) {
    this.healthy = false;
    this.generation++;
    if (this.pending) {
      clearTimeout(this.pending.timer);
      this.pending.reject(error);
      this.pending = null;
    }
  }
  async close() {
    this.fail(Error("Keyboard disconnected."));
    this.device.removeEventListener("inputreport", this.onInput);
    if (this.device.opened) await this.device.close();
  }
  batch(work) {
    const generation = this.generation;
    const next = this.queue.then(async () => {
      if (!this.healthy || generation !== this.generation)
        throw Error("Connection needs reconnecting. No commands were retried.");
      return work((data, options) => this.roundTrip(data, options));
    });
    this.queue = next.catch(() => {});
    return next;
  }
  request(data, options) {
    return this.batch((send) => send(data, options));
  }
  async roundTrip(data, { timeout = this.timeout } = {}) {
    if (!this.healthy) throw Error("Reconnect before continuing.");
    if (data.length > 32) throw Error("Raw HID packet exceeds 32 bytes.");
    const packet = new Uint8Array(32);
    packet.set(data);
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(
        () =>
          reject(
            Error(
              "Keyboard response timed out. Close other keyboard apps and reconnect.",
            ),
          ),
        timeout,
      );
    });
    const response = new Promise((resolve, reject) => {
      this.pending = { resolve, reject, timer };
    });
    response.catch(() => {});
    try {
      const [, reply] = await Promise.race([
        Promise.all([
          this.device.sendReport(this.reports.output, packet),
          response,
        ]),
        deadline,
      ]);
      return reply;
    } catch (error) {
      this.fail(error);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
}
