/*
 * SDK de overlays de Streamer Linux Bot.
 *
 * Inclúyelo en tu index.html:   <script src="/sdk/overlay-sdk.js"></script>
 *
 * Parámetros (vienen de la URL, ej. ?color=%23ff0000&duration=8):
 *   SLB.param("color", "#ff4d8d")     -> texto
 *   SLB.number("duration", 5)         -> número
 *   SLB.bool("sound", true)           -> booleano
 *
 * Mensajes en vivo:
 *   SLB.onEvent("gift", fn)           -> eventos de plataforma (tipo "gift", "follow", "chat"...; "*" = todos)
 *   SLB.onAlert("mi-overlay", fn)     -> alertas que una acción envía a este overlay
 *   SLB.onMessage(fn)                 -> todos los mensajes sin filtrar
 *
 * IMPORTANTE: usa siempre textContent (no innerHTML) para mostrar nombres y
 * mensajes de los espectadores; así no pueden inyectar HTML en tu stream.
 */
(function () {
  "use strict";

  const query = new URLSearchParams(window.location.search);
  const messageHandlers = [];

  function param(name, fallback) {
    return query.has(name) ? query.get(name) : fallback;
  }

  function number(name, fallback) {
    const value = parseFloat(param(name, ""));
    return Number.isFinite(value) ? value : fallback;
  }

  function bool(name, fallback) {
    if (!query.has(name)) return fallback;
    return ["1", "true", "yes", "si", "on"].includes(query.get(name).toLowerCase());
  }

  function onMessage(fn) {
    messageHandlers.push(fn);
  }

  function onEvent(type, fn) {
    onMessage((msg) => {
      if (msg.channel === "event" && (type === "*" || msg.type === type)) fn(msg);
    });
  }

  function onAlert(overlayId, fn) {
    onMessage((msg) => {
      if (msg.channel === "alert" && msg.overlay === overlayId) fn(msg);
    });
  }

  function connect() {
    const ws = new WebSocket("ws://" + window.location.host + "/ws");
    ws.onmessage = (e) => {
      let msg;
      try {
        msg = JSON.parse(e.data);
      } catch (_) {
        return;
      }
      for (const fn of messageHandlers) {
        try {
          fn(msg);
        } catch (err) {
          console.error("[SLB] error en un manejador:", err);
        }
      }
    };
    ws.onclose = () => setTimeout(connect, 2000); // reconexión automática
  }

  window.SLB = { param, number, bool, onMessage, onEvent, onAlert };
  connect();
})();
