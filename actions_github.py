# -*- coding: utf-8 -*-
"""Actions lancées depuis la page GitHub de l'outil (bouton → workflow « Outil CRHB – action »).
Usage : python actions_github.py <action> '<paramètres JSON>'
Le résultat est écrit dans etat_web/<id>.json (lu par la page), puis le site est mis à jour."""
import base64
import json
import os
import shutil
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import ffhb_resultats as f  # noqa: E402
import generer_page as g    # noqa: E402

ETAT = os.path.join(ICI, "etat_web")
ENTREES = os.path.join(ICI, "entrees")


def _data_uri(chemin):
    ext = chemin.lower().rsplit(".", 1)[-1]
    mime = {"png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(open(chemin, "rb").read()).decode()


def _fichiers(dossier):
    d = os.path.join(ICI, dossier or "")
    if not dossier or not d.startswith(ENTREES) or not os.path.isdir(d):
        return []
    return [os.path.join(d, x) for x in sorted(os.listdir(d)) if not x.endswith(".json")]


def faire(action, p):
    """Renvoie le résultat (dict) de l'action. Met à jour les morceaux du site concernés."""
    if action in ("reconstruire", "actualiser"):
        g.complet()
        return {"ok": True}
    if action == "visuels":
        off, mode, theme = int(p["offset"]), p.get("mode", "resultats"), p.get("theme", "bleu")
        noms = g.visuels(off, mode, theme)
        return {"fichiers": noms, "dossier": "GitHub (site)"}
    if action == "publier":
        res = f.run_all(f.load_config(), int(p.get("offset", 0)), force=True)
        return f.wp_publier(res, p.get("mode", "resultats"), p.get("theme", "bleu"))
    if action == "affiche":
        _, det = f.generer_affiche(type_affiche="cdf" if p.get("type") == "cdf" else "n1",
                                   photo=p.get("photo") or None, relire=p.get("relire", 1) not in (0, "0", False))
        return g.publier_affiche(det)
    if action in ("valider", "devalider"):
        return f.valider_photo(p.get("date", ""), p.get("photo", ""), action == "valider")
    if action == "horaire":
        out = f.corriger_horaire(p.get("date", ""), p.get("dom", ""), p.get("ext", ""), p.get("heure", ""))
        g.semaines(force=False)
        return out
    if action == "logo":
        fic = _fichiers(p.get("dossier"))
        if not fic:
            raise RuntimeError("image du logo introuvable")
        return f.enregistrer_logo(p.get("nom", ""), _data_uri(fic[0]), p.get("detourer", "auto"))
    if action == "infos":
        fic = _fichiers(p.get("dossier"))
        return f.enregistrer_infos("cdf" if p.get("type") == "cdf" else "n1", p.get("date", ""), p.get("texte", ""),
                                   _data_uri(fic[0]) if fic else None, bool(p.get("sans_image")))
    if action == "ecran":
        r = f.generer_videos_ecran()
        g.ecran(r)
        return dict(r, dossier="GitHub (site)")
    if action == "article":
        photos = [{"nom": os.path.basename(x), "data": _data_uri(x), "ia": _data_uri(x)} for x in _fichiers(p.get("dossier"))]
        out = f.creer_article(p.get("texte", ""), p.get("type", "match"), photos=photos, couverture=bool(p.get("couverture", True)))
        if out.get("couverture") and os.path.exists(os.path.join(f.VISUELS_DIR, out["couverture"])):
            g._copier_visuel(os.path.join(f.VISUELS_DIR, out["couverture"]))
        out.pop("html", None)
        return out
    if action == "publier_article":
        out = f.publier_article(p.get("post_id"))
        g.articles()
        return out
    if action == "supprimer_article":
        out = f.wp_supprimer_article(p.get("post_id"), bool(p.get("definitif")))
        g.articles()
        return out
    if action == "liste_articles":
        g.articles()
        return g._lire("articles.json") or {}
    if action == "tester_wp":
        return f.wp_tester()
    if action == "tester_ia":
        return f.ia_tester()
    raise RuntimeError(f"action inconnue : {action}")


def main():
    action = sys.argv[1]
    p = json.loads(sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else "{}")
    ident = "".join(c for c in str(p.get("id", "")) if c.isalnum() or c in "-_")[:40] or str(int(time.time()))
    os.makedirs(ETAT, exist_ok=True)
    try:
        out = faire(action, p)
        out = json.loads(json.dumps(out if isinstance(out, dict) else {"resultat": out}, default=str))
    except Exception as e:
        out = {"erreur": str(e.args[0]) if getattr(e, "args", None) else str(e)}
        print("ERREUR :", out["erreur"])
    out["_action"], out["_fini"] = action, time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(ETAT, f"{ident}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    # on ne garde que les 30 derniers résultats, et on efface les fichiers envoyés pour cette action
    anciens = sorted((os.path.join(ETAT, x) for x in os.listdir(ETAT)), key=os.path.getmtime)[:-30]
    for x in anciens:
        os.remove(x)
    if p.get("dossier") and os.path.isdir(os.path.join(ICI, p["dossier"])) and os.path.join(ICI, p["dossier"]).startswith(ENTREES):
        shutil.rmtree(os.path.join(ICI, p["dossier"]))
    if action not in ("reconstruire", "actualiser"):
        g.page()
        g._ecrire("config.json", g.config_publique())
    g.version(ident)
    print(json.dumps(out, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
