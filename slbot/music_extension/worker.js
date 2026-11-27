import {parseCode, providerFor} from "./providers.js";

function readMetadata(origin) {
  if (location.origin !== origin) return null;
  const meta = navigator.mediaSession?.metadata;
  if (typeof meta?.title !== "string" || !meta.title.trim()) return null;
  const declared = navigator.mediaSession?.playbackState;
  const media = [...document.querySelectorAll("audio, video")].filter(item => !item.ended && item.readyState > 0);
  const playing = declared === "playing" || media.some(item => !item.paused);
  const paused = !playing && (declared === "paused" || media.some(item => item.paused && item.currentTime > 0));
  return {
    state: playing ? "playing" : paused ? "paused" : "idle",
    title: Array.from(meta.title.slice(0, 360)).slice(0, 160).join(""),
    artist: typeof meta.artist === "string" ? Array.from(meta.artist.slice(0, 300)).slice(0, 140).join("") : ""
  };
}

async function report(session, track = null) {
  const fallback = {state:"idle", title:"", artist:""};
  let reply;
  try {
    reply = await fetch("http://127.0.0.1:" + session.port + "/api/music/browser", {
      method:"POST", redirect:"error", credentials:"omit", cache:"no-store", signal:AbortSignal.timeout(2000),
      headers:{"Authorization":"Bearer " + session.token, "Content-Type":"application/json"},
      body:JSON.stringify({provider:session.provider, ...(track || fallback)})
    });
  } catch { return {ok:false, error:"No se pudo conectar al bot local. Comprueba que esté abierto."}; }
  if (!reply.ok) return {ok:false, error:"Revisa que el servicio coincida con Ahora suena y copia un código actual."};
  return {ok:true, waiting:!track || track.state === "idle" || !track.title};
}

async function waitForTrack(session) {
  try {
    const tab = await chrome.tabs.get(session.tabId);
    if (providerFor(tab.url) !== session.provider) return null;
    const results = await chrome.scripting.executeScript({
      target:{tabId:session.tabId}, world:"MAIN", func:readMetadata, args:[new URL(tab.url).origin]
    });
    const current = await chrome.tabs.get(session.tabId);
    return providerFor(current.url) === session.provider ? results[0]?.result || null : null;
  } catch { return null; }
}

async function command(message, sender) {
  const existing = (await chrome.storage.session.get("active")).active;
  if (message.kind === "tick") {
    if (!existing || sender.frameId !== 0 || sender.tab?.id !== existing.tabId
        || providerFor(sender.url) !== existing.provider) return {ok:false};
    const track = await waitForTrack(existing);
    const current = (await chrome.storage.session.get("active")).active;
    if (!current || current.session !== existing.session) return {ok:false};
    return report(existing, track);
  }
  if (sender.url !== chrome.runtime.getURL("popup.html")) return {ok:false};
  if (message.kind === "state") return {ok:true, active:existing?.provider || ""};
  if (message.kind === "stop") {
    await chrome.storage.session.remove("active");
    if (existing) await report(existing);
    return {ok:true};
  }
  if (message.kind !== "start") return {ok:false};
  const pairing = parseCode(message.code);
  const [tab] = await chrome.tabs.query({active:true, currentWindow:true});
  const provider = providerFor(tab?.url);
  if (!pairing || !provider || !Number.isInteger(tab?.id)) {
    return {ok:false,error:"Abre una pestaña de un servicio compatible y pega un código de Ahora suena."};
  }
  const session = {...pairing, tabId:tab.id, provider, session:crypto.randomUUID()};
  const result = await report(session, await waitForTrack(session));
  if (!result.ok) return result;
  await chrome.storage.session.set({active:session});
  try {
    await chrome.scripting.executeScript({target:{tabId:tab.id}, files:["collector.js"]});
  } catch {
    await chrome.storage.session.remove("active");
    await report(session);
    return {ok:false,error:"Abre la pestaña de música y vuelve a pulsar Compartir."};
  }
  return {...result, active:provider};
}

let serial = Promise.resolve();
function ordered(operation) {
  const result = serial.then(operation);
  serial = result.catch(() => {});
  return result;
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  ordered(() => command(message || {}, sender)).then(respond).catch(() =>
    respond({ok:false,error:"No se pudo compartir esta pestaña."}));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId => ordered(async () => {
  const {active} = await chrome.storage.session.get("active");
  if (active?.tabId !== tabId) return;
  await chrome.storage.session.remove("active");
  await report(active);
}).catch(() => {}));
