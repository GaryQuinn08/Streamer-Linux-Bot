const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function main() {
  const root = path.join(__dirname, "../slbot/music_extension");
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1/*"]);
  assert.equal(manifest.content_scripts, undefined);
  const mod = fs.readFileSync(path.join(root, "providers.js"), "utf8");
  const {parseCode, providerFor} = await import("data:text/javascript;base64," + Buffer.from(mod).toString("base64"));
  for (const [url, expected] of [
    ["https://open.spotify.com/track/demo", "spotify"],
    ["https://music.youtube.com/watch?v=a", "youtube"],
    ["https://music.amazon.com.mx/", "amazon"],
    ["https://music.apple.com/mx", "apple"],
    ["https://www.deezer.com/mx/", "deezer"],
    ["https://listen.tidal.com/", "tidal"],
    ["https://youtube.com/", ""],
    ["file:///tmp/song.mp3", ""],
    ["https://music.amazon.com.evil.invalid/", ""],
    ["https://private.invalid/?token=x", ""],
    ["http://music.youtube.com/", ""],
    ["https://music.youtube.com:8000/", ""]
  ]) assert.equal(providerFor(url), expected, url);
  const secret = "a".repeat(43);
  assert.deepEqual(parseCode("8765." + secret), {port:8765, token:secret});
  assert.equal(parseCode("65536." + secret), null);

  const calls = [];
  const store = {};
  let listener, tab = {id:1, url:"https://music.youtube.com/watch?v=a"};
  const sandbox = {
    URL, AbortSignal, providerFor, parseCode, crypto:{randomUUID:() => "test"},
    fetch: async (url, options) => { calls.push({url, options}); return {ok:true}; },
    chrome:{
      runtime:{getURL: path => "chrome-extension://mock/" + path, onMessage:{addListener: fn => {listener = fn;}}},
      tabs:{query:async()=>[tab], get:async()=>tab, onRemoved:{addListener(){}}},
      storage:{session:{get:async()=>store, set:async x=>Object.assign(store,x), remove:async()=>delete store.active}},
      scripting:{executeScript:async options => {
        if (options.files) {
          assert.deepEqual(Array.from(options.files), ["collector.js"]);
          return [];
        }
        assert.equal(options.world, "MAIN");
        assert.equal(options.target.tabId, 1);
        sandbox.location = new URL(tab.url);
        sandbox.navigator = {mediaSession:{metadata:{title:"Canción", artist:"Artista", artwork:"no compartir"}, playbackState:"playing"}};
        sandbox.document = {querySelectorAll: () => []};
        return [{result:options.func(...options.args)}];
      }}
    }
  };
  const code = fs.readFileSync(path.join(root,"worker.js"),"utf8").replace(/^import[^\n]+\n/, "");
  vm.runInNewContext(code, sandbox);
  function send(kind, sender, fields={}) {
    return new Promise(resolve => listener({kind,...fields}, sender, resolve));
  }
  const popup = {url:"chrome-extension://mock/popup.html"};
  const sender = {url:tab.url, tab:{id:1}, frameId:0};
  assert.equal((await send("start", {url:"https://music.youtube.com/"}, {code:"8765." + secret})).ok, false);
  assert.equal((await send("start", popup, {code:"8765." + secret})).active, "youtube");
  assert.equal(calls[0].url, "http://127.0.0.1:8765/api/music/browser");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    provider:"youtube",state:"playing",title:"Canción",artist:"Artista"
  });
  assert.equal((await send("tick", {...sender, tab:{id:2}})).ok, false);
  assert.equal(calls.length, 1);
  assert.equal((await send("tick", sender)).ok, true);
  tab = {...tab,url:"https://private.invalid/"};
  await send("tick", sender);
  assert.equal(JSON.parse(calls.at(-1).options.body).state, "idle");
  await send("stop", popup);
  assert.equal(store.active, undefined);
  assert.equal((await send("tick", sender)).ok, false);
  console.log("Provider allowlist, explicit tab selection, loopback and track-only sample verified");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
