/* Contadores públicos y votos de la Galería/Comunidad: sin almacenamiento de votos en el navegador. */
(() => {
  "use strict";
  const setup = window.SLB_COMMUNITY || {};
  const configured = /^https:\/\/[a-z0-9]{20}\.supabase\.co$/.test(setup.url || "") &&
    /^sb_publishable_[A-Za-z0-9_-]{20,160}$/.test(setup.publishableKey || "");
  const sdk = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.2/dist/umd/supabase.js";
  const sdkIntegrity = "sha384-A97u3Qnt9GZHURO9YJZRe7VQgGUeFzcv6I1oIGnUTxQrCxnpQMwR0/G8F2zt9abZ";
  const validKey = /^(?:(?:gallery|theme):[a-z0-9][a-z0-9-]{0,63}|(?:community|pack):[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$/;
  const number = new Intl.NumberFormat("es-MX");
  const decimal = new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const licenses = new Map([
    ["CC0-1.0", ["Reutilización sin exigir crédito", "https://creativecommons.org/publicdomain/zero/1.0/deed.es"]],
    ["CC-BY-4.0", ["Reutilización con crédito al creador", "https://creativecommons.org/licenses/by/4.0/deed.es"]],
    ["CC-BY-SA-4.0", ["Crédito al creador y misma licencia al compartir adaptaciones", "https://creativecommons.org/licenses/by-sa/4.0/deed.es"]]
  ]);
  const views = new Map(), stats = new Map(), requests = new Map();
  let clientPromise, authPromise, verifiedEmail = "", nextId = 0;
  let authState = configured ? "loading" : "offline";

  function loadSDK() {
    if (window.supabase?.createClient) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = sdk;
      script.integrity = sdkIntegrity;
      script.crossOrigin = "anonymous";
      script.referrerPolicy = "no-referrer";
      const failed = () => {
        clearTimeout(timeout);
        script.remove();
        reject(new Error("El servicio de comunidad no está disponible."));
      };
      const timeout = setTimeout(failed, 9000);
      script.addEventListener("load", () => { clearTimeout(timeout); resolve(); }, { once: true });
      script.addEventListener("error", failed, { once: true });
      document.head.append(script);
    });
  }

  function client() {
    if (!configured) return Promise.reject(new Error("La comunidad todavía no está configurada."));
    if (!clientPromise) clientPromise = loadSDK().then(() => window.supabase.createClient(setup.url, setup.publishableKey, {
      auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true, storage: sessionStorage,
        storageKey: "slb-creator-session" }
    })).catch((error) => { clientPromise = undefined; throw error; });
    return clientPromise;
  }

  function setAuth(state) {
    authState = state;
    if (state !== "google") verifiedEmail = "";
    for (const entries of views.values()) for (const update of entries) update();
    return state === "google";
  }

  function googleSession() {
    if (!configured) return Promise.resolve(false);
    if (!authPromise) {
      authPromise = client().then(async (db) => {
        const { data, error } = await db.auth.getSession();
        if (error) return setAuth("guest");
        if (!data?.session) return setAuth("guest");
        const result = await db.auth.getUser();
        if (result.error) return setAuth("guest");
        const user = result.data?.user;
        if (user?.app_metadata?.provider !== "google") return setAuth("guest");
        verifiedEmail = typeof user.email === "string" ? user.email : "";
        return setAuth("google");
      }).catch(() => { authPromise = undefined; return setAuth("offline"); });
    }
    return authPromise;
  }

  function googleEmail() { return authState === "google" ? verifiedEmail : ""; }

  function nonNegative(value) {
    const numeric = typeof value === "string" || typeof value === "number" ? Number(value) : NaN;
    return Number.isSafeInteger(numeric) && numeric >= 0 ? numeric : 0;
  }

  function recordView(key, value) {
    stats.set(key, value);
    for (const update of views.get(key) || []) update();
  }

  async function refresh(keys) {
    const unique = [...new Set(keys)].filter((key) => typeof key === "string" && validKey.test(key));
    if (!unique.length) return;
    if (!configured) {
      for (const key of unique) recordView(key, "offline");
      return;
    }
    const pending = unique.map((key) => [key, (requests.get(key) || 0) + 1]);
    for (const [key, order] of pending) requests.set(key, order);
    try {
      const db = await client();
      for (let start = 0; start < unique.length; start += 40) {
        const batch = pending.slice(start, start + 40);
        const { data, error } = await db.from("overlay_catalog_stats")
          .select("design_key,downloads,rating_count,rating_average").in("design_key", batch.map(([key]) => key));
        if (error) throw error;
        const rows = new Map((Array.isArray(data) ? data : []).map((row) => [row.design_key, row]));
        for (const [key, order] of batch) {
          if (requests.get(key) !== order) continue;
          const row = rows.get(key);
          const average = row?.rating_average == null ? NaN : Number(row.rating_average);
          recordView(key, {
            downloads: nonNegative(row?.downloads),
            votes: nonNegative(row?.rating_count),
            average: Number.isFinite(average) && average >= 1 && average <= 5 ? average : null
          });
        }
      }
    } catch {
      for (const [key, order] of pending) {
        if (requests.get(key) === order && (!stats.has(key) || stats.get(key) === "offline")) recordView(key, "offline");
      }
    }
  }

  async function downloadStarted(key) {
    if (typeof key !== "string" || !validKey.test(key) || !configured) return false;
    try {
      const db = await client();
      const { error } = await db.rpc("record_overlay_download", { p_key: key, p_nonce: crypto.randomUUID() });
      if (error) return false;
      // No se espera el contador para entregar ni confirmar el archivo.
      void refresh([key]);
      return true;
    } catch { return false; }
  }

  function el(parent, name, text, className) {
    const node = document.createElement(name);
    if (className) node.className = className;
    if (text) node.textContent = text;
    parent.append(node);
    return node;
  }

  function licenseLink(parent, value) {
    const license = licenses.get(value);
    if (!license) return el(parent, "span", "Sin licencia indicada");
    const link = el(parent, "a", license[0]);
    link.href = license[1];
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  function controls(parent, { key, name, signIn }) {
    if (typeof key !== "string" || !validKey.test(key)) return () => {};
    const box = el(parent, "div", "", "catalog-social");
    const total = el(box, "p", "Cargando estadísticas…", "catalog-total");
    const detail = el(box, "details", "", "catalog-rating");
    el(detail, "summary", "Calificar");
    const guide = el(detail, "p", "Consultando tu sesión…", "catalog-guide");
    const login = el(guide, "a", "Inicia sesión con Google");
    login.href = signIn;
    login.hidden = true;
    const group = el(detail, "fieldset", "", "catalog-stars");
    group.hidden = true;
    el(group, "legend", "Estrellas para " + name, "catalog-sr");
    const options = el(group, "div", "", "catalog-options");
    const radioName = "stars-" + (++nextId);
    for (let value = 1; value <= 5; value++) {
      const label = el(options, "label");
      const radio = el(label, "input", "", "catalog-sr");
      radio.name = radioName;
      radio.type = "radio";
      radio.value = String(value);
      el(label, "span", value === 1 ? "1 estrella" : value + " estrellas", "catalog-sr");
      const star = el(label, "span", "★", "catalog-star-symbol");
      star.setAttribute("aria-hidden", "true");
      label.title = value === 1 ? "1 estrella" : value + " estrellas";
    }
    const submit = el(group, "button", "Guardar voto", "button secondary");
    submit.type = "button";
    const message = el(detail, "p", "", "catalog-message");
    message.setAttribute("role", "status");
    let writing = false;

    options.addEventListener("change", () => {
      const selected = Number(options.querySelector("input:checked")?.value);
      for (const label of options.children) {
        label.classList.toggle("chosen", Number(label.querySelector("input").value) <= selected);
      }
    });

    submit.addEventListener("click", async () => {
      if (writing || authState !== "google") return;
      const stars = Number(options.querySelector("input:checked")?.value);
      if (!Number.isInteger(stars) || stars < 1 || stars > 5) {
        message.textContent = "Selecciona de 1 a 5 estrellas.";
        options.querySelector("input")?.focus();
        return;
      }
      writing = submit.disabled = true;
      message.textContent = "Guardando voto…";
      try {
        const db = await client();
        const { error } = await db.rpc("rate_overlay", { p_key: key, p_stars: stars });
        if (error) throw error;
        message.textContent = "Voto guardado. Puedes cambiarlo cuando quieras.";
        void refresh([key]);
      } catch {
        message.textContent = "No se pudo guardar el voto. Comprueba tu sesión y vuelve a intentar.";
      } finally {
        writing = submit.disabled = false;
      }
    });

    function update() {
      const entry = stats.get(key);
      if (entry === "offline") total.textContent = "Estadísticas no disponibles.";
      else if (entry) {
        const downloads = number.format(entry.downloads) + (entry.downloads === 1 ? " descarga" : " descargas");
        const votes = entry.votes && entry.average !== null
          ? decimal.format(entry.average) + " ★ · " + number.format(entry.votes) + (entry.votes === 1 ? " voto" : " votos")
          : "Sin votos";
        total.textContent = downloads + " · " + votes;
      }
      group.hidden = authState !== "google";
      guide.hidden = authState === "google";
      guide.replaceChildren();
      if (authState === "guest") { login.hidden = false; guide.append(login, " para votar, publicar tus diseños y ver tus aportes. Puedes descargar sin cuenta."); }
      else if (authState === "loading") guide.textContent = "Consultando tu sesión…";
      else if (authState === "offline") guide.textContent = "Los votos no están disponibles ahora.";
    }

    if (!views.has(key)) views.set(key, new Set());
    views.get(key).add(update);
    update();
    return () => {
      const observers = views.get(key);
      observers?.delete(update);
      if (!observers?.size) views.delete(key);
    };
  }

  window.SLB_SOCIAL = Object.freeze({ configured, client, googleSession, googleEmail, refresh, controls, downloadStarted, licenseLink });
})();
