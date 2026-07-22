import { copyFile, mkdir } from "node:fs/promises";

await mkdir("dist/src", { recursive: true });
await Promise.all([
  copyFile("index.html", "dist/index.html"),
  copyFile("src/main.js", "dist/src/main.js"),
  copyFile("src/sensor-data.mjs", "dist/src/sensor-data.mjs"),
  copyFile("src/styles.css", "dist/src/styles.css")
]);
console.log("Static dashboard built in frontend/dist");
