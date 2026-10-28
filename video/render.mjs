// Rendert animation.html Bild für Bild zu einem MP4.
// Aufruf:  node video/render.mjs [--out datei.mp4] [--fps 30] [--workers 4] [--hud 0] [--sub 0] [--from s] [--to s]
// Braucht: Playwright (npm i playwright) und ffmpeg mit libx264.
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith("--") ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(args.out || join(here, "entwurf.mp4"));
const fps = +(args.fps || 30), workers = +(args.workers || 4);
const query = new URLSearchParams({ render: "1" });
if (args.hud === "0") query.set("hud", "0");
if (args.sub === "0") query.set("sub", "0");
const url = pathToFileURL(join(here, "animation.html")).href + "?" + query;
const browserOpts = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};

const run = (cmd, argv, opts) => new Promise((ok, fail) => {
  const p = spawn(cmd, argv, { stdio: ["pipe", "inherit", "inherit"], ...opts });
  p.on("exit", c => (c === 0 ? ok() : fail(new Error(cmd + " exit " + c))));
  return p;
});

const browser = await chromium.launch(browserOpts);
const probe = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await probe.goto(url);
const duration = await probe.evaluate(() => window.ready);
await probe.close();
const from = +(args.from || 0), to = Math.min(+(args.to || duration), duration);
const first = Math.round(from * fps), total = Math.round(to * fps) - first;
const tmp = mkdtempSync(join(tmpdir(), "render-"));
const per = Math.ceil(total / workers);
let done = 0;
const started = Date.now();

async function part(k) {
  const a = first + k * per, b = Math.min(first + total, a + per);
  const file = join(tmp, `part${k}.mp4`);
  if (a >= b) return null;
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.on("pageerror", e => console.error("Seitenfehler:", e.message));
  await page.goto(url);
  await page.evaluate(() => window.ready);
  const ff = spawn("ffmpeg", ["-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", String(fps), file], { stdio: ["pipe", "inherit", "inherit"] });
  const finished = new Promise((ok, fail) => ff.on("exit", c => (c === 0 ? ok() : fail(new Error("ffmpeg exit " + c)))));
  for (let f = a; f < b; f++) {
    await page.evaluate(t => renderAt(t), f / fps);
    const buf = await page.screenshot({ type: "jpeg", quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (++done % 300 === 0) console.log(`${done}/${total} Bilder · ${((Date.now() - started) / 1000).toFixed(0)} s`);
  }
  ff.stdin.end();
  await finished;
  await page.close();
  return file;
}

const parts = (await Promise.all(Array.from({ length: workers }, (_, k) => part(k)))).filter(Boolean);
await browser.close();
const list = join(tmp, "list.txt");
writeFileSync(list, parts.map(p => `file '${p}'`).join("\n"));
// Stille Tonspur, damit jeder Player und jedes Schnittprogramm die Datei problemlos öffnet
await run("ffmpeg", ["-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
  "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", out]);
rmSync(tmp, { recursive: true, force: true });
console.log(`Fertig: ${out} (${(to - from).toFixed(1)} s, ${((Date.now() - started) / 1000).toFixed(0)} s Renderzeit)`);
