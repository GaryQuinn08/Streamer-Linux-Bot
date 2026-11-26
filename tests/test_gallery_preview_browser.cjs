// Browser regression: npm install playwright && npx playwright install chromium
// Optional: CHROMIUM_EXECUTABLE=/path/to/chromium node tests/test_gallery_preview_browser.cjs
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { readFile } = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const docs = path.resolve(__dirname, '../docs');
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json' };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const route = url.pathname.replace(/^\/Streamer-Linux-Bot\//, '');
  const file = path.resolve(docs, route.endsWith('/') ? route + 'index.html' : route);
  if (!file.startsWith(docs + path.sep)) return res.writeHead(404).end();
  try {
    const data = await readFile(file);
    res.writeHead(200, { 'Content-Type': (types[path.extname(file)] || 'text/plain') + '; charset=utf-8' });
    res.end(data);
  } catch {
    res.writeHead(404).end();
  }
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, acceptDownloads: true });
    const styleViolations = [];
    page.on('console', msg => {
      if (/violates.*(?:style-src|inline style)/i.test(msg.text())) styleViolations.push(msg.text());
    });
    await page.route(/^(?!http:\/\/127\.0\.0\.1:)/, route => route.abort());
    const base = 'http://127.0.0.1:' + server.address().port + '/Streamer-Linux-Bot';
    await page.goto(base + '/galeria/');
    const opener = page.getByRole('button', { name: 'Ver las 8 piezas de Neón nocturno', exact: true });
    await opener.click();
    const modal = page.getByRole('dialog');
    const frame = page.frameLocator('#theme-preview');
    assert.match(await modal.textContent(), /Diseño de Gary Quinn/);
    assert.equal(await modal.getByRole('listitem').count(), 8);
    const scene = frame.locator('.scene');
    await scene.waitFor();
    assert.match(await frame.locator('h1').textContent(), /La ciudad se enciende/);
    assert.equal(await scene.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(25, 14, 46)');
    assert.match(await scene.evaluate(el => getComputedStyle(el).backgroundImage), /radial-gradient/);
    assert.equal(await frame.locator('body').evaluate(el => getComputedStyle(el).color), 'rgb(255, 240, 250)');
    for (const label of ['Alerta', 'Multichat', 'Actividad']) {
      await modal.getByRole('button', { name: label, exact: true }).click();
      const row = frame.locator('.slb-row').first();
      await row.waitFor();
      assert.equal(await row.evaluate(el => getComputedStyle(el).getPropertyValue('--accent').trim()), '#ff78cc');
      assert.notEqual(await row.locator('.card').evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)');
    }
    await modal.getByRole('button', { name: 'Marco de cámara', exact: true }).click();
    const camera = frame.locator('.frame');
    await camera.waitFor();
    assert.equal(await camera.evaluate(el => getComputedStyle(el).borderTopColor), 'rgb(255, 120, 204)');
    assert.equal(await camera.evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)');
    for (const [label, selector, title] of [['Banner', '.banner', 'Zona nocturna'],
      ['En pausa', '.scene', 'Pausa breve'], ['Cierre', '.scene', 'Gracias por acompañarnos']]) {
      await modal.getByRole('button', { name: label, exact: true }).click();
      const preview = frame.locator(selector).filter({ hasText: title });
      await preview.waitFor();
      assert.equal(await preview.evaluate(el => getComputedStyle(el).position), 'absolute');
    }
    const [download] = await Promise.all([
      page.waitForEvent('download'), modal.getByRole('button', { name: 'Descargar pack completo' }).click()
    ]);
    assert.equal(download.suggestedFilename(), 'neon-nocturno.slbpack');
    assert.equal(JSON.parse(await readFile(await download.path(), 'utf8')).components.length, 8);
    await page.keyboard.press('Escape');
    assert(await opener.evaluate(el => el === document.activeElement));
    assert.equal(await page.locator('.theme-card .theme-credit').filter({ hasText: 'Gary Quinn' }).count(), 20);
    await page.waitForFunction(() => document.querySelectorAll('.pin').length >= 12);
    assert.equal(await page.locator('.pin .meta a').filter({ hasText: 'Gary Quinn' }).count(), 12);
    await page.setViewportSize({ width: 390, height: 820 });
    await opener.click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    const bounds = await modal.boundingBox();
    assert(bounds.x >= 0 && bounds.x + bounds.width <= 390);
    assert.deepEqual(styleViolations, []);
    console.log('PASS: branded previews for all eight pieces, sandboxed layout, mobile, download, and original credits.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => server.close());
