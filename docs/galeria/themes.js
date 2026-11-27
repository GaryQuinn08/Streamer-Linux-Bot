/* Colección oficial de temas declarativos. Sin dependencias de red para descargar. */
(() => {
  "use strict";
  const codec = window.SLB_PACK;
  const social = window.SLB_SOCIAL;
  const get = (key) => document.getElementById(key);
  const section = get("temas");
  const themeGrid = get("theme-grid");
  const search = get("theme-search");
  const filters = [...section.querySelectorAll("[data-theme-filter]")];
  const dialog = get("theme-dialog");
  const palette = /^#[0-9a-f]{6}$/i;
  const categories = ["Luminosos", "Naturales", "Retro", "Tecnológicos"];
  const terrain = ("neon forest coral grain terminal sakura solar polar mars patio arcade crystal star paper hazard depth vitrail coffee circuit prism").split(" ");
  const maxEntries = 20;
  let catalogue = [];
  let activeFilter = "all";
  let previewURL = "";
  let modalOpener = null;
  let shownTheme = null;
  let catalogueReady = false;

  if (new URLSearchParams(location.search).has("creador")) {
    section.hidden = true;
    get("section-links").hidden = true;
    return;
  }

  const safe = (value, limit) => typeof value === "string" ? value.trim().slice(0, limit) : "";
  const keyFor = (theme) => "theme:" + theme.id;
  const indexable = (text) => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es").trim();

  function add(parent, name, text, cls) {
    const node = document.createElement(name);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    parent.append(node);
    return node;
  }

  function button(parent, name, handler, cls) {
    const node = add(parent, "button", name, cls);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function themeFrom(raw, used) {
    if (!raw || typeof raw.id !== "string" || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(raw.id) || used.has(raw.id)
        || !categories.includes(raw.category) || !terrain.includes(raw.art)) return null;
    for (const key of ["accent", "text", "background", "secondary"]) {
      if (typeof raw[key] !== "string" || !palette.test(raw[key])) return null;
    }
    const name = safe(raw.name, 60);
    if (!name) return null;
    const description = safe(raw.description, 240);
    const author = safe(raw.author, 80);
    const radius = Number.isFinite(raw.radius) ? Math.max(0, Math.min(48, Math.round(raw.radius))) : 12;
    const border = Number.isFinite(raw.border) ? Math.max(0, Math.min(16, Math.round(raw.border))) : 4;
    const common = { accent: raw.accent, textColor: raw.text, background: raw.background, radius, border };
    const starting = safe(raw.starting, 90) || "Empezamos pronto";
    const banner = safe(raw.banner, 60) || "En directo";
    const mark = safe(raw.mark, 10) || "VIVO";
    const catalogueIndex = used.size;
    const dynamic = { enter: raw.motion, exit: "fade", enterMs: 310 + catalogueIndex * 9, exitMs: 250 };
    const part = (kind, override) => codec.component(kind, { ...common, name: name + " · " + codec.LABELS[kind], ...override });
    const pieces = [
      part("alert", { ...dynamic, title: "{alert_title}", body: "{alert_text}", duration: 6 + (catalogueIndex % 4),
        size: 36 + (catalogueIndex % 7), opacity: 97, width: 68 + 5 * (catalogueIndex % 3), padding: 21, align: "center" }),
      part("chat", { ...dynamic, title: "{user}", body: "{text}", size: 19 + (catalogueIndex % 6),
        max: 5 + (catalogueIndex % 4), opacity: 88, padding: 10 + (catalogueIndex % 4), width: 100 }),
      part("events", { ...dynamic, title: "{user}", body: "{event_label}", size: 22, max: 4, opacity: 92, width: 100 }),
      part("banner", { title: banner, body: "ESTAMOS EN DIRECTO  /  " + mark, positionX: 13, positionY: 91,
        width: 58 + (catalogueIndex % 4) * 9, padding: 18, opacity: 98, size: 36, align: "left" }),
      part("camera", { title: "●  EN VIVO  /  " + mark, body: "", padding: 11,
        size: 19, border: Math.max(3, border) }),
      part("starting", { title: starting, body: "El directo comienza en unos minutos  /  " + mark,
        positionX: 50, positionY: 53, width: 84, padding: 36, size: 70, opacity: 100 }),
      part("brb", { title: "Pausa breve", body: "Enseguida seguimos  /  " + mark, positionX: 46, positionY: 50,
        width: 76, padding: 36, size: 66, opacity: 100 }),
      part("ending", { title: "Gracias por acompañarnos", body: "Hasta el próximo directo  /  " + mark,
        positionX: 50, positionY: 54, width: 84, padding: 36, size: 64, opacity: 100 })
    ];
    const pack = codec.normalize({ format: "slb-pack", version: 1, name, description, components: pieces });
    used.add(raw.id);
    return { id: raw.id, name, description, author, category: raw.category, art: raw.art,
      index: indexable([name, description, author, raw.category, starting, banner, mark].join(" ")),
      secondary: raw.secondary, common, banner, starting, mark, pack };
  }

  function thumb(card, theme) {
    const media = add(card, "div", "", "theme-art");
    media.setAttribute("aria-hidden", "true");
    media.dataset.art = theme.art;
    for (const [key, value] of Object.entries({ "--ta": theme.common.accent, "--tb": theme.common.background,
      "--tt": theme.common.textColor, "--ts": theme.secondary, "--tr": theme.common.radius + "px" })) {
      media.style.setProperty(key, value);
    }
    add(media, "div", "", "theme-surface");
    const backdrop = add(media, "div", "", "theme-backdrop");
    add(backdrop, "span", theme.mark, "theme-grid-id");
    add(backdrop, "strong", theme.starting);
    add(backdrop, "div", "", "theme-progress");
    const view = add(media, "div", "", "theme-camera");
    add(view, "span", "", "theme-camera-person");
    add(view, "b", "●  VIVO", "theme-camera-live");
    const chat = add(media, "div", "", "theme-chat");
    add(chat, "b", "Luna");
    add(chat, "span", "¡Aquí estamos!");
    const live = add(media, "div", "", "theme-live");
    add(live, "i", "03");
    add(live, "span", theme.banner);
  }

  function downloadTheme(theme, piece = null) {
    try {
      const filename = piece ? codec.downloadComponent(piece, theme.id + "-" + piece.kind) : codec.download(theme.pack, theme.id);
      void social?.downloadStarted(keyFor(theme));
      const phrase = piece ? "Descarga iniciada: " + filename + ". Impórtalo en Overlays." :
        "Descarga iniciada: " + filename + ". Abrirá las ocho piezas en el importador del bot.";
      get("theme-notice").textContent = phrase;
      if (dialog.open) get("theme-dialog-notice").textContent = phrase;
    } catch {
      get("theme-notice").textContent = "No se pudo descargar. Recarga la página e inténtalo otra vez.";
      if (dialog.open) get("theme-dialog-notice").textContent = get("theme-notice").textContent;
    }
  }

  function createCard(theme) {
    const card = document.createElement("article");
    card.className = "theme-card";
    card.dataset.theme = theme.id;
    thumb(card, theme);
    const body = add(card, "div", "", "theme-body");
    add(body, "p", theme.category + " / 8 piezas", "theme-kicker");
    add(body, "h3", theme.name);
    add(body, "p", theme.description, "theme-description");
    const actions = add(body, "div", "", "theme-buttons");
    const inspect = button(actions, "Ver las 8 piezas", () => view(theme, inspect), "button secondary");
    inspect.setAttribute("aria-label", "Ver las 8 piezas de " + theme.name);
    const down = button(actions, "Descargar pack", () => downloadTheme(theme), "button primary");
    down.setAttribute("aria-label", "Descargar pack " + theme.name);
    add(body, "p", "Diseño de " + theme.author + " · Colección oficial", "meta theme-credit");
    social?.controls(body, { key: keyFor(theme), name: theme.name, signIn: "../cuenta/" });
    return card;
  }

  function clearPreview() {
    get("theme-preview").removeAttribute("src");
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = "";
  }

  function showPiece(theme, piece) {
    try {
      clearPreview();
      const html = codec.previewComponent(piece);
      previewURL = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const frame = get("theme-preview");
      frame.src = previewURL;
      frame.title = "Vista previa: " + codec.LABELS[piece.kind] + " de " + theme.name;
      frame.dataset.piece = piece.kind;
      get("theme-dialog-piece-name").textContent = codec.LABELS[piece.kind];
      for (const active of dialog.querySelectorAll("[data-piece-select]")) {
        active.setAttribute("aria-pressed", String(active.dataset.pieceSelect === piece.kind));
      }
      get("theme-dialog-notice").textContent = "";
    } catch {
      get("theme-dialog-notice").textContent = "No se pudo abrir la vista previa. Puedes descargar la pieza e importarla en el bot.";
    }
  }

  function view(theme, trigger) {
    modalOpener = trigger;
    shownTheme = theme;
    get("theme-dialog-title").textContent = theme.name;
    get("theme-dialog-description").textContent = theme.description;
    get("theme-dialog-credit").textContent = "Diseño de " + theme.author + " · Colección oficial";
    const pieces = get("theme-pieces");
    pieces.replaceChildren();
    for (const piece of theme.pack.components) {
      const row = add(pieces, "li", "", "theme-piece");
      const select = button(row, codec.LABELS[piece.kind], () => showPiece(theme, piece), "button secondary");
      select.dataset.pieceSelect = piece.kind;
      select.setAttribute("aria-pressed", "false");
      const save = button(row, "↓ HTML", () => downloadTheme(theme, piece), "button secondary");
      save.setAttribute("aria-label", "Descargar HTML: " + codec.LABELS[piece.kind]);
    }
    dialog.showModal();
    showPiece(theme, theme.pack.components.find(({ kind }) => kind === "starting") || theme.pack.components[0]);
  }

  get("theme-close").addEventListener("click", () => dialog.close());
  get("theme-dialog-download").addEventListener("click", () => { if (shownTheme) downloadTheme(shownTheme); });
  dialog.addEventListener("close", () => {
    clearPreview();
    const opener = modalOpener;
    modalOpener = null;
    shownTheme = null;
    opener?.focus();
  });

  function render() {
    for (const filter of filters) filter.setAttribute("aria-pressed", String(filter.dataset.themeFilter === activeFilter));
    if (!catalogueReady) return;
    const criteria = indexable(search.value).split(/\s+/).filter(Boolean);
    const matched = catalogue.filter((theme) =>
      (activeFilter === "all" || theme.category === activeFilter) && criteria.every((token) => theme.index.includes(token)));
    themeGrid.replaceChildren(...matched.map((theme) => theme.node));
    get("theme-count").textContent = matched.length === 1 ? "1 de 20 temas" : matched.length + " de 20 temas";
    get("theme-empty").hidden = matched.length !== 0;
  }

  search.addEventListener("input", render);
  for (const filter of filters) filter.addEventListener("click", () => { activeFilter = filter.dataset.themeFilter; render(); });

  fetch("themes.json?v=credits-preview-1").then((response) => {
    if (!response.ok || !codec) throw Error("No se pudo cargar la colección.");
    return response.json();
  }).then((data) => {
    if (!Array.isArray(data) || data.length !== maxEntries) throw Error("Colección incompleta.");
    const used = new Set();
    catalogue = data.map((raw) => themeFrom(raw, used));
    if (catalogue.some((theme) => !theme)) throw Error("Hay un tema inválido.");
    for (const theme of catalogue) theme.node = createCard(theme);
    catalogueReady = true;
    themeGrid.setAttribute("aria-busy", "false");
    render();
    void social?.googleSession();
    void social?.refresh(catalogue.map(keyFor));
  }).catch(() => {
    themeGrid.setAttribute("aria-busy", "false");
    get("theme-count").textContent = "No pudimos abrir la colección de temas.";
  });
})();
