// Render the dashboard at chosen as-of months to PNG for visual QA.
// node screenshot.mjs 2024-06 2025-03 2025-12   (uses the lab's pinned Playwright)
import { createRequire } from "module";
import { pathToFileURL } from "url";
import path from "path";
const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1"));
const { chromium } = require(path.join(here, "..", "customer-economics-lab", "tools", "node_modules", "playwright"));
const page_url = pathToFileURL(path.join(here, "output", "studio-north-monthly-replay.html")).href;
const months = process.argv.slice(2).length ? process.argv.slice(2) : ["2025-12"];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: process.env.SCHEME || "light" });
const errors = [];
page.on("pageerror", e => errors.push(String(e)));
page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
for (const m of months) {
  await page.goto(`${page_url}?month=${m}`);
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(here, "output", "checks", `screen-${m}${process.env.SCHEME === "dark" ? "-dark" : ""}.png`), fullPage: true });
}
console.log(JSON.stringify({ months, errors }));
await browser.close();
