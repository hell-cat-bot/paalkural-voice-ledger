import { readFileSync } from 'node:fs';

const BASE = process.env.DV_BASE_URL || 'http://127.0.0.1:7860';

const COMPACT = `
.line-intro{display:none!important}
.panel{padding-top:18px!important}
.sheet{padding:20px!important}
.sheet-head{margin-bottom:10px!important}
.transcript-block{margin-bottom:8px!important}
.slot{padding:7px 0!important}
.second-listen{margin:8px 0!important;padding:10px 12px!important}
.readback{padding:12px 14px!important;margin:10px 0!important}
.readback-ta{font-size:20px!important;line-height:1.35!important}
.member-strip{padding:8px 10px!important;margin:10px 0!important}
.preview{padding:8px 10px!important;margin:10px 0!important}
.sheet-actions{margin-top:12px!important}
.sheet-note{margin-top:6px!important}
`;

const EVIDENCE = `
.evidence-head{display:none!important}
.panel{padding-top:18px!important}
.claim{margin-top:0!important}
`;

/** Sentence start times from the Timbre VTT, so actions follow the real voice. */
function starts(id) {
  const raw = readFileSync(new URL(`./audio/${id}.vtt`, import.meta.url), 'utf8');
  return [...raw.matchAll(/(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->/g)].map(
    (m) => Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / 1000
  );
}

async function boot(page, css, zoom, hash = '', clip = '', snr = '') {
  await page.addInitScript(() => {
    const apply = () => {
      if (document.getElementById('dv-boot-hide')) return true;
      const root = document.head || document.documentElement;
      if (!root) return false;
      const s = document.createElement('style');
      s.id = 'dv-boot-hide';
      s.textContent = 'html{background:#FBF8F1!important}body{opacity:0!important}';
      root.appendChild(s);
      return true;
    };
    if (!apply()) {
      const mo = new MutationObserver(() => { if (apply()) mo.disconnect(); });
      mo.observe(document, { childList: true, subtree: true });
    }
    window.__dvBootReady = true;
  });
  await page.goto(BASE + hash, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForFunction(
    () => document.querySelectorAll('#clip-select option').length > 0,
    null,
    { timeout: 20000 }
  );
  await page.waitForFunction(
    () => {
      const el = document.querySelector('#health-text');
      return el && el.textContent.trim() !== 'checking engine';
    },
    null,
    { timeout: 15000 }
  );
  if (clip) {
    await page.selectOption('#clip-select', clip);
    await page.selectOption('#snr-select', snr);
    await page.waitForTimeout(120);
  }
  if (css) await page.addStyleTag({ content: css });
  await page.evaluate((z) => { document.documentElement.style.zoom = z; }, zoom);
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    document.getElementById('dv-boot-hide')?.remove();
    window.dispatchEvent(new Event('resize'));
    document.body.style.transition = 'opacity .28s ease';
    document.body.style.setProperty('opacity', '1', 'important');
  });
  await page.waitForTimeout(320);
}

async function chooseClip(page, ctx, clip, snr) {
  const { moveMouse } = ctx;
  const box = await page.locator('#clip-select').boundingBox();
  if (box) await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
  await page.selectOption('#clip-select', clip);
  await page.waitForTimeout(160);
  await page.selectOption('#snr-select', snr);
  await page.waitForTimeout(220);
}

