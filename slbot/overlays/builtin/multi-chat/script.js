(() => {
  "use strict";

  const platforms = new Map([
    ["twitch", "Twitch"], ["youtube", "YouTube"], ["kick", "Kick"], ["tiktok", "TikTok"]
  ]);
  const chat = document.getElementById("chat");
  const root = document.documentElement.style;
  const query = new URLSearchParams(window.location.search);
  const rows = new Map();
  const fadeMs = 320;
  let saved = null;
  let maxLines, duration, badges;

  function param(key, fallback) {
    if (query.has(key)) return query.get(key);
    if (saved === null) return SLB.param(key, fallback);
    return Object.prototype.hasOwnProperty.call(saved, key) ? String(saved[key]) : fallback;
  }

  function clamp(key, fallback, min, max) {
    const value = Number.parseFloat(param(key, String(fallback)));
    return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
  }

  function enabled(key) {
    return ["1", "true", "yes", "si", "on"].includes(String(param(key, "true")).toLowerCase());
  }

  function tag(parent, cls, text, name = "span") {
    const node = document.createElement(name);
    node.className = cls;
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function remove(row) {
    const entry = rows.get(row);
    if (entry) clearTimeout(entry.timer);
    rows.delete(row);
    row.remove();
  }

  function schedule(row, entry) {
    clearTimeout(entry.timer);
    row.classList.remove("fading");
    const seconds = entry.simulated ? Math.min(duration || 8, 8) : duration;
    entry.timer = undefined;
    if (!seconds) return;
    const remaining = Math.max(0, seconds * 1000 - (performance.now() - entry.at));
    const startFade = () => {
      row.classList.add("fading");
      entry.timer = setTimeout(() => remove(row), fadeMs);
    };
    if (remaining > 0) entry.timer = setTimeout(startFade, remaining);
    else startFade();
  }

  function trim() {
    while (chat.children.length > maxLines) remove(chat.firstElementChild);
  }

  function applySettings() {
    maxLines = Math.floor(clamp("max", 8, 1, 24));
    const previousDuration = duration;
    duration = clamp("duration", 15, 0, 300);
    badges = enabled("badges");
    const accent = param("color", "#a8f1dd");
    root.setProperty("--chat-name", /^#[0-9a-f]{6}$/i.test(accent) ? accent : "#a8f1dd");
    root.setProperty("--chat-size", clamp("size", 22, 12, 60) + "px");
    root.setProperty("--chat-opacity", clamp("opacity", 78, 0, 100) / 100);
    for (const [row, entry] of rows) {
      if (!enabled(row.dataset.platform)) remove(row);
      else {
        entry.badge.hidden = !badges;
        if (duration !== previousDuration) schedule(row, entry);
      }
    }
    trim();
  }

  applySettings();
  SLB.onMessage((message) => {
    if (!message || typeof message !== "object") return;
    if (message.channel === "chat-settings") {
      const values = message.values;
      if (!values || typeof values !== "object" || Array.isArray(values)) return;
      saved = values;
      applySettings();
      return;
    }
    if (message.channel !== "chat" || typeof message.text !== "string") return;
    const platform = platforms.get(message.platform);
    if (!platform || !enabled(message.platform)) return;
    const row = document.createElement("li");
    row.className = "message";
    row.dataset.platform = message.platform;

    const simulated = message.simulated === true;
    if (simulated) tag(row, "demo", "Prueba");
    const badge = tag(row, "platform", platform);
    badge.hidden = !badges;
    const sender = typeof message.user === "string" ? message.user.slice(0, 100) : "";
    tag(row, "sender", sender || platform, "bdi");
    row.appendChild(document.createTextNode(" · "));
    tag(row, "text", message.text.slice(0, 500), "bdi");

    chat.appendChild(row);
    const entry = { at: performance.now(), simulated, badge, timer: undefined };
    rows.set(row, entry);
    schedule(row, entry);
    trim();
  });
})();
