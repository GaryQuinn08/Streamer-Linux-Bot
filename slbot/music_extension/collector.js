(() => {
  if (globalThis.__slbMusicCollector) return;
  globalThis.__slbMusicCollector = true;
  let busy = false;
  function tick() {
    if (busy) return;
    busy = true;
    chrome.runtime.sendMessage({kind:"tick"}).catch(() => {}).finally(() => { busy = false; });
  }
  setInterval(tick, 4000);
  document.addEventListener("visibilitychange", tick);
  for (const event of ["playing", "pause", "ended"]) document.addEventListener(event, tick, true);
  tick();
})();
