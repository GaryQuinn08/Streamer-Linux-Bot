(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const studio = window.SLB_EDITOR;
  const packs = window.SLB_PACK;
  const social = window.SLB_SOCIAL;
  const statuses = { pending: "Sin publicar", approved: "Publicado", rejected: "No publicado" };
  const modes = new Set(["alert", "chat", "events"]);
  let db, signedIn = false, publications = [], publishedPacks = [];
  let profile = null, publishing = false;
  const oauthParams = new URLSearchParams(location.search);
  const googleCallback = ["code", "error", "error_code"].some((key) => oauthParams.has(key));
  const returnKey = "slb-oauth-return-account";

  function status(message, error = false) {
    get("status").textContent = message;
    get("status").dataset.error = String(error);
  }

  function renderPublishing() {
    const editor = profile?.is_creator === true;
    get("creator").value = profile?.display_name || "";
    get("submission").hidden = !editor;
    get("submit").disabled = publishing || !editor;
    get("submission-kind").disabled = publishing || !editor || !packs;
  }

  async function loadPublisher() {
    try {
      const {data, error} = await db.from("overlay_profiles").select("display_name,is_creator").maybeSingle();
      if (error) throw error;
      profile = data;
      get("auth-info").textContent = profile?.is_creator === true ?
        "Ya puedes publicar overlays o paquetes. El crédito se toma del nombre guardado en Mi cuenta." :
        profile ? "Tu perfil ya está guardado. En Mi cuenta puedes activar la opción de publicar como editor." :
        "Guarda tu perfil en Mi cuenta. Después puedes elegir si quieres publicar como editor.";
    } catch {
      get("auth-info").textContent = "No se pudo consultar tu perfil. Puedes revisarlo desde Mi cuenta.";
    } finally { renderPublishing(); }
  }

  function returnToAccount() {
    if (!googleCallback) return false;
    try {
      const started = Number(sessionStorage.getItem(returnKey));
      sessionStorage.removeItem(returnKey);
      if (!started || Date.now() - started > 15 * 60_000 || started > Date.now()) return false;
    } catch { return false; }
    location.replace(new URL(signedIn ? "../cuenta/" : "../cuenta/?login=error", location.href));
    return true;
  }

  function element(parent, name, text) {
    const node = document.createElement(name);
    if (text) node.textContent = text;
    parent.append(node);
    return node;
  }

  function sample(mode) {
    if (mode === "alert") return {channel:"alert", user:"Luna", platform:"tiktok", type:"gift",
      title:"Luna envió un regalo", text:"Rosa ×3", variables:{gift_name:"Rosa", count:3}, simulated:true};
    if (mode === "chat") return {channel:"chat", user:"Luna", platform:"twitch", text:"¡Hola, chat!", simulated:true};
    return {channel:"event", user:"Luna", platform:"tiktok", type:"gift", data:{gift_name:"Rosa", count:3}, simulated:true};
  }

  function download(design, key) {
    const html = studio.build(design, [sample(design.mode)], true);
    const url = URL.createObjectURL(new Blob([html], {type:"text/html;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = (design.name.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "overlay") + ".html";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2500);
    void social.downloadStarted(key);
  }

  function publication(item) {
    if (!item || !modes.has(item.design?.mode)) return;
    const key = "community:" + item.id;
    const design = studio.normalize(item.design);
    let preview;
    try { preview = studio.build(design, [sample(design.mode)], false); }
    catch { return; } // no servir material histórico que el editor ya no acepte
    const card = element(get("published"), "article");
    element(card, "h3", design.name);
    const credit = element(card, "p", "Diseño de " + String(item.creator_name).slice(0,60) + " · ");
    social.licenseLink(credit, item.license);
    element(card, "p", String(item.description).slice(0,280));
    const frame = document.createElement("iframe");
    frame.title = "Muestra de " + design.name;
    frame.setAttribute("sandbox", "");
    frame.referrerPolicy = "no-referrer";
    frame.loading = "lazy";
    frame.srcdoc = preview;
    card.append(frame);
    const actions = element(card, "div");
    actions.className = "community-actions";
    const replay = element(actions,"button","Repetir muestra");
    replay.type = "button";
    replay.className = "button secondary";
    replay.addEventListener("click", () => { frame.srcdoc = studio.build(design, [sample(design.mode)], false, { replay:true }); });
    const save = element(actions,"button","Descargar HTML");
    save.type = "button";
    save.className = "button primary";
    save.setAttribute("aria-label", "Descargar HTML de " + design.name);
    save.addEventListener("click", () => {
      try { download(design, key); }
      catch { status("No se pudo generar el HTML de este diseño.", true); }
    });
    const release = social.controls(card, { key, name:design.name, signIn:"../cuenta/" });
    publications.push({ key, release });
  }

  function packFields() {
    const isPack = get("submission-kind").value === "pack";
    get("description-field").hidden = isPack;
    get("description").disabled = isPack;
    get("overlay-file-field").hidden = isPack;
    get("file").disabled = isPack;
    get("pack-file-field").hidden = !isPack;
    get("pack-file").disabled = !isPack;
    get("pack-help").hidden = !isPack;
    get("submit").textContent = isPack ? "Publicar paquete" : "Publicar diseño";
  }

  function packPublication(item) {
    let pack;
    try { pack = packs.parse(JSON.stringify(item.pack)); }
    catch { return; }
    const key = "pack:" + item.id;
    const card = element(get("published-packs"), "article");
    element(card, "h3", pack.name);
    const credit = element(card, "p", "Paquete de " + String(item.creator_name).slice(0,60) + " · ");
    social.licenseLink(credit, item.license);
    element(card, "p", pack.description);
    const list = element(card, "ul");
    list.className = "pack-components";
    for (const component of pack.components) {
      element(list, "li", (packs.LABELS[component.kind] || "Overlay") + ": " + component.design.name);
    }
    try {
      const first = pack.components[0], design = first.design;
      const preview = modes.has(first.kind)
        ? studio.build(design, [sample(design.mode)], false)
        : packs.buildComponent(first);
      if (typeof preview === "string") {
        const frame = document.createElement("iframe");
        frame.title = "Muestra de " + pack.name;
        frame.setAttribute("sandbox", "");
        frame.referrerPolicy = "no-referrer";
        frame.loading = "lazy";
        frame.srcdoc = preview;
        card.append(frame);
      }
    } catch { /* Un diseño sin vista previa todavía puede descargarse. */ }
    const save = element(card, "button", "Descargar paquete");
    save.className = "button primary";
    save.type = "button";
    save.setAttribute("aria-label", "Descargar paquete " + pack.name);
    save.addEventListener("click", () => {
      try { if (packs.download(pack) !== false) void social.downloadStarted(key); }
      catch { status("No se pudo descargar este paquete.", true); }
    });
    const release = social.controls(card, {key, name:pack.name, signIn:"../cuenta/"});
    publishedPacks.push({key,release});
  }

  async function showPublished() {
    const {data, error} = await db.from("overlay_publications")
      .select("id,creator_name,description,license,design,published_at").order("published_at",{ascending:false}).limit(40);
    if (error) { get("published-note").textContent = "No se pudo consultar la comunidad. La galería original sigue disponible."; return; }
    for (const entry of publications) entry.release();
    publications = [];
    get("published").replaceChildren();
    if (Array.isArray(data)) data.forEach(publication);
    void social.refresh(publications.map((item) => item.key));
    get("published-note").textContent = get("published").childElementCount
      ? "No necesitas cuenta para descargar. El contador muestra descargas iniciadas."
      : "Todavía no hay diseños publicados.";
  }

  async function showPublishedPacks() {
    if (!packs) {
      get("packs-note").textContent = "Los paquetes no están disponibles en este momento."; return;
    }
    const {data, error} = await db.from("overlay_pack_publications")
      .select("id,creator_name,description,license,pack,published_at").order("published_at",{ascending:false}).limit(40);
    if (error) { get("packs-note").textContent = "No se pudieron consultar los paquetes de la comunidad."; return; }
    for (const entry of publishedPacks) entry.release();
    publishedPacks = [];
    get("published-packs").replaceChildren();
    if (Array.isArray(data)) data.forEach(packPublication);
    void social.refresh(publishedPacks.map((entry) => entry.key));
    get("packs-note").textContent = publishedPacks.length
      ? "Cada descarga reúne varios componentes en un archivo .slbpack."
      : "Todavía no hay paquetes publicados.";
  }

  async function showMine() {
    const {data, error} = await db.from("overlay_submissions")
      .select("id,design,status,created_at").order("created_at",{ascending:false}).limit(40);
    get("my-list").replaceChildren();
    if (error) { element(get("my-list"), "li", "No se pudieron consultar tus aportes."); return; }
    if (!data?.length) { element(get("my-list"), "li", "Aún no has enviado overlays individuales."); return; }
    for (const item of data) {
      const label = typeof item.design?.name === "string" ? item.design.name.slice(0,60) : "Diseño";
      const state = Object.prototype.hasOwnProperty.call(statuses, item.status) ? statuses[item.status] : "Sin estado";
      element(get("my-list"), "li", label + " · " + state);
    }
  }

  async function showMyPacks() {
    if (!packs) return;
    const {data, error} = await db.rpc("my_overlay_packs");
    get("my-packs").replaceChildren();
    if (error) { element(get("my-packs"), "li", "No se pudieron consultar tus paquetes."); return; }
    if (!data?.length) { element(get("my-packs"), "li", "Aún no has publicado paquetes."); return; }
    for (const item of data) {
      const label = typeof item.pack?.name === "string" ? item.pack.name.slice(0,60) : "Paquete";
      element(get("my-packs"), "li", label + " · Paquete publicado");
    }
  }

  async function submitPack(license) {
    const file = get("pack-file").files[0];
    if (!packs || !file || !/\.slbpack$/i.test(file.name)) {
      status("Selecciona un archivo .slbpack del creador de paquetes.", true); return;
    }
    if (file.size > 65536) { status("Selecciona un archivo .slbpack de hasta 64 KiB.", true); return; }
    publishing = true;
    renderPublishing();
    try {
      let pack;
      try { pack = packs.parse(await file.text()); }
      catch { status("No se pudo leer el archivo. Exporta un .slbpack válido desde el creador de paquetes.", true); return; }
      const {error} = await db.rpc("publish_overlay_pack", {p_pack:pack,p_license:license});
      if (error) {
        status(error.message === "Daily theme limit reached" ? "Alcanzaste el límite de 5 paquetes en 24 horas." :
          "No se pudo publicar el paquete. Revisa tu sesión o inténtalo más tarde.", true);
        return;
      }
      get("submission").reset();
      packFields();
      status("Tu paquete ya está publicado.");
      await Promise.allSettled([showPublishedPacks(),showMyPacks()]);
    } catch { status("No se pudo publicar el paquete. Inténtalo más tarde.", true); }
    finally { publishing = false; renderPublishing(); }
  }

  async function submit(event) {
    event.preventDefault();
    if (!signedIn || !profile?.is_creator || get("submit").disabled) return;
    if (get("submission-kind").value === "pack") return submitPack(get("license").value);
    const creator_name = profile.display_name, description = get("description").value.trim();
    const license = get("license").value, file = get("file").files[0];
    if (creator_name.length < 2 || description.length < 10 || !file) {
      status("Revisa el crédito, la descripción, la licencia y el archivo.", true); return;
    }
    if (!/\.html?$/i.test(file.name) || file.size > 250000) {
      status("Selecciona un HTML exportado por el editor de hasta 250 KB.", true); return;
    }
    publishing = true;
    renderPublishing();
    try {
      const reopened = studio.reopen(await file.text());
      // Se envían únicamente los ajustes declarativos; ningún código del archivo.
      const { markup: _markup, css: _css, ...design } = studio.normalize(reopened, true);
      const {error} = await db.from("overlay_submissions").insert({creator_name, description, license, design});
      if (error) {
        status(error.message === "Daily submission limit reached" ? "Alcanzaste el límite de 10 aportes en 24 horas." :
          "No se pudo publicar. Revisa tu sesión o intenta más tarde.", true);
        return;
      }
      get("submission").reset();
      packFields();
      status("Tu diseño ya está publicado.");
      await Promise.allSettled([showPublished(), showMine()]);
    } catch {
      status("No se pudo leer el diseño. Descarga un HTML nuevo desde nuestro editor e inténtalo otra vez.", true);
    } finally { publishing = false; renderPublishing(); }
  }

  async function init() {
    if (!social?.configured) {
      status("El acceso con Google aún no está habilitado. Puedes seguir usando la galería y el editor sin cuenta.");
      return;
    }
    try {
      db = await social.client();
      signedIn = await social.googleSession();
      if (returnToAccount()) return;
      get("legacy").hidden = true;
      get("my").hidden = !signedIn;
      status(signedIn ? "Sesión iniciada con Google." : "Puedes explorar y descargar sin iniciar sesión.");
      if (signedIn) get("account-link").textContent = "Editar mi perfil";
      get("submission").addEventListener("submit",submit);
      get("submission-kind").addEventListener("change",packFields);
      packFields();
      await Promise.all([showPublished(),showPublishedPacks(),signedIn ? showMine() : null,
        signedIn ? showMyPacks() : null,signedIn ? loadPublisher() : null]);
    } catch {
      status("El servicio de comunidad no está disponible. Puedes seguir usando el editor y la galería.",true);
    }
  }
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && signedIn) location.reload();
  });
  init();
})();
