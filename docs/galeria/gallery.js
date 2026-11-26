/* Galería declarativa de Streamer Linux Bot. No recibe HTML ni JavaScript del catálogo. */
(() => {
  "use strict";
  const get = (id) => document.getElementById(id);
  const social = window.SLB_SOCIAL;
  const designKey = (model) => "gallery:" + model.id;
  const storageKey = "streamer-linux-bot.gallery.favorites.v1";
  const modes = { alert: "Alerta", chat: "Multichat", events: "Eventos" };
  const artKeys = new Set(["orbit", "wave", "grid", "ribbon", "spark", "scan"]);
  const shapeKeys = new Set(["wide", "square", "tall"]);
  const hex = /^#[0-9a-f]{6}$/i;
  const ranges = { duration: [0, 300], size: [12, 72], max: [1, 24], opacity: [0, 100],
    enterMs: [0, 3000], exitMs: [0, 3000], positionX: [0, 100], positionY: [0, 100], width: [24, 100],
    radius: [0, 48], padding: [0, 48], border: [0, 16] };
  const effects = new Set(window.SLB_EDITOR?.EFFECTS || ["none"]);
  const labelLimits = { name: 60, title: 220, body: 380 };
  const validId = /^[a-z0-9][a-z0-9-]{0,63}$/;
  const githubLogin = /^[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38}$/i;
  const requestedCreator = new URLSearchParams(location.search).get("creador") || "";
  const selectedCreator = validId.test(requestedCreator) ? requestedCreator : "";
  const chips = Array.from(document.querySelectorAll("[data-mode].chip"));
  const knownIds = new Set();
  let favorites = loadFavorites();
  let catalogue = [];
  let selectedMode = "all";
  let savedOnly = false;
  let isLoaded = false;

  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  function safeText(value, limit) {
    return typeof value === "string" ? value.trim().slice(0, limit) : "";
  }

  function loadFavorites() {
    try {
      const values = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (Array.isArray(values)) return new Set(values.slice(0, 1000).filter((key) => typeof key === "string" && validId.test(key)));
    } catch { /* El almacenamiento puede estar bloqueado. */ }
    return new Set();
  }

  function saveFavorites() {
    try {
      localStorage.setItem(storageKey, JSON.stringify([...favorites].slice(0, 1000)));
    } catch {
      document.querySelector(".privacy").textContent = "El navegador no permite guardarlos; tus favoritos duran esta visita.";
    }
  }

  function modelFrom(entry) {
    if (!entry || typeof entry.id !== "string" || !validId.test(entry.id) || knownIds.has(entry.id)) return null;
    const raw = entry.preset;
    if (!raw || typeof raw.mode !== "string" || !own(modes, raw.mode)) return null;
    const name = safeText(raw.name, labelLimits.name);
    if (!name) return null;
    const preset = { mode: raw.mode, name };
    for (const [key, max] of Object.entries(labelLimits)) {
      if (key !== "name" && typeof raw[key] === "string") preset[key] = raw[key].slice(0, max);
    }
    for (const key of ["accent", "textColor", "background"]) {
      if (typeof raw[key] === "string" && hex.test(raw[key])) preset[key] = raw[key];
    }
    for (const [key, [min, max]] of Object.entries(ranges)) {
      if (typeof raw[key] === "number" && Number.isFinite(raw[key])) {
        preset[key] = Math.min(max, Math.max(min, Math.round(raw[key])));
      }
    }
    for (const key of ["enter", "exit"]) {
      if (effects.has(raw[key])) preset[key] = raw[key];
    }
    if (["left", "center", "right"].includes(raw.align)) preset.align = raw.align;
    if (typeof raw.showPlatform === "boolean") preset.showPlatform = raw.showPlatform;
    const description = safeText(entry.description, 240);
    const author = safeText(entry.author, 80) || "Comunidad";
    const creatorId = typeof entry.creatorId === "string" && validId.test(entry.creatorId) ? entry.creatorId : "";
    const official = creatorId === "streamer-linux-bot";
    const candidate = typeof entry.submittedBy === "string" ? entry.submittedBy : "";
    const issue = Number.isSafeInteger(entry.sourceIssue) && entry.sourceIssue > 0 ? entry.sourceIssue : 0;
    const submittedBy = issue && githubLogin.test(candidate) ? candidate : "";
    const license = safeText(entry.license, 35) || "Sin licencia indicada";
    const topics = Array.isArray(entry.topics) ? entry.topics.slice(0, 16).map((word) => safeText(word, 35)).join(" ") : "";
    const renderArt = artKeys.has(entry.art) ? entry.art : "orbit";
    const shape = shapeKeys.has(entry.shape) ? entry.shape : "square";
    const example = entry.example === "follow" || entry.example === "donation" ? entry.example : "gift";
    knownIds.add(entry.id);
    return { id: entry.id, description, author, creatorId, official, submittedBy, issue, license, renderArt, shape, preset, example,
      index: normalized([name, description, author, submittedBy, modes[preset.mode], topics].join(" ")) };
  }

  function normalized(text) {
    return text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es").trim();
  }

  function add(parent, tag, value, cls) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value) node.textContent = value;
    parent.append(node);
    return node;
  }

  function now() {
    return Math.floor(Date.now() / 1000);
  }

  function samples(model) {
    if (model.preset.mode === "alert") {
      if (model.example === "follow") {
        return [{ channel: "alert", user: "Mar", platform: "twitch", type: "follow", ts: now(), title: "¡Bienvenida, Mar!", text: "Nuevo seguimiento", variables: { user: "Mar", platform: "twitch", type: "follow" }, simulated: true }];
      }
      if (model.example === "donation") {
        return [{ channel: "alert", user: "Sol", platform: "youtube", type: "donation", ts: now(), title: "¡Gracias por el apoyo, Sol!", text: "Donación de 25 MXN", variables: { user: "Sol", platform: "youtube", type: "donation", amount: 25, currency: "MXN" }, simulated: true }];
      }
      return [{ channel: "alert", user: "Luna", platform: "tiktok", type: "gift", ts: now(), title: "¡Luna envió un regalo!", text: "Rose ×3", variables: { user: "Luna", platform: "tiktok", type: "gift", gift_name: "Rose", count: 3 }, simulated: true }];
    }
    if (model.preset.mode === "chat") {
      return [
        { channel: "chat", user: "Luna", platform: "twitch", type: "chat", text: "¡Buen directo! ¿Qué jugamos hoy?" },
        { channel: "chat", user: "Sol", platform: "youtube", type: "chat", text: "Saludos desde México." },
        { channel: "chat", user: "Paz", platform: "kick", type: "chat", text: "Lista para la siguiente partida." }
      ].map((entry) => ({ ...entry, simulated: true }));
    }
    return [
      { channel: "event", user: "Luna", platform: "tiktok", type: "gift", data: { gift_name: "Rose", count: 3 } },
      { channel: "event", user: "Mar", platform: "twitch", type: "follow", data: {} },
      { channel: "event", user: "Sol", platform: "youtube", type: "donation", data: { amount: 25, currency: "MXN" } }
    ].map((entry) => ({ ...entry, ts: now(), simulated: true }));
  }

  function sampleTpl(input, fields) {
    return input.replace(/\{([a-z][a-z0-9_]{0,40})\}/gi, (_match, key) =>
      own(fields, key) ? String(fields[key] ?? "") : "");
  }

  function sampleFields(message) {
    const eventLabels = { gift: "envió un regalo", follow: "ahora te sigue", donation: "hizo una donación" };
    return { ...message.data, ...message.variables,
      user: message.user, platform: message.platform, type: message.type, event_type: message.type, text: message.text,
      event_label: eventLabels[message.type] || message.type,
      alert_title: message.title, alert_text: message.text, title: message.title };
  }

  function pinPreview(card, model, target) {
    const media = add(card, "a", "", "pin-preview");
    media.href = target;
    media.setAttribute("aria-label", "Abrir vista editable de " + model.preset.name);
    media.dataset.shape = model.shape;
    media.dataset.art = model.renderArt;
    media.dataset.mode = model.preset.mode;
    const accent = model.preset.accent || "#a7f2cc";
    const background = model.preset.background || "#203440";
    media.style.setProperty("--accent", accent);
    media.style.setProperty("--accent-dim", accent + "48");
    media.style.setProperty("--halo", accent + "45");
    media.style.setProperty("--ink", model.preset.textColor || "#f0f6fb");
    media.style.setProperty("--sample", background);
    media.style.setProperty("--panel-sample", background + Math.round((model.preset.opacity ?? 90) * 2.55).toString(16).padStart(2, "0"));
    add(media, "span", modes[model.preset.mode], "kind");
    const stage = add(media, "div", "", "peek-stage");
    stage.setAttribute("aria-hidden", "true");
    const fixtures = samples(model).slice(0, model.shape === "tall" ? 3 : 2);
    for (const fixture of fixtures) {
      const fields = sampleFields(fixture);
      const title = model.preset.title ?? (model.preset.mode === "alert" ? "{alert_title}" : "{user}");
      const body = model.preset.body ?? (model.preset.mode === "alert" ? "{alert_text}" : model.preset.mode === "chat" ? "{text}" : "{event_label}");
      const peek = add(stage, "div", "", "peek-card");
      add(peek, "span", fixture.platform, "platform");
      add(peek, "strong", sampleTpl(title, fields));
      add(peek, "p", sampleTpl(body, fields));
    }
    return stage;
  }

  function download(model) {
    try {
      const editor = window.SLB_EDITOR;
      if (!editor) throw Error("El exportador no está disponible. Abre el editor e inténtalo otra vez.");
      const html = editor.build(editor.normalize(model.preset, true), samples(model), true);
      const object = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = object;
      anchor.download = model.id + ".html";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(object), 2000);
      void social?.downloadStarted(designKey(model));
      get("notice").textContent = "Descargado " + model.preset.name + ". Impórtalo en Overlays → Importar HTML…";
    } catch {
      get("notice").textContent = "No se pudo descargar el diseño. Prueba el botón Personalizar y descarga desde el editor.";
    }
  }

  function setFavoriteButton(model) {
    const isFavorite = favorites.has(model.id);
    model.favorite.textContent = isFavorite ? "♥" : "♡";
    model.favorite.setAttribute("aria-pressed", String(isFavorite));
    model.favorite.setAttribute("aria-label", (isFavorite ? "Quitar de favoritos: " : "Guardar en favoritos: ") + model.preset.name);
    model.favorite.title = isFavorite ? "Quitar de favoritos" : "Guardar en favoritos";
  }

  function toggleFavorite(model) {
    const old = favorites.has(model.id);
    if (old) favorites.delete(model.id);
    else favorites.add(model.id);
    saveFavorites();
    setFavoriteButton(model);
    if (savedOnly) {
      render();
      // Si la ficha desapareció, deja el foco en el primer resultado, o en la salida del filtro.
      get("designs").querySelector("button.favorite")?.focus();
      if (!get("empty").hidden) get("clear-filters").focus();
    } else {
      updateCount();
    }
    get("notice").textContent = model.preset.name + (old ? " se quitó de favoritos." : " se guardó en favoritos.");
  }

  function createCard(model) {
    const card = document.createElement("article");
    card.className = "pin";
    card.dataset.id = model.id;
    const target = "../editor/#preset=" + encodeURIComponent(JSON.stringify(model.preset));
    const stage = pinPreview(card, model, target);
    const motion = (model.preset.enter && model.preset.enter !== "none" && model.preset.enterMs !== 0)
      || (model.preset.exit && model.preset.exit !== "none" && model.preset.exitMs !== 0);
    if (motion) {
      const play = add(card, "button", "", "play-motion");
      play.type = "button";
      play.setAttribute("aria-label", "Reproducir animación de " + model.preset.name);
      play.title = "Reproducir animación";
      play.addEventListener("click", () => {
        const played = window.SLB_EDITOR?.animateSample(stage, model.preset);
        get("notice").textContent = played
          ? "Reproduciendo la animación de " + model.preset.name + "."
          : "La animación está desactivada o el navegador prefiere movimiento reducido.";
      });
    }
    model.favorite = add(card, "button", "", "favorite");
    model.favorite.type = "button";
    model.favorite.addEventListener("click", () => toggleFavorite(model));
    setFavoriteButton(model);
    const body = add(card, "div", "", "pin-body");
    add(body, "h2", model.preset.name, "pin-name");
    add(body, "p", model.description, "description");
    const credit = add(body, "p", "Diseño de ", "meta");
    if (model.creatorId) {
      const profile = add(credit, "a", model.author);
      profile.href = "./?creador=" + encodeURIComponent(model.creatorId);
    } else add(credit, "span", model.author);
    if (model.official) add(credit, "span", " · Colección oficial");
    add(credit, "span", " · ");
    if (social?.licenseLink) social.licenseLink(credit, model.license);
    else add(credit, "span", "Ver licencia en el catálogo");
    if (model.submittedBy) {
      const contribution = add(body, "p", "Compartido por ", "meta");
      const owner = add(contribution, "a", "@" + model.submittedBy);
      owner.href = "https://github.com/" + encodeURIComponent(model.submittedBy);
      const origin = add(contribution, "a", " · Ver aporte");
      origin.href = "https://github.com/GaryQuinn08/Streamer-Linux-Bot/issues/" + model.issue;
    }
    const actions = add(body, "div", "", "pin-actions");
    const edit = add(actions, "a", "Personalizar", "button primary");
    edit.href = target;
    edit.setAttribute("aria-label", "Personalizar " + model.preset.name);
    const save = add(actions, "button", "Descargar HTML", "button secondary");
    save.type = "button";
    save.setAttribute("aria-label", "Descargar HTML de " + model.preset.name);
    save.addEventListener("click", () => download(model));
    social?.controls(body, { key: designKey(model), name: model.preset.name, signIn: "../cuenta/" });
    return card;
  }

  function updateCount() {
    get("favorite-count").textContent = String(catalogue.filter((model) => favorites.has(model.id)).length);
  }

  function render() {
    for (const chip of chips) chip.setAttribute("aria-pressed", String(chip.dataset.mode === selectedMode));
    get("favorites").setAttribute("aria-pressed", String(savedOnly));
    if (!isLoaded) return;
    const words = normalized(get("search").value).split(/\s+/).filter(Boolean);
    const matches = catalogue.filter((card) => {
      if (selectedCreator && selectedCreator !== card.creatorId) return false;
      if (savedOnly && !favorites.has(card.id)) return false;
      if (selectedMode !== "all" && selectedMode !== card.preset.mode) return false;
      return words.every((word) => card.index.includes(word));
    });
    get("designs").replaceChildren(...matches.map((model) => model.node));
    get("status").textContent = matches.length === 1 ? "1 diseño" : matches.length + " diseños";
    get("empty").hidden = matches.length > 0;
    if (!matches.length) {
      const noneSaved = savedOnly && !catalogue.some((card) => favorites.has(card.id));
      const missing = selectedCreator && !catalogue.some(card => card.creatorId === selectedCreator);
      get("empty-title").textContent = missing ? "No encontramos este perfil" : noneSaved ? "Todavía no tienes favoritos" : "No encontramos diseños";
      get("empty-body").textContent = noneSaved
        ? "Pulsa el corazón de un diseño para guardarlo en este navegador."
        : "Prueba con otra búsqueda o elige una categoría distinta.";
    }
    updateCount();
  }

  for (const chip of chips) chip.addEventListener("click", () => { selectedMode = chip.dataset.mode; render(); });
  get("search").addEventListener("input", render);
  get("favorites").addEventListener("click", () => { savedOnly = !savedOnly; selectedMode = "all"; render(); });
  get("clear-filters").addEventListener("click", () => {
    if (selectedCreator) { location.assign("./"); return; }
    get("search").value = "";
    selectedMode = "all";
    savedOnly = false;
    render();
    get("search").focus();
  });

  fetch("./designs.json?v=credits-preview-1").then((response) => {
    if (!response.ok) throw Error("No se pudo leer el catálogo");
    return response.json();
  }).then((entries) => {
    if (!Array.isArray(entries)) throw Error("Catálogo inválido");
    catalogue = entries.slice(0, 200).map(modelFrom).filter(Boolean);
    if (selectedCreator) {
      const creator = catalogue.find(item => item.creatorId === selectedCreator);
      if (creator) {
        get("gallery-title").textContent = creator.author;
        get("gallery-description").textContent = creator.official
          ? "Diseños de la colección oficial de Streamer Linux Bot."
          : "Diseños atribuidos a este creador y publicados tras revisión.";
        document.title = creator.author + " · Galería de overlays";
      }
      get("leave-creator").hidden = false;
    }
    for (const item of catalogue) item.node = createCard(item);
    isLoaded = true;
    get("designs").setAttribute("aria-busy", "false");
    render();
    void social?.googleSession();
    void social?.refresh(catalogue.map(designKey));
  }).catch(() => {
    get("status").textContent = "No se pudo cargar la galería.";
    get("designs").setAttribute("aria-busy", "false");
    get("empty").hidden = false;
    get("empty-title").textContent = "No pudimos abrir el catálogo";
    get("empty-body").textContent = "Recarga la página o abre la galería desde GitHub Pages o desde un servidor local.";
    get("clear-filters").hidden = true;
  });
})();
