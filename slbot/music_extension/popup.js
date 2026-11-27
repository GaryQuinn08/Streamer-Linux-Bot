import {labels} from "./providers.js";

const code = document.querySelector("#code");
const status = document.querySelector("#status");
const start = document.querySelector("#start");
const stop = document.querySelector("#stop");
function show(text) { status.textContent = text; }
async function send(message) {
  try { return await chrome.runtime.sendMessage(message); }
  catch { return {ok:false,error:"No se pudo iniciar la extensión."}; }
}
start.addEventListener("click", async () => {
  start.disabled = stop.disabled = true;
  const result = await send({kind:"start", code:code.value});
  start.disabled = stop.disabled = false;
  if (!result?.ok) { show(result?.error || "No se pudo compartir."); return; }
  code.value = "";
  show(result.waiting ? "Conectado a " + labels[result.active] + ". Reproduce una canción." :
                        "Compartiendo " + labels[result.active] + ".");
});
stop.addEventListener("click", async () => {
  const result = await send({kind:"stop"});
  show(result?.ok ? "Dejaste de compartir." : "No se pudo detener.");
});
send({kind:"state"}).then(result => {
  if (result?.active) show("Pestaña seleccionada: " + labels[result.active] + ".");
});
