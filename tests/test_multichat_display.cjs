// Browser regression for the built-in audience overlay (actual HTTP and WebSocket).
// CHROMIUM_EXECUTABLE=... PYTHON=... node tests/test_multichat_display.cjs
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { spawn } = require('node:child_process');
const { mkdtemp, rm } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { chromium } = require('playwright');

const fixture = `
import asyncio, json, sys
from slbot.core.config import Config
from slbot.core.events import Event
from slbot.runtime import Runtime
async def main():
    rt = Runtime(config=Config.defaults(), port=0)
    await rt.overlays.start(0)
    print(rt.port, flush=True)
    try:
        while raw := await asyncio.to_thread(sys.stdin.readline):
            name, payload = json.loads(raw)
            if name == "preset":
                await rt.save_overlay_preset("multi-chat", payload)
            else:
                for platform in ("twitch", "tiktok", "youtube", "kick"):
                    await rt.overlays.forward_chat(Event(platform, "chat", "Viewer " + platform, {"text": payload}))
    finally:
        await rt.overlays.stop()
asyncio.run(main())
`;

async function main() {
  const tmp = await mkdtemp(path.join(tmpdir(), 'slb-chat-appearance-'));
  const proc = spawn(process.env.PYTHON || 'python3', ['-c', fixture], {
    cwd: path.resolve(__dirname, '..'), env: { ...process.env, SLB_DATA_DIR: tmp, SLB_CONFIG_DIR: tmp },
    stdio: ['pipe','pipe','inherit']
  });
  const stopped = once(proc, 'exit');
  const lines = createInterface({input: proc.stdout});
  let browser;
  try {
    const [port] = await Promise.race([once(lines, 'line'), stopped.then(() => { throw Error('server did not start'); })]);
    const base = 'http://127.0.0.1:' + port;
    const send = (kind, body) => proc.stdin.write(JSON.stringify([kind,body]) + '\n');
    browser = await chromium.launch({executablePath: process.env.CHROMIUM_EXECUTABLE});
    const page = await browser.newPage({viewport:{width:680,height:420}});
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    const open = async (target, suffix = '') => {
      const settings = target.waitForEvent('websocket').then(ws => ws.waitForEvent('framereceived', {
        predicate: frame => JSON.parse(frame.payload).channel === 'chat-settings'
      }));
      await target.goto(base + '/overlay/multi-chat/' + suffix);
      await settings;
    };
    const card = platform => page.locator(`.message[data-platform=${platform}]`).first();
    const border = el => el.evaluate(node => getComputedStyle(node).borderInlineStartColor);
    const color = el => el.evaluate(node => getComputedStyle(node).color);
    await open(page);
    send('messages','Hola <img src="ignored">');
    await card('kick').waitFor();
    assert.equal(await border(card('twitch')), 'rgb(195, 154, 249)');
    assert.equal(await border(card('tiktok')), 'rgb(167, 173, 183)');
    assert.equal(await page.locator('img').count(),0);
    assert.equal(await card('tiktok').locator('.platform').textContent(), 'TikTok');

    send('preset',{twitchColor:'#4285a4',tiktokColor:'#ff8800',badges:'false',nameByPlatform:'true'});
    await card('twitch').locator('.platform').waitFor({state:'hidden'});
    assert.equal(await border(card('tiktok')), 'rgb(255, 136, 0)');
    assert.equal(await color(card('twitch').locator('.sender')), 'rgb(66, 133, 164)');
    assert.equal(await card('twitch').locator('.sender').isVisible(), true);

    send('preset',{color:'#1cf205',badges:'true',names:'false',platformStripe:'false',youtube:'false'});
    await card('twitch').locator('.sender').waitFor({state:'hidden'});
    await card('youtube').waitFor({state:'hidden'});
    assert.equal(await border(card('twitch')), 'rgba(0, 0, 0, 0)');
    assert.equal(await card('twitch').locator('.separator').isVisible(), false);
    assert.equal(await card('twitch').locator('.platform').isVisible(), true);

    const scoped = await browser.newPage();
    await open(scoped,'?twitch=true&tiktok=false&youtube=false&kick=false&twitchColor=not-a-color');
    send('messages','Solo plataforma');
    await scoped.getByText('Solo plataforma',{exact:true}).waitFor();
    assert.deepEqual(await scoped.locator('.message').evaluateAll(nodes => nodes.map(el => el.dataset.platform)), ['twitch']);
    await scoped.close();
    assert.deepEqual(errors,[]);
    console.log('PASS: four platform colors, live customization, independent labels/names, isolated Twitch link.');
  } finally {
    await browser?.close();
    proc.stdin.end();
    await stopped;
    await rm(tmp,{recursive:true,force:true});
  }
}
main().catch(error => {console.error(error); process.exitCode=1;});