export default {
  name: 'PaalKural demo · 3 min',
  narration: 'narration.md',
  finalVideo: 'paalkural-demo-3min.mp4',
  viewport: { width: 1920, height: 1080 },
  fps: 25,
  baseUrl: BASE,
  browser: { channel: 'chrome', headless: true },

  // Narration audio was synthesized with Gnani Timbre v2.5 (Nalini) by
  // video/tools/timbre_narration.py; this block only configures the engine's
  // edge-tts fallback if someone regenerates it without the key.
  tts: {
    voice: 'en-IN-NeerjaNeural',
    rate: '-4%',
    defaultFixes: false,
  },

  compose: { crf: 18, preset: 'medium', audioBitrate: '192k', sampleRate: 44100, padSeconds: 5 },

  scenes: [
    { id: 'm00', title: 'Title', overlay: 'overlay/title.html' },
    { id: 'm01', title: 'The idea', overlay: 'overlay/idea.html' },

    { id: 'm1', title: 'Both listens agree', async run(ctx) {
      const { page, at, clickLoc } = ctx;
      const s = starts('m1');
      await boot(page, COMPACT, '0.93', '', 'b12', '5');

      await at(s[0] + 1.0);
      await chooseClip(page, ctx, 'b12', '5');
      await ctx.moveMouse(page, 800, 760);

      await at(s[0] + 1.5);
      await clickLoc(page, page.locator('#run-clip'), 260, 'read b12');
      await page.waitForSelector('#sheet-body:not([hidden])', { timeout: 60000 });
      await page.waitForTimeout(450);

      await at(Math.max(s[1] + 0.3, s[0] + 3.4));
      await ctx.moveMouse(page, 1260, 700);

      await at(Math.max(s[2] + 0.7, s[1] + 2.4));
      await clickLoc(page, page.locator('#confirm-btn'), 260, 'confirm b12');
      await page.waitForSelector('#receipt:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(500);
    } },

    { id: 'm2', title: 'Listens disagree', async run(ctx) {
      const { page, at, clickLoc } = ctx;
      const s = starts('m2');
      await boot(page, COMPACT, '0.93', '', 'b05', '15');

      await at(s[0] + 0.6);
      await chooseClip(page, ctx, 'b05', '15');

      await at(s[0] + 1.1);
      await clickLoc(page, page.locator('#run-clip'), 260, 'read b05');
      await page.waitForSelector('#sheet-body:not([hidden])', { timeout: 60000 });
      await page.waitForTimeout(600);

      await at(s[1] + 0.5);
      await ctx.moveMouse(page, 1260, 660);

      await at(s[2] + 0.4);
      await ctx.moveMouse(page, 1476, 146);

      await at(s[3] + 0.2);
      await clickLoc(page, page.locator('#confirm-btn'), 260, 'resolve');
      await page.waitForSelector('#edit-dialog[open]', { timeout: 8000 });
      await page.waitForTimeout(300);

      await at(s[3] + 1.0);
      await clickLoc(page, page.locator('#edit-fat'), 180, 'keep 4.7');

      await at(s[3] + 1.8);
      await clickLoc(page, page.locator('#edit-save'), 260, 'save');
      await page.waitForSelector('#receipt:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(500);
    } },

    { id: 'm4', title: 'The day book', async run(ctx) {
      const { page, at } = ctx;
      const s = starts('m4');
      await boot(page, '', '0.95', '#ledger');
      await page.waitForSelector('.ledger-export', { timeout: 15000 });
      await page.waitForTimeout(300);

      await at(s[0] + 0.9);
      await ctx.moveMouse(page, 900, 330);

      await at(s[1] + 0.4);
      await page.locator('.ledger-export').scrollIntoViewIfNeeded();
      const box = await page.locator('.ledger-export').boundingBox();
      if (box) await ctx.moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
      await page.waitForTimeout(300);
    } },

    { id: 'm3', title: 'The evidence', async run(ctx) {
      const { page, at } = ctx;
      const s = starts('m3');
      await boot(page, EVIDENCE, '0.90', '#evidence');
      await page.waitForSelector('#evidence-run:not([hidden])', { timeout: 30000 });
      await page.waitForSelector('#provider-card:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(400);

      await at(s[0] + 0.6);
      await ctx.moveMouse(page, 950, 230);

      await at(s[2] + 0.5);
      await ctx.moveMouse(page, 950, 360);

      await at(s[3] + 0.6);
      await ctx.scrollAt(page, 950, 760, 300, 4);
      await page.waitForTimeout(240);
      await ctx.moveMouse(page, 950, 560);

      await at(s[4] + 0.4);
      await ctx.scrollAt(page, 950, 760, 300, 3);
      await page.waitForTimeout(200);
      await ctx.moveMouse(page, 900, 850);
    } },

    { id: 'm5', title: 'Close', overlay: 'overlay/outro.html' },
  ],
};
