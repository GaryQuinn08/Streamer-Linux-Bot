const accent = SLB.param("color", "#ff4d8d");
const duration = SLB.number("duration", 5) * 1000;
const size = SLB.number("size", 42);

document.documentElement.style.setProperty("--accent", accent);
document.documentElement.style.setProperty("--size", size + "px");

const stage = document.getElementById("stage");
const queue = [];
let showing = false;

function nextAlert() {
  if (showing || queue.length === 0) return;
  showing = true;
  const msg = queue.shift();

  const card = document.createElement("div");
  card.className = "alert";

  const title = document.createElement("div");
  title.className = "title";
  title.textContent = msg.title || "";   // textContent: nunca innerHTML
  card.appendChild(title);

  if (msg.text) {
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = msg.text;
    card.appendChild(text);
  }

  stage.appendChild(card);

  setTimeout(() => {
    card.classList.add("leaving");
    setTimeout(() => {
      card.remove();
      showing = false;
      nextAlert();
    }, 400);
  }, duration);
}

SLB.onAlert(SLB.overlayId, (msg) => {
  queue.push(msg);
  nextAlert();
});
