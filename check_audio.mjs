// Verify the narrated demo: decode its audio in Chromium and confirm speech starts at each caption cue.
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1"));
const { chromium } = require(path.join(here, "..", "customer-economics-lab", "tools", "node_modules", "playwright"));
const demo = path.join(here, "demo");
const { cues } = JSON.parse(fs.readFileSync(path.join(demo, "cues.json"), "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage();
await page.route("http://demo.local/**", r => r.fulfill(r.request().url().endsWith(".webm")
  ? { contentType: "video/webm", body: fs.readFileSync(path.join(demo, "studio-north-replay-demo.webm")) }
  : { contentType: "text/html", body: "<!doctype html><title>check</title>" }));
await page.goto("http://demo.local/");
const res = await page.evaluate(async cues => {
  const ac = new OfflineAudioContext(1, 48000, 48000);
  const audio = await ac.decodeAudioData(await (await fetch("/demo.webm")).arrayBuffer());
  const d = audio.getChannelData(0), sr = audio.sampleRate, win = Math.round(sr * 0.1);
  const rms = []; for (let i = 0; i + win <= d.length; i += win) { let s = 0; for (let j = i; j < i + win; j++) s += d[j] * d[j]; rms.push(Math.sqrt(s / win)); }
  const thr = 0.01;
  const onsets = cues.map(c => { const k0 = Math.floor(c.start_ms / 100); for (let k = Math.max(0, k0 - 10); k < Math.min(rms.length, k0 + 30); k++) if (rms[k] > thr) return { id: c.id, cue_s: c.start_ms / 1000, speech_s: k / 10 }; return { id: c.id, cue_s: c.start_ms / 1000, speech_s: null }; });
  const v = document.createElement("video"); v.src = "/demo.webm"; await new Promise(r => v.onloadedmetadata = r);
  return { audio_seconds: audio.duration, video_duration_metadata: v.duration, speech_fraction: rms.filter(x => x > thr).length / rms.length, onsets };
}, cues);
await browser.close();
console.log(JSON.stringify(res, null, 1));
