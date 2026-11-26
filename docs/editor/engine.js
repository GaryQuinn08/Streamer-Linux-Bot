/* Motor del editor y runtime de las exportaciones. Sin librerías ni servicios externos. */
(() => {
  "use strict";

  const MARKUP = [
    '<article class="card">',
    '  <div class="eyebrow">{platform}</div>',
    '  <strong class="title">{title}</strong>',
    '  <p class="body">{body}</p>',
    '</article>'
  ].join("\n");
  const CSS = [
    '/* Cambia aquí los estilos de la tarjeta. */',
    '.card { border-radius: .72em; }',
    '.title { letter-spacing: -.02em; }',
    '.body { line-height: 1.35; }'
  ].join("\n");
  const DEFAULTS = Object.freeze({
    alert: Object.freeze({ name: "Mi alerta", title: "{alert_title}", body: "{alert_text}", accent: "#9ef3c9",
      textColor: "#f5fcff", background: "#13282b", duration: 6, size: 27, max: 1, opacity: 94, markup: MARKUP, css: CSS }),
    chat: Object.freeze({ name: "Mi chat", title: "{user}", body: "{text}", accent: "#b2d5ff",
      textColor: "#f2f7ff", background: "#142333", duration: 0, size: 22, max: 6, opacity: 86, markup: MARKUP, css: CSS }),
    events: Object.freeze({ name: "Mis últimos eventos", title: "{user}", body: "{event_label}", accent: "#e8b6ff",
      textColor: "#fff7ff", background: "#261a34", duration: 0, size: 22, max: 5, opacity: 90, markup: MARKUP, css: CSS })
  });
  const RANGES = Object.freeze({ duration: [0, 300], size: [12, 72], max: [1, 24], opacity: [0, 100],
    enterMs: [0, 3000], exitMs: [0, 3000] });
  const MOTION_DEFAULTS = Object.freeze({ enter: "none", exit: "none", enterMs: 320, exitMs: 240 });
  const MOTIONS = Object.freeze({
    fade: [["none", "none"], ["none", "none"]],
    "slide-up": [["translateY(24px)", "none"], ["none", "translateY(-24px)"]],
    "slide-left": [["translateX(24px)", "none"], ["none", "translateX(-24px)"]],
    zoom: [["scale(.88)", "none"], ["none", "scale(.88)"]],
    pop: [["scale(.84)", "scale(1.06)", "none"], ["none", "scale(1.05)", "scale(.88)"]]
  });
  const EFFECTS = Object.freeze(["none", ...Object.keys(MOTIONS)]);
  const TIMING_IN = "cubic-bezier(.2,.75,.35,1)";
  const TIMING_OUT = "ease-in";
  const localAnimations = new WeakMap();
  const LIMITS = Object.freeze({ name: 60, title: 220, body: 380, markup: 12000, css: 12000 });
  const SAFE_TAGS = new Set(("article aside b blockquote br code dd div dl dt em footer h1 h2 h3 h4 header hr i li mark ol p pre section small span strong time u ul").split(" "));
  const VOID_TAGS = new Set(["br", "hr"]);
  const ENTITIES = Object.freeze({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0" });

  const ONSCREEN_CSS = `
    *{box-sizing:border-box}
    :root{font-family:"Noto Sans","Segoe UI",Arial,sans-serif}
    html,body{margin:0;overflow:hidden;background:transparent;width:100%;height:100%;color:var(--ink)}
    #slb-stage{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:flex-end;gap:.35em;padding:.66em}
    body[data-mode="alert"] #slb-stage{align-items:center;justify-content:center}
    .slb-row{display:block;flex:0 0 auto;max-width:100%;min-width:0;overflow-wrap:anywhere}
    .card{position:relative;min-width:0;padding:.52em .83em;background:var(--card);border-left:.15em solid var(--accent);box-shadow:0 .16em .8em #0003;overflow:hidden}
    body[data-mode="alert"] .card{max-width:min(94vw,38em);min-width:min(68vw,13em);padding:.72em 1.15em;box-shadow:0 .3em 1.35em #0006}
    .eyebrow{color:var(--accent);font-weight:740;font-size:.55em;letter-spacing:.14em;text-transform:uppercase;margin:0 0 .36em}
    .eyebrow:empty{display:none}
    .title{display:block;margin:0 0 .16em;color:var(--ink);font-weight:750;line-height:1.15;font-size:1em}
    .title:empty{display:none}
    .body{margin:0;white-space:pre-wrap;color:var(--ink);font-size:.82em}
    .body:empty{display:none}
    .slb-simulation{display:inline-block;margin-bottom:.22em;padding:.16em .35em;border-radius:.28em;background:#402f16;color:#ffe0a3;font-size:.52em;font-weight:780;letter-spacing:.08em}
  `;

  function own(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function normalize(values = {}, presetOnly = false) {
    const mode = typeof values.mode === "string" && own(DEFAULTS, values.mode) ? values.mode : "alert";
    const clean = { ...MOTION_DEFAULTS, ...DEFAULTS[mode], mode };
    for (const [name, max] of Object.entries(LIMITS)) {
      if (presetOnly && (name === "css" || name === "markup")) continue;
      if (typeof values[name] === "string") clean[name] = values[name].slice(0, max);
    }
    for (const key of ["accent", "textColor", "background"]) {
      if (typeof values[key] === "string" && /^#[0-9a-f]{6}$/i.test(values[key])) clean[key] = values[key];
    }
    for (const stage of ["enter", "exit"]) {
      if (EFFECTS.includes(values[stage])) clean[stage] = values[stage];
    }
    for (const [key, [low, high]] of Object.entries(RANGES)) {
      const n = values[key];
      if (typeof n === "number" && Number.isFinite(n)) clean[key] = Math.min(high, Math.max(low, Math.round(n)));
    }
    if (mode === "alert") clean.max = 1;
    return clean;
  }

  function decodeEntities(text) {
    return text.replace(/&(#x[0-9a-f]{1,6}|#[0-9]{1,7}|[a-z]{2,5});/gi, (token, body) => {
      const key = body.toLowerCase();
      if (own(ENTITIES, key)) return ENTITIES[key];
      if (!key.startsWith("#")) return token;
      const hex = key[1] === "x";
      const code = Number.parseInt(key.slice(hex ? 2 : 1), hex ? 16 : 10);
      if (code <= 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return "\uFFFD";
      return String.fromCodePoint(code);
    });
  }

  // Construye DOM solo con etiquetas locales y atributos sin destinos ni eventos.
  // No insertamos ni parseamos como HTML el contenido de la persona.
  function parseMarkup(raw) {
    if (!raw.trim()) throw new Error("Escribe algo de HTML antes de previsualizar o exportar.");
    if (raw.length > LIMITS.markup) throw new Error("El HTML supera el límite de 12 000 caracteres.");
    const fragment = document.createDocumentFragment();
    const stack = [{ name: "", node: fragment }];
    let offset = 0;
    while (offset < raw.length) {
      const parent = stack.at(-1).node;
      if (raw[offset] !== "<") {
        let end = raw.indexOf("<", offset);
        if (end === -1) end = raw.length;
        parent.append(document.createTextNode(decodeEntities(raw.slice(offset, end))));
        offset = end;
        continue;
      }

      const part = /^<(\/?)([a-z][a-z0-9]*)([^<>]*)>/i.exec(raw.slice(offset));
      if (!part) throw new Error("Revisa el HTML: usa &lt; para mostrar el símbolo < como texto.");
      const closing = !!part[1];
      const name = part[2].toLowerCase();
      let attributes = part[3];
      if (!SAFE_TAGS.has(name)) throw new Error("La etiqueta <" + name + "> no se admite en este editor.");
      offset += part[0].length;
      if (closing) {
        if (attributes.trim() || stack.at(-1).name !== name) throw new Error("Revisa el cierre de </" + name + ">.");
        stack.pop();
        continue;
      }

      const selfClosing = attributes.trimEnd().endsWith("/");
      if (selfClosing) attributes = attributes.trimEnd().slice(0, -1);
      const el = document.createElement(name);
      const seen = new Set();
      while (attributes.trim()) {
        const parsed = /^\s+([a-z][a-z-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(attributes);
        if (!parsed) throw new Error("Escribe los atributos entre comillas. Solo se permiten class y dir.");
        const key = parsed[1].toLowerCase();
        const value = parsed[2] ?? parsed[3];
        if (seen.has(key)) throw new Error("No repitas el atributo " + key + ".");
        if (key === "class") {
          if (!/^[a-z0-9_ -]{0,240}$/i.test(value)) throw new Error("La clase tiene caracteres no permitidos.");
        } else if (key === "dir") {
          if (!["ltr", "rtl", "auto"].includes(value)) throw new Error("dir solo admite ltr, rtl o auto.");
        } else {
          throw new Error("El atributo " + key + " no se admite. Usa class o dir.");
        }
        seen.add(key);
        el.setAttribute(key, value);
        attributes = attributes.slice(parsed[0].length);
      }
      parent.append(el);
      if (!VOID_TAGS.has(name)) {
        if (selfClosing) throw new Error("Cierra <" + name + "> con </" + name + ">.");
        if (stack.length > 24) throw new Error("Hay demasiados elementos HTML anidados.");
        stack.push({ name, node: el });
      }
    }
    if (stack.length > 1) throw new Error("Falta el cierre </" + stack.at(-1).name + ">.");
    return fragment;
  }

  function checkCss(raw) {
    if (raw.length > LIMITS.css) throw new Error("El CSS supera el límite de 12 000 caracteres.");
    // Ningún cierre de elemento ni secuencias de escape capaces de ocultar una función URL.
    if (/[<\\]/.test(raw)) throw new Error("El CSS no admite la marca < ni secuencias de escape.");
    const readable = raw.replace(/\/\*[\s\S]*?\*\//g, "");
    if (/@(?:import|font-face|namespace)\b|(?:url|src|(?:-webkit-)?image-set|expression)\s*\(/i.test(readable)) {
      throw new Error("Quita las referencias externas del CSS, como url(), image-set() o @import.");
    }
    return raw;
  }

  function frames(effect, exit = false) {
    const transforms = MOTIONS[effect][exit ? 1 : 0];
    return transforms.map((transform, at) => ({
      transform, opacity: (exit ? at === transforms.length - 1 : at === 0) ? 0 : 1,
      offset: at === 0 ? 0 : at === transforms.length - 1 ? 1 : .68
    }));
  }

  function animationCss(config, replay) {
    const enter = config.enter !== "none" && config.enterMs > 0;
    const exit = config.exit !== "none" && config.exitMs > 0;
    if (!enter && !exit) return "";
    const css = [];
    const rule = (name, keyframes) => "@keyframes " + name + "{"
      + keyframes.map((frame) => (frame.offset * 100) + "%{opacity:" + frame.opacity + ";transform:" + frame.transform + "}").join("")
      + "}";
    const entry = enter ? "slb-entry " + config.enterMs + "ms " + TIMING_IN + " both" : "";
    const leave = exit ? "slb-leave " + config.exitMs + "ms " + TIMING_OUT + " forwards" : "";
    if (enter) {
      css.push(rule("slb-entry", frames(config.enter)));
      css.push(".slb-row.slb-enter{animation:" + entry + "}");
    }
    if (exit) {
      css.push(rule("slb-leave", frames(config.exit, true)));
      css.push(".slb-row.slb-exit{animation:" + leave + "}");
    }
    if (replay) {
      // En la vista de prueba se resume el tiempo de espera, no el efecto.
      const delay = Math.max(950, (enter ? config.enterMs : 0) + 160);
      css.push(".slb-motion-preview .slb-row{animation:"
        + [entry, leave ? leave + " " + delay + "ms" : ""].filter(Boolean).join(",") + "}");
    }
    css.push("@media(prefers-reduced-motion:reduce){.slb-row.slb-enter,.slb-row.slb-exit,.slb-motion-preview .slb-row{animation:none!important}}");
    return css.join("\n");
  }

  // Reproducción local, solo por petición explícita en un pin de la galería.
  function animateSample(element, input) {
    if (typeof element?.animate !== "function") return false;
    localAnimations.get(element)?.();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
    const config = normalize(input, true);
    const enter = config.enter !== "none" && config.enterMs > 0;
    const exit = config.exit !== "none" && config.exitMs > 0;
    if (!enter && !exit) return false;
    let active = enter ? element.animate(frames(config.enter), {
      duration: config.enterMs, easing: TIMING_IN, fill: "backwards"
    }) : null;
    const timer = exit ? setTimeout(() => {
      active?.cancel();
      active = element.animate(frames(config.exit, true), { duration: config.exitMs, easing: TIMING_OUT });
    }, Math.max(950, (enter ? config.enterMs : 0) + 160)) : null;
    localAnimations.set(element, () => {
      if (timer !== null) clearTimeout(timer);
      active?.cancel();
    });
    return true;
  }

  function properties(config, style, replay) {
    const digits = config.background.slice(1).match(/.{2}/g);
    const rgb = digits.map((part) => parseInt(part, 16)).join(", ");
    return `:root{--accent:${config.accent};--ink:${config.textColor};--card:rgba(${rgb},${config.opacity / 100});font-size:${config.size}px}\n${ONSCREEN_CSS}\n${style}\n${animationCss(config, replay)}`;
  }

  // Se evalúa aquí para la previsualización y se copia al HTML descargado.
  // Mantener esta función autocontenida.
  function renderEngine(doc, config, card, stage) {
    function read(object, key) {
      return Object.prototype.hasOwnProperty.call(object, key) ? object[key] : "";
    }
    function value(input) {
      if (typeof input === "string") return input.slice(0, 700);
      if ((typeof input === "number" && Number.isFinite(input)) || typeof input === "boolean") return String(input);
      return "";
    }
    function expand(template, fields) {
      return String(template).replace(/\{([a-z][a-z0-9_]{0,40})\}/gi,
        (_, key) => value(read(fields, key)));
    }
    function adapt(msg) {
      const data = Object.create(null);
      const raw = config.mode === "alert" ? msg.variables : msg.data;
      if (raw && typeof raw === "object") {
        for (const key of Object.keys(raw).slice(0, 48)) {
          if (/^[a-z][a-z0-9_]{0,40}$/i.test(key)) data[key] = value(raw[key]);
        }
      }
      const type = value(msg.type) || data.type || "";
      const platform = value(msg.platform) || data.platform || "";
      if (platform) data.platform = platform;
      data.type = type;
      data.event_type = type;
      if (typeof msg.user === "string") data.user = value(msg.user);
      if (typeof msg.simulated === "boolean") data.simulated = value(msg.simulated);
      const ts = msg.ts ?? data.ts;
      if (ts !== undefined && ts !== "" && Number.isFinite(Number(ts))) {
        data.ts = String(ts);
        const when = new Date(Number(ts) * 1000);
        if (Number.isFinite(when.getTime())) data.time = when.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
      }
      if (config.mode === "alert") {
        data.event_text = data.text || "";
        data.alert_title = value(msg.title);
        data.alert_text = value(msg.text);
        data.title = data.alert_title;
        data.text = data.alert_text;
        data.image = value(msg.image);
      } else if (config.mode === "chat") {
        data.text = value(msg.text);
      } else {
        const descriptions = { chat: "escribió en el chat", follow: "ahora te sigue", sub: "se suscribió",
          gift: "envió un regalo", donation: "hizo una donación", bits: "envió bits",
          raid: "hizo una raid", points: "canjeó puntos", like: "dio Me gusta", share: "compartió el directo" };
        data.event_label = read(descriptions, type) || type;
      }
      return data;
    }
    const timers = new Map();
    function remove(row) {
      if (timers.has(row)) clearTimeout(timers.get(row));
      timers.delete(row);
      row.remove();
    }
    function dismiss(row) {
      if (config.exit !== "none" && config.exitMs > 0
          && !doc.defaultView?.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        row.classList.remove("slb-enter");
        row.classList.add("slb-exit");
        timers.set(row, setTimeout(() => remove(row), config.exitMs));
      } else remove(row);
    }
    function draw(msg, timed = false, labelSample = false, animate = false) {
      if (!msg || typeof msg !== "object") return;
      const fields = adapt(msg);
      const slots = Object.create(null);
      for (const k of Object.keys(fields)) slots[k] = fields[k];
      slots.title = expand(config.title, fields);
      slots.body = expand(config.body, fields);
      const row = doc.createElement("div");
      row.className = "slb-row";
      if (animate && config.enter !== "none" && config.enterMs > 0) row.classList.add("slb-enter");
      if (labelSample && (msg.simulated === true || msg.variables?.simulated === true)) {
        const badge = doc.createElement("span");
        badge.className = "slb-simulation";
        badge.textContent = "PRUEBA";
        row.append(badge);
      }
      const clone = card.cloneNode(true);
      const walker = doc.createTreeWalker(clone, 4); // NodeFilter.SHOW_TEXT
      while (walker.nextNode()) {
        const text = walker.currentNode;
        text.nodeValue = expand(text.nodeValue, slots);
      }
      row.append(clone);
      stage.append(row);
      while (stage.children.length > config.max) remove(stage.firstElementChild);
      const sampled = msg.simulated === true || msg.variables?.simulated === true;
      const duration = sampled && labelSample ? Math.min(config.duration || 8, 8) : config.duration;
      if (timed && duration > 0) timers.set(row, setTimeout(() => dismiss(row), duration * 1000));
    }
    return { draw };
  }

  // Toda exportación es un archivo autónomo. Solo hace una suscripción local
  // si el bot la sirve bajo su ruta de overlay; la descarga no busca nada.
  function startRuntime(config) {
    const card = document.getElementById("slb-template").content;
    const stage = document.getElementById("slb-stage");
    const { draw } = renderEngine(document, config, card, stage);
    const local = /^https?:$/.test(location.protocol) && ["127.0.0.1", "localhost"].includes(location.hostname);
    const overlay = /^\/overlay\/([a-z0-9][a-z0-9_-]{0,63})(?:\/(?:index\.html)?)?$/.exec(location.pathname);
    if (!local || !overlay) {
      if (config.example) draw(config.example, false, true, true);
      return;
    }
    const target = config.mode === "alert" ? overlay[1] : config.mode === "chat" ? "multi-chat" : "event-feed";
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    function connect() {
      const socket = new WebSocket(scheme + "//" + location.host + "/ws/" + target);
      socket.addEventListener("message", (event) => {
        if (typeof event.data !== "string" || event.data.length > 16000) return;
        let msg;
        try { msg = JSON.parse(event.data); } catch { return; }
        if (!msg || typeof msg !== "object") return;
        if (config.mode === "alert" && (msg.channel !== "alert" || msg.overlay !== target)) return;
        if (config.mode === "chat" && msg.channel !== "chat") return;
        if (config.mode === "events" && msg.channel !== "event") return;
        draw(msg, true, true, true);
      });
      socket.addEventListener("close", () => setTimeout(connect, 2000));
    }
    connect();
  }

  function safeScript(value) {
    return JSON.stringify(value).replace(/[<>&\u2028\u2029]/g, (char) =>
      "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"));
  }

  function escape(text) {
    return text.replace(/[<>&"]/g, (character) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[character]));
  }

  function build(input, samples, exported, { replay = false } = {}) {
    const config = normalize(input);
    const previewMotion = replay && !exported;
    const template = parseMarkup(config.markup);
    const css = properties(config, checkCss(config.css), previewMotion);
    const policy = exported
      ? "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src ws://127.0.0.1:* ws://localhost:* wss://127.0.0.1:* wss://localhost:*; base-uri 'none'; form-action 'none'"
      : "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
    const header = "<!doctype html><html lang=\"es\"><meta charset=\"utf-8\">"
      + '<meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width, initial-scale=1">'
      + '<meta http-equiv="Content-Security-Policy" content="' + policy + '">'
      + "<title>" + escape(config.name || "Overlay") + "</title><style>" + css + "</style>"
      + '<body data-mode="' + config.mode + '">';
    const stage = document.createElement("main");
    stage.id = "slb-stage";
    if (previewMotion) stage.className = "slb-motion-preview";
    if (exported) {
      const templateEl = document.createElement("template");
      templateEl.id = "slb-template";
      templateEl.content.append(template);
      const runtime = { mode: config.mode, title: config.title, body: config.body,
        max: config.max, duration: config.duration, enter: config.enter, exit: config.exit,
        enterMs: config.enterMs, exitMs: config.exitMs, example: samples.at(-1) };
      const metadata = '<script id="slb-design-v1" type="application/json">' + safeScript(config) + '</script>';
      return header + stage.outerHTML + templateEl.outerHTML + metadata + "<script>"
        + renderEngine.toString() + "\n(" + startRuntime.toString() + ")(" + safeScript(runtime) + ");"
        + "</script></body></html>";
    }
    const { draw } = renderEngine(document, config, template, stage);
    for (const msg of samples) draw(msg);
    return header + stage.outerHTML + "</body></html>";
  }

  function fromUrl(location) {
    const requested = new URLSearchParams(location.search).get("mode");
    const hash = location.hash;
    if (hash.startsWith("#preset=") && hash.length <= 4200) {
      try {
        const json = JSON.parse(decodeURIComponent(hash.slice(8)));
        if (json && typeof json === "object" && !Array.isArray(json)) return normalize(json, true);
      } catch { /* Un enlace defectuoso no altera las plantillas. */ }
    }
    return normalize({ mode: requested });
  }

  function reopen(source) {
    if (source.length > 250000) throw new Error("El archivo supera 250 KB.");
    // Lee solo nuestros metadatos; nunca se interpreta el HTML seleccionado.
    const match = /<script id="slb-design-v1" type="application\/json">([\s\S]*?)<\/script>/.exec(source);
    if (!match) throw new Error("El archivo no tiene los ajustes del editor. Puedes pegar su marcado seguro en el campo HTML.");
    let data;
    try { data = JSON.parse(match[1]); } catch { throw new Error("El archivo tiene ajustes incompletos."); }
    if (!data || !own(DEFAULTS, data.mode)) throw new Error("La plantilla guardada no se reconoce.");
    const config = normalize(data);
    parseMarkup(config.markup);
    checkCss(config.css);
    return config;
  }

  window.SLB_EDITOR = { DEFAULTS, EFFECTS, normalize, build, fromUrl, reopen, animateSample };
})();
