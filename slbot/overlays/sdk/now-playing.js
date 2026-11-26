(() => {
  "use strict";
  const body = document.body, card = document.getElementById("track");
  const title = document.getElementById("title"), artist = document.getElementById("artist");
  const status = document.getElementById("status"), demo = document.getElementById("demo");
  const query = new URLSearchParams(location.search);
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  const id = /^\/overlay\/(now-playing(?:-spectrum)?)(?:\/(?:index\.html)?)?$/.exec(location.pathname)?.[1];
  if (!id || !["127.0.0.1","localhost"].includes(location.hostname)) return;
  const position = Object.freeze({
    "Abajo a la izquierda":"bottom-left","Abajo a la derecha":"bottom-right",
    "Arriba a la izquierda":"top-left","Arriba a la derecha":"top-right"
  });
  const defaults = body.dataset.variant === "vinyl" ? ["#b490ff","#ebfc92","#121629"] : ["#63f6de","#fcc45d","#101b24"];
  const idle = Object.freeze({state:"idle",title:"",artist:""});
  let saved = {}, live = idle, sample = null, sampleTimer, player, retry, wait = 550, shutdown = false;
  let signature = "", revision = 0, animation, showArtist = true;

  function read(key, fallback) {
    if (query.has(key)) return query.get(key);
    return Object.hasOwn(saved,key) ? String(saved[key]) : String(fallback);
  }
  function choice(key, fallback) { return /^(true|1|yes|on|si)$/i.test(read(key,fallback)); }
  function number(key, min, max, fallback) {
    const value = Number(read(key,fallback));
    return Number.isFinite(value) ? Math.max(min, Math.min(max,value)) : fallback;
  }
  function color(key, fallback) {
    const value = read(key,fallback);
    return /^#[a-f0-9]{6}$/i.test(value) ? value : fallback;
  }
  function style() {
    body.style.setProperty("--accent",color("accent",defaults[0]));
    body.style.setProperty("--secondary",color("secondary",defaults[1]));
    const alpha = Math.round(number("opacity",0,100,90) * 255 / 100).toString(16).padStart(2,"0");
    body.style.setProperty("--ink",color("background",defaults[2]) + alpha);
    body.style.setProperty("--width",number("width",17,85,34) + "vw");
    const key = read("position","Abajo a la izquierda");
    body.dataset.position = Object.hasOwn(position,key) ? position[key] : "bottom-left";
    body.dataset.motion = String(choice("motion",true));
    showArtist = choice("showArtist",true);
    artist.hidden = !artist.textContent || !showArtist;
    if (!canAnimate() && animation) {
      animation.cancel();
      animation = null;
      if (card.dataset.state === "idle") card.hidden = true;
    }
  }

  function canAnimate() {
    return typeof card.animate === "function" && body.dataset.motion !== "false" && !media.matches;
  }

  function animate(entering, token) {
    const shift = body.dataset.variant === "vinyl" ? "translateY(1.15em) scale(.975)" : "translateX(-1.35em)";
    const hide = {opacity:0,transform:shift}, show = {opacity:1,transform:"none"};
    animation = card.animate(entering ? [hide,show] : [show,hide], {
      duration:entering ? 480 : 300,fill:"both",easing:entering ? "cubic-bezier(.16,1,.3,1)" : "ease-in"
    });
    const current = animation;
    current.finished.then(() => {
      if (revision !== token) return;
      if (!entering) card.hidden = true;
      current.cancel();
      if (animation === current) animation = null;
    }).catch(() => {});
  }

  function draw(data, isDemo = false, instant = false) {
    const active = (data.state === "playing" || data.state === "paused") && typeof data.title === "string" && data.title.trim();
    if (!active) {
      if (card.dataset.state === "idle" && !instant) return;
      ++revision;
      signature = "";
      card.dataset.state = "idle";
      animation?.cancel();
      animation = null;
      if (card.hidden || instant || !canAnimate()) {
        card.hidden = true;
      } else animate(false,revision);
      return;
    }
    const nextSignature = JSON.stringify([data.title,data.artist,isDemo]);
    const changed = nextSignature !== signature || card.hidden;
    signature = nextSignature;
    title.textContent = Array.from(data.title).slice(0,110).join("");
    artist.textContent = typeof data.artist === "string" ? Array.from(data.artist).slice(0,90).join("") : "";
    artist.hidden = !artist.textContent || !showArtist;
    status.textContent = data.state === "paused" ? "EN PAUSA" : "AHORA SUENA";
    demo.hidden = !isDemo;
    card.dataset.state = data.state;
    card.hidden = false;
    if (changed) {
      ++revision;
      animation?.cancel();
      animation = null;
      if (!instant && canAnimate()) animate(true,revision);
    }
  }

  function clearSample() {
    clearTimeout(sampleTimer);
    sample = null;
  }

  function onMessage(e) {
    if (typeof e.data !== "string" || e.data.length > 4096) return;
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg?.channel === "now-playing-settings" && msg.values && typeof msg.values === "object") {
      saved = msg.values;
      style();
    } else if (msg?.channel === "now-playing") {
      wait = 550;
      live = msg;
      if (!sample) draw(live);
    } else if (msg?.channel === "now-playing-preview") {
      clearSample();
      sample = msg;
      draw(sample,true);
      sampleTimer = setTimeout(() => { clearSample(); draw(live); },5500);
    }
  }

  function connect() {
    if (shutdown) return;
    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    player = new WebSocket(scheme + location.host + "/ws/" + id);
    const socket = player;
    player.onmessage = onMessage;
    player.onclose = () => {
      if (socket !== player || shutdown) return;
      clearSample();
      live = idle;
      draw(idle,false,true);
      retry = setTimeout(connect,wait);
      wait = Math.min(8000,wait * 2);
    };
  }
  window.addEventListener("pagehide", () => {
    shutdown = true;
    clearTimeout(retry);
    player?.close();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) { shutdown = false; connect(); }
  });
  media.addEventListener?.("change",style);
  style();
  window.addEventListener("DOMContentLoaded",connect,{once:true});
})();
