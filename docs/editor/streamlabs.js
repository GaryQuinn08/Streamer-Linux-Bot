/* Traductor local de mensajes de Streamlabs; no admite URL ni código de widgets. */
(() => {
  "use strict";
  const fields = Object.freeze({
    follow: Object.freeze({name:"{user}"}),
    donation: Object.freeze({name:"{user}",amount:"{amount} {currency}"}),
    bits: Object.freeze({name:"{user}",amount:"{bits}"}),
    sub: Object.freeze({name:"{user}"}),
  });
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  function convert(source, kind) {
    if (!own(fields, kind)) throw Error("Elige un evento de la lista.");
    if (typeof source !== "string" || !source.trim()) throw Error("Pega primero la plantilla de mensaje.");
    const text = source.trim().replace(/<br\s*\/?>/gi, "\n");
    if (/https?:\/\//i.test(text)) throw Error("No pegues enlaces de widgets. Solo necesitamos el texto de la alerta.");
    if (/[<>]/.test(text)) throw Error("Usa texto y etiquetas entre llaves; para HTML o CSS propios usa las pestañas de código.");
    const missing = new Set();
    const result = text.replace(/\{([^{}]+)\}/g, (token, key) => {
      const normalized = key.trim().toLowerCase();
      if (own(fields[kind], normalized)) return fields[kind][normalized];
      missing.add(token);
      return token;
    });
    if (missing.size) throw Error("Estas etiquetas no tienen equivalente para ese evento: " + [...missing].join(", ") + ". Quítalas de la plantilla para continuar.");
    if (result.length > 380) throw Error("Acorta el texto de la plantilla antes de adaptarlo.");
    return result;
  }
  window.SLB_STREAMLABS = Object.freeze({convert});
})();
