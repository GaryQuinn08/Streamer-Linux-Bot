(() => {
  "use strict";
  const api = window.SLB_PACK, editor = window.SLB_EDITOR, $ = id => document.getElementById(id);
  const list = new Map();
  let active = null;
  if (!api || !editor) { $("feedback").textContent = "No se pudo cargar el estudio. Recarga la página."; return; }
  const palette = () => Object.fromEntries(["accent","textColor","background"].map(key=>[key,$(key).value]));
  const status = (message,error=false) => { $("feedback").textContent=message; $("feedback").dataset.error=String(error); };
  const widthLimit = 250000;
  const nameFor = kind => api.LABELS[kind];
  for (const kind of api.KINDS) {
    const option = new Option(nameFor(kind),kind);
    $("piece-kind").append(option);
  }
  function notify(message, error) { status(error instanceof Error ? error.message : message, true); }
  function newPiece(kind) {
    const dynamic = ["alert","chat","events"].includes(kind);
    const base = editor.normalize({mode:dynamic ? kind : "alert"},true);
    const staticTexts={banner:"EN VIVO",camera:"CÁMARA",starting:"Empezamos pronto",brb:"Volvemos enseguida",ending:"Gracias por acompañarnos"};
    return api.component(kind,{...base,...palette(),name:nameFor(kind),...(dynamic?{}:{title:staticTexts[kind]||nameFor(kind),body:"",mode:"static"})});
  }
  function currentPack() {
    return api.normalize({format:"slb-pack",version:1,name:$("pack-name").value,description:$("pack-description").value,components:[...list.values()]});
  }
  function preview() {
    if (!active) return;
    const piece=list.get(active), d=piece.design;
    if (["alert","chat","events"].includes(piece.kind)) {
      const sample=piece.kind==="alert"?{channel:"alert",platform:"tiktok",title:"Luna envió un regalo",text:"Rosa ×3",user:"Luna",variables:{gift_name:"Rosa",count:3}}:
        piece.kind==="chat"?{channel:"chat",platform:"twitch",user:"Luna",text:"¡Hola, chat!"}:{channel:"event",platform:"tiktok",type:"follow",user:"Luna"};
      $("preview").srcdoc=editor.build(d,[sample],false);
    } else $("preview").srcdoc=api.buildComponent(piece);
  }
  function refresh() {
    $("piece-list").replaceChildren();
    for (const [kind, piece] of list) {
      const li = document.createElement("li"), edit = document.createElement("button"), drop = document.createElement("button");
      edit.type=drop.type="button"; edit.className=drop.className="button secondary";
      edit.textContent=nameFor(kind); edit.title=piece.design.name;
      if (kind===active) edit.setAttribute("aria-current","true");
      edit.addEventListener("click",()=>{active=kind;refresh();$("piece-name").focus();});
      drop.textContent="Quitar"; drop.setAttribute("aria-label","Quitar "+nameFor(kind));
      drop.addEventListener("click",()=>{list.delete(kind); if(active===kind)active=list.keys().next().value||null; refresh(); $("add-piece").focus();});
      li.append(edit,drop); $("piece-list").append(li);
    }
    $("piece-editor").hidden=!active;
    $("no-piece").hidden=Boolean(active);
    $("save-pack").disabled=!list.size;
    if (!active) { $("preview").removeAttribute("srcdoc"); return; }
    const {design}=list.get(active);
    for (const field of ["name","title","body"]) $("piece-"+field).value=design[field]||"";
    $("edit-single").href="../editor/"+(["alert","chat","events"].includes(active)? "?mode="+active:"");
    preview();
  }
  function install(piece, replace=false) {
    if (list.has(piece.kind)&&!replace) throw Error("Esa pieza ya existe en el pack. Quita la anterior para reemplazarla.");
    list.set(piece.kind,piece);
    active=piece.kind;
  }
  $("add-piece").addEventListener("click",()=>{try {install(newPiece($("piece-kind").value)); refresh(); status("Pieza agregada.");} catch(error){notify("",error);}});
  $("palette").addEventListener("click",()=>{
    try { if(!list.size)throw Error("Agrega al menos una pieza."); for(const [kind,piece] of list)list.set(kind,api.component(kind,{...piece.design,...palette()})); refresh(); status("Colores aplicados."); }
    catch(error){notify("",error);}
  });
  for (const field of ["name","title","body"]) $("piece-"+field).addEventListener("input",()=>{
    if (!active) return;
    const {design}=list.get(active);
    const updated={...design,[field]:$("piece-"+field).value};
    if (!String(updated.name).trim())return;
    try {list.set(active,api.component(active,updated)); preview();}catch(error){notify("",error);}
  });
  $("save-pack").addEventListener("click",()=>{try {api.download(currentPack()); status("Pack descargado. Puedes abrirlo aquí o subirlo a Comunidad.");}catch(error){notify("",error);}});
  $("save-piece").addEventListener("click",()=>{try {api.downloadComponent(list.get(active));status("HTML de la pieza descargado.");}catch(error){notify("",error);}});
  $("open-pack").addEventListener("click",()=>$("pack-file").click());
  $("import-html").addEventListener("click",()=>$("html-files").click());
  $("pack-file").addEventListener("change",async ev=>{
    const file=ev.target.files[0]; ev.target.value="";
    if (!file)return;
    try {
      if(file.size>widthLimit)throw Error("El pack supera 250 KB.");
      const pack=api.parse(await file.text());
      if(list.size&&!window.confirm("¿Reemplazar las piezas del estudio con el pack que abriste?"))return;
      list.clear(); $("pack-name").value=pack.name; $("pack-description").value=pack.description;
      for(const c of pack.components)install(c,true);
      refresh(); status("Pack abierto. Puedes editarlo antes de volver a descargar.");
    }catch(error){notify("",error);}
  });
  $("html-files").addEventListener("change",async ev=>{
    const files=[...ev.target.files]; ev.target.value="";
    let added=0, skipped=0;
    for(const f of files.slice(0,8)) {
      try {
        if(!/\.html?$/i.test(f.name)||f.size>widthLimit)throw Error("Formato no compatible");
        const piece=api.componentFromHTML(await f.text());
        if(list.has(piece.kind)&&!window.confirm("¿Reemplazar "+nameFor(piece.kind)+" con el archivo seleccionado?")){skipped++;continue;}
        install(piece,true);added++;
      }catch {skipped++;}
    }
    refresh();
    status(`Piezas añadidas: ${added}. No añadidas: ${skipped}.`,!added);
  });
  refresh();
})();
