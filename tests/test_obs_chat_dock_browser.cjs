// Browser dock regression. Requires Python dependencies + playwright Chromium.
// CHROMIUM_EXECUTABLE=/path/to/chromium node tests/test_obs_chat_dock_browser.cjs
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtemp, rm } = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { chromium } = require('playwright');

const repo = path.resolve(__dirname, '..');
const fixture = String.raw`
import asyncio, json, sys
from slbot.core.config import Config
from slbot.core.events import Event
from slbot.runtime import Runtime
async def main():
    rt = Runtime(config=Config.load(), port=0)
    rt.config.settings["overlay_presets"] = {"multi-chat": {"twitch":"false", "badges":"false", "names":"false"}}
    await rt._startup()
    port, route = rt.port, rt.overlays.chat_dock_path
    print(json.dumps([port, route]), flush=True)
    try:
        while raw := await asyncio.to_thread(sys.stdin.readline):
            cmd = json.loads(raw)
            if cmd == "stop":
                await rt.overlays.stop()
            elif cmd == "start":
                await rt.overlays.start(port)
                assert rt.overlays.chat_dock_path == route
            else:
                for platform, user, text, simulated in cmd:
                    await rt.bus.publish(Event(platform, "chat", user, {"text": text,"simulated":simulated}))
            print("OK", flush=True)
    finally:
        await rt._shutdown()
asyncio.run(main())
`;

(async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'slb-browser-dock-'));
  const server = spawn(process.env.PYTHON || 'python3', ['-u', '-c', fixture], {
    cwd:repo, stdio:['pipe','pipe','inherit'],
    env:{...process.env, SLB_CONFIG_DIR:folder, SLB_DATA_DIR:folder}
  });
  const lines = createInterface({input:server.stdout});
  let browser;
  try {
    const [ready] = await once(lines,'line');
    const [port,dock] = JSON.parse(ready);
    const origin = 'http://127.0.0.1:' + port;
    browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE});
    const page = await browser.newPage({viewport:{width:290,height:370}});
    const logs = [];
    page.on('pageerror', error => logs.push(String(error)));
    await page.goto(origin + dock);
    await page.getByRole('status').getByText('Conectado',{exact:true}).waitFor();
    assert.equal(await page.locator('input,textarea,form').count(),0);
    assert.equal(await page.title(),'Chat privado · Streamer Linux Bot');
    const viewers = await browser.newPage();
    const settings = viewers.waitForEvent('websocket', {predicate: socket => socket.url().endsWith('/ws/multi-chat')})
      .then(socket => socket.waitForEvent('framereceived', {predicate: frame => String(frame.payload).includes('chat-settings')}));
    await viewers.goto(origin + '/overlay/multi-chat/');
    await settings;
    async function send(payload){
      const reply = once(lines,'line');
      server.stdin.write(JSON.stringify(payload) + '\n');
      assert.equal((await reply)[0], 'OK');
    }
    await send([
      ['youtube','Prueba','Solo público',true],
      ['twitch','<em>persona','<img src=x onerror=alert(1)>',false],
      ['youtube','YouTube Cuenta','YouTube vivo',false],
      ['kick','Kick Cuenta','Kick vivo',false],
      ['tiktok','TikTok Cuenta','🩵'.repeat(500),false]
    ]);
    await page.getByText('Kick vivo',{exact:true}).waitFor();
    const rows = page.locator('#messages li');
    await rows.nth(3).waitFor();
    assert.equal(await rows.count(),4);
    assert.deepEqual(await page.locator('.platform').allTextContents(),['Twitch','YouTube','Kick','TikTok']);
    assert.equal(await page.locator('.msg').first().textContent(),'<img src=x onerror=alert(1)>');
    assert.equal(await page.locator('#messages img, #messages em').count(),0);
    assert.equal(await page.locator('.user').first().textContent(),'<em>persona');
    assert.equal(await page.locator('.msg').last().textContent(),'🩵'.repeat(500));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.equal(await viewers.getByText('Solo público',{exact:true}).count(),1);
    assert.equal(await viewers.locator('[data-platform=twitch]').count(),0);
    assert.equal(await viewers.getByText('YouTube Cuenta',{exact:true}).isVisible(),false);

    await send('stop');
    await page.getByRole('status').getByText('Reconectando…',{exact:true}).waitFor();
    await send('start');
    await page.getByRole('status').getByText('Conectado',{exact:true}).waitFor();
    await send([['tiktok','TikTok Cuenta','Tras reconectar',false]]);
    await page.getByText('Tras reconectar',{exact:true}).waitFor();
    assert.equal(await rows.count(),5);
    assert.equal(page.url(),origin + dock);

    await send(Array.from({length:156}, (_,i)=>['twitch','Voy '+i,'Línea '+i,false]));
    await page.getByText('Línea 155',{exact:true}).waitFor();
    assert.equal(await rows.count(),150);
    assert.equal(await page.getByText('Línea 0',{exact:true}).count(),0);
    await page.locator('main').evaluate(el => { el.scrollTop = 0; });
    await send([['kick','Otra cuenta','Prueba de posición',false]]);
    const follow = page.getByRole('button',{name:'Ir al último mensaje'});
    await follow.waitFor();
    assert.ok(await page.locator('main').evaluate(el => el.scrollTop < el.scrollHeight - el.clientHeight - 32));
    await follow.click();
    assert.ok(await page.locator('main').evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop < 32));
    assert.deepEqual(logs,[]);
    console.log('PASS: private OBS dock browser entry, scoped live labels, public filter independence, safe text, reconnect, responsive and bounded view');
    server.stdin.end();
  } finally {
    if (browser) await browser.close();
    server.kill();
    await rm(folder,{recursive:true,force:true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
