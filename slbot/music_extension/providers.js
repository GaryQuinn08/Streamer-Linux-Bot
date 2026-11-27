const exact = new Map(Object.entries({
  "open.spotify.com":"spotify",
  "music.youtube.com":"youtube",
  "music.amazon.com.mx":"amazon", "music.amazon.com":"amazon", "music.amazon.co.uk":"amazon",
  "music.amazon.ca":"amazon", "music.amazon.de":"amazon", "music.amazon.fr":"amazon",
  "music.amazon.es":"amazon", "music.amazon.it":"amazon", "music.amazon.co.jp":"amazon",
  "music.amazon.com.au":"amazon", "music.amazon.com.br":"amazon", "music.amazon.in":"amazon",
  "music.apple.com":"apple",
  "www.deezer.com":"deezer", "deezer.com":"deezer",
  "listen.tidal.com":"tidal"
}));
export const labels = Object.freeze({
  spotify:"Spotify web", youtube:"YouTube Music", amazon:"Amazon Music",
  apple:"Apple Music", deezer:"Deezer", tidal:"TIDAL"
});
export function providerFor(href) {
  try {
    const url = new URL(href);
    if (url.protocol === "https:" && !url.username && !url.password && !url.port) {
      return exact.get(url.hostname) || "";
    }
  } catch {}
  return "";
}
export function parseCode(code) {
  const match = /^(\d{1,5})\.([A-Za-z0-9_-]{43})$/.exec(String(code).trim());
  if (!match || +match[1] < 1 || +match[1] > 65535) return null;
  return {port:+match[1], token:match[2]};
}
