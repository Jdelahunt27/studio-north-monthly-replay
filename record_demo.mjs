// Record a captioned, narrated ~2.5-3 minute demo of the replay dashboard.
//   node record_demo.mjs --script      -> demo/narration.json  (text for each scene)
//   powershell -File narrate.ps1       -> demo/narration/*.wav + durations.json  (Windows built-in TTS)
//   node record_demo.mjs               -> silent screen recording timed to the narration + cue times
//   node mux_audio.mjs                 -> demo/studio-north-replay-demo.webm  (VP8 video + Opus narration)
// Captions and narration quote numbers read from output/replay_data.json, so they always match the dashboard.
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
const demo = path.join(here, "demo");
fs.mkdirSync(demo, { recursive: true });
const at = m => data.find(d => d.month === m);
const idx = m => data.findIndex(d => d.month === m);
const money = v => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(0);
const sayMoney = v => (v < 0 ? "minus " : "") + Math.abs(v).toFixed(0) + " dollars";
const name = m => new Date(m + "-15").toLocaleString("en-US", { month: "long", year: "numeric" });
const cellName = c => c.replace("|", " / ").replace("_", " ");

// ---- Scenes: on-screen caption (html), narration (say), and the action that precedes it ----
const jan = at("2024-01"), mar = at("2024-03"), jun = at("2025-06"), jul = at("2025-07");
const early = jun.cohorts.filter(r => r.cohort <= "2024-03"), late = jun.cohorts.filter(r => r.age5 && r.cohort >= "2024-10").slice(-3);
const avg = (rs, f) => rs.reduce((a, r) => a + f(r), 0) / rs.length;
const eRet = (100 * avg(early, r => r.age5.retained)).toFixed(0), lRet = (100 * avg(late, r => r.age5.retained)).toFixed(0);
const cells = jul.decision.cells;
const losers = cells.filter(c => c.value_less_icac < 0).map(c => cellName(c.cell));
const first = name(ans.first_month_pattern_matches_report), firstRobust = name(ans.first_month_matching_with_search_build_skill_above_upper_icac);
const scenes = [
  { id: "01", html: "<b>Studio North monthly replay.</b> This dashboard replays the customer-economics report one month at a time, January 2024 → December 2025.",
    say: "This is the Studio North monthly replay. It replays the customer economics report one month at a time, from January 2024 to December 2025." },
  { id: "02", html: "Each <b>as-of month</b> shows only what management could have known at that month's end. Solid = observed. Hatched/dashed = a forecast refitted on data through that month only.",
    say: "Each as-of month shows only what management could have known at the end of that month. Solid marks are observed results. Hatched, dashed marks are forecasts, refitted on data through that month only." },
  { id: "03", pre: "ctrl", html: "Use <b>Next ▶ / ◀ Prev</b> (or the arrow keys), the slider, or <b>▶ Play</b>. Hover any bar or cell for exact values.",
    say: "Use Next and Previous, or the arrow keys, the slider, or Play. Hover over any bar or cell for exact values." },
  { id: "04", pre: "changes", html: `January 2024: the first cohort joins: <b>${jan.cohorts[0].n}</b> customers at a historical average CAC of <b>${money(jan.cohorts[0].cac)}</b>. No renewals yet, so the model can't be fitted and the forecast is left blank.`,
    say: `In January 2024 the first cohort joins: ${jan.cohorts[0].n} customers, at a historical average acquisition cost of ${sayMoney(jan.cohorts[0].cac)}. There are no renewals yet, so the model can't be fitted, and the forecast is left blank.` },
  { id: "05", pre: "toMarch", html: `March 2024 is the first month with enough renewal history. The model is refitted on data through March only. Its R-hat is ${mar.model.diagnostics.max_r_hat.toFixed(3)} and there are ${mar.model.diagnostics.divergences} divergences.`,
    say: "March 2024 is the first month with enough renewal history. The model is refitted on data through March only, and it passes the report's convergence checks." },
  { id: "06", pre: "play", html: "Press <b>Play</b> and watch the retention triangle grow down and to the right while the value bars fill in.",
    say: "Press Play, and watch the retention triangle grow down and to the right, while the value bars fill in." },
  { id: "07", pre: "ltv", html: "In the value chart, the <b>solid blue</b> part of each bar is observed contribution and the <b>hatched</b> part is the forecast remainder. The black tick marks the cohort's CAC.",
    say: "In the value chart, the solid blue part of each bar is observed contribution, and the hatched part is the forecast remainder. The black tick marks each cohort's acquisition cost." },
  { id: "08", pre: "toJune", html: `June 2025. Newer cohorts keep more members at the same age. At age 5, Jan–Mar 2024 kept <b>${eRet}%</b> and ${late.map(r => r.cohort).join(", ")} kept <b>${lRet}%</b>.`,
    say: `Now June 2025. Newer cohorts keep more members at the same age. At age five, the first three cohorts of 2024 kept ${eRet} percent of their customers. The newest comparable cohorts kept ${lRet} percent.` },
  { id: "09", pre: "decision", html: "But the decision panel is empty. No holdout test has finished, so only <b>historical average CAC</b> is known. That includes people who would have joined anyway, so it can't price an <i>additional</i> customer.",
    say: "But the decision panel is still empty. No holdout test has finished, so only historical average acquisition cost is known. That includes people who would have joined anyway, so it can't price an additional customer." },
  { id: "10", pre: "toJuly", html: `<b>July 2025: the change that matters.</b> The first holdout wave completes, and value per customer can be set against what an <i>additional</i> customer costs (iCAC). ${cells.map(c => `${cellName(c.cell)}: ${c.value_less_icac >= 0 ? "+" : ""}${money(c.value_less_icac)}`).join(" · ")}`,
    say: `July 2025 is the change that matters. The first holdout wave completes, so value per customer can finally be compared with what an additional customer costs, the incremental acquisition cost. ${cells.map(c => `${cellName(c.cell)}: ${sayMoney(c.value_less_icac)}`).join(". ")}.` },
  { id: "11", html: `Management implication: <b>${losers.join(" and ")}</b> cost more at the margin than a customer is worth over 12 receipts, even though every cohort clears its <i>average</i> CAC. Spending there should be constrained or redesigned.`,
    say: `The management implication: ${losers.join(" and ")} cost more at the margin than a customer is worth over twelve payments, even though every cohort clears its average acquisition cost. Spending there should be constrained or redesigned.` },
  { id: "12", pre: "toNov", html: `Each month the newest wave updates iCAC. Both build-skill cells beat iCAC and both save-time cells fall short from <b>${first}</b> in every month after. Until November, though, <b>partner / build skill</b> had the larger margin.`,
    say: `Each month, the newest wave updates the incremental cost. Both build skill cells beat it, and both save time cells fall short, from ${first} onward. Until November, though, partner build skill had the larger margin.` },
  { id: "13", pre: "toDec", html: `December 2025: search / build skill moves ahead, and now clears even its pessimistic iCAC bound (first in <b>${firstRobust}</b>). This is the evidence behind the report's choice of it as the first priority.`,
    say: `In December 2025, search build skill moves ahead, and now clears even its pessimistic cost bound. That is the evidence behind the report's choice of it as the first priority.` },
  { id: "14", pre: "recon", html: `December 2025 is the report's own data cutoff. ${recon.matches_report ? "The replay <b>reproduces the PDF's tables</b>: same LTVs, paybacks and value − iCAC to the cent." : "The replay is compared with the PDF's tables; see the reconciliation note."}`,
    say: recon.matches_report ? "December 2025 is the report's own data cutoff, and the replay reproduces the PDF's tables: the same lifetime values, paybacks, and value minus incremental cost, to the cent." : "December 2025 is the report's own data cutoff. The reconciliation note compares the replay with the PDF." },
  { id: "15", html: "FAQ 4 check: rebuilding a month from raw records cut off at that month gives the same view, so no later information leaks in.",
    say: "As a further check, rebuilding a month from raw records cut off at that month gives exactly the same view, so no later information leaks in." },
  { id: "16", pre: "top", html: "Open <b>output/studio-north-monthly-replay.html</b> in any browser to explore. Code, checks and README are in this repository.",
    say: "Open the dashboard file in any browser to explore it yourself. The code, checks, and read me are in this repository." },
];

