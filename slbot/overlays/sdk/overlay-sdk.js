/*
 * SDK de overlays de Streamer Linux Bot.
 *
 * Inclúyelo en tu index.html:   <script src="/sdk/overlay-sdk.js"></script>
 *
 * Parámetros (URL personalizada > preferencia guardada > valor del script):
 *   SLB.param("color", "#ff4d8d")     -> texto
 *   SLB.number("duration", 5)         -> número
 *   SLB.bool("sound", true)           -> booleano
 *
 * Mensajes en vivo:
 *   SLB.onEvent("gift", fn)           -> eventos de plataforma (solo feed integrado)
 *   SLB.onAlert("mi-overlay", fn)     -> alertas que una acción envía a este overlay
 *   SLB.onMessage(fn)                 -> mensajes de esta suscripción
 *
 * IMPORTANTE: usa siempre textContent (no innerHTML) para mostrar nombres y
 * mensajes de los espectadores; así no pueden inyectar HTML en tu stream.
 */
(function () {
  "use strict";

  const query = new URLSearchParams(window.location.search);
  const messageHandlers = [];
  const overlayPath = window.location.pathname.match(/^\/overlay\/([a-z0-9_-]+)(?:\/|$)/);

  const overlayId = overlayPath ? overlayPath[1] : null;
  const presets = /* SLB_PRESETS */ {};
  const preset = overlayId && Object.prototype.hasOwnProperty.call(presets, overlayId) ? presets[overlayId] : {};

  function param(name, fallback) {
    if (query.has(name)) return query.get(name);
    return Object.prototype.hasOwnProperty.call(preset, name) ? String(preset[name]) : fallback;
  }

  function number(name, fallback) {
    const value = parseFloat(param(name, ""));
    return Number.isFinite(value) ? value : fallback;
  }

  function bool(name, fallback) {
    const value = param(name, null);
    return value === null ? fallback : ["1", "true", "yes", "si", "on"].includes(value.toLowerCase());
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
    if (!overlayPath) return;
    const scheme = window.location.protocol === "https:" ? "wss://" : "ws://";
    const ws = new WebSocket(scheme + window.location.host + "/ws/" + overlayPath[1]);
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

  window.SLB = { overlayId, param, number, bool, onMessage, onEvent, onAlert };
  connect();
})();
