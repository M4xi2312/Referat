// Erzeugt video/names.png: die Namensschilder auf transparentem Hintergrund (für assemble.py).
import { chromium } from "playwright";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(pathToFileURL(join(here, "animation.html")).href + "?render=1");
await page.evaluate(() => window.ready);
await page.evaluate(() => window.renderNames());
await page.screenshot({ path: join(here, "names.png"), omitBackground: true });
await browser.close();
console.log("names.png geschrieben");
