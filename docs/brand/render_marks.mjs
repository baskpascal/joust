import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

process.chdir(dirname(fileURLToPath(import.meta.url)));

// Any Chromium works; point CHROME at one if the default guess is wrong.
const CHROME = process.env.CHROME
  || process.env.HOME + "/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome";
const jobs = [
  ["shot-hero.html", "joust-hero.png", 1280, 384],
  ["shot-card.html", "joust-card.png", 1200, 600],
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
  "--remote-debugging-port=9333", "--remote-allow-origins=*", "about:blank",
], { stdio: "ignore" });
await sleep(2500);

for (const [page, out, width, height] of jobs) {
  const target = await (await fetch(
    `http://127.0.0.1:9333/json/new?file://${resolve(page)}`, { method: "PUT" })).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0;
  const pending = new Map();
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) pending.get(m.id)(m.result);
  };
  const send = (method, params = {}) =>
    new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

  await send("Page.enable");
  // The clip is what makes the output exact: window geometry never enters into it.
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  await sleep(2200);
  const shot = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true,
    clip: { x: 0, y: 0, width, height, scale: 1 },
  });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log(`${out} ${width}x${height}`);
  ws.close();
  await fetch(`http://127.0.0.1:9333/json/close/${target.id}`);
}
chrome.kill();
