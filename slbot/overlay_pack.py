"""Read v1 declarative theme packs and render trusted local overlay components."""
from __future__ import annotations

import html
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from .overlay_manager import OverlayInfo, _new_overlay_id, import_overlay

LABELS = {"alert": "Alerta", "chat": "Multichat", "events": "Actividad", "banner": "Banner",
          "camera": "Marco de cámara", "starting": "Empezando", "brb": "En pausa", "ending": "Cierre"}
DYNAMIC = {"alert", "chat", "events"}
MAX_BYTES = 65536
COLORS = {"accent": "#9ef3c9", "textColor": "#f5fcff", "background": "#13282b"}
RANGES = {
    "duration": (0, 300, 6), "size": (12, 72, 27), "max": (1, 24, 1), "opacity": (0, 100, 94),
    "enterMs": (0, 3000, 320), "exitMs": (0, 3000, 240), "positionX": (0, 100, 50),
    "positionY": (0, 100, 50), "width": (24, 100, 75), "radius": (0, 48, 16),
    "padding": (0, 48, 17), "border": (0, 16, 4),
}
MOTION = {"none", "fade", "slide-up", "slide-left", "zoom", "pop"}
STYLE = """
*{box-sizing:border-box} html,body{width:100%;height:100%;margin:0;overflow:hidden;background:transparent}
body{font:var(--size) system-ui,sans-serif;color:var(--ink)}
.stage{position:absolute;left:var(--offset);top:var(--y);width:var(--width);transform:translateY(var(--shift));text-align:var(--align)}
.card{background:var(--fill);padding:var(--padding);border-radius:var(--radius);border-left:var(--line) solid var(--accent);margin:.25em 0;overflow-wrap:anywhere}
h1,p{margin:0;overflow-wrap:anywhere;white-space:pre-wrap}h1{font-size:1em}p{font-size:.78em;padding-top:.24em}p:empty,h1:empty{display:none}
.platform{display:var(--platform);font-size:.52em;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin:0 0 .32em}
.platform:empty{display:none}.frame,.scene{position:absolute;inset:0}
.frame{border:var(--line) solid var(--accent);border-radius:var(--radius)}.frame .card{position:absolute;bottom:0;left:0;margin:0}
.scene{background:var(--fill);background-image:radial-gradient(ellipse at 83% 13%,var(--glow),transparent 42%),repeating-linear-gradient(135deg,transparent 0 18px,var(--tracer) 19px 20px,transparent 21px 38px)}
.scene .card,.banner .card{border-left:0;border-top:var(--line) solid var(--accent)}
@keyframes slb-in{from{opacity:0;transform:var(--in)}to{opacity:1;transform:none}}
@keyframes slb-out{from{opacity:1;transform:none}to{opacity:0;transform:var(--out)}}
.card.enter{animation:slb-in var(--in-time) ease-out both}.card.leave{animation:slb-out var(--out-time) ease-in forwards}
@media(prefers-reduced-motion:reduce){.card.enter,.card.leave{animation:none}}
"""
RUNTIME = r"""
(() => {
  'use strict';
  const config=JSON.parse(document.getElementById('slb-pack-data').textContent);
  const id=location.pathname.match(/^\/overlay\/([a-z0-9][a-z0-9_-]{0,63})(?:\/(?:index\.html)?)?$/)?.[1];
  const stage=document.getElementById('stage');
  if (!id || !['localhost','127.0.0.1'].includes(location.hostname)) return;
  const events={chat:'escribió en el chat',follow:'ahora te sigue',sub:'se suscribió',gift:'envió un regalo',
    donation:'hizo una donación',bits:'envió bits',raid:'hizo una raid',points:'canjeó puntos',like:'dio Me gusta',share:'compartió el directo'};
  const render=(e)=>{
    if (!e || typeof e!=='object') return;
    if(config.mode==='alert' && (e.channel!=='alert'||e.overlay!==id))return;
    if(config.mode==='chat' && e.channel!=='chat')return;
    if(config.mode==='events' && e.channel!=='event')return;
    const vars=Object.create(null);
    const source=config.mode==='alert'?e.variables:e.data;
    const plain=v=>typeof v==='string'?v.slice(0,700):(typeof v==='number'||typeof v==='boolean'?String(v):'');
    if(source && typeof source==='object')for(const k of Object.keys(source).slice(0,48)){
      if(/^[a-z][a-z0-9_]{0,40}$/i.test(k))vars[k]=plain(source[k]);
    }
    vars.user=plain(e.user)||vars.user||'';
    vars.platform=plain(e.platform)||vars.platform||'';
    vars.type=vars.event_type=plain(e.type)||vars.type||'';
    vars.event_label=Object.hasOwn(events,vars.type)?events[vars.type]:vars.type;
    vars.event_text=vars.text||'';
    vars.text=plain(e.text)||vars.text||'';
    vars.alert_text=vars.text;
    vars.title=vars.alert_title=plain(e.title);
    const time=Number(e.ts ?? vars.ts);if(Number.isFinite(time)){const when=new Date(time*1000);
      if(Number.isFinite(when.getTime()))vars.time=when.toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'});}
    const expand=s=>s.replace(/\{([a-z][a-z0-9_]{0,40})\}/gi,(_,key)=>vars[key]||'');
    const card=document.createElement('article');card.className='card';
    const label=document.createElement('div');label.className='platform';label.textContent=vars.platform;
    const h=document.createElement('h1');h.textContent=expand(config.title);
    const p=document.createElement('p');p.textContent=expand(config.body);
    card.append(label,h,p);stage.append(card);
    if(config.enter!=='none' && config.enterMs>0)card.classList.add('enter');
    while(stage.childElementCount>config.max)stage.firstElementChild.remove();
    if(config.duration) setTimeout(()=>{
      if(!card.isConnected)return;
      if(config.exit!=='none'&&config.exitMs>0&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
        card.classList.remove('enter');card.classList.add('leave');setTimeout(()=>card.remove(),config.exitMs);
      }else card.remove();
    },config.duration*1000);
  };
  const channel=config.mode==='alert'?id:config.mode==='chat'?'multi-chat':'event-feed';
  const connect=()=>{
    const socket=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws/'+channel);
    socket.addEventListener('message',({data})=>{if(typeof data==='string'&&data.length<=16000){try{render(JSON.parse(data));}catch{}}});
    socket.addEventListener('close',()=>setTimeout(connect,2000));
  };
  connect();
})();
"""


