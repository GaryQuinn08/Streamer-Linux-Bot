/* v1: solo ajustes, sin JavaScript, CSS, HTML, fuentes, imágenes u otros recursos de terceros. */
(() => {
  "use strict";
  const FORMAT = "slb-pack";
  const VERSION = 1;
  const LIMIT = 65536;
  const KINDS = Object.freeze(["alert", "chat", "events", "banner", "camera", "starting", "brb", "ending"]);
  const LABELS = Object.freeze({
    alert: "Alerta", chat: "Multichat", events: "Actividad", banner: "Banner",
    camera: "Marco de cámara", starting: "Empezando", brb: "En pausa", ending: "Cierre"
  });
  const DYNAMIC = new Set(KINDS.slice(0, 3));
  const STATIC = Object.freeze({
    banner: { title: "ESTAMOS EN DIRECTO", body: "Qué gusto verte por aquí", positionY: 92, width: 63, size: 34, opacity: 96, radius: 11 },
    camera: { title: "EN VIVO", body: "", positionY: 50, width: 95, size: 18, opacity: 95, radius: 14 },
    starting: { title: "Empezamos pronto", body: "Ponte a gusto y saluda en el chat", positionY: 50, width: 80, size: 68, opacity: 100, radius: 21 },
    brb: { title: "Volvemos enseguida", body: "Gracias por esperar", positionY: 50, width: 80, size: 66, opacity: 100, radius: 18 },
    ending: { title: "¡Gracias por estar aquí!", body: "Nos vemos en el próximo directo", positionY: 50, width: 80, size: 64, opacity: 100, radius: 18 }
  });
  const HEX = /^#[a-f0-9]{6}$/i;
  const MOTION = ["none", "fade", "slide-up", "slide-left", "zoom", "pop"];
  const RANGES = Object.freeze({ duration: [0, 300], size: [12, 72], max: [1, 24], opacity: [0, 100],
    enterMs: [0, 3000], exitMs: [0, 3000], positionX: [0, 100], positionY: [0, 100], width: [24, 100],
    radius: [0, 48], padding: [0, 48], border: [0, 16] });
  const DESIGN_KEYS = Object.freeze(["mode", "name", "title", "body", "accent", "textColor", "background",
    ...Object.keys(RANGES), "enter", "exit", "align", "showPlatform"]);
  const isRecord = (object) => !!object && typeof object === "object" && !Array.isArray(object);
  function text(value, max, fallback = "") {
    if (typeof value !== "string") return fallback;
    // Comparte el límite en puntos de código con el importador Python. Sustituye
    // sustitutos Unicode sueltos de un JSON externo antes de exportarlo.
    let result = "", count = 0;
    for (const char of value) {
      if (count++ === max) break;
      result += /^[\uD800-\uDFFF]$/.test(char) ? "\uFFFD" : char;
    }
    return result;
  }

  function defaults(kind) {
    const base = {
      mode: kind, name: LABELS[kind], title: "", body: "", accent: "#9ef3c9", textColor: "#f5fcff",
      background: "#13282b", duration: 6, size: 27, max: 1, opacity: 94, enter: "none", exit: "none",
      enterMs: 320, exitMs: 240, positionX: 50, positionY: 50, width: 75, radius: 16, padding: 17, border: 4,
      align: "left", showPlatform: true
    };
    if (DYNAMIC.has(kind)) {
      const editor = window.SLB_EDITOR;
      return editor?.normalize ? { ...base, ...editor.normalize({ mode: kind }, true) } : {
        ...base, title: kind === "alert" ? "{alert_title}" : "{user}",
        body: kind === "alert" ? "{alert_text}" : kind === "chat" ? "{text}" : "{event_label}",
        ...(kind === "alert" ? {} : { duration: 0, max: 5, size: 22, positionY: 100, width: 100 })
      };
    }
    return { ...base, ...STATIC[kind], mode: "static", duration: 0, align: "center", showPlatform: false };
  }

  function component(kind, input = {}) {
    if (!KINDS.includes(kind) || !isRecord(input)) throw Error("El pack contiene una pieza desconocida o incompleta.");
    const base = defaults(kind);
    const design = Object.fromEntries(DESIGN_KEYS.map((key) => [key, base[key]]));
    design.name = text(input.name, 60).trim() || base.name;
    design.title = text(input.title, 220, base.title);
    design.body = text(input.body, 380, base.body);
    for (const key of ["accent", "textColor", "background"]) {
      if (typeof input[key] === "string" && HEX.test(input[key])) design[key] = input[key].toLowerCase();
    }
    for (const [key, [min, max]] of Object.entries(RANGES)) {
      if (typeof input[key] === "number" && Number.isFinite(input[key])) {
        design[key] = Math.max(min, Math.min(max, Math.round(input[key])));
      }
    }
    for (const key of ["enter", "exit"]) if (MOTION.includes(input[key])) design[key] = input[key];
    if (["left", "center", "right"].includes(input.align)) design.align = input.align;
    if (typeof input.showPlatform === "boolean") design.showPlatform = input.showPlatform;
    if (!DYNAMIC.has(kind)) {
      design.duration = 0;
      design.max = 1;
      design.enter = design.exit = "none";
      design.showPlatform = false;
    } else if (kind === "alert") {
      design.max = 1;
    }
    return { kind, design };
  }

  function normalize(pack) {
    if (!isRecord(pack) || pack.format !== FORMAT || pack.version !== VERSION) {
      throw Error("El archivo no es un pack de Streamer Linux Bot v1.");
    }
    const name = text(pack.name, 60).trim();
    if (!name) throw Error("Escribe un nombre para el pack.");
    if (!Array.isArray(pack.components) || pack.components.length < 1 || pack.components.length > KINDS.length) {
      throw Error("Selecciona entre 1 y " + KINDS.length + " piezas.");
    }
    const seen = new Set();
    const components = [];
    for (const piece of pack.components) {
      if (!isRecord(piece) || !isRecord(piece.design)) throw Error("Faltan ajustes en una pieza del pack.");
      if (seen.has(piece.kind)) throw Error("Un pack solo puede incluir una pieza de cada tipo.");
      const clean = component(piece.kind, piece.design);
      seen.add(clean.kind);
      components.push(clean);
    }
    return { format: FORMAT, version: VERSION, name, description: text(pack.description, 240).trim(), components };
  }

  function parse(source) {
    if (typeof source !== "string" || source.length > LIMIT || new TextEncoder().encode(source).length > LIMIT) {
      throw Error("El pack supera el límite de 64 KiB.");
    }
    let value;
    try { value = JSON.parse(source.replace(/^\uFEFF/, "")); }
    catch { throw Error("El contenido del pack no es JSON válido."); }
    return normalize(value);
  }

  const serialize = (pack) => JSON.stringify(normalize(pack), null, 2) + "\n";

  function escape(value) {
    return value.replace(/[<>&"]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[char]);
  }

  function staticPage(piece) {
    const { kind, design: d } = piece;
    const frame = kind === "camera";
    const scene = kind !== "banner" && !frame;
    const colors = "font-family:system-ui,Segoe UI,sans-serif;color:" + d.textColor
      + ";--accent:" + d.accent + ";--base:" + d.background + ";--base-alpha:" + d.background
      + Math.round(d.opacity * 255 / 100).toString(16).padStart(2, "0")
      + ";--radius:" + d.radius + "px;--padding:" + d.padding + "px;--rule:" + d.border + "px";
    const css = `*{box-sizing:border-box}
html,body{width:100%;height:100%;margin:0;overflow:hidden;background:transparent}
body{${colors}}
.outer{position:absolute;overflow:hidden;isolation:isolate}
h1,p{margin:0;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere}
h1{font-size:1em;line-height:1.08;font-weight:790;letter-spacing:-.03em}
p{margin-top:.4em;font-size:.52em;line-height:1.38}
p:empty{display:none}
.frame{inset:0;border:var(--rule) solid var(--accent);border-radius:var(--radius);background:transparent}
.frame:before,.frame:after{content:"";position:absolute;width:20%;height:24%;max-width:130px;max-height:130px;pointer-events:none;border-style:solid;border-color:var(--accent);border-width:0;border-radius:calc(var(--radius) / 2)}
.frame:before{inset:4px auto auto 4px;border-top-width:3px;border-left-width:3px}
.frame:after{inset:auto 4px 4px auto;border-bottom-width:3px;border-right-width:3px}
.frame .copy{position:absolute;bottom:0;left:0;background:var(--base-alpha);border-radius:0 var(--radius) 0 0;padding:calc(var(--padding) * .6) var(--padding);border-right:3px solid var(--accent)}
.banner,.scene .copy{padding:var(--padding);border-radius:var(--radius);border-block-start:var(--rule) solid var(--accent)}
.banner{background:var(--base-alpha);box-shadow:0 10px 44px #0005}
.scene{inset:0;background:var(--base-alpha);background-image:radial-gradient(ellipse at 83% 13%,${d.accent}70,transparent 42%),repeating-linear-gradient(135deg,transparent 0 18px,${d.accent}20 19px 20px,transparent 21px 38px)}
.scene:before,.scene:after{content:"";position:absolute;border:1px solid var(--accent);width:44vw;height:44vw;border-radius:var(--radius);transform:rotate(-22deg);opacity:.27;z-index:-1}
.scene:before{top:-30vw;right:-16vw}.scene:after{bottom:-29vw;left:-13vw}
.scene .copy{position:absolute;background:var(--base-alpha);box-shadow:0 0 100px #0004;min-height:4rem}
.banner,.scene .copy{inset-inline-start:${d.positionX * (100 - d.width) / 100}%;top:${d.positionY}%;width:${d.width}%;transform:translateY(-${d.positionY}%);text-align:${d.align}}
.copy{font-size:clamp(12px,${(d.size / 1920 * 100).toFixed(3)}vw,${d.size}px)}
.banner.copy,.frame .copy{font-size:clamp(12px,${(d.size / 960 * 100).toFixed(3)}vw,${d.size}px)}`;
    const copy = "<h1>" + escape(d.title) + "</h1><p>" + escape(d.body) + "</p>";
    const markup = frame
      ? '<main class="outer frame">' + ((d.title || d.body) ? '<div class="copy">' + copy + "</div>" : "") + "</main>"
      : scene ? '<main class="outer scene"><div class="copy">' + copy + "</div></main>"
        : '<main class="outer banner copy">' + copy + "</main>";
    const metadata = JSON.stringify(piece).replace(/[<>&\u2028\u2029]/g,
      (char) => "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"));
    return '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
      + "<title>" + escape(d.name) + "</title><style>" + css + "</style><body>" + markup
      + '<script id="slb-pack-component-v1" type="application/json">' + metadata + "</script></body></html>";
  }

  function componentDocument(raw, exported) {
    if (!isRecord(raw) || !isRecord(raw.design)) throw Error("No se reconoció la pieza.");
    const piece = component(raw.kind, raw.design);
    if (!DYNAMIC.has(piece.kind)) return staticPage(piece);
    const editor = window.SLB_EDITOR;
    if (!editor?.build) throw Error("El exportador del editor no está disponible.");
    const kind = piece.kind;
    const base = { simulated: true, user: "Luna", platform: "tiktok", ts: 1735689600 };
    const preview = kind === "alert"
      ? { ...base, channel: "alert", type: "gift", title: "¡Luna envió un regalo!", text: "Rose ×3",
        variables: { user: "Luna", platform: "tiktok", type: "gift", gift_name: "Rose", count: 3 } }
      : kind === "chat" ? { ...base, channel: "chat", type: "chat", text: "¡Qué buen directo!" }
        : { ...base, channel: "event", type: "gift", data: { gift_name: "Rose", count: 3 } };
    return editor.build(piece.design, [preview], exported);
  }

  const buildComponent = (raw) => componentDocument(raw, true);
  const previewComponent = (raw) => componentDocument(raw, false);

  function componentFromHTML(source) {
    if (typeof source !== "string" || source.length > 250000) throw Error("El HTML supera el límite de 250 KB.");
    const saved = /<script id="slb-pack-component-v1" type="application\/json">([\s\S]*?)<\/script>/.exec(source);
    if (saved) {
      let piece;
      try { piece = JSON.parse(saved[1]); }
      catch { throw Error("No se reconocen los ajustes de la pieza."); }
      if (!isRecord(piece) || !isRecord(piece.design)) throw Error("La pieza tiene ajustes inválidos.");
      return component(piece.kind, piece.design);
    }
    const editor = window.SLB_EDITOR;
    if (!editor?.reopen) throw Error("El lector de diseños del editor no está disponible.");
    const normalized = editor.reopen(source);
    // La versión compartible conserva solo ajustes; nunca conserva HTML ni CSS personalizado.
    return component(normalized.mode, normalized);
  }

  function basename(value, fallback) {
    const clean = String(value).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 75);
    return clean || fallback;
  }

  function downloadFile(source, filename, type) {
    const url = URL.createObjectURL(new Blob([source], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return filename;
  }

  function download(pack, name) {
    const normalized = normalize(pack);
    return downloadFile(serialize(normalized), basename(name || normalized.name, "overlay-pack") + ".slbpack", "application/json;charset=utf-8");
  }

  function downloadComponent(piece, name) {
    const html = buildComponent(piece);
    return downloadFile(html, basename(name || piece.design.name, "overlay") + ".html", "text/html;charset=utf-8");
  }

  window.SLB_PACK = Object.freeze({ FORMAT, VERSION, KINDS, LABELS, DESIGN_KEYS,
    normalize, parse, serialize, component, buildComponent, previewComponent, componentFromHTML, download, downloadComponent });
})();
