/* Conecta el laboratorio a un frame de origen opaco. No recibe ni envía eventos reales. */
(() => {
  "use strict";
  let current = null;

  function finish(error = null, text = "") {
    if (!current) return;
    const job = current;
    current = null;
    clearTimeout(job.timer);
    job.frame.remove();
    error ? job.reject(new Error(error)) : job.resolve(text);
  }

  window.addEventListener("message", (event) => {
    const job = current;
    if (!job || event.source !== job.frame.contentWindow || event.origin !== "null") return;
    const data = event.data;
    if (!data || typeof data !== "object" || data.id !== job.id) return;
    if (data.kind === "slb-js-ok") {
      finish(null, typeof data.text === "string" ? data.text.slice(0, 2400) : "");
    } else if (data.kind === "slb-js-error") {
      finish(typeof data.text === "string" ? data.text.slice(0, 200) : "No se pudo ejecutar la prueba.");
    }
  });

  function run(source, fixture) {
    if (typeof source !== "string" || source.length > 8000) {
      return Promise.reject(new Error("El laboratorio acepta hasta 8 000 caracteres."));
    }
    finish("Prueba cancelada.");
    const frame = document.createElement("iframe");
    frame.className = "js-sandbox";
    frame.title = "Laboratorio de JavaScript aislado";
    frame.setAttribute("sandbox", "allow-scripts");
    frame.referrerPolicy = "no-referrer";
    frame.src = "js-sandbox.html?v=editor-visual-1";
    const id = Array.from(crypto.getRandomValues(new Uint32Array(3)), (value) => value.toString(16)).join("-");
    const demo = {};
    for (const key of ["plataforma", "usuario", "tipo", "texto", "regalo"]) {
      demo[key] = typeof fixture?.[key] === "string" ? fixture[key].slice(0, 200) : "";
    }
    demo.cantidad = Number.isFinite(fixture?.cantidad) ? fixture.cantidad : 0;
    return new Promise((resolve, reject) => {
      current = { id, frame, resolve, reject,
        timer: setTimeout(() => finish("No se recibió respuesta del laboratorio en esta página."), 2600) };
      frame.addEventListener("load", () => {
        if (current?.id !== id) return;
        frame.contentWindow.postMessage({ kind: "slb-js-run", id, source, demo }, "*");
      }, { once: true });
      document.body.append(frame);
    });
  }

  window.SLB_JS_RUNNER = Object.freeze({ run, stop: () => finish("Prueba cancelada."), busy: () => !!current });
})();
