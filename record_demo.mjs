// Record a captioned ~2.5 minute demo of the replay dashboard (WebM, no audio).
// node record_demo.mjs   -> demo/studio-north-replay-demo.webm
// Captions quote numbers read from output/replay_data.json, so they always match the dashboard.
import { createRequire } from "module";
import { pathToFileURL } from "url";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1"));
const { chromium } = require(path.join(here, "..", "customer-economics-lab", "tools", "node_modules", "playwright"));
const data = JSON.parse(fs.readFileSync(path.join(here, "output", "replay_data.json"), "utf8"));
const ans = JSON.parse(fs.readFileSync(path.join(here, "output", "checks", "faq4_answers.json"), "utf8"));
const recon = JSON.parse(fs.readFileSync(path.join(here, "output", "checks", "reconciliation.json"), "utf8"));
const at = m => data.find(d => d.month === m);
const money = v => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(0);
const name = m => new Date(m + "-15").toLocaleString("en-US", { month: "long", year: "numeric" });
const tmp = path.join(here, "output", "video-tmp");
fs.rmSync(tmp, { recursive: true, force: true });
const W = 1280, H = 800;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: tmp, size: { width: W, height: H } }, colorScheme: "light" });
const page = await ctx.newPage();
await page.goto(pathToFileURL(path.join(here, "output", "studio-north-monthly-replay.html")).href + "?month=2024-01");
await page.addStyleTag({ content: `#cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1040px;background:rgba(11,11,11,.88);color:#fff;
  font:500 19px/1.4 system-ui,"Segoe UI",sans-serif;padding:12px 18px;border-radius:10px;z-index:99;box-shadow:0 4px 16px rgba(0,0,0,.3)}
  #cap b{color:#9ec5f4} .hl{outline:3px solid #eb6834!important;outline-offset:3px;border-radius:10px}` });
await page.evaluate(() => { const d = document.createElement("div"); d.id = "cap"; document.body.appendChild(d); });
const cap = async (html, ms) => { await page.evaluate(h => { document.getElementById("cap").innerHTML = h; }, html); await page.waitForTimeout(ms); };
const hl = async (sel, on = true) => page.evaluate(([s, o]) => document.querySelectorAll(".hl").forEach(e => e.classList.remove("hl")) || (o && document.querySelector(s)?.classList.add("hl")), [sel, on]);
const scrollTo = async sel => { await page.evaluate(s => { const e = document.querySelector(s); window.scrollTo({ top: e.getBoundingClientRect().top + scrollY - 150, behavior: "smooth" }); }, sel); await page.waitForTimeout(900); };
const click = async sel => { const b = await page.$(sel); const box = await b.boundingBox(); await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 }); await page.waitForTimeout(250); await b.click(); };

