// Browser Source regression. Requires Python requirements + playwright Chromium.
// Optional: CHROMIUM_EXECUTABLE=/path/to/chromium PYTHON=python3 node tests/test_obs_overlay_motion.cjs
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtemp, readFile, rm, writeFile } = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { inflateSync } = require('node:zlib');
const { chromium } = require('playwright');

const repo = path.resolve(__dirname, '..');
const py = process.env.PYTHON || 'python3';
const runtimeCode = String.raw`
import asyncio,json,sys
from pathlib import Path
from slbot.core.actions import run_action
from slbot.core.config import Action, Config
from slbot.core.events import Event
from slbot.overlay_manager import import_overlay
from slbot.overlay_pack import import_pack
from slbot.runtime import Runtime
async def main():
    root = Path(sys.argv[1])
    pack, camera = import_pack(root / 'motion.slbpack')
    old_pack = import_overlay(root / 'legacy-pack')
    web = import_overlay(root / 'motion.html')
    old_web = import_overlay(root / 'legacy-web.html')
    rt = Runtime(config=Config.load(), port=0)
    await rt.overlays.start(0)
    await rt.save_overlay_preset(old_web.id, {"enter":"pop", "enterMs":"1500", "exit":"slide-left", "exitMs":"420"})
    try:
        print(json.dumps({"port":rt.port, "pack":pack.id, "camera":camera.id, "old_pack":old_pack.id,
                          "web":web.id, "old_web":old_web.id}), flush=True)
        while command := await asyncio.to_thread(sys.stdin.readline):
            ids = json.loads(command)
            for _ in range(100):
                if set(ids) <= set(rt.overlays.clients.values()):
                    break
                await asyncio.sleep(.01)
            else:
                raise RuntimeError('Browser source WebSocket did not connect')
            for ident in set(ids):
                await run_action(rt, Action('probe', 'Probe', [
                    {"type":"overlay_alert", "overlay":ident, "title":"{user}", "text":"×{count}"}
                ]), Event('tiktok', 'gift', '<visor>', {"count":3,"gift_name":"Rosa"}))
    finally:
        await rt.overlays.stop()
asyncio.run(main())
`;

function topLeftAlpha(image) {
  assert.equal(image[25], 6, 'expected an RGBA PNG');
  const blocks = [];
  for (let offset = 8; offset < image.length;) {
    const length = image.readUInt32BE(offset);
    if (image.toString('ascii', offset + 4, offset + 8) === 'IDAT') {
      blocks.push(image.subarray(offset + 8, offset + 8 + length));
    }
    offset += length + 12;
  }
  // In the first scanline's first pixel PNG filtering has no left/up neighbors.
  return inflateSync(Buffer.concat(blocks))[4];
}

async function track(page, url, selector) {
  await page.addInitScript(selector => {
    window.motionTrace = [];
    const stamp = name => window.motionTrace.push([name, performance.now()]);
    document.addEventListener('DOMContentLoaded', () => {
      new MutationObserver(records => {
        for (const line of records) {
          for (const node of line.addedNodes) if (node.matches?.(selector)) stamp('attached');
          for (const node of line.removedNodes) if (node.matches?.(selector)) stamp('detached');
        }
      }).observe(document.querySelector(selector.startsWith('.slb') ? '#slb-stage' : '#stage'), {childList:true});
    });
    for (const type of ['animationstart','animationend','animationcancel']) {
      document.addEventListener(type, event => {
        if (event.target.matches(selector)) stamp(type + ':' + event.animationName);
      });
    }
  }, selector);
  const response = await page.goto(url);
  assert.equal(response.status(), 200);
  assert.match(response.headers()['cache-control'], /no-store/);
  assert.equal(await page.locator('body').evaluate(x => getComputedStyle(x).backgroundColor), 'rgba(0, 0, 0, 0)');
  assert.equal(topLeftAlpha(await page.screenshot({omitBackground:true, clip:{x:0,y:0,width:10,height:10}})), 0);
}

async function assertMotion(page, probe, enter, exit, entranceMs) {
  const row = page.locator(probe);
  await row.waitFor({state:'attached'});
  assert.match(await row.textContent(), /<visor>/);
  assert.match(await row.textContent(), /×3/);
  assert.equal(await row.locator('visor').count(), 0);
  const keyframes = await row.evaluate(x => x.getAnimations()[0]?.effect.getKeyframes().map(frame => frame.transform));
  assert.ok(keyframes?.includes('scale(1.06)'), 'Pop includes visible overshoot');
  await row.waitFor({state:'detached', timeout:6000});
  const trace = new Map(await page.evaluate(() => window.motionTrace));
  assert.ok(trace.get('animationend:' + enter) - trace.get('animationstart:' + enter) > entranceMs - 90);
  assert.ok(trace.get('animationstart:' + exit) - trace.get('attached') >= entranceMs + 960);
  assert.ok(trace.get('detached') - trace.get('animationstart:' + exit) > 350);
  assert.ok(!trace.has('animationcancel:' + enter), 'the long entrance must not be cut short');
}