// Spoken lines are shorter than the captions so the narrated video stays within 2-3 minutes.
const SPOKEN = {
  "01": "This dashboard replays the Studio North report one month at a time, from January 2024 to December 2025.",
  "02": "Each month shows only what management knew at that month's end. Solid marks are observed. Hatched marks are forecasts, refitted on data through that month.",
  "03": "Step with Next and Previous, the arrow keys, the slider, or Play. Hover for exact values.",
  "04": `In January 2024 the first cohort joins: ${jan.cohorts[0].n} customers. With no renewals yet, the forecast is left blank.`,
  "05": "March 2024 is the first month with enough history to fit the model, using data through March only.",
  "06": "Press Play to watch the retention triangle and the value bars grow.",
  "07": "In the value chart, solid blue is observed contribution, hatched is forecast, and the black tick is each cohort's acquisition cost.",
  "08": `By June 2025, newer cohorts keep more members. At age five: ${eRet} percent for early 2024, versus ${lRet} percent now.`,
  "09": "But no holdout test has finished yet, so we can't price an additional customer.",
  "10": `July 2025 is the change that matters. The first holdout wave lets us compare value with the incremental cost of an extra customer. ${cells.filter(c => c.value_less_icac >= 0).length === 2 && losers.length === 2 ? "Both build skill cells clear it. Both save time cells fall short." : ""}`,
  "11": `So ${losers.length ? "save time spending should be constrained or redesigned" : "every cell can grow"}, even though every cohort clears its average acquisition cost.`,
  "12": "That pattern holds every month after. Until November, partner build skill had the larger margin.",
  "13": "In December, search build skill moves ahead and clears even its pessimistic cost bound, matching the report's first priority.",
  "14": recon.matches_report ? "At December 2025, the replay reproduces the PDF's tables to the cent." : "At December 2025, the replay is compared with the PDF's tables.",
  "15": "And rebuilding any month from raw records cut off at that month gives the same view.",
  "16": "Open the dashboard file in any browser. The code and checks are in this repository.",
};
scenes.forEach(s => { if (SPOKEN[s.id]) s.say = SPOKEN[s.id]; });

