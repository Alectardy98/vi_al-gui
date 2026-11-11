// A deterministic protocol peer. Never opens USB or persists real settings.
export function createLeydenPeer(config = {}) {
  const rows = config.rows ?? 8,
    cols = config.cols ?? 16,
    pr = config.expanded ? 4 : 8,
    pc = config.expanded ? 20 : config.direct ? 16 : 18;
  const version =
    config.version ??
    (config.legacy
      ? [0, 9, 1]
      : config.split
        ? [1, 0, 0]
        : config.expanded
          ? [0, 10, 2]
          : [0, 10, 1]);
  const bins = config.bins ?? 2,
    beam = !!config.beamspring || !!config.expanded;
  const peer = {
    rows,
    cols,
    pr,
    pc,
    version,
    bins,
    beam,
    enabled: true,
    pressed: new Set(),
    directPressed: false,
    calls: [],
    fault: null,
    refs: Array.from({ length: bins }, (_, i) => 410 + i * 10),
    defaults: Array(bins).fill(beam ? -30 : 10),
    saved: Array(bins).fill(false),
  };
  peer.offsets = [...peer.defaults];
  peer.rowMap = Array.from({ length: pr }, (_, i) =>
    config.reverseRows ? pr - 1 - i : i,
  );
  if (config.direct) peer.rowMap.push(255);
  peer.colMap = Array.from({ length: pc }, (_, i) =>
    i < cols ? (config.reverseCols ? cols - 1 - i : i) : 255,
  );
  if (config.direct) peer.colMap[cols - 1] = 255;
  peer.bin = (r, c) =>
    c >= cols ||
    (config.direct && c === cols - 1) ||
    (config.unused ?? []).some((p) => p[0] === r && p[1] === c)
      ? 255
      : (r + c) % bins;
  const get16 = (a, i = 0) => a[i] | (a[i + 1] << 8),
    put16 = (a, i, n) => {
      a[i] = n & 255;
      a[i + 1] = (n >> 8) & 255;
    };
  peer.reply = (q) => {
    peer.calls.push([...q]);
    if (peer.fault === "timeout") throw Error("simulated transport timeout");
    const op = q[0],
      cmd = q[1],
      r = new Uint8Array(32);
    r.set(q.slice(0, 4));
    const a = r.subarray(4),
      payload = q.subarray(4),
      bin = get16(payload);
    if (peer.fault === "reject") {
      r[0] = 255;
      return r;
    }
    if (peer.fault === "header") {
      r[1] ^= 1;
      return r;
    }
    if (cmd === 0x81) {
      a.set(version.slice(0, 2));
      put16(a, 2, version[2]);
    } else if (cmd === 0x82) {
      a.set([rows, cols, pr, pc, +beam, bins]);
      if (config.direct) a.set([1, 8, cols - 1, 27], 6);
      if (config.expanded) {
        a[6] = 2;
        a.set([31, 32, 4, 4, 7], 10);
      }
      if (peer.fault === "details") a[2] = 7;
    } else if (cmd === 0x8e) {
      a[0] = 1;
      a.set(peer.colMap, 1);
      a.set(peer.rowMap.slice(0, pr), 1 + pc);
      if (peer.fault === "mapping") a[2] = a[1];
    } else if (cmd === 0x83) {
      if (op === 3) peer.enabled = !!payload[0];
      a[0] = +peer.enabled;
      if (peer.fault === "enable") a[0] ^= 1;
    } else if (cmd === 0x85) {
      if (op === 3 && peer.fault !== "readback") {
        const target = payload[2];
        peer.offsets[target] = bin - peer.refs[target];
      }
      put16(a, 0, bin);
      put16(a, 2, peer.refs[bin] + peer.offsets[bin]);
      if (peer.fault === "range") put16(a, 2, 1024);
    } else if (cmd === 0x8f) {
      put16(a, 0, bin);
      put16(a, 2, peer.refs[bin]);
    } else if (cmd === 0x90) {
      put16(a, 0, bin);
      for (let row = 0; row < pr; row++) a[2 + row] = peer.bin(row, bin);
      if (peer.fault === "bins") a[2] = bins;
    } else if (cmd === 0x92) a.set([1, 3, 16]);
    else if (cmd === 0x93) {
      if (op === 3) {
        const target = payload[2];
        if (peer.fault !== "readback") {
          peer.offsets[target] = bin >= 32768 ? bin - 65536 : bin;
          peer.saved[target] = true;
        }
        return r;
      }
      put16(a, 0, bin);
      put16(a, 2, peer.offsets[bin]);
      put16(a, 4, peer.defaults[bin]);
      a[6] = +peer.saved[bin];
    } else if (cmd === 0x94) {
      peer.offsets = [...peer.defaults];
      peer.saved.fill(false);
    } else if (cmd === 0x88 || cmd === 0x87 || cmd === 0x84) {
    } else if (cmd === 0x8d) {
      for (let col = 0; col < pc; col++)
        for (let row = 0; row < pr; row++) {
          const held = peer.pressed.has(`${row}:${col}`);
          if (held !== beam) a[col] |= 1 << row;
        }
    } else if (cmd === 0x8c) {
      put16(a, 0, bin);
      if (peer.directPressed) {
        new DataView(a.buffer, a.byteOffset, a.byteLength).setUint32(
          4,
          1 << (cols - 1),
          true,
        );
      }
    } else if (cmd === 0x86) {
      put16(a, 0, bin);
      for (let row = 0; row < pr; row++) {
        const group = peer.bin(row, bin),
          ref = peer.refs[group === 255 ? 0 : group];
        const value = peer.pressed.has(`${row}:${bin}`)
          ? ref + (beam ? -50 : 50)
          : ref;
        put16(a, 2 + row * 2, value);
      }
      if (peer.fault === "levels") put16(a, 2, 1024);
    } else if (cmd === 0x91) a[0] = config.side ?? 1;
    else throw Error(`Unexpected native command ${cmd}`);
    return peer.fault === "short" ? r.slice(0, 31) : r;
  };
  return peer;
}
