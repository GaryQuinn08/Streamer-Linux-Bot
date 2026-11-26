(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const studio = window.SLB_EDITOR;
  const packs = window.SLB_PACK;
  const social = window.SLB_SOCIAL;
  const statuses = { pending: "Sin publicar", approved: "Publicado", rejected: "No publicado" };
  const modes = new Set(["alert", "chat", "events"]);
  let db, signedIn = false, publications = [], publishedPacks = [];
  let profile = null, profileReady = false, profileBusy = false, publishing = false;

  function status(message, error = false) {
    get("status").textContent = message;
    get("status").dataset.error = String(error);
  }

  function profileStatus(message, error = false) {
    get("profile-status").textContent = message;
    get("profile-status").dataset.error = String(error);
  }

  function draftProfile() {
    return {display_name: get("display-name").value.trim(), bio: get("bio").value.trim()};
  }

  function renderProfileControls() {
    const draft = draftProfile();
    const editor = profile?.is_creator === true;
    const dirty = profile && (draft.display_name !== profile.display_name || draft.bio !== profile.bio);
    const blocked = !profileReady || profileBusy || publishing;
    get("display-name").disabled = blocked;
    get("bio").disabled = blocked;
    get("save-profile").disabled = blocked;
    get("enable-creator").hidden = editor;
    get("enable-creator").disabled = blocked || !profile || dirty;
    get("role-info").textContent = !profileReady ? "El perfil debe estar disponible para habilitar esta opción." :
      editor ? "Ya eres editor. Tu nombre aparece como crédito en lo que publiques a partir de ahora." :
      dirty || !profile ? "Guarda tu perfil para habilitar esta opción." :
      "Es opcional. Al hacerlo, podrás publicar y tu nombre aparecerá como crédito. Tu biografía seguirá siendo privada.";
    get("creator").value = profile?.display_name || "";
    get("submission").hidden = !editor;
    get("submit").disabled = blocked || !editor;
    get("submission-kind").disabled = blocked || !editor || !packs;
  }

  async function loadProfile() {
    renderProfileControls();
    try {
      const {data:saved, error} = await db.from("overlay_profiles").select("display_name,bio,is_creator").maybeSingle();
      if (error) throw error;
      profile = saved ? {
        display_name: typeof saved.display_name === "string" ? saved.display_name : "",
        bio: typeof saved.bio === "string" ? saved.bio : "",
        is_creator: saved.is_creator === true
      } : null;
      get("display-name").value = profile?.display_name || "";
      get("bio").value = profile?.bio || "";
      profileReady = true;
    } catch {
      profileStatus("No se pudo consultar tu perfil. Recarga la página para volver a intentarlo.", true);
    } finally { renderProfileControls(); }
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (!signedIn || !profileReady || profileBusy || publishing) return;
    const draft = draftProfile();
    if (draft.display_name.length < 2 || draft.display_name.length > 60 || draft.bio.length > 280) {
      profileStatus("Escribe un nombre de 2 a 60 caracteres y una biografía de hasta 280.", true); return;
    }
    profileBusy = true;
    renderProfileControls();
    try {
      const {error} = await db.rpc("save_overlay_profile", {p_display_name:draft.display_name, p_bio:draft.bio});
      if (error) throw error;
      profile = {...draft, is_creator:profile?.is_creator === true};
      get("display-name").value = draft.display_name;
      get("bio").value = draft.bio;
      profileStatus(profile.is_creator ? "Cambios guardados." : "Perfil guardado. Convertirte en editor es opcional.");
    } catch { profileStatus("No se pudo guardar tu perfil. Intenta de nuevo.", true); }
    finally { profileBusy = false; renderProfileControls(); }
  }

  async function enableCreator() {
    if (!signedIn || !profile || get("enable-creator").disabled) return;
    profileBusy = true;
    renderProfileControls();
    try {
      const {error} = await db.rpc("enable_overlay_creator");
      if (error) throw error;
      profile.is_creator = true;
      profileStatus("Ya puedes publicar como editor.");
    } catch { profileStatus("No se pudo habilitar el modo editor. Intenta de nuevo.", true); }
    finally { profileBusy = false; renderProfileControls(); }
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
    const release = social.controls(card, { key, name:design.name, signIn:"#creator-access" });
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
    const release = social.controls(card, {key, name:pack.name, signIn:"#creator-access"});
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
    renderProfileControls();
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
    finally { publishing = false; renderProfileControls(); }
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
    renderProfileControls();
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
    } finally { publishing = false; renderProfileControls(); }
  }

  async function init() {
    if (!social?.configured) {
      status("El acceso con Google aún no está habilitado. Puedes seguir usando la galería y el editor sin cuenta.");
      return;
    }
    try {
      db = await social.client();
      signedIn = await social.googleSession();
      get("legacy").hidden = true;
      get("sign-in").hidden = signedIn;
      get("sign-out").hidden = !signedIn;
      get("creator-profile").hidden = !signedIn;
      get("my").hidden = !signedIn;
      status(signedIn ? "Sesión iniciada con Google." : "Inicia sesión con Google para votar o crear tu perfil.");
      get("auth-info").textContent = signedIn ?
        "Tu correo no se publica. Puedes votar aunque no crees un perfil." :
        "Inicia sesión con Google. Puedes votar sin crear un perfil y tu correo nunca se publica.";
      get("sign-in").addEventListener("click", async () => {
        try {
          const callback = new URL("./",location.href);
          const {error} = await db.auth.signInWithOAuth({provider:"google",options:{redirectTo:callback.href,
            queryParams:{prompt:"select_account"}}});
          if (error) status("No se pudo abrir Google; vuelve a intentarlo.",true);
        } catch { status("No se pudo abrir Google; vuelve a intentarlo.",true); }
      });
      get("sign-out").addEventListener("click", async () => {
        try {
          const {error} = await db.auth.signOut({scope:"local"});
          if (error) { status("No se pudo cerrar la sesión. Intenta de nuevo.",true); return; }
          location.replace("./");
        } catch { status("No se pudo cerrar la sesión. Intenta de nuevo.",true); }
      });
      get("submission").addEventListener("submit",submit);
      get("submission-kind").addEventListener("change",packFields);
      get("profile-form").addEventListener("input",renderProfileControls);
      get("profile-form").addEventListener("submit",saveProfile);
      get("enable-creator").addEventListener("click",enableCreator);
      packFields();
      await Promise.all([showPublished(),showPublishedPacks(),signedIn ? showMine() : null,
        signedIn ? showMyPacks() : null,signedIn ? loadProfile() : null]);
    } catch {
      status("El servicio de comunidad no está disponible. Puedes seguir usando el editor y la galería.",true);
    }
  }
  init();
})();
