(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const social = window.SLB_SOCIAL;
  const returnKey = "slb-oauth-return-account";
  let db, profile, ready = false, busy = false;

  function message(id, text, error = false) {
    get(id).textContent = text;
    get(id).dataset.error = String(error);
  }

  function draft() {
    return {display_name:get("display-name").value.trim(), bio:get("bio").value.trim()};
  }

  function render() {
    const changes = draft();
    const editor = profile?.is_creator === true;
    const dirty = profile && (changes.display_name !== profile.display_name || changes.bio !== profile.bio);
    const blocked = !ready || busy;
    for (const id of ["display-name", "bio", "save-profile"]) get(id).disabled = blocked;
    get("sign-out").disabled = busy;
    get("retry-profile").disabled = busy;
    get("enable-creator").hidden = editor;
    get("enable-creator").disabled = blocked || !profile || dirty;
    get("go-publish").hidden = !editor;
    get("role-info").textContent = editor ? "Ya eres editor. Puedes publicar cuando quieras, desde Comunidad." :
      !ready ? "Necesitamos cargar tu perfil antes de habilitar esta opción." :
      !profile || dirty ? "Guarda tu perfil para habilitar esta opción." :
      "Es opcional. Podrás publicar overlays y paquetes con tu nombre como crédito. Tu biografía seguirá siendo privada.";
  }

  async function loadProfile() {
    busy = true;
    render();
    get("retry-profile").hidden = true;
    message("profile-status", "Cargando tu perfil…");
    try {
      const {data, error} = await db.from("overlay_profiles").select("display_name,bio,is_creator").maybeSingle();
      if (error) throw error;
      profile = data ? {
        display_name:typeof data.display_name === "string" ? data.display_name : "",
        bio:typeof data.bio === "string" ? data.bio : "",
        is_creator:data.is_creator === true
      } : null;
      get("display-name").value = profile?.display_name || "";
      get("bio").value = profile?.bio || "";
      ready = true;
      message("profile-status", "");
    } catch {
      message("profile-status", "No se pudo consultar tu perfil. Vuelve a intentarlo.", true);
      get("retry-profile").hidden = false;
    } finally { busy = false; render(); }
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (!ready || busy) return;
    const changes = draft();
    if (changes.display_name.length < 2 || changes.display_name.length > 60 || changes.bio.length > 280) {
      message("profile-status", "Escribe un nombre de 2 a 60 caracteres y una biografía de hasta 280.", true);
      return;
    }
    busy = true;
    render();
    message("profile-status", "Guardando tu perfil…");
    try {
      const {error} = await db.rpc("save_overlay_profile", {p_display_name:changes.display_name, p_bio:changes.bio});
      if (error) throw error;
      profile = {...changes, is_creator: profile?.is_creator === true};
      get("display-name").value = changes.display_name;
      get("bio").value = changes.bio;
      message("profile-status", profile.is_creator ? "Cambios guardados." : "Perfil guardado. Convertirte en editor es opcional.");
      message("role-status", "");
    } catch { message("profile-status", "No se pudo guardar tu perfil. Intenta de nuevo.", true); }
    finally { busy = false; render(); }
  }

  async function enableCreator() {
    if (!profile || get("enable-creator").disabled) return;
    busy = true;
    render();
    try {
      const {error} = await db.rpc("enable_overlay_creator");
      if (error) throw error;
      profile.is_creator = true;
      message("role-status", "Ya puedes publicar como editor.");
    } catch { message("role-status", "No se pudo habilitar el perfil de editor. Intenta de nuevo.", true); }
    finally { busy = false; render(); }
  }

  async function signIn() {
    get("sign-in").disabled = true;
    try {
      sessionStorage.setItem(returnKey, String(Date.now()));
      // Supabase ya tiene autorizada esta URL exacta. El callback nos regresa
      // a esta pantalla solo después de comprobar la sesión de Google.
      const redirectTo = new URL("../comunidad/", location.href).href;
      const {error} = await db.auth.signInWithOAuth({provider:"google", options:{redirectTo, queryParams:{prompt:"select_account"}}});
      if (error) throw error;
    } catch {
      try { sessionStorage.removeItem(returnKey); } catch { /* El almacenamiento puede estar bloqueado. */ }
      message("account-status", "No se pudo abrir Google. Intenta de nuevo.", true);
      get("sign-in").disabled = false;
    }
  }

  async function signOut() {
    if (busy) return;
    busy = true;
    render();
    try {
      const {error} = await db.auth.signOut({scope:"local"});
      if (error) throw error;
      get("verified-email").value = "";
      get("email-field").hidden = true;
      location.replace("./");
    } catch {
      message("account-status", "No se pudo cerrar sesión. Intenta de nuevo.", true);
      busy = false;
      render();
    }
  }

  async function init() {
    if (!social?.configured) {
      message("account-status", "El acceso con Google todavía no está disponible.");
      return;
    }
    try {
      db = await social.client();
      const signedIn = await social.googleSession();
      if (!signedIn) {
        get("sign-in").hidden = false;
        get("sign-in").addEventListener("click", signIn);
        const failed = new URLSearchParams(location.search).get("login") === "error";
        message("account-status", failed ? "No se completó el inicio de sesión. Puedes volver a intentarlo." :
          "Inicia sesión con Google para personalizar tu perfil. Explorar y descargar no requiere sesión.", failed);
        return;
      }
      message("account-status", "Sesión iniciada con Google.");
      const email = social.googleEmail?.();
      if (email) {
        get("verified-email").value = email;
        get("email-field").hidden = false;
      }
      get("sign-out").hidden = false;
      get("sign-out").addEventListener("click", signOut);
      get("profile-form").addEventListener("input", render);
      get("profile-form").addEventListener("submit", saveProfile);
      get("retry-profile").addEventListener("click", loadProfile);
      get("enable-creator").addEventListener("click", enableCreator);
      get("account-settings").hidden = false;
      await loadProfile();
    } catch { message("account-status", "El acceso a tu cuenta no está disponible en este momento.", true); }
  }
  window.addEventListener("pageshow", (event) => {
    // Volver a una página restaurada no debe mostrar el perfil de una sesión cerrada.
    if (event.persisted) location.reload();
  });
  init();
})();