def _text(value, limit: int, default: str = "") -> str:
    return value[:limit] if isinstance(value, str) else default


def _component(kind: str, raw: dict) -> dict:
    dyn = kind in DYNAMIC
    title = "{alert_title}" if kind == "alert" else "{user}" if dyn else LABELS[kind]
    body = {"alert": "{alert_text}", "chat": "{text}", "events": "{event_label}"}.get(kind, "")
    c = {"mode": kind if dyn else "static", "name": _text(raw.get("name"),60).strip() or LABELS[kind],
         "title": _text(raw.get("title"),220,title), "body": _text(raw.get("body"),380,body), **COLORS}
    for key, default in COLORS.items():
        value = raw.get(key)
        if isinstance(value,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",value):
            c[key] = value.lower()
    for key, (lo, hi, default) in RANGES.items():
        if kind in {"chat","events"}:
            default = {"duration":0,"size":22,"max":6,"positionY":100,"width":100}.get(key,default)
        value = raw.get(key)
        if type(value) is int:  # clamp before any float conversion
            c[key] = min(hi,max(lo,value))
        elif type(value) is float and math.isfinite(value):
            c[key] = min(hi,max(lo,math.floor(value + .5)))
        else:
            c[key] = default
    for key in ("enter","exit"):
        value = raw.get(key)
        c[key] = value if dyn and isinstance(value,str) and value in MOTION else "none"
    align = raw.get("align")
    c["align"] = align if align in ("left","center","right") else ("left" if dyn else "center")
    c["showPlatform"] = dyn and raw.get("showPlatform") is not False
    if not dyn or kind == "alert":
        c["max"] = 1
    return c


def read_pack(source: Path) -> tuple[str, str, list[tuple[str,dict]]]:
    if source.suffix.lower() != ".slbpack":
        raise ValueError("Selecciona un tema .slbpack.")
    with source.open("rb") as stream:
        data = stream.read(MAX_BYTES+1)
    if len(data) > MAX_BYTES:
        raise ValueError("El pack supera 64 KiB.")
    try:
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError,ValueError,RecursionError) as exc:
        raise ValueError("El pack no es un JSON válido.") from exc
    if not isinstance(raw,dict) or raw.get("format")!="slb-pack" or type(raw.get("version")) is not int or raw["version"]!=1:
        raise ValueError("El archivo no es un tema de Streamer Linux Bot v1.")
    name = _text(raw.get("name"),60).strip()
    pieces=raw.get("components")
    if not name or not isinstance(pieces,list) or not 1<=len(pieces)<=len(LABELS):
        raise ValueError("Elige un tema con nombre y entre 1 y 8 piezas.")
    out: list[tuple[str,dict]]=[]
    seen: set[str]=set()
    for item in pieces:
        if not isinstance(item,dict) or not isinstance(item.get("design"),dict):
            raise ValueError("Una pieza no tiene ajustes válidos.")
        kind=item.get("kind")
        if not isinstance(kind,str) or kind not in LABELS or kind in seen:
            raise ValueError("Una pieza está duplicada o no es compatible.")
        seen.add(kind)
        out.append((kind,_component(kind,item["design"])))
    return name,_text(raw.get("description"),240).strip(),out


