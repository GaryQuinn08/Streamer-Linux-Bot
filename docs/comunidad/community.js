(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const studio = window.SLB_EDITOR;
  const setup = window.SLB_COMMUNITY || {};
  const configOK = /^https:\/\/[a-z0-9]{20}\.supabase\.co$/.test(setup.url || "") &&
    /^sb_publishable_[A-Za-z0-9_-]{20,160}$/.test(setup.publishableKey || "");
  const sdk = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.2/dist/umd/supabase.js";
  const sdkIntegrity = "sha384-A97u3Qnt9GZHURO9YJZRe7VQgGUeFzcv6I1oIGnUTxQrCxnpQMwR0/G8F2zt9abZ";
  const statuses = { pending: "En revisión", approved: "Publicado", rejected: "No aprobado" };
  const modes = new Set(["alert", "chat", "events"]);
  let db, signedIn = false;

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

  function download(design) {
    const html = studio.build(design, [sample(design.mode)], true);
    const url = URL.createObjectURL(new Blob([html], {type:"text/html;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = (design.name.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "overlay") + ".html";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 2500);
  }

  function publication(item) {
    if (!item || !modes.has(item.design?.mode)) return;
    const design = studio.normalize(item.design);
    let preview;
    try { preview = studio.build(design, [sample(design.mode)], false); }
    catch { return; } // aunque esté aprobado, no servir material que el editor no acepta
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
    replay.addEventListener("click", () => { frame.srcdoc = preview; });
    const save = element(actions,"button","Descargar HTML");
    save.type = "button";
    save.className = "button primary";
    save.addEventListener("click", () => download(design));
  }

  async function showPublished() {
    const {data, error} = await db.from("overlay_publications")
      .select("id,creator_name,description,license,design,published_at").order("published_at",{ascending:false}).limit(40);
    get("published").replaceChildren();
    if (error) { get("published-note").textContent = "No se pudo consultar la comunidad. La galería original sigue disponible."; return; }
    if (Array.isArray(data)) data.forEach(publication);
    get("published-note").textContent = get("published").childElementCount ? "Diseños revisados. No necesitas cuenta para descargarlos." : "Todavía no hay aportes aprobados.";
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
    if (!get("rights").checked || creator_name.length < 2 || description.length < 10 || !file) {
      status("Revisa los campos y confirma que puedes compartir el diseño.", true); return;
    }
    if (!/\.html?$/i.test(file.name) || file.size > 250000) {
      status("Selecciona un HTML exportado por el editor de hasta 250 KB.", true); return;
    }
    get("submit").disabled = true;
    try {
      const design = studio.reopen(await file.text());
      // No mandamos el archivo: solo el modelo normalizado del editor.
      const {error} = await db.from("overlay_submissions").insert({creator_name, description, license, design});
      if (error) {
        status(error.message === "Daily submission limit reached" ? "Alcanzaste el límite de 10 aportes en 24 horas." :
          "No se pudo enviar. Revisa tu sesión o intenta más tarde.", true);
        return;
      }
      get("submission").reset();
      status("Diseño enviado. Quedó en revisión y todavía no es público.");
      await showMine();
    } catch {
      status("No se pudo leer el diseño. Descarga un HTML nuevo desde nuestro editor e inténtalo otra vez.", true);
    } finally { get("submit").disabled = false; }
  }

  function loadSDK() {
    return new Promise((resolve,reject) => {
      const script = document.createElement("script");
      script.src = sdk;
      script.integrity = sdkIntegrity;
      script.crossOrigin = "anonymous";
      script.referrerPolicy = "no-referrer";
      script.addEventListener("load",resolve,{once:true});
      script.addEventListener("error",reject,{once:true});
      document.head.append(script);
    });
  }

  async function init() {
    if (!configOK) {
      status("El acceso con Google aún no está habilitado. Puedes seguir usando la galería y el editor sin cuenta.");
      return;
    }
    try {
      await loadSDK();
      db = window.supabase.createClient(setup.url, setup.publishableKey, {
        auth:{flowType:"pkce", detectSessionInUrl:true, persistSession:true, storage:sessionStorage,
          storageKey:"slb-creator-session"}
      });
      const {data} = await db.auth.getSession();
      if (data?.session) {
        const {data:userData} = await db.auth.getUser();
        signedIn = userData?.user?.app_metadata?.provider === "google";
      }
      get("legacy").hidden = true;
      get("sign-in").hidden = signedIn;
      get("sign-out").hidden = !signedIn;
      get("submission").hidden = !signedIn;
      get("my").hidden = !signedIn;
      status(signedIn ? "Sesión de creador activa." : "Inicia sesión con Google si quieres enviar un diseño.");
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
