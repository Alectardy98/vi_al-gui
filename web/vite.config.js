import { defineConfig } from "vite";
import { readFileSync, existsSync } from "node:fs";

// Keep runtime credits in the static distribution after minification.
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const notices = [
  "Vi_al Web — source: https://github.com/Alectardy98/vi_al-gui/tree/web",
  "kle-serial by Ian Prest (MIT). xz-decompress by Tim Perry and contributors (MIT).",
  read("./node_modules/xz-decompress/dist/package/xz-decompress.js").split(
    "*/",
    1,
  )[0] + "*/",
  read("./node_modules/@ijprest/kle-serial/LICENSE"),
  read("../COPYING"),
];
if (existsSync(new URL("../docs/ec42/COPYING", import.meta.url)))
  notices.push(read("../docs/ec42/COPYING"));

export default defineConfig({
  base: "./",
  server: { fs: { allow: [".."] } },
  build: { target: "es2022", outDir: "dist", emptyOutDir: true },
  plugins: [
    {
      name: "runtime-notices",
      generateBundle() {
        this.emitFile({
          type: "asset",
          fileName: "THIRD_PARTY_NOTICES.txt",
          source: notices.join("\n\n"),
        });
      },
    },
  ],
});