// 1. Purpose
await cap("<b>Studio North monthly replay.</b> This dashboard replays the customer-economics report one month at a time, January 2024 → December 2025.", 7000);
await cap("Each <b>as-of month</b> shows only what management could have known at that month's end. Solid = observed. Hatched/dashed = a forecast refitted on data through that month only.", 8000);
// 2. Controls
await hl(".ctrl");
await cap("Use <b>Next ▶ / ◀ Prev</b> (or the arrow keys), the slider, or <b>▶ Play</b>. Hover any bar or cell for exact values.", 5000);
await hl(".ctrl", false);
const jan = at("2024-01");
await hl("#changes");
await cap(`January 2024: the first cohort joins: <b>${jan.cohorts[0].n}</b> customers at a historical average CAC of <b>${money(jan.cohorts[0].cac)}</b>. No renewals yet, so the model can't be fitted and the forecast is left blank.`, 8500);
await click("#next"); await page.waitForTimeout(800);
await click("#next"); await page.waitForTimeout(600);
const mar = at("2024-03");
await hl("#model");
await cap(`March 2024 is the first month with enough renewal history. The model is refitted on data through March only. Its R-hat is ${mar.model.diagnostics.max_r_hat.toFixed(3)} and there are ${mar.model.diagnostics.divergences} divergences.`, 8500);
await hl("#model", false);
// 3. Watch the triangle and the value chart grow
await cap("Press <b>Play</b> and watch the retention triangle grow down and to the right while the value bars fill in.", 3000);
await click("#play");
await page.waitForTimeout(1200 * 6 + 300);
await click("#play");
await scrollTo("#ltv");
function idx_of(m) { return data.findIndex(d => d.month === m); }
await cap("In the value chart, the <b>solid blue</b> part of each bar is observed contribution and the <b>hatched</b> part is the forecast remainder. The black tick marks the cohort's CAC.", 8000);
// 4. Jump to June 2025 via slider
await page.evaluate(i => { const s = document.getElementById("slider"); s.value = i; s.dispatchEvent(new Event("input")); }, idx_of("2025-06"));
await page.waitForTimeout(700);
await scrollTo("#tri");
const jun = at("2025-06");
const early = jun.cohorts.filter(r => r.cohort <= "2024-03"), late = jun.cohorts.filter(r => r.age5 && r.cohort >= "2024-10").slice(-3);
const avg = (rs, f) => rs.reduce((a, r) => a + f(r), 0) / rs.length;
await cap(`June 2025. Newer cohorts keep more members at the same age. At age 5, Jan–Mar 2024 kept <b>${(100 * avg(early, r => r.age5.retained)).toFixed(0)}%</b> and ${late.map(r => r.cohort).join(", ")} kept <b>${(100 * avg(late, r => r.age5.retained)).toFixed(0)}%</b>.`, 9000);
await scrollTo("#decision");
await hl("#decision");
await cap("But the decision panel is empty. No holdout test has finished, so only <b>historical average CAC</b> is known. That includes people who would have joined anyway, so it can't price an <i>additional</i> customer.", 9000);
// 5. The month that matters
await click("#next"); await page.waitForTimeout(800);
await scrollTo("#decision");
const jul = at("2025-07");
const cells = (jul.decision?.cells || []).map(c => `${c.cell.replace("|", "/").replace("_", "-")}: ${c.value_less_icac >= 0 ? "+" : ""}${money(c.value_less_icac)}`).join(" · ");
await cap(`<b>July 2025: the change that matters.</b> The first holdout wave completes, and value per customer can be set against what an <i>additional</i> customer costs (iCAC). ${cells}`, 11000);
const losers = (jul.decision?.cells || []).filter(c => c.value_less_icac < 0).map(c => c.cell.replace("|", " / ").replace("_", " "));
await cap(`Management implication: ${losers.length ? `<b>${losers.join(" and ")}</b> cost more at the margin than a customer is worth over 12 receipts, even though every cohort clears its <i>average</i> CAC. Spending there should be constrained or redesigned.` : "every cell clears its iCAC this month."}`, 10000);
await hl("#decision", false);
// 6. Advance to the end
for (const m of ["2025-08", "2025-09", "2025-10", "2025-11"]) { await click("#next"); await page.waitForTimeout(1100); }
const stableSame = ans.first_month_pattern_stable_through_dec_2025 === ans.first_month_pattern_matches_report;
await cap(`Each month the newest wave updates iCAC. Both build-skill cells beat iCAC and both save-time cells fall short from <b>${name(ans.first_month_pattern_matches_report)}</b>${stableSame ? " in every month after" : `, without interruption from <b>${name(ans.first_month_pattern_stable_through_dec_2025)}</b>`}. Until November, though, <b>partner / build skill</b> had the larger margin.`, 9500);
await click("#next"); await page.waitForTimeout(900);
await scrollTo("#decision");
await cap(`December 2025: search / build skill moves ahead, and now clears even its pessimistic iCAC bound (first in <b>${name(ans.first_month_matching_with_search_build_skill_above_upper_icac)}</b>). This is the evidence behind the report's choice of it as the first priority.`, 9000);
await scrollTo("#recon");
await hl("#recon");
await cap(`December 2025 is the report's own data cutoff. ${recon.matches_report ? "The replay <b>reproduces the PDF's tables</b>: same LTVs, paybacks and value − iCAC to the cent." : "The replay is compared with the PDF's tables; see the reconciliation note."}`, 9000);
await cap("FAQ 4 check: rebuilding a month from raw records cut off at that month gives the same view, so no later information leaks in.", 8000);
await hl("#recon", false);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await cap("Open <b>output/studio-north-monthly-replay.html</b> in any browser to explore. Code, checks and README are in this repository.", 7000);
await ctx.close();
await browser.close();
const vid = fs.readdirSync(tmp).find(f => f.endsWith(".webm"));
fs.mkdirSync(path.join(here, "demo"), { recursive: true });
fs.copyFileSync(path.join(tmp, vid), path.join(here, "demo", "studio-north-replay-demo.webm"));
fs.rmSync(tmp, { recursive: true, force: true });
console.log("saved demo/studio-north-replay-demo.webm");
