// Requires Python deps + Playwright. CHROMIUM_EXECUTABLE=/path/to/chromium node tests/test_now_playing_browser.cjs
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtemp, rm } = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { inflateSync } = require('node:zlib');
const { chromium } = require('playwright');

const repo = path.resolve(__dirname,'..');
const fixture = String.raw`
import asyncio,json,sys
from slbot.core.config import Config
from slbot.now_playing import Track
from slbot.runtime import Runtime
async def main():
    rt=Runtime(config=Config.load())
    await rt.overlays.start(0)
    port=rt.port
    print(port,flush=True)
    try:
        while raw:=await asyncio.to_thread(sys.stdin.readline):
            command,*args=json.loads(raw)
            if command=="publish": await rt.now_playing._publish(Track(*args))
            elif command=="demo": await rt.overlays.preview_now_playing(*args)
            elif command=="preset":
                await rt.save_overlay_preset(*args)
                await rt.overlays.broadcast_now_playing_settings(args[0])
            elif command=="stop": await rt.overlays.stop()
            elif command=="start": await rt.overlays.start(port)
            print("OK",flush=True)
    finally: await rt.overlays.stop()
asyncio.run(main())
`;

function topLeftAlpha(image) {
  assert.equal(image[25],6);
  const blocks = [];
  for (let off=8; off<image.length;) {
    const length=image.readUInt32BE(off);
    if (image.toString('ascii',off+4,off+8)==='IDAT') blocks.push(image.subarray(off+8,off+8+length));
    off += length+12;
  }
  return inflateSync(Buffer.concat(blocks))[4];
}

(async()=>{
  const tmp=await mkdtemp(path.join(os.tmpdir(),'slb-nowplaying-browser-'));
  const processFixture=spawn(process.env.PYTHON||'python3',['-u','-c',fixture],{
    cwd:repo, env:{...process.env,SLB_CONFIG_DIR:tmp,SLB_DATA_DIR:tmp}, stdio:['pipe','pipe','inherit']
  });
  const lines=createInterface({input:processFixture.stdout});
  const exited=once(processFixture,'exit');
  let browser;
  try{
    const [port]=await Promise.race([once(lines,'line'),exited.then(()=>{throw Error('server did not start')})]);
    const base='http://127.0.0.1:'+port;
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE});
    const requests=[], errors=[];
    const vinyl=await browser.newPage({viewport:{width:1200,height:675}});
    const neon=await browser.newPage({viewport:{width:340,height:245}});
    const noMotion=await browser.newPage({viewport:{width:600,height:400},reducedMotion:'reduce'});
    const views=[vinyl,neon,noMotion], ids=['now-playing','now-playing-spectrum','now-playing-spectrum'];
    for (const [i,page] of views.entries()){
      page.on('request',req=>requests.push(req.url()));
      page.on('pageerror',error=>errors.push(String(error)));
      page.on('console',message=>{ if(/violat|Refused/i.test(message.text())) errors.push(message.text()); });
      const ready=page.waitForEvent('websocket').then(ws=>ws.waitForEvent('framereceived',{
        predicate:frame=>String(frame.payload).includes('"channel": "now-playing"')
      }));
      await page.goto(base + '/overlay/' + ids[i] + '/');
      await ready;
      assert.equal(await page.locator('#track').isVisible(),false);
      assert.equal(topLeftAlpha(await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:10,height:10}})),0);
    }
    async function send(...message){
      const reply=once(lines,'line');
      processFixture.stdin.write(JSON.stringify(message)+'\n');
      assert.equal((await reply)[0],'OK');
    }
    await send('publish','playing','Título <em>visualmente literal</em>','Lunaluz','never-exposed');
    for (const page of views){
      await page.locator('#track').waitFor();
      assert.equal(await page.locator('#title').textContent(),'Título <em>visualmente literal</em>');
      assert.equal(await page.locator('#track img, #track em').count(),0);
      assert.equal(await page.locator('#artist').textContent(),'Lunaluz');
      assert.equal(await page.locator('body').evaluate(node=>getComputedStyle(node).backgroundColor),'rgba(0, 0, 0, 0)');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    assert.equal(await vinyl.locator('.record').evaluate(node=>getComputedStyle(node).animationName),'vinyl-spin');
    assert.equal(await neon.locator('.meter i').first().evaluate(node=>getComputedStyle(node).animationName),'pulse-bars');
    assert.equal(await noMotion.locator('.meter i').first().evaluate(node=>getComputedStyle(node).animationName),'none');
    assert.ok(await neon.locator('#track').evaluate(node=>getComputedStyle(node).clipPath.includes('polygon')));
    if(process.env.SLB_OVERLAY_SHOTS){
      await vinyl.screenshot({path:process.env.SLB_OVERLAY_SHOTS+'-vinyl.png',omitBackground:true});
      await neon.screenshot({path:process.env.SLB_OVERLAY_SHOTS+'-neon.png',omitBackground:true});
    }

    await send('publish','paused','Título <em>visualmente literal</em>','Lunaluz','never-exposed');
    for(const [page,selector] of [[vinyl,'.record'],[neon,'.meter i']]){
      await page.getByText('EN PAUSA',{exact:true}).waitFor();
      assert.equal(await page.locator(selector).first().evaluate(node=>getComputedStyle(node).animationPlayState),'paused');
    }
    await send('preset','now-playing', {showArtist:'false',accent:'#ff5432',position:'Arriba a la derecha',width:'66'});
    await vinyl.locator('#artist').waitFor({state:'hidden'});
    assert.equal(await vinyl.locator('body').getAttribute('data-position'),'top-right');
    assert.equal(await vinyl.locator('#track').evaluate(node=>getComputedStyle(node).borderTopColor),'rgb(255, 84, 50)');
    assert.equal(await neon.locator('#artist').isVisible(),true);

    await send('demo','now-playing-spectrum');
    await neon.getByText('PRUEBA',{exact:true}).waitFor();
    assert.equal(await vinyl.locator('#demo').isVisible(),false);
    assert.equal(await neon.locator('#title').textContent(),'Órbita de medianoche');
    await send('publish','playing','Sincronizado','Auris','private');
    await neon.getByText('PRUEBA',{exact:true}).waitFor({state:'hidden',timeout:7500});
    await neon.getByText('Sincronizado',{exact:true}).waitFor();
    await send('stop');
    await Promise.all(views.map(page=>page.locator('#track').waitFor({state:'hidden'})));
    await send('publish','playing','Volvió el reproductor','','private');
    await send('start');
    await Promise.all(views.map(page=>page.getByText('Volvió el reproductor',{exact:true}).waitFor()));
    assert.deepEqual(views.map(page=>page.url()),ids.map(id=>base+'/overlay/'+id+'/'));
    await send('publish','playing','https://privado.invalid/audio.mp3','Auris','private');
    await Promise.all(views.map(page=>page.locator('#track').waitFor({state:'hidden'})));
    assert.deepEqual(errors,[]);
    assert.ok(requests.every(url=>url.startsWith(base+'/')));
    console.log('PASS: actual OBS Browser URLs + WS, two animated designs, pause/idle, private metadata, styling, scoped demo, reduced motion, reconnect and transparent canvas');
    processFixture.stdin.end();
  }finally{
    if(browser) await browser.close();
    processFixture.kill();
    await rm(tmp,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1});
