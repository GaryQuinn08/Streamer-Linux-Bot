(() => {
  "use strict";
  const modeNames = new Map([["alert","Alerta"],["chat","Multichat"],["events","Actividad"]]);
  const safeHex = /^#[0-9a-f]{6}$/i;
  const textKeys = ["name","title","body"];
  const colorKeys = ["accent","textColor","background"];
  const limits = {duration:[0,300],size:[12,120],max:[1,24],opacity:[0,100]};
  const designs = document.querySelector("#designs");
  const status = document.querySelector("#status");

  function preset(raw) {
    if (!raw || !modeNames.has(raw.mode) || typeof raw.name !== "string" || !raw.name.trim()) return null;
    const output = {mode:raw.mode};
    for (const key of textKeys) if (typeof raw[key] === "string") output[key] = raw[key].slice(0,200);
    for (const key of colorKeys) if (typeof raw[key] === "string" && safeHex.test(raw[key])) output[key] = raw[key];
    for (const [key,[min,max]] of Object.entries(limits)) {
      if (typeof raw[key] === "number" && Number.isFinite(raw[key])) output[key] = Math.max(min,Math.min(max,raw[key]));
    }
    return output;
  }

  function add(parent, tag, value, cls) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    node.textContent = value;
    parent.append(node);
    return node;
  }

  function render(entry) {
    const model = preset(entry?.preset);
    if (!model) return;
    const card = add(designs,"article","");
    const sample = add(card,"div","","sample");
    sample.style.setProperty("--accent",model.accent || "#91eed4");
    sample.style.setProperty("--sample",model.background || "#151d28");
    sample.style.setProperty("--ink",model.textColor || "#fffaf6");
    add(sample,"span",modeNames.get(model.mode));
    add(sample,"strong",model.mode === "alert" ? "Luna envió una Rosa" : model.mode === "chat" ? "Luna · ¡Hola, chat!" : "Luna · Nuevo seguidor");
    add(card,"h2",model.name,"card-name");
    add(card,"p",String(entry.description || "").slice(0,240),"description");
    add(card,"p",String(entry.author || "Comunidad").slice(0,80) + " · " + String(entry.license || "Sin licencia indicada").slice(0,35),"meta");
    const link = add(card,"a","Personalizar diseño →","button");
    link.href = "../editor/#preset=" + encodeURIComponent(JSON.stringify(model));
    link.setAttribute("aria-label","Personalizar " + model.name);
  }

  fetch("./designs.json").then(response => {
    if (!response.ok) throw Error("No se pudo leer el catálogo");
    return response.json();
  }).then(entries => {
    if (!Array.isArray(entries)) throw Error("Catálogo inválido");
    entries.slice(0,200).forEach(render);
    status.textContent = designs.childElementCount ? "" : "Todavía no hay diseños.";
  }).catch(() => {
    status.textContent = "No se pudo cargar la galería. Abre el sitio desde GitHub Pages o con un servidor local.";
  });
})();