if (process.argv.includes("--script")) {
  fs.writeFileSync(path.join(demo, "narration.json"), JSON.stringify(scenes.map(s => ({ id: s.id, say: s.say })), null, 1));
  console.log(`wrote ${scenes.length} narration lines`);
  process.exit(0);
}
const durFile = path.join(demo, "narration", "durations.json");
const durations = fs.existsSync(durFile) ? JSON.parse(fs.readFileSync(durFile, "utf8")) : {};

const tmp = path.join(here, "output", "video-tmp");
fs.rmSync(tmp, { recursive: true, force: true });
const W = 1280, H = 800;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: tmp, size: { width: W, height: H } }, colorScheme: "light" });
const t0 = Date.now();
const page = await ctx.newPage();
await page.goto(pathToFileURL(path.join(here, "output", "studio-north-monthly-replay.html")).href + "?month=2024-01");
await page.addStyleTag({ content: `#cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1040px;background:rgba(11,11,11,.88);color:#fff;
  font:500 19px/1.4 system-ui,"Segoe UI",sans-serif;padding:12px 18px;border-radius:10px;z-index:99;box-shadow:0 4px 16px rgba(0,0,0,.3)}
  #cap b{color:#9ec5f4} .hl{outline:3px solid #eb6834!important;outline-offset:3px;border-radius:10px}` });
await page.evaluate(() => { const d = document.createElement("div"); d.id = "cap"; document.body.appendChild(d); });
const hl = async (sel) => page.evaluate(s => { document.querySelectorAll(".hl").forEach(e => e.classList.remove("hl")); if (s) document.querySelector(s)?.classList.add("hl"); }, sel);
const scrollTo = async sel => { await page.evaluate(s => { const e = document.querySelector(s); window.scrollTo({ top: e.getBoundingClientRect().top + scrollY - 150, behavior: "smooth" }); }, sel); await page.waitForTimeout(900); };
const click = async sel => { const b = await page.$(sel); const box = await b.boundingBox(); await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 }); await page.waitForTimeout(250); await b.click(); };
const slide = async m => { await page.evaluate(i => { const s = document.getElementById("slider"); s.value = i; s.dispatchEvent(new Event("input")); }, idx(m)); await page.waitForTimeout(700); };
const actions = {
  ctrl: async () => hl(".ctrl"),
  changes: async () => hl("#changes"),
  toMarch: async () => { await hl(null); await click("#next"); await page.waitForTimeout(700); await click("#next"); await page.waitForTimeout(500); await hl("#model"); },
  play: async () => { await hl(null); },
  ltv: async () => { await scrollTo("#ltv"); },
  toJune: async () => { await slide("2025-06"); await scrollTo("#tri"); },
  decision: async () => { await scrollTo("#decision"); await hl("#decision"); },
  toJuly: async () => { await click("#next"); await page.waitForTimeout(700); await scrollTo("#decision"); },
  toNov: async () => { for (let i = 0; i < 4; i++) { await click("#next"); await page.waitForTimeout(900); } },
  toDec: async () => { await click("#next"); await page.waitForTimeout(800); await scrollTo("#decision"); },
  recon: async () => { await hl(null); await scrollTo("#recon"); await hl("#recon"); },
  top: async () => { await hl(null); await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await page.waitForTimeout(700); },
};
const cues = [];
for (const s of scenes) {
  if (s.pre) await actions[s.pre]();
  await page.evaluate(h => { document.getElementById("cap").innerHTML = h; }, s.html);
  cues.push({ id: s.id, start_ms: Date.now() - t0 });
  const speak = durations[s.id] ? durations[s.id] + 700 : 7000;
  if (s.pre === "play") {           // let the replay run while the line is spoken
    await click("#play");
    await page.waitForTimeout(Math.max(speak, 1200 * 6 + 300));
    await click("#play");
  } else {
    await page.waitForTimeout(speak);
  }
}
await hl(null);
await page.waitForTimeout(800);
const total = Date.now() - t0;
await ctx.close();
await browser.close();
const vid = fs.readdirSync(tmp).find(f => f.endsWith(".webm"));
fs.copyFileSync(path.join(tmp, vid), path.join(demo, "silent.webm"));
fs.rmSync(tmp, { recursive: true, force: true });
fs.writeFileSync(path.join(demo, "cues.json"), JSON.stringify({ total_ms: total, cues }, null, 1));
console.log(`saved demo/silent.webm (${(total / 1000).toFixed(1)}s) and demo/cues.json`);
