// SPDX-License-Identifier: GPL-2.0-or-later
// Match desktop Vial's KLE cluster resets and option-group placement.
import kle from "@ijprest/kle-serial";

export function deserializeLayout(rows) {
  const keys = kle.Serial.deserialize(rows).keys;
  let x = 0,
    y = 0,
    rx = 0,
    ry = 0,
    width = 1,
    index = 0;
  // kle-serial 0.15.1 changes the rotation origin without resetting its cursor.
  // Vial definitions also use rx/ry for unrotated keys (e.g. Zenithal spacebar).
  for (const row of rows) {
    if (!Array.isArray(row)) continue;
    for (const item of row) {
      if (typeof item === "string") {
        Object.assign(keys[index++], { x, y });
        x += width;
        width = 1;
      } else {
        if (Object.hasOwn(item, "rx")) {
          rx = item.rx;
          x = rx;
          y = ry;
        }
        if (Object.hasOwn(item, "ry")) {
          ry = item.ry;
          x = rx;
          y = ry;
        }
        x += item.x ?? 0;
        y += item.y ?? 0;
        width = item.w ?? width;
      }
    }
    y++;
    x = rx;
  }
  return keys;
}

function rectangles(key) {
  return [
    { x: key.x, y: key.y, w: key.width, h: key.height },
    {
      x: key.x + (key.x2 ?? 0),
      y: key.y + (key.y2 ?? 0),
      w: key.width2 ?? key.width,
      h: key.height2 ?? key.height,
    },
  ];
}
export function keyBounds(key) {
  const angle = ((key.rotation_angle ?? 0) * Math.PI) / 180;
  const cos = Math.cos(angle),
    sin = Math.sin(angle);
  const rx = key.rotation_x ?? 0,
    ry = key.rotation_y ?? 0;
  const points = rectangles(key).flatMap((r) =>
    [
      [r.x, r.y],
      [r.x + r.w, r.y],
      [r.x + r.w, r.y + r.h],
      [r.x, r.y + r.h],
    ].map(([x, y]) => ({
      x: rx + (x - rx) * cos - (y - ry) * sin,
      y: ry + (x - rx) * sin + (y - ry) * cos,
    })),
  );
  return {
    left: Math.min(...points.map((p) => p.x)),
    top: Math.min(...points.map((p) => p.y)),
    right: Math.max(...points.map((p) => p.x)),
    bottom: Math.max(...points.map((p) => p.y)),
  };
}

export function placeLayout(keys, choices) {
  const usable = keys.filter(
    (k) => k.row !== null || k.encoder !== null || k.decal,
  );
  const groups = new Map();
  for (const key of usable) {
    if (!key.option) continue;
    const id = key.option.join(":"),
      bounds = keyBounds(key),
      old = groups.get(id);
    groups.set(id, {
      left: Math.min(old?.left ?? Infinity, bounds.left),
      top: Math.min(old?.top ?? Infinity, bounds.top),
    });
  }
  return usable
    .filter(
      (k) => !k.decal && (!k.option || choices[k.option[0]] === k.option[1]),
    )
    .map((key) => {
      if (!key.option) return key;
      const anchor = groups.get(`${key.option[0]}:0`),
        own = groups.get(key.option.join(":"));
      if (!anchor) return key;
      const dx = anchor.left - own.left,
        dy = anchor.top - own.top;
      return {
        ...key,
        x: key.x + dx,
        y: key.y + dy,
        rotation_x: key.rotation_x + dx,
        rotation_y: key.rotation_y + dy,
      };
    });
}

// Outline the union of KLE's two rectangles, retaining ISO/stepped key shapes.
// Coordinates remain local and unrotated; the button rotates about its KLE pivot.
export function keyOutline(key) {
  const rects = rectangles(key);
  const xs = [...new Set(rects.flatMap((r) => [r.x, r.x + r.w]))].sort(
    (a, b) => a - b,
  );
  const ys = [...new Set(rects.flatMap((r) => [r.y, r.y + r.h]))].sort(
    (a, b) => a - b,
  );
  const edges = new Map(),
    point = (p) => p.join(",");
  const add = (a, b) => {
    const reverse = `${point(b)}>${point(a)}`;
    if (edges.has(reverse)) edges.delete(reverse);
    else edges.set(`${point(a)}>${point(b)}`, [a, b]);
  };
  for (let y = 0; y < ys.length - 1; y++)
    for (let x = 0; x < xs.length - 1; x++) {
      const cx = (xs[x] + xs[x + 1]) / 2,
        cy = (ys[y] + ys[y + 1]) / 2;
      if (
        !rects.some(
          (r) => cx > r.x && cx < r.x + r.w && cy > r.y && cy < r.y + r.h,
        )
      )
        continue;
      const a = [xs[x], ys[y]],
        b = [xs[x + 1], ys[y]],
        c = [xs[x + 1], ys[y + 1]],
        d = [xs[x], ys[y + 1]];
      add(a, b);
      add(b, c);
      add(c, d);
      add(d, a);
    }
  const next = new Map([...edges.values()].map(([a, b]) => [point(a), b]));
  const start = edges.values().next().value?.[0],
    polygon = [];
  if (start) {
    let p = start;
    do {
      polygon.push(p);
      p = next.get(point(p));
    } while (p && point(p) !== point(start) && polygon.length <= edges.size);
  }
  // Disconnected rectangles cannot form a single CSS polygon.
  const connected = polygon.length === edges.size;
  return {
    left: xs[0],
    top: ys[0],
    width: xs.at(-1) - xs[0],
    height: ys.at(-1) - ys[0],
    points: polygon,
    connected,
  };
}