def render_piece(kind: str, c: dict) -> str:
    dyn=kind in DYNAMIC
    colors = {
        "ink":c["textColor"],"accent":c["accent"],"fill":c["background"]+f"{round(c['opacity']*255/100):02x}",
        "glow":c["accent"]+"70","tracer":c["accent"]+"20",
    }
    transform={"slide-up":("translateY(24px)","translateY(-24px)"),"slide-left":("translateX(24px)","translateX(-24px)"),
               "zoom":("scale(.88)","scale(.88)"),"pop":("scale(.84)","scale(.88)")}
    a=transform.get(c["enter"],("none","none"))[0]
    b=transform.get(c["exit"],("none","none"))[1]
    props=colors|{"size":str(c["size"])+"px","padding":str(c["padding"])+"px","line":str(c["border"])+"px",
        "radius":str(c["radius"])+"px","offset":f"{(100-c['width'])*c['positionX']/100:g}%","y":f"{c['positionY']}%",
        "shift":f"-{c['positionY']}%","width":f"{c['width']}%","align":c["align"],
        "platform":"block" if c["showPlatform"] else "none","in":a,"out":b,
        "in-time":str(c["enterMs"])+"ms","out-time":str(c["exitMs"])+"ms"}
    # Quotes and HTML are never interpolated from untrusted values into styles or the fixed runtime.
    heading=f"<title>{html.escape(c['name'])}</title>"
    css=":root{"+";".join("--"+k+":"+v for k,v in props.items())+"}"+STYLE
    policy="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    if dyn:
        policy+="; script-src 'unsafe-inline'; connect-src ws://127.0.0.1:* ws://localhost:* wss://127.0.0.1:* wss://localhost:*"
        payload=json.dumps(c,ensure_ascii=True).replace("<",r"\u003c").replace(">",r"\u003e").replace("&",r"\u0026")
        body='<main id="stage" class="stage"></main><script type="application/json" id="slb-pack-data">'+payload+"</script><script>"+RUNTIME+"</script>"
    else:
        copy=f"<h1>{html.escape(c['title'])}</h1><p>{html.escape(c['body'])}</p>"
        label='<article class="card">'+copy+"</article>"
        body='<main class="frame">'+(label if c["title"] or c["body"] else "")+"</main>" if kind=="camera" else (
          '<main class="banner"><div class="stage">'+label+"</div></main>" if kind=="banner" else
          '<main class="scene"><div class="stage">'+label+"</div></main>")
    return ('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'
            +policy+'">'+heading+"<style>"+css+"</style><body>"+body+"</body></html>")


def import_pack(source: Path) -> list[OverlayInfo]:
    """Install each source into its own catalog entry, never replacing existing overlays."""
    name, desc, pieces=read_pack(Path(source))
    rendered=[(kind,render_piece(kind,piece)) for kind,piece in pieces]
    added: list[OverlayInfo]=[]
    try:
        for kind, content in rendered:
            title=name[:55]+" · "+LABELS[kind]
            with tempfile.TemporaryDirectory(prefix="slb-theme-") as staging:
                path=Path(staging)
                manifest={"id":_new_overlay_id(title),"name":title,"description":desc or f"Tema: {name}",
                          "params":[],"version":"1"}
                (path/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8")
                (path/"index.html").write_text(content,encoding="utf-8")
                added.append(import_overlay(path))
    except (OSError, ValueError):
        for info in reversed(added):
            shutil.rmtree(info.path,ignore_errors=True)
        raise
    return added
