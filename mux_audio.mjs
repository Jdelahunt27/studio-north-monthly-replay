// Combine demo/silent.webm with the narration clips (demo/narration/*.wav at demo/cues.json times)
// into demo/studio-north-replay-demo.webm (VP8 video + Opus audio), using only the lab's pinned
// Playwright Chromium: the page plays the video and schedules the clips through Web Audio, and
// MediaRecorder captures both in real time. No external encoder is needed.
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1"));
const { chromium } = require(path.join(here, "..", "customer-economics-lab", "tools", "node_modules", "playwright"));
const demo = path.join(here, "demo");
const { cues, total_ms } = JSON.parse(fs.readFileSync(path.join(demo, "cues.json"), "utf8"));
const LEAD_MS = Number(process.env.LEAD_MS || 0);  // shift narration if the recording starts late
const CLIP_EXT = process.env.CLIP_EXT || "wav";      // narration clip format: wav (Windows TTS) or mp3 (e.g. ElevenLabs)

const page_html = `<!doctype html><html><body style="margin:0;background:#000">
<video id="v" src="silent.webm" muted playsinline style="width:1280px;height:800px"></video>
<script>
window.mux = async (cues, lead) => {
  const v = document.getElementById("v");
  await new Promise(r => v.readyState >= 2 ? r() : v.addEventListener("loadeddata", r, { once: true }));
  const ac = new AudioContext({ sampleRate: 48000 });
  const dest = ac.createMediaStreamDestination();
  const buffers = await Promise.all(cues.map(async c => ac.decodeAudioData(await (await fetch("narration/" + c.id + "." + window.CLIP_EXT)).arrayBuffer())));
  const vs = v.captureStream();
  const stream = new MediaStream([...vs.getVideoTracks(), ...dest.stream.getAudioTracks()]);
  const rec = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp8,opus", videoBitsPerSecond: 900000, audioBitsPerSecond: 64000 });
  rec.ondataavailable = async e => { if (e.data.size) { const b = new Uint8Array(await e.data.arrayBuffer()); let s = ""; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768)); await window.saveChunk(btoa(s)); } };
  const done = new Promise(r => rec.onstop = r);
  rec.start(1000);
  await v.play();
  const t0 = ac.currentTime;
  cues.forEach((c, i) => { const src = ac.createBufferSource(); src.buffer = buffers[i]; src.connect(dest); src.start(t0 + Math.max(0, (c.start_ms + lead) / 1000)); });
  await new Promise(r => v.addEventListener("ended", r, { once: true }));
  await new Promise(r => setTimeout(r, 300));
  rec.stop(); await done;
  return { duration: v.duration };
};
</script></body></html>`;

const out = path.join(demo, "studio-north-replay-demo.webm");
const fd = fs.openSync(out, "w");
const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
const page = await browser.newPage();
await page.exposeFunction("saveChunk", b64 => { fs.writeSync(fd, Buffer.from(b64, "base64")); });
await page.route("http://demo.local/**", async route => {
  const rel = decodeURIComponent(new URL(route.request().url()).pathname.slice(1));
  if (rel === "" || rel === "index.html") return route.fulfill({ contentType: "text/html", body: page_html });
  const file = path.join(demo, rel);
  if (!file.startsWith(demo) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: "" });
  return route.fulfill({ contentType: rel.endsWith(".wav") ? "audio/wav" : rel.endsWith(".mp3") ? "audio/mpeg" : "video/webm", body: fs.readFileSync(file) });
});
await page.addInitScript(ext => { window.CLIP_EXT = ext; }, CLIP_EXT);
await page.goto("http://demo.local/index.html");
console.log(`muxing ${cues.length} narration clips into ${(total_ms / 1000).toFixed(0)}s of video (real time)...`);
const result = await page.evaluate(([c, lead]) => window.mux(c, lead), [cues, LEAD_MS]);
fs.closeSync(fd);
await browser.close();
console.log(`saved demo/studio-north-replay-demo.webm, ${(fs.statSync(out).size / 1e6).toFixed(1)} MB, source ${result.duration.toFixed(1)}s`);
