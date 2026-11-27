(() => {
  "use strict";
  const platforms = Object.freeze({ twitch: "Twitch", youtube: "YouTube", kick: "Kick", tiktok: "TikTok" });
  const limit = 150;
  const main = document.querySelector("main");
  const list = document.getElementById("messages");
  const empty = document.getElementById("empty");
  const status = document.getElementById("status");
  const follow = document.getElementById("follow");
  const url = new URL("events", location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  let delay = 400, retry, socket, active = true;

  function report(state, text) {
    status.dataset.state = state;
    if (status.textContent !== text) status.textContent = text;
  }

  function atBottom() {
    return main.scrollHeight - main.scrollTop - main.clientHeight < 32;
  }

  function jump() {
    main.scrollTop = main.scrollHeight;
    follow.hidden = true;
  }

  function bounded(value, max) {
    return Array.from(value).slice(0, max).join("");
  }

  function receive(data) {
    if (!data || data.channel !== "chat" || !Object.hasOwn(platforms, data.platform) ||
        typeof data.text !== "string" || !data.text.trim() || data.simulated === true) return;
    const shouldFollow = atBottom();
    const row = document.createElement("li");
    const byline = document.createElement("div");
    byline.className = "byline";
    const platform = document.createElement("span");
    platform.className = "platform";
    platform.dataset.platform = data.platform;
    platform.textContent = platforms[data.platform];
    const name = document.createElement("bdi");
    name.className = "user";
    name.textContent = typeof data.user === "string" && data.user.trim() ? bounded(data.user, 100) : "Sin nombre";
    byline.append(platform, name);
    const message = document.createElement("p");
    message.className = "msg";
    message.dir = "auto";
    message.textContent = bounded(data.text, 500);
    row.append(byline, message);
    list.append(row);
    while (list.childElementCount > limit) {
      const removed = list.firstElementChild;
      const height = removed.offsetHeight;
      const top = main.scrollTop;
      removed.remove();
      if (!shouldFollow) main.scrollTop = Math.max(0, top - height);
    }
    empty.hidden = true;
    if (shouldFollow) jump();
    else follow.hidden = false;
  }

  function schedule() {
    if (!active || retry !== undefined) return;
    report("retry", "Reconectando…");
    retry = setTimeout(() => {
      retry = undefined;
      connect();
    }, delay);
    delay = Math.min(10000, delay * 2);
  }

  function connect() {
    if (!active) return;
    try { socket = new WebSocket(url); }
    catch { schedule(); return; }
    const connection = socket;
    connection.addEventListener("message", ({ data }) => {
      if (!active || socket !== connection || typeof data !== "string" || data.length > 8192) return;
      let value;
      try { value = JSON.parse(data); } catch { return; }
      if (value?.channel === "dock" && value.type === "hello") {
        delay = 400;
        report("live", "Conectado");
      } else receive(value);
    });
    connection.addEventListener("close", () => {
      if (connection === socket) schedule();
    });
  }

  main.addEventListener("scroll", () => { if (atBottom()) follow.hidden = true; }, { passive: true });
  follow.addEventListener("click", jump);
  window.addEventListener("pagehide", () => {
    active = false;
    clearTimeout(retry);
    retry = undefined;
    socket?.close();
  });
  window.addEventListener("pageshow", event => {
    if (event.persisted) {
      active = true;
      connect();
    }
  });
  connect();
})();
