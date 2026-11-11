import { readFileSync } from "node:fs";
import { mockKeyboard } from "./mock-hid.js";
import { createLeydenPeer } from "../helpers/leyden-peer.js";
const fixtures = JSON.parse(
  readFileSync(new URL("../fixtures/leyden-jar.json", import.meta.url)),
);
export async function mockLeyden(
  page,
  kind = "fat",
  legacy = false,
  options = {},
) {
  await page.addInitScript({
    content: `window.createLeydenPeer = ${createLeydenPeer.toString()};`,
  });
  await page.addInitScript(
    ({ fixture, kind, legacy, options }) => {
      window.__leydenFixture = fixture;
      window.__leydenPeer = window.createLeydenPeer({
        ...fixture,
        beamspring: kind === "beamal" || kind === "expanded",
        direct: kind === "direct",
        expanded: kind === "expanded",
        reverseCols: kind === "beamal",
        reverseRows: kind === "fat",
        bins: kind === "beamal" ? 1 : 2,
        legacy,
        ...options,
      });
    },
    { fixture: fixtures[kind], kind, legacy, options },
  );
  await mockKeyboard(page, "leyden");
}
