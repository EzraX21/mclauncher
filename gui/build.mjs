import { build } from "esbuild";
import { cp, mkdir } from "node:fs/promises";

await mkdir("dist", { recursive: true });

await build({
  entryPoints: ["src/renderer.ts"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: "dist/renderer.js",
  logLevel: "info",
});

await build({
  entryPoints: ["src/main.ts"],
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node20",
  external: ["electron"],
  outfile: "dist/main.cjs",
  logLevel: "info",
});

await cp("index.html", "dist/index.html");
await cp("src/styles.css", "dist/styles.css");
console.log("gui built -> dist/");
