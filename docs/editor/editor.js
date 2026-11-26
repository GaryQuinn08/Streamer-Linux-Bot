/* Controles del editor; no consulta cuentas, APIs ni contenido de terceros. */
(() => {
  "use strict";

  const get = (id) => document.getElementById(id);
  const api = window.SLB_EDITOR;
  const modeInfo = {
    alert: "Una tarjeta que aparece cuando una acción del bot envía una alerta a este overlay.",
    chat: "Una lista de mensajes nuevos de las plataformas conectadas al bot.",
    events: "Una lista de eventos nuevos del directo, como regalos, seguidores o donaciones."
  };
  const inputKeys = ["name", "title", "body", "accent", "textColor", "background", "size", "duration", "opacity", "max", "enter", "exit", "enterMs", "exitMs", "markup", "css"];
  const numberKeys = new Set(["size", "duration", "opacity", "max", "enterMs", "exitMs"]);
  const fieldFor = (key) => get(key === "css" ? "custom-css" : key);
  const titles = {
    gift: "Regalo de TikTok", follow: "Nuevo seguidor", donation: "Donación", bits: "Bits de Twitch", sub: "Suscripción",
    twitch: "Chat de Twitch", youtube: "Chat de YouTube", kick: "Chat de Kick", tiktok: "Chat de TikTok",
    chat: "Mensaje de chat"
  };

  const ts = () => Math.floor(Date.now() / 1000);
  const commonFixtures = {
    gift: () => ({ platform: "tiktok", user: "Luna", type: "gift", ts: ts(),
      data: { gift_name: "Rose", count: 3, value: 3 }, title: "¡Luna envió un regalo!", text: "Rose ×3" }),
    follow: () => ({ platform: "twitch", user: "Mar", type: "follow", ts: ts(),
      data: {}, title: "¡Un nuevo seguidor!", text: "Gracias por seguir a Mar." }),
    donation: () => ({ platform: "youtube", user: "Sol", type: "donation", ts: ts(),
      data: { amount: 25, currency: "MXN", value: 25, text: "Sigue así 🤍" },
      title: "¡Gracias por el apoyo, Sol!", text: "Donación de 25 MXN." }),
    bits: () => ({ platform: "twitch", user: "Mar", type: "bits", ts: ts(), data: { bits: 100, value: 100 },
      title: "¡Lluvia de Bits!", text: "100 Bits" }),
    sub: () => ({ platform: "twitch", user: "Sol", type: "sub", ts: ts(), data: { tier: "1000" },
      title: "¡Nueva suscripción!", text: "Bienvenido al canal" }),
    chat: () => ({ platform: "kick", user: "Paz", type: "chat", ts: ts(), data: { text: "¿Qué jugamos hoy?" } })
  };
  const chatFixtures = {
    twitch: ["Luna", "¡Hola, chat! ¿Cómo les va?"],
    youtube: ["Mar", "Saludos desde México 🇲🇽"],
    kick: ["Paz", "Listos para la siguiente partida."],
    tiktok: ["Sol", "Pasaba a saludar, ¡buen directo!"]
  };
  const byMode = {
    alert: ["gift", "follow", "donation", "bits", "sub"],
    chat: ["twitch", "youtube", "kick", "tiktok"],
    events: ["gift", "follow", "donation", "chat"]
  };
  const drafts = new Map();
  let placeholders = [];
  let mode = "alert";
  let lastTagTarget = "body";
  let raf = 0;
  let previewRestore = null;
  const motionLabels = {
    none: "Ninguna", fade: "Fundido", "slide-up": "Deslizar arriba",
    "slide-left": "Deslizar a la izquierda", zoom: "Zoom", pop: "Rebote"
  };
  for (const id of ["enter", "exit"]) {
    for (const key of api.EFFECTS) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = motionLabels[key];
      get(id).append(option);
    }
  }

  function status(message, error = false) {
    get("status").textContent = message;
    get("status").dataset.error = String(error);
  }

  function sample(key) {
    if (mode === "chat") {
      const [user, text] = chatFixtures[key] || chatFixtures.twitch;
      return { channel: "chat", platform: key, user, text, ts: ts(), simulated: true };
    }
    const event = (commonFixtures[key] || commonFixtures.gift)();
    if (mode === "alert") {
      return { channel: "alert", platform: event.platform, user: event.user, type: event.type,
        ts: event.ts, title: event.title, text: event.text, simulated: true, variables: event.data };
    }
    return { channel: "event", platform: event.platform, user: event.user, type: event.type,
      ts: event.ts, data: event.data, simulated: true };
  }

  function state() {
    const values = { mode };
    for (const key of inputKeys) {
      const input = fieldFor(key);
      values[key] = numberKeys.has(key) ? input.valueAsNumber : input.value;
    }
    return api.normalize(values);
  }

  function showPreview(replay = false) {
    if (previewRestore !== null) {
      clearTimeout(previewRestore);
      previewRestore = null;
    }
    const config = state();
    get("enterMs").disabled = config.enter === "none";
    get("exitMs").disabled = config.exit === "none";
    const enter = config.enter !== "none" && config.enterMs > 0;
    const exit = config.exit !== "none" && config.exitMs > 0;
    get("replay").disabled = !enter && !exit;
    try {
      get("preview").srcdoc = api.build(config, placeholders, false, { replay });
      get("preview-help").textContent = placeholders.length
        ? "La muestra es local y no se conecta a chats. Pulsa Limpiar para quitarla."
        : "Sin muestras visibles. Elige un ejemplo y pulsa Simular evento.";
      if (replay && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        get("preview-help").textContent = "El navegador tiene activada la preferencia de movimiento reducido.";
      } else if (replay && exit) {
        const wait = Math.max(950, (enter ? config.enterMs : 0) + 160);
        previewRestore = setTimeout(() => showPreview(), wait + config.exitMs + 280);
        get("preview-help").textContent = "Reproduciendo una muestra. El tiempo de espera se acorta solo en la vista previa.";
      }
      get("preview-help").dataset.error = "false";
      get("export").disabled = false;
    } catch (error) {
      get("preview-help").textContent = error instanceof Error ? error.message : "Revisa el HTML o CSS.";
      get("preview-help").dataset.error = "true";
      get("export").disabled = true;
      get("replay").disabled = true;
    }
  }

  function queuePreview() {
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      raf = 0;
      showPreview();
    });
  }

  function selectTab(tabId, focus = false) {
    for (const tab of ["html", "css"]) {
      const selected = tab === tabId;
      get("tab-" + tab).setAttribute("aria-selected", String(selected));
      get("tab-" + tab).tabIndex = selected ? 0 : -1;
      get("panel-" + tab).hidden = !selected;
    }
    if (focus) get("tab-" + tabId).focus();
  }

  function open(values) {
    mode = values.mode;
    get("mode").value = mode;
    get("mode-description").textContent = modeInfo[mode];
    for (const key of inputKeys) fieldFor(key).value = values[key];
    get("max-field").hidden = mode === "alert";
    const choices = byMode[mode].map((key) => {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = titles[key];
      return option;
    });
    get("fixture").replaceChildren(...choices);
    placeholders = [sample(choices[0].value)];
    populateTags();
    showPreview();
  }

  function selectTagTarget(target) {
    lastTagTarget = target;
    get("tag-target").value = target;
  }

  function insertTag(token) {
    const field = get(lastTagTarget);
    if (field.id === "markup") selectTab("html");
    const start = field.selectionStart ?? field.value.length;
    const end = field.selectionEnd ?? field.value.length;
    if (field.maxLength > 0 && field.value.length - (end - start) + token.length > field.maxLength) {
      status("El campo no tiene espacio para otra etiqueta.", true);
      return;
    }
    field.setRangeText(token, start, end, "end");
    field.focus();
    status("Etiqueta " + token + " insertada en " + field.dataset.tagTarget + ".");
    queuePreview();
  }

  async function copy(value) {
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(value); return true; }
      catch { /* Las políticas de algunos navegadores necesitan otra vía. */ }
    }
    const backup = document.createElement("textarea");
    backup.className = "sr-only";
    backup.value = value;
    const focused = document.activeElement;
    document.body.append(backup);
    backup.select();
    let ok = false;
    try { ok = document.execCommand("copy"); }
    finally { backup.remove(); focused?.focus(); }
    return ok;
  }

  function makeButton(label, callback, description) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-label", description);
    button.addEventListener("click", callback);
    return button;
  }

  function populateTags() {
    const items = window.SLB_TAGS?.[mode] || [];
    const list = items.map(({ key, label, description, example }) => {
      const li = document.createElement("li");
      const head = document.createElement("div");
      head.className = "tag-head";
      const token = "{" + key + "}";
      const code = document.createElement("code");
      code.textContent = token;
      head.append(code,
        makeButton("Insertar", () => insertTag(token), "Insertar etiqueta " + label),
        makeButton("Copiar", async () => {
          if (await copy(token)) status("Etiqueta " + token + " copiada.");
          else status("No se pudo copiar. Puedes seleccionar la etiqueta con el ratón.", true);
        }, "Copiar etiqueta " + label));
      const caption = document.createElement("p");
      const captionLabel = document.createElement("strong");
      captionLabel.textContent = label + ". ";
      caption.append(captionLabel, document.createTextNode(description));
      const usage = document.createElement("p");
      const exampleValue = document.createElement("code");
      exampleValue.textContent = example;
      usage.append(document.createTextNode("Ejemplo: "), exampleValue);
      li.append(head, caption, usage);
      return li;
    });
    get("tag-list").replaceChildren(...list);
  }

  function download() {
    try {
      const config = state();
      const output = api.build(config, [sample(get("fixture").value)], true);
      const filename = (config.name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
        .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 56) || "overlay") + ".html";
      const url = URL.createObjectURL(new Blob([output], { type: "text/html;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      status("Descargado: " + filename + ". Impórtalo desde Overlays → Importar HTML…");
    } catch (error) {
      status(error instanceof Error ? error.message : "No se pudo exportar el overlay.", true);
    }
  }

  async function reopen(file) {
    if (!file) return;
    try {
      if (file.size > 250000) throw new Error("El archivo supera 250 KB.");
      const restored = api.reopen(await file.text());
      drafts.set(mode, state());
      open(restored);
      status("Diseño abierto. Puedes editarlo y exportarlo otra vez.");
    } catch (error) {
      status(error instanceof Error ? error.message : "No se pudo abrir el diseño.", true);
    }
  }

  get("streamlabs-apply").addEventListener("click", () => {
    const note = get("streamlabs-status");
    try {
      const event = get("streamlabs-event").value;
      const text = window.SLB_STREAMLABS.convert(get("streamlabs-text").value, event);
      if (mode !== "alert") open(api.normalize({ mode: "alert" }));
      get("body").value = text;
      get("fixture").value = event;
      placeholders = [sample(event)];
      showPreview();
      note.textContent = "Mensaje adaptado. Revisa la muestra, descarga el HTML e impórtalo como overlay.";
      note.dataset.error = "false";
    } catch (error) {
      note.textContent = error.message;
      note.dataset.error = "true";
    }
  });

  get("mode").addEventListener("change", () => {
    const target = get("mode").value;
    drafts.set(mode, state());
    open(drafts.get(target) || api.normalize({ mode: target }));
    status("Plantilla cargada.");
  });
  get("reset").addEventListener("click", () => {
    if (window.confirm("¿Restablecer el diseño actual? Los cambios que no hayas descargado se perderán.")) {
      drafts.delete(mode);
      open(api.normalize({ mode }));
      status("Ajustes restablecidos.");
    }
  });
  for (const key of inputKeys) fieldFor(key).addEventListener("input", queuePreview);
  for (const target of ["title", "body", "markup"]) {
    get(target).addEventListener("focus", () => selectTagTarget(target));
  }
  get("tag-target").addEventListener("change", (event) => selectTagTarget(event.currentTarget.value));
  get("play").addEventListener("click", () => {
    if (mode === "alert") placeholders = [];
    placeholders.push(sample(get("fixture").value));
    placeholders = placeholders.slice(-24);
    showPreview();
  });
  get("replay").addEventListener("click", () => {
    if (!placeholders.length) placeholders = [sample(get("fixture").value)];
    showPreview(true);
  });
  get("clear").addEventListener("click", () => { placeholders = []; showPreview(); });
  for (const tab of ["html", "css"]) {
    const button = get("tab-" + tab);
    button.addEventListener("click", () => selectTab(tab));
    button.addEventListener("keydown", (event) => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const other = event.key === "Home" ? "html" : event.key === "End" ? "css" : tab === "html" ? "css" : "html";
        selectTab(other, true);
      }
    });
  }
  get("export").addEventListener("click", download);
  get("reopen").addEventListener("click", () => get("design-file").click());
  get("design-file").addEventListener("change", (event) => {
    reopen(event.target.files[0]);
    event.target.value = "";
  });
  function shareableSettings() {
    const { mode: source, name, title, body, accent, textColor, background, duration, size, max, opacity,
      enter, exit, enterMs, exitMs } = state();
    return { mode: source, name, title, body, accent, textColor, background, duration, size, max, opacity,
      enter, exit, enterMs, exitMs };
  }

  get("share").addEventListener("click", async () => {
    const uri = new URL(location.href);
    uri.search = "";
    uri.hash = "preset=" + encodeURIComponent(JSON.stringify(shareableSettings()));
    if (await copy(uri.toString())) status("Enlace copiado. Incluye textos, aspecto y animación, no cambios de HTML o CSS.");
    else status("No se pudo copiar el enlace de ajustes.", true);
  });

  get("suggest-design").addEventListener("click", () => {
    const preset = shareableSettings();
    if ([preset.name, preset.title, preset.body].some(value => /(?:https?:\/\/|www\.)/i.test(value))) {
      status("Quita los enlaces de los textos antes de proponer el diseño. No compartas URL privadas.", true);
      return;
    }
    const dest = new URL("https://github.com/GaryQuinn08/Streamer-Linux-Bot/issues/new");
    dest.searchParams.set("title", "Diseño para la galería: " + (preset.name || "Sin nombre"));
    dest.searchParams.set("body", [
      "## Descripción", "Describe el diseño y cuándo usarlo.", "",
      "## Autor y licencia", "Indica quién lo creó y qué licencia permite reutilizarlo.", "",
      "## Ajustes visuales", "~~~json", JSON.stringify(preset, null, 2), "~~~", "",
      "Revisa antes de enviar. No incluyas URL privadas, tokens ni credenciales. La propuesta requiere revisión."
    ].join("\n"));
    const link = document.createElement("a");
    link.href = dest.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.click();
    status("Se abrió un borrador en GitHub. Revísalo allí antes de enviarlo.");
  });

  open(api.fromUrl(location));
})();
