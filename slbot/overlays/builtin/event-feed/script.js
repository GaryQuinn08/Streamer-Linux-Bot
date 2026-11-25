document.documentElement.style.setProperty("--accent", SLB.param("color", "#4dd0ff"));
document.documentElement.style.setProperty("--size", SLB.number("size", 22) + "px");

const maxLines = Math.max(1, SLB.number("max", 6));
const feed = document.getElementById("feed");

const LABELS = {
  chat: "escribió",
  follow: "ahora te sigue",
  sub: "se suscribió",
  gift: "envió un regalo",
  donation: "donó",
  bits: "envió bits",
  raid: "hizo raid",
};

function describe(msg) {
  const data = msg.data || {};
  let detail = LABELS[msg.type] || msg.type;
  if (msg.type === "chat" && data.text) detail += ": " + data.text;
  if (msg.type === "gift" && data.gift_name) detail += ": " + data.gift_name + " x" + (data.count || 1);
  if (msg.type === "donation" && data.amount) detail += " " + data.amount + " " + (data.currency || "");
  return detail;
}

SLB.onEvent("*", (msg) => {
  const li = document.createElement("li");

  const who = document.createElement("span");
  who.className = "who";
  who.textContent = msg.user || msg.platform;   // textContent: nunca innerHTML
  li.appendChild(who);

  li.appendChild(document.createTextNode(" " + describe(msg)));

  feed.appendChild(li);
  while (feed.children.length > maxLines) feed.firstElementChild.remove();
});
