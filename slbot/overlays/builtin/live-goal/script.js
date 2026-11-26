const metric = SLB.param("metric", "Regalos") === "Seguidores" ? "follow" : "gift";
const target = Math.min(1000000, Math.max(1, Math.floor(SLB.number("target", 25))));
const name = SLB.param("title", "").trim() || (metric === "follow" ? "Meta de seguidores" : "Meta de regalos");
const color = SLB.param("color", "#37dfa8");
if (/^#[0-9a-f]{6}$/i.test(color)) document.documentElement.style.setProperty("--accent", color);

let totals = {};
let preview;
function draw(counts, demo) {
  const value = Number(counts?.[metric]) || 0;
  document.getElementById("title").textContent = demo ? name + " (prueba)" : name;
  document.getElementById("total").textContent = value + " / " + target;
  const progress = document.getElementById("progress");
  progress.max = target;
  progress.value = Math.min(value, target);
}
draw(totals, false);
SLB.onMessage((msg) => {
  if (msg.channel === "goal") {
    totals = msg.counts;
    if (!preview) draw(totals, false);
  } else if (msg.channel === "goal-preview") {
    clearTimeout(preview);
    draw(msg.counts, true);
    preview = setTimeout(() => {
      preview = null;
      draw(totals, false);
    }, 3500);
  }
});
