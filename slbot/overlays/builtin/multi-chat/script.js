(() => {
  "use strict";

  const platforms = new Map([
    ["twitch", "Twitch"], ["youtube", "YouTube"], ["kick", "Kick"], ["tiktok", "TikTok"]
  ]);
  const chat = document.getElementById("chat");
  const pendingRemoval = new Map();
  const clamp = (key, fallback, min, max) => Math.min(max, Math.max(min, SLB.number(key, fallback)));
  const maxLines = Math.floor(clamp("max", 8, 1, 24));
  const duration = clamp("duration", 0, 0, 300);
  const accent = SLB.param("color", "#a8f1dd");
  const root = document.documentElement.style;
  if (/^#[0-9a-f]{6}$/i.test(accent)) root.setProperty("--chat-name", accent);
  root.setProperty("--chat-size", clamp("size", 22, 12, 60) + "px");
  root.setProperty("--chat-opacity", clamp("opacity", 78, 0, 100) / 100);

  function tag(parent, cls, text, name = "span") {
    const node = document.createElement(name);
    node.className = cls;
    node.textContent = text;
    parent.appendChild(node);
  }

  function remove(row) {
    if (pendingRemoval.has(row)) clearTimeout(pendingRemoval.get(row));
    pendingRemoval.delete(row);
    row.remove();
  }

  SLB.onMessage((message) => {
    if (!message || message.channel !== "chat" || typeof message.text !== "string") return;
    const platform = platforms.get(message.platform);
    if (!platform || !SLB.bool(message.platform, true)) return;
    const row = document.createElement("li");
    row.className = "message";
    row.dataset.platform = message.platform;

    if (message.simulated === true) tag(row, "demo", "Prueba");
    if (SLB.bool("badges", true)) tag(row, "platform", platform);
    const sender = typeof message.user === "string" ? message.user.slice(0, 100) : "";
    tag(row, "sender", sender || platform, "bdi");
    row.appendChild(document.createTextNode(" · "));
    tag(row, "text", message.text.slice(0, 500), "bdi");

    chat.appendChild(row);
    const visibleFor = message.simulated === true ? Math.min(duration || 8, 8) : duration;
    if (visibleFor > 0) pendingRemoval.set(row, setTimeout(() => remove(row), visibleFor * 1000));
    while (chat.children.length > maxLines) remove(chat.firstElementChild);
  });
})();
