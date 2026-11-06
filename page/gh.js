// ===== Outil CRHB — version GitHub =====
// La page est la même que sur l'ordinateur. Ici, ses demandes « api/… » sont traitées ainsi :
//  - lecture (résultats, visuels, affiches, articles…) : fichiers du site (data/*.json), créés par GitHub ;
//  - actions (affiche, article, publication, réglages…) : lancées sur GitHub avec ton jeton, puis
//    la page attend le résultat (2 à 3 minutes).
(function () {
  const P = location.pathname.split("/").filter(Boolean);
  const DEPOT = { owner: location.hostname.split(".")[0], repo: P[0] || "outil-crhb" };
  const BASE = location.pathname.replace(/[^/]*$/, "");
  const _fetch = window.fetch.bind(window);
  const CLE = "crhb_jeton_github";
  const tok = { get() { try { return localStorage.getItem(CLE) || ""; } catch (e) { return ""; } },
                set(v) { try { v ? localStorage.setItem(CLE, v) : localStorage.removeItem(CLE); } catch (e) {} } };
  const dort = ms => new Promise(r => setTimeout(r, ms));
  const json = (o, code) => new Response(JSON.stringify(o), { status: code || 200, headers: { "Content-Type": "application/json" } });
  const b64d = s => decodeURIComponent(escape(atob(s.replace(/\n/g, ""))));
  const b64e = s => btoa(unescape(encodeURIComponent(s)));

  // service worker : images / vidéos / PDF / CSV
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(BASE + "sw.js", { scope: BASE }).then(() => {
      if (!navigator.serviceWorker.controller) {
        navigator.serviceWorker.addEventListener("controllerchange", () => {
          try { if (!sessionStorage.getItem("crhb_sw")) { sessionStorage.setItem("crhb_sw", "1"); location.reload(); } } catch (e) {}
        });
      }
    }).catch(() => {});
  }

  // ---- données du site ----
  let VERSION = null;
  async function version() {
    try { VERSION = await (await _fetch(BASE + "data/version.json?t=" + Date.now(), { cache: "no-store" })).json(); }
    catch (e) { VERSION = VERSION || { build: Date.now() }; }
    return VERSION;
  }
  async function donnee(nom) {
    if (!VERSION) await version();
    const r = await _fetch(BASE + "data/" + nom + "?v=" + VERSION.build);
    if (!r.ok) return null;
    return nom.endsWith(".json") ? r.json() : r.text();
  }

  // ---- GitHub ----
  function erreurGH(code, j) {
    const m = (j && j.message) || "";
    if (code === 401) return "jeton GitHub refusé (expiré ou mal copié) : reconnecte-toi dans Réglages.";
    if (code === 403) return "le jeton n'a pas toutes les permissions (Actions, Contents, Secrets, Variables en « Read and write »)." + (m ? " (" + m + ")" : "");
    if (code === 404) return "introuvable sur GitHub" + (m ? " (" + m + ")" : "");
    if (code === 422) return "GitHub a refusé la demande" + (m ? " : " + m : "");
    return "GitHub a répondu erreur " + code + (m ? " : " + m : "");
  }
  async function gh(methode, chemin, corps, jeton) {
    const t = jeton || tok.get();
    if (!t) { const e = new Error("connecte d'abord ce téléphone : Réglages → « Connexion administrateur »."); e.connexion = true; throw e; }
    const r = await _fetch("https://api.github.com/repos/" + DEPOT.owner + "/" + DEPOT.repo + chemin, {
      method: methode, cache: "no-store",
      headers: Object.assign({ Authorization: "Bearer " + t, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
                             corps ? { "Content-Type": "application/json" } : {}),
      body: corps ? JSON.stringify(corps) : undefined });
    if (r.status === 204) return null;
    const j = await r.json().catch(() => null);
    if (!r.ok) { const e = new Error(erreurGH(r.status, j)); e.status = r.status; throw e; }
    return j;
  }
  async function ecrireFichier(chemin, contenuB64, message) {
    let sha;
    try { sha = (await gh("GET", "/contents/" + chemin + "?ref=main")).sha; } catch (e) { if (e.status !== 404) throw e; }
    return gh("PUT", "/contents/" + chemin, { message: message || "Outil CRHB : " + chemin, content: contenuB64, sha, branch: "main" });
  }
  async function variable(nom, valeur) {
    try { await gh("PATCH", "/actions/variables/" + nom, { name: nom, value: valeur }); }
    catch (e) { if (e.status === 404) await gh("POST", "/actions/variables", { name: nom, value: valeur }); else throw e; }
  }
  async function lireVariable(nom) {
    try { return (await gh("GET", "/actions/variables/" + nom)).value; } catch (e) { if (e.status === 404) return null; throw e; }
  }
  let sodium = null;
  async function secret(nom, valeur) {
    if (!sodium) { sodium = (await import("https://cdn.jsdelivr.net/npm/libsodium-wrappers@0.7.13/+esm")).default; await sodium.ready; }
    const cle = await gh("GET", "/actions/secrets/public-key");
    const chiffre = sodium.crypto_box_seal(sodium.from_string(valeur), sodium.from_base64(cle.key, sodium.base64_variants.ORIGINAL));
    await gh("PUT", "/actions/secrets/" + nom, { encrypted_value: sodium.to_base64(chiffre, sodium.base64_variants.ORIGINAL), key_id: cle.key_id });
  }

  // lance une action sur GitHub et attend son résultat
  async function action(nom, params, attendre) {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    const t0 = Date.now();
    await gh("POST", "/actions/workflows/outil.yml/dispatches", { ref: "main", inputs: { action: nom, params: JSON.stringify(Object.assign({}, params || {}, { id })) } });
    if (attendre === false) return { id };
    let res = null;
    while (Date.now() - t0 < 20 * 60000) {
      await dort(7000);
      try { const fic = await gh("GET", "/contents/etat_web/" + id + ".json?ref=main"); res = JSON.parse(b64d(fic.content)); break; }
      catch (e) { if (e.status !== 404) throw e; }
      if (Date.now() - t0 > 60000) {   // la tâche a-t-elle échoué avant d'écrire son résultat ?
        const runs = (await gh("GET", "/actions/workflows/outil.yml/runs?per_page=10")).workflow_runs || [];
        const run = runs.find(r => (r.display_title || "").includes(id));
        if (run && run.status === "completed" && run.conclusion !== "success")
          throw new Error("la tâche a échoué sur GitHub (" + run.conclusion + "). Détails : " + run.html_url);
      }
    }
    if (!res) throw new Error("GitHub met plus de 20 minutes : regarde l'onglet Actions du dépôt.");
    // attendre que le site contienne le résultat (images, données)
    const t1 = Date.now();
    while (Date.now() - t1 < 5 * 60000) {
      await version();
      if ((VERSION.actions || []).includes(id)) break;
      await dort(6000);
    }
    return res;
  }
  // envoi de fichiers (photos, logo) dans entrees/<id>/ avant une action
  async function envoyer(fichiers) {
    const dossier = "entrees/" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    let i = 0;
    for (const f of fichiers) {
      i++;
      const [entete, donnees] = f.data.split(",");
      const ext = /png/.test(entete) ? "png" : /webp/.test(entete) ? "webp" : "jpg";
      await ecrireFichier(dossier + "/" + String(i).padStart(2, "0") + "." + ext, donnees, "Outil CRHB : fichier envoyé");
    }
    return dossier;
  }

  // ---- mise à jour complète en cours (bouton Actualiser / réglages) ----
  const MAJ = "crhb_maj";
  const majEnCours = () => { try { const m = JSON.parse(localStorage.getItem(MAJ) || "null"); return m && Date.now() - m.t < 15 * 60000 ? m : null; } catch (e) { return null; } };
  async function lancerMaj() {
    const v = await version();
    await action("reconstruire", {}, false);
    try { localStorage.setItem(MAJ, JSON.stringify({ t: Date.now(), build: v.build })); } catch (e) {}
  }

  async function etatAuto() {
    if (!tok.get()) return { non_configure: true, depot: DEPOT.owner + "/" + DEPOT.repo, jeton: false };
    let wf;
    try { wf = await gh("GET", "/actions/workflows/publication.yml"); }
    catch (e) { if (e.status === 404) return { erreur: "le fichier .github/workflows/publication.yml manque dans le dépôt (voir le guide)." }; throw e; }
    const modes = {};
    for (const [m, v] of [["resultats", "FFHB_AUTO_RESULTATS"], ["programme", "FFHB_AUTO_PROGRAMME"]])
      modes[m] = !/^(off|non|false|0)$/i.test((await lireVariable(v)) || "on");
    const runs = (await gh("GET", "/actions/workflows/publication.yml/runs?per_page=8")).workflow_runs || [];
    return { workflow_actif: wf.state === "active", modes, statut_publication: (await lireVariable("FFHB_WP_STATUT")) || "draft",
             lien: "https://github.com/" + DEPOT.owner + "/" + DEPOT.repo + "/actions/workflows/publication.yml",
             depot: DEPOT.owner + "/" + DEPOT.repo, jeton: true,
             executions: runs.map(r => ({ date: r.created_at, declencheur: r.event, statut: r.status, resultat: r.conclusion, lien: r.html_url })) };
  }

  // ---- toutes les demandes « api/… » de la page ----
  async function traiter(u, o) {
    const q = u.searchParams, m = (o && o.method || "GET").toUpperCase();
    const corps = o && o.body ? JSON.parse(o.body) : {};
    const chemin = u.pathname.slice((BASE + "api/").length);
    const off = parseInt(q.get("offset") || "0", 10) || 0;
    switch (chemin) {
      case "resultats": {
        if (q.get("force") === "1") await lancerMaj();
        await version();
        const r = await donnee("res_" + off + ".json");
        if (!r) return { erreur: "ce week-end n'est pas disponible ici (4 week-ends passés et 3 à venir)." };
        const enCours = majEnCours();
        if (enCours) Object.assign(r, { maj_en_cours: true, progression: { total: 0, lus: 0 } });
        return r;
      }
      case "etat": {
        const mj = majEnCours(); await version();
        if (mj && VERSION.build !== mj.build) { try { localStorage.removeItem(MAJ); } catch (e) {} return { maj_en_cours: false }; }
        return { maj_en_cours: !!mj, salles_en_cours: false, progression: { total: 0, lus: 0 } };
      }
      case "config":
        if (m === "GET") return (await donnee("config.json")) || { club: "", competitions: [] };
        {
          const fic = await gh("GET", "/contents/ffhb_config.json?ref=main");
          const c = JSON.parse(b64d(fic.content));
          c.club = corps.club ?? c.club; c.competitions = corps.competitions ?? c.competitions;
          await gh("PUT", "/contents/ffhb_config.json", { message: "Outil CRHB : réglages", content: b64e(JSON.stringify(c, null, 2)), sha: fic.sha, branch: "main" });
          return {};
        }
      case "visuels": {
        const mode = q.get("mode") === "programme" ? "programme" : "resultats", theme = q.get("theme") === "jaune" ? "jaune" : "bleu";
        const nom = "visuels_" + off + "_" + mode + "_" + theme + ".json";
        return (await donnee(nom)) || await action("visuels", { offset: off, mode, theme });
      }
      case "wordpress/publier":
        return action("publier", { offset: off, mode: q.get("mode") || "resultats", theme: q.get("theme") || "bleu" });
      case "affiche/derniere": return (await donnee("affiche_" + (q.get("type") === "cdf" ? "cdf" : "n1") + ".json")) || {};
      case "affiche": return action("affiche", { type: q.get("type"), photo: q.get("photo") || "", relire: q.get("relire") === "0" ? 0 : 1 });
      case "affiche/valider": case "affiche/devalider":
        return action(chemin.endsWith("devalider") ? "devalider" : "valider", { date: q.get("date"), photo: q.get("photo") || "" });
      case "affiche/logo": return action("logo", { nom: corps.nom, detourer: corps.detourer, dossier: await envoyer([{ data: corps.data }]) });
      case "affiche/infos":
        return action("infos", { type: corps.type, date: corps.date, texte: corps.texte, sans_image: corps.sans_image,
                                 dossier: corps.image ? await envoyer([{ data: corps.image }]) : "" });
      case "horaire": return action("horaire", corps);
      case "ecran": return action("ecran", {});
      case "ecran/dernieres": return (await donnee("ecran.json")) || {};
      case "article":
        return action("article", { texte: corps.texte, type: corps.type, couverture: corps.couverture,
                                   dossier: (corps.photos || []).length ? await envoyer(corps.photos) : "" });
      case "article/publier": return action("publier_article", { post_id: q.get("id") });
      case "wp/articles": return (await donnee("articles.json")) || { articles: [] };
      case "wp/supprimer": return action("supprimer_article", { post_id: corps.id, definitif: corps.definitif });
      case "auto/etat": return etatAuto();
      case "auto/regler":
        await variable(corps.mode === "programme" ? "FFHB_AUTO_PROGRAMME" : "FFHB_AUTO_RESULTATS", corps.actif ? "on" : "off");
        if (corps.actif) { try { await gh("PUT", "/actions/workflows/publication.yml/enable"); } catch (e) {} }
        return etatAuto();
      case "auto/statut": await variable("FFHB_WP_STATUT", corps.statut === "publish" ? "publish" : "draft"); return etatAuto();
      case "auto/lancer":
        await gh("POST", "/actions/workflows/publication.yml/dispatches", { ref: "main", inputs: { mode: corps.mode === "programme" ? "programme" : "resultats" } });
        return { lance: true };
      case "auto/local": return { mode_auto: "github", modes: { resultats: false, programme: false }, journal: [] };
      case "github/config": if (corps.jeton) await GHWEB.connecter(corps.jeton); return etatAuto();
      case "wordpress/config":
        if (corps.site) await secret("FFHB_WP_SITE", corps.site);
        if (corps.utilisateur) await secret("FFHB_WP_USER", corps.utilisateur);
        if (corps.mot_de_passe) await secret("FFHB_WP_PASSWORD", corps.mot_de_passe);
        if (corps.statut) await variable("FFHB_WP_STATUT", corps.statut === "publish" ? "publish" : "draft");
        return {};
      case "wordpress/test": return action("tester_wp", {});
      case "ia/config":
        for (const [mot, cle] of Object.entries(corps.cles || {})) if (cle) await secret("FFHB_" + mot.toUpperCase() + "_KEY", cle);
        if (corps.moteur) await variable("FFHB_IA_MOTEUR", corps.moteur);
        for (const [mot, mod] of Object.entries(corps.modeles || {})) if (mod) await variable("FFHB_IA_MODELE_" + mot.toUpperCase(), mod);
        return {};
      case "ia/test": return action("tester_ia", {});
      case "mobile": return {};
      default: return { erreur: "fonction non disponible sur la version GitHub : " + chemin };
    }
  }

  window.fetch = async function (entree, o) {
    const url = typeof entree === "string" ? entree : entree.url;
    const u = new URL(url, location.href);
    if (u.origin === location.origin && u.pathname.startsWith(BASE + "api/") && !/^visuel\.|^csv$/.test(u.pathname.slice((BASE + "api/").length))) {
      try { return json(await traiter(u, o)); }
      catch (e) { return json({ erreur: e.message || String(e) }); }
    }
    return _fetch(entree, o);
  };

  window.GHWEB = {
    depot: DEPOT,
    connecte: () => !!tok.get(),
    async connecter(t) {
      if (!/^(github_pat_|ghp_)/.test(t || "")) throw new Error("ce n'est pas un jeton GitHub : il commence par « github_pat_ ».");
      const d = await gh("GET", "", null, t);
      if (d.permissions && !d.permissions.push) throw new Error("ce jeton ne peut pas modifier le dépôt (Contents doit être en « Read and write »).");
      await gh("GET", "/actions/variables?per_page=1", null, t);
      tok.set(t);
    },
    deconnecter() { tok.set(""); },
  };
})();
