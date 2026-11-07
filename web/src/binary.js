// SPDX-License-Identifier: GPL-2.0-or-later
export function bytes(...parts) {
  const result = [];
  const append = (part) => {
    if (typeof part === "number") {
      integer(part, 0, 255, "Packet byte");
      result.push(part);
    } else if (Array.isArray(part) || ArrayBuffer.isView(part)) {
      for (const value of part) append(value);
    } else throw Error("Packet fields must contain bytes.");
  };
  parts.forEach(append);
  return Uint8Array.from(result);
}
export const equal = (a, b) =>
  a.length === b.length && a.every((v, i) => v === b[i]);
export const hex = (a) =>
  [...a].map((n) => n.toString(16).padStart(2, "0")).join("");
export const text = (a) => new TextDecoder().decode(a).replace(/\0+$/, "");
export const u16 = (a, at = 0, little = false) =>
  new DataView(a.buffer, a.byteOffset, a.byteLength).getUint16(at, little);
export const u32 = (a, at = 0, little = false) =>
  new DataView(a.buffer, a.byteOffset, a.byteLength).getUint32(at, little);
export function integer(n, low, high, label = "Value") {
  if (!Number.isInteger(n) || n < low || n > high)
    throw Error(`${label} must be ${low}–${high}.`);
  return n;
}
export const word = (n, little = false) => {
  integer(n, 0, 65535);
  return little ? [n & 255, n >>> 8] : [n >>> 8, n & 255];
};
export const dword = (n, little = false) => {
  integer(n, 0, 0xffffffff);
  const a = [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  return little ? a.reverse() : a;
};
export function crc32(data) {
  let crc = 0xffffffff;
  for (const value of data) {
    crc ^= value;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
export const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export function crcRecord(data) {
  return bytes(data, dword(crc32(data), true));
}
export function verifyCrc(data) {
  if (
    data.length < 4 ||
    u32(data, data.length - 4, true) !== crc32(data.slice(0, -4))
  )
    throw Error("Settings checksum is invalid.");
  return data;
}
