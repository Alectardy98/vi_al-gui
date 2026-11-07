import { test } from "node:test";
import assert from "node:assert/strict";
import { RawHidTransport, rawInterface } from "../src/transport.js";

class Device extends EventTarget {
  collections = [
    {
      usagePage: 0xff60,
      usage: 0x61,
      outputReports: [
        { reportId: 7, items: [{ reportSize: 8, reportCount: 32 }] },
      ],
      inputReports: [
        { reportId: 8, items: [{ reportSize: 8, reportCount: 32 }] },
      ],
    },
  ];
  opened = false;
  writes = [];
  reply = true;
  async open() {
    this.opened = true;
  }
  async close() {
    this.opened = false;
  }
  async sendReport(id, data) {
    this.writes.push({ id, data });
    if (this.reply)
      setTimeout(() => {
        const event = new Event("inputreport");
        event.reportId = 8;
        event.data = new DataView(data.slice().buffer);
        this.dispatchEvent(event);
      }, 2);
  }
}
test("raw interface selection excludes keyboard usage pages", () => {
  assert.equal(
    rawInterface({ collections: [{ usagePage: 1, usage: 6 }] }),
    null,
  );
  assert.deepEqual(rawInterface(new Device()), { output: 7, input: 8 });
});
test("requests are serialized and report IDs are separate from payload", async () => {
  const device = new Device(),
    transport = await new RawHidTransport(device).open();
  const replies = await Promise.all([
    transport.request([1]),
    transport.request([2]),
  ]);
  assert.deepEqual(
    replies.map((x) => x[0]),
    [1, 2],
  );
  assert.equal(device.writes[0].id, 7);
  assert.equal(device.writes[0].data.length, 32);
  await transport.close();
});
test("timeout poisons queued requests and never retries a write", async () => {
  const device = new Device();
  device.reply = false;
  const transport = await new RawHidTransport(device, { timeout: 15 }).open();
  const replies = await Promise.allSettled([
    transport.request([5]),
    transport.request([5]),
  ]);
  assert.ok(replies.every((r) => r.status === "rejected"));
  assert.equal(device.writes.length, 1);
  assert.equal(transport.healthy, false);
  await transport.close();
});
test("disconnect rejects pending work without replay", async () => {
  const device = new Device();
  device.reply = false;
  const transport = await new RawHidTransport(device).open();
  const pending = transport.request([1]);
  await new Promise((r) => setTimeout(r, 1));
  await transport.close();
  await assert.rejects(pending);
  assert.equal(device.writes.length, 1);
});
test("a stalled browser send is bounded by the same timeout as a missing reply", async () => {
  const device = new Device();
  device.sendReport = () => new Promise(() => {});
  const transport = await new RawHidTransport(device, { timeout: 15 }).open();
  await assert.rejects(transport.request([5]), /timed out/);
  assert.equal(transport.healthy, false);
  await transport.close();
});
test("a reply cannot disable the deadline for an unfinished browser send", async () => {
  const device = new Device(),
    send = device.sendReport.bind(device);
  device.sendReport = (id, data) => {
    send(id, data);
    return new Promise(() => {});
  };
  const transport = await new RawHidTransport(device, { timeout: 15 }).open();
  await assert.rejects(transport.request([5]), /timed out/);
  assert.equal(transport.healthy, false);
  await transport.close();
});
