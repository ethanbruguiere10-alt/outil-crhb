// Outil CRHB (version GitHub) : les images, vidéos, PDF et CSV demandés par la page
// (adresses « api/visuel.png?f=… », « api/csv?offset=… ») sont redirigés vers les fichiers du site.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  const base = new URL(self.registration.scope).pathname;
  if (u.origin !== location.origin || !u.pathname.startsWith(base + "api/")) return;
  const quoi = u.pathname.slice((base + "api/").length);
  let cible = null;
  if (/^visuel\.(png|jpg|mp4|pdf)$/.test(quoi) && u.searchParams.get("f"))
    cible = base + "visuels/" + encodeURIComponent(u.searchParams.get("f"));
  else if (quoi === "csv")
    cible = base + "data/csv_" + (parseInt(u.searchParams.get("offset") || "0", 10) || 0) + ".csv";
  if (cible) e.respondWith(Response.redirect(cible, 302));
});
