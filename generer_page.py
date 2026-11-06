# -*- coding: utf-8 -*-
"""Construit la version GitHub de l'outil CRHB (même page que sur l'ordinateur) dans le dossier « site ».
- python generer_page.py --complet        : tout (lancé chaque jour et après un changement de réglages)
- utilisé aussi par actions_github.py pour ne refaire que ce qu'une action a changé.
Les données sont écrites dans site/data/*.json, les images dans site/visuels/."""
import json
import os
import shutil
import sys
from datetime import datetime

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import ffhb_resultats as f  # noqa: E402

SITE = os.environ.get("FFHB_SITE") or os.path.join(ICI, "site")
DATA = os.path.join(SITE, "data")
VIS = os.path.join(SITE, "visuels")
SEMAINES = list(range(4, -4, -1))          # 4 week-ends passés … 3 à venir (0 = ce week-end / le dernier)
VISUELS_AUTO = (1, 0, -1)                  # visuels créés d'avance (les autres : à la demande)
SECRETS = (("wordpress", "mot_de_passe"), ("github", "jeton"), ("claude", "cle"))


def _ecrire(rel, obj):
    p = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, default=str)


def _lire(rel):
    try:
        with open(os.path.join(DATA, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _copier_visuel(chemin, nom=None):
    os.makedirs(VIS, exist_ok=True)
    nom = nom or os.path.basename(chemin)
    shutil.copy(chemin, os.path.join(VIS, nom))
    return nom


def config_publique():
    c = f.load_config()
    for sec, cle in SECRETS:
        if (c.get(sec) or {}).get(cle):
            c[sec][cle] = ""
    if (c.get("ia") or {}).get("cles"):
        c["ia"]["cles"] = {k: "" for k in c["ia"]["cles"]}
    c.pop("acces_mobile", None)
    return c


def page():
    """La page de l'outil, adaptée à GitHub (chemins relatifs + module GitHub)."""
    html = f.PAGE.replace("__CLOUD__", "false", 1)
    html = html.replace('"/api/', '"api/').replace("`/api/", "`api/").replace("'/api/", "'api/") \
               .replace('="/api/', '="api/').replace('"/logo.png"', '"logo.png"').replace('href="/logo.png"', 'href="logo.png"')
    html = html.replace("/api/", "api/").replace("/logo.png", "logo.png")
    module = open(os.path.join(ICI, "page", "gh.js"), encoding="utf-8").read()
    html = html.replace("<script>", "<script>\n" + module + "\n</script>\n<script>", 1)
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    shutil.copy(os.path.join(ICI, "page", "sw.js"), os.path.join(SITE, "sw.js"))
    shutil.copy(os.path.join(f.CHARTE_DIR, "logo.png"), os.path.join(SITE, "logo.png"))
    open(os.path.join(SITE, ".nojekyll"), "w").close()


def semaines(force=True):
    cfg = f.load_config()
    keys = f.club_keys(cfg)
    res_par_off = {}
    for i, off in enumerate(SEMAINES):
        print(f"Week-end {off}…", flush=True)
        res = f.run_all(cfg, off, force=force and i == 0)
        res = json.loads(json.dumps(res, default=str))
        res["texte"] = f.texte_reseaux(res, keys)
        res.update(maj_en_cours=False, salles_en_cours=False, progression={"total": 0, "lus": 0})
        _ecrire(f"res_{off}.json", res)
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, f"csv_{off}.csv"), "w", encoding="utf-8") as fh:
            fh.write(f.to_csv(res))
        res_par_off[off] = res
    return res_par_off


def visuels(off, mode, theme, res=None):
    if res is None:
        res = f.run_all(f.load_config(), off)
    noms = [_copier_visuel(p, f"{mode}_{theme}_{res['du']}_{i}.png")
            for i, p in enumerate(f.generer_visuels(res, mode, theme=theme), 1)]
    _ecrire(f"visuels_{off}_{mode}_{theme}.json", {"fichiers": noms, "dossier": "GitHub (site)"})
    return noms


def affiches():
    etat = f._etat_affiche()
    for t in ("n1", "cdf"):
        try:
            info = f.prochain_match_affiche(type_affiche=t, relire=False)
            jour = info["n1"][3]["date"]
            prec = (etat.get("dernieres_affiches") or {}).get(t) or {}
            photos = sorted(x for x in os.listdir(f._dossier_photos()) if x.lower().endswith((".jpg", ".jpeg", ".png")))
            photo = (prec.get("photo") if prec.get("date") == jour else None) \
                or (os.path.basename(f.photo_validee(jour)) if f.photo_validee(jour) else None) \
                or (photos[sum(map(ord, jour + t)) % len(photos)] if photos else None)
            print(f"Affiche {t}…", flush=True)
            _, det = f.generer_affiche(info, type_affiche=t, photo=photo, relire=False)
            publier_affiche(det)
        except Exception as e:
            print(f"Pas d'affiche {t} :", e)
            _ecrire(f"affiche_{t}.json", {})


def publier_affiche(det):
    for k in ("fichier", "fichier_a4", "fichier_pdf"):
        if det.get(k):
            _copier_visuel(os.path.join(det["dossier"], det[k]))
    det = dict(det, dossier="GitHub (site)")
    _ecrire(f"affiche_{det.get('type', 'n1')}.json", det)
    return det


def articles():
    try:
        _ecrire("articles.json", {"articles": f.wp_articles()})
    except Exception as e:
        _ecrire("articles.json", {"erreur": str(e)})


def ecran(r=None):
    r = r or (f._etat_affiche().get("ecran") or {})
    for v in r.get("videos") or []:
        for k in ("fichier", "apercu"):
            if v.get(k) and os.path.exists(os.path.join(f.VISUELS_DIR, v[k])):
                _copier_visuel(os.path.join(f.VISUELS_DIR, v[k]))
    _ecrire("ecran.json", dict(r, dossier="GitHub (site)"))


def version(action_id=None, complet=False):
    v = _lire("version.json") or {}
    actions = (v.get("actions") or [])[-30:]
    if action_id:
        actions.append(action_id)
    v = {"build": datetime.now().strftime("%Y%m%d%H%M%S"), "genere": datetime.now().strftime("%d/%m/%Y %H:%M"),
         "actions": actions, "complet": v.get("complet") if not complet else datetime.now().strftime("%d/%m/%Y %H:%M")}
    _ecrire("version.json", v)


def complet():
    if os.path.isdir(VIS):
        shutil.rmtree(VIS)       # on repart propre (les anciens week-ends disparaissent)
    os.makedirs(DATA, exist_ok=True)
    for x in os.listdir(DATA):
        if x.startswith("visuels_"):
            os.remove(os.path.join(DATA, x))
    page()
    _ecrire("config.json", config_publique())
    res = semaines(force=True)
    for off in VISUELS_AUTO:
        for mode in ("resultats", "programme"):
            for theme in ("bleu", "jaune"):
                try:
                    print(f"Visuels {off} {mode} {theme}…", flush=True)
                    visuels(off, mode, theme, res[off])
                except Exception as e:
                    print("Visuels impossibles :", e)
    affiches()
    ecran()
    articles()
    version(complet=True)


if __name__ == "__main__":
    complet()
    print("Site prêt :", SITE)