async function main() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'slb-browser-motion-'));
  const children = [];
  let browser;
  try {
    const docs = spawn(py, ['-u', '-m', 'http.server', '0', '--bind', '127.0.0.1', '--directory', path.join(repo, 'docs')],
      {stdio:['ignore','pipe','inherit']});
    children.push(docs);
    const [listen] = await once(docs.stdout, 'data');
    const port = String(listen).match(/port (\d+)/)[1];
    browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE});
    const studio = await browser.newPage({acceptDownloads:true});
    const design = {mode:'alert',name:'Overlay nuevo',title:'{user}',body:'{alert_text}',duration:1,
      enter:'pop',exit:'slide-left',enterMs:1400,exitMs:420};
    await studio.goto('http://127.0.0.1:' + port + '/editor/#preset=' + encodeURIComponent(JSON.stringify(design)));
    await studio.locator('#enter').waitFor();
    assert.equal(await studio.locator('#enter').inputValue(),'pop');
    const [download] = await Promise.all([studio.waitForEvent('download'),studio.locator('#export').click()]);
    const web = path.join(root,'motion.html');
    await download.saveAs(web);
    const output = await readFile(web,'utf8');
    const legacy = output.replace(
      /      \/\/ La duraci[oó]n es el tiempo visible[^\n]*\n      const entrance = .*\n        && .*\n      if \(timed && duration > 0\).*\n/,
      '      if (timed && duration > 0) timers.set(row, setTimeout(() => dismiss(row), duration * 1000));\n'
    );
    assert.notEqual(legacy, output);
    await writeFile(path.join(root,'legacy-web.html'),legacy);
    const pack = {format:'slb-pack',version:1,name:'Prueba Motion',components:[
      {kind:'alert',design},{kind:'camera',design:{title:'',body:'',background:'#442244',opacity:100}}
    ]};
    await writeFile(path.join(root,'motion.slbpack'),JSON.stringify(pack));
    const buildLegacy = String.raw`
import json,sys
from pathlib import Path
from slbot.overlay_pack import read_pack,render_piece
root=Path(sys.argv[1])
content=render_piece(*read_pack(root/'motion.slbpack')[2][0])
old=content.replace("const entrance=config.enter!=='none'&&config.enterMs>0&&!matchMedia('(prefers-reduced-motion: reduce)').matches;\n    if(entrance)card.classList.add('enter');",
                    "if(config.enter!=='none' && config.enterMs>0)card.classList.add('enter');").replace("(entrance?config.enterMs:0)+config.duration*1000","config.duration*1000")
assert old != content
out=root/'legacy-pack'; out.mkdir()
(out/'index.html').write_text(old, encoding='utf-8')
(out/'manifest.json').write_text(json.dumps({'id':'legacy-pack','name':'Legacy Pack','params':[]}), encoding='utf-8')
`;
    const env = {...process.env,SLB_DATA_DIR:path.join(root,'data'),SLB_CONFIG_DIR:path.join(root,'config'),
      PYTHONPATH:[repo,process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)};
    const prep = spawn(py,['-c',buildLegacy,root],{cwd:repo,env,stdio:['ignore','ignore','inherit']});
    const [code] = await once(prep,'exit');
    assert.equal(code,0);
    const run = spawn(py,['-u','-c',runtimeCode,root],{cwd:repo,env,stdio:['pipe','pipe','inherit']});
    children.push(run);
    const lines = createInterface({input:run.stdout});
    const [raw] = await once(lines,'line');
    const ids = JSON.parse(raw);
    const source = id => 'http://127.0.0.1:' + ids.port + '/overlay/' + id + '/';
    const tests = [
      ['web','.slb-row','slb-entry','slb-leave',1400],
      ['old_web','.slb-row','slb-custom-in','slb-custom-out',1500],
      ['pack','.card','slb-in','slb-out',1400],
      ['old_pack','.card','slb-in','slb-out',1400],
    ];
    const browsers = await Promise.all(tests.map(async ([name, probe]) => {
      const page = await browser.newPage({viewport:{width:960,height:540},reducedMotion:'no-preference'});
      await track(page, source(ids[name]), probe);
      return page;
    }));
    const reduced = await browser.newPage({viewport:{width:960,height:540},reducedMotion:'reduce'});
    await track(reduced,source(ids.pack),'.card');
    const camera = await browser.newPage({viewport:{width:960,height:540}});
    await camera.goto(source(ids.camera));
    assert.equal(topLeftAlpha(await camera.screenshot({omitBackground:true,clip:{x:20,y:20,width:10,height:10}})),0);
    // The pages subscribe to the actual bot server. Only a genuine test action emits the fixture event.
    run.stdin.write(JSON.stringify(tests.map(([name]) => ids[name])) + '\n');
    await Promise.all(tests.map(([,probe,enter,exit,ms],idx) => assertMotion(browsers[idx], probe, enter, exit, ms)));
    const trace = new Map(await reduced.evaluate(() => window.motionTrace));
    assert.equal(trace.size,2,'reduced motion must not run either animation');
    assert.ok(trace.get('detached')-trace.get('attached') >= 950 && trace.get('detached')-trace.get('attached') < 1300);
    assert.equal(await readFile(path.join(root,'legacy-web.html'),'utf8'),legacy);
    run.stdin.end();
    console.log('PASS: real local OBS URLs + WebSocket actions, transparency, independent entrance/hold/exit, older exports, Pop, reduced motion');
  } finally {
    if (browser) await browser.close();
    for (const child of children) child.kill();
    await rm(root,{recursive:true,force:true});
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
