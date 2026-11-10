import { readFileSync, writeFileSync } from 'node:fs';

const ORDER = ['m00', 'm1', 'm2', 'm3', 'm4'];
const dur = JSON.parse(readFileSync('audio/durations.json', 'utf8'));

const toMs = (t) => {
  const [h, m, s] = t.split(':');
  const [sec, ms] = s.split(',');
  return ((+h * 60 + +m) * 60 + +sec) * 1000 + +ms;
};
const pad = (n, w = 2) => String(n).padStart(w, '0');
const fmt = (ms) =>
  `${pad(Math.floor(ms / 3600000))}:${pad(Math.floor((ms % 3600000) / 60000))}:${pad(
    Math.floor((ms % 60000) / 1000)
  )},${pad(ms % 1000, 3)}`;

let offset = 0;
let n = 1;
const out = [];
for (const id of ORDER) {
  const raw = readFileSync(`audio/${id}.vtt`, 'utf8').replace(/\r/g, '').trim();
  for (const block of raw.split(/\n\n+/)) {
    const lines = block.split('\n');
    if (!/^\d+$/.test(lines[0]?.trim())) continue;
    const [a, z] = lines[1].split(' --> ').map((t) => t.trim());
    out.push(`${n++}\n${fmt(toMs(a) + offset)} --> ${fmt(toMs(z) + offset)}\n${lines.slice(2).join('\n')}\n`);
  }
  offset += dur[id];
}
writeFileSync('out/paalkural-demo.srt', out.join('\n'));
console.log(`cues=${n - 1} end=${fmt(offset)}`);
