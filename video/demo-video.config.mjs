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
  await page.addStyleTag({ content: css });
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
  name: 'PaalKural demo',
  narration: 'narration.md',
  finalVideo: 'paalkural-demo.mp4',
  viewport: { width: 1920, height: 1080 },
  fps: 25,
  baseUrl: BASE,
  browser: { channel: 'chrome', headless: true },

  tts: {
    voice: 'en-IN-NeerjaNeural',
    rate: '-4%',
    defaultFixes: false,
  },

  compose: { crf: 18, preset: 'medium', audioBitrate: '192k', sampleRate: 44100, padSeconds: 5 },

  scenes: [
    { id: 'm00', title: 'Title', overlay: 'overlay/title.html' },

    { id: 'm1', title: 'Both listens agree', async run(ctx) {
      const { page, at, clickLoc, ensureInView } = ctx;
      await boot(page, COMPACT, '0.93', '', 'b12', '5');

      await at(1.3);
      await chooseClip(page, ctx, 'b12', '5');
      await ctx.moveMouse(page, 800, 760);

      await at(2.5);
      await clickLoc(page, page.locator('#run-clip'), 260, 'read b12');
      await page.waitForSelector('#sheet-body:not([hidden])', { timeout: 60000 });
      await page.waitForTimeout(500);

      await at(7.6);
      await ctx.moveMouse(page, 1260, 700);

      await at(11.5);
      await clickLoc(page, page.locator('#confirm-btn'), 260, 'confirm b12');
      await page.waitForSelector('#receipt:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(500);
    } },

    { id: 'm2', title: 'Listens disagree', async run(ctx) {
      const { page, at, clickLoc } = ctx;
      await boot(page, COMPACT, '0.93', '', 'b05', '15');

      await at(0.9);
      await chooseClip(page, ctx, 'b05', '15');

      await at(2.5);
      await clickLoc(page, page.locator('#run-clip'), 260, 'read b05');
      await page.waitForSelector('#sheet-body:not([hidden])', { timeout: 60000 });
      await page.waitForTimeout(600);

      await at(4.9);
      await ctx.moveMouse(page, 1260, 660);

      await at(8.5);
      await ctx.moveMouse(page, 1476, 146);

      await at(13.0);
      await clickLoc(page, page.locator('#confirm-btn'), 260, 'resolve');
      await page.waitForSelector('#edit-dialog[open]', { timeout: 8000 });
      await page.waitForTimeout(300);

      await at(14.4);
      await clickLoc(page, page.locator('#edit-fat'), 180, 'keep 4.7');

      await at(15.7);
      await clickLoc(page, page.locator('#edit-save'), 260, 'save');
      await page.waitForSelector('#receipt:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(500);
    } },

    { id: 'm3', title: 'Evidence', async run(ctx) {
      const { page, at } = ctx;
      await boot(page, EVIDENCE, '0.90', '#evidence');
      await page.waitForSelector('#evidence-run:not([hidden])', { timeout: 30000 });
      await page.waitForSelector('#provider-card:not([hidden])', { timeout: 30000 });
      await page.waitForTimeout(400);

      await at(1.4);
      await ctx.moveMouse(page, 950, 230);

      await at(8.2);
      await ctx.moveMouse(page, 950, 560);

      await at(12.6);
      await ctx.scrollAt(page, 950, 760, 300, 4);
      await page.waitForTimeout(240);

      await at(13.4);
      await ctx.moveMouse(page, 900, 850);
    } },

    { id: 'm4', title: 'Close', overlay: 'overlay/outro.html' },
  ],
};
