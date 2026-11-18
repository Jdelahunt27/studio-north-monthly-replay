// MediaRecorder WebM files have no Duration in their Segment Info, so players can't show length or
// seek well. This inserts the Duration element (EBML ID 0x4489, float64, in TimecodeScale units).
//   node fix_webm_duration.mjs demo/studio-north-replay-demo.webm 148900
import fs from "fs";
const [file, msArg] = process.argv.slice(2);
const buf = fs.readFileSync(file);
const vintLen = b => { for (let i = 0; i < 8; i++) if (b & (0x80 >> i)) return i + 1; throw new Error("bad vint"); };
const readId = p => { const n = vintLen(buf[p]); return { id: buf.readUIntBE(p, n), len: n }; };
const readSize = p => { const n = vintLen(buf[p]); let v = buf[p] & (0xff >> n); for (let i = 1; i < n; i++) v = v * 256 + buf[p + i]; return { size: v, len: n, unknown: v === Math.pow(2, 7 * n) - 1 }; };
let p = 0;
const ebml = readId(p); const es = readSize(p + ebml.len); p += ebml.len + es.len + es.size;           // EBML header
const seg = readId(p); if (seg.id !== 0x18538067) throw new Error("no Segment");
const ss = readSize(p + seg.len); let q = p + seg.len + ss.len;
while (q < buf.length) {
  const el = readId(q); const sz = readSize(q + el.len);
  if (el.id === 0x1549a966) {                                                                         // Info
    const start = q + el.len + sz.len, end = start + sz.size;
    let r = start, scale = 1000000;
    while (r < end) { const c = readId(r), cs = readSize(r + c.len);
      if (c.id === 0x4489) { console.log("Duration already present"); process.exit(0); }
      if (c.id === 0x2ad7b1) scale = buf.readUIntBE(r + c.len + cs.len, cs.size);
      r += c.len + cs.len + cs.size; }
    const dur = Buffer.alloc(11); dur.writeUInt16BE(0x4489, 0); dur[2] = 0x88; dur.writeDoubleBE(Number(msArg) * 1e6 / scale, 3);
    const newSize = sz.size + 11; if (newSize >= Math.pow(2, 7 * sz.len) - 1) throw new Error("Info size field too small");
    const sizeBytes = Buffer.alloc(sz.len); let v = newSize; for (let i = sz.len - 1; i >= 0; i--) { sizeBytes[i] = v & 0xff; v = Math.floor(v / 256); } sizeBytes[0] |= 0x80 >> (sz.len - 1);
    if (!ss.unknown) throw new Error("Segment has a known size; refusing to patch");
    fs.writeFileSync(file, Buffer.concat([buf.subarray(0, q + el.len), sizeBytes, buf.subarray(start, end), dur, buf.subarray(end)]));
    console.log(`inserted Duration ${msArg} ms`); process.exit(0);
  }
  if (sz.unknown) break; q += el.len + sz.len + sz.size;
}
throw new Error("Info element not found");
