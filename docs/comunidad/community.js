(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const studio = window.SLB_EDITOR;
  const social = window.SLB_SOCIAL;
  const statuses = { pending: "Sin publicar", approved: "Publicado", rejected: "No publicado" };
  const modes = new Set(["alert", "chat", "events"]);
  let db, signedIn = false, publications = [];

  function status(message, error = false) {
    get("status").textContent = message;
    get("status").dataset.error = String(error);
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
    element(card, "p", "Diseño de " + String(item.creator_name).slice(0,60) + " · " + String(item.license).slice(0,20));
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

  async function showMine() {
    const {data, error} = await db.from("overlay_submissions")
      .select("id,design,status,created_at").order("created_at",{ascending:false}).limit(40);
    get("my-list").replaceChildren();
    if (error) { element(get("my-list"), "li", "No se pudieron consultar tus aportes."); return; }
    if (!data?.length) { element(get("my-list"), "li", "Aún no has enviado diseños."); return; }
    for (const item of data) {
      const label = typeof item.design?.name === "string" ? item.design.name.slice(0,60) : "Diseño";
      const state = Object.prototype.hasOwnProperty.call(statuses, item.status) ? statuses[item.status] : "Sin estado";
      element(get("my-list"), "li", label + " · " + state);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (!signedIn || get("submit").disabled) return;
    const creator_name = get("creator").value.trim(), description = get("description").value.trim();
    const license = get("license").value, file = get("file").files[0];
    if (creator_name.length < 2 || description.length < 10 || !file) {
      status("Revisa el crédito, la descripción, la licencia y el archivo.", true); return;
    }
    if (!/\.html?$/i.test(file.name) || file.size > 250000) {
      status("Selecciona un HTML exportado por el editor de hasta 250 KB.", true); return;
    }
    get("submit").disabled = true;
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
      status("Tu diseño ya está publicado.");
      await Promise.allSettled([showPublished(), showMine()]);
    } catch {
      status("No se pudo leer el diseño. Descarga un HTML nuevo desde nuestro editor e inténtalo otra vez.", true);
    } finally { get("submit").disabled = false; }
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
      get("submission").hidden = !signedIn;
      get("my").hidden = !signedIn;
      status(signedIn ? "Sesión de creador activa." : "Inicia sesión con Google para publicar un diseño o votar.");
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
      await Promise.all([showPublished(),signedIn ? showMine() : null]);
    } catch {
      status("El servicio de comunidad no está disponible. Puedes seguir usando el editor y la galería.",true);
    }
  }
  init();
})();
