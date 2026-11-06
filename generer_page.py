# -*- coding: utf-8 -*-
"""Prépare les données de la page en ligne « CRHB Week-end » (résultats, programme, visuels, textes).
Lancé automatiquement par une tâche planifiée Claude : lit la FFHB, crée les visuels et écrit
le dossier page_en_ligne/ (donnees.json + visuels/*.png) à publier sur la page."""
import json
import os
import shutil
import sys
from datetime import date, datetime

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import ffhb_resultats as f  # noqa: E402

SORTIE = os.path.join(ICI, "page_en_ligne")


def semaines():
    """Quel week-end pour les résultats et lequel pour le programme, selon le jour."""
    j = date.today().weekday()          # 0 = lundi
    if j <= 3:
        return 0, -1                    # lun-jeu : week-end passé / week-end suivant
    if j == 4:
        return 1, 0                     # vendredi : week-end passé / ce week-end
    return 0, 0                         # sam-dim : ce week-end (scores au fil de l'eau)


def matchs(res, mode):
    out = []
    for m in f.matchs_pour_visuel(res, mode):
        out.append({k: m.get(k) for k in ("categorie", "groupe_nom", "lieu", "salle", "jour", "dom", "ext",
                                           "sd", "se", "res", "heure", "date")})
    return out


def main():
    cfg = f.load_config()
    keys = f.club_keys(cfg)
    off_res, off_prog = semaines()
    print("Lecture de la FFHB…", flush=True)
    r_res = f.run_all(cfg, off_res, force=True)
    r_prog = r_res if off_prog == off_res else f.run_all(cfg, off_prog)
    if os.path.isdir(SORTIE):
        shutil.rmtree(SORTIE)
    os.makedirs(os.path.join(SORTIE, "visuels"))
    donnees = {"genere": datetime.now().strftime("%Y-%m-%dT%H:%M"), "club": cfg.get("club", ""),
               "controle": r_res.get("controle"), "semaines": {}}
    for cle, res, mode in (("resultats", r_res, "resultats"), ("programme", r_prog, "programme")):
        print(f"Visuels {mode}…", flush=True)
        fichiers = []
        try:
            for i, p in enumerate(f.generer_visuels(res, mode, theme="bleu"), 1):
                nom = f"{mode}_{res['du']}_{i}.png"
                shutil.copy(p, os.path.join(SORTIE, "visuels", nom))
                fichiers.append("visuels/" + nom)
        except Exception as e:
            print("Visuels impossibles :", e)
        ms = matchs(res, mode)
        texte = f.texte_programme(res, keys) if mode == "programme" else f.texte_reseaux(dict(res, offset=0), keys)
        donnees["semaines"][cle] = {"du": res["du"], "au": res["au"],
                                    "dates": f.titre_dates(res["du"], res["au"], ms) if ms else "",
                                    "matchs": ms, "visuels": fichiers, "texte": texte}
    # affiches du prochain match de N1 à domicile (championnat et Coupe de France)
    donnees["affiches"] = []
    os.makedirs(os.path.join(SORTIE, "affiches"), exist_ok=True)
    for t in ("n1", "cdf"):
        try:
            info = f.prochain_match_affiche(cfg, type_affiche=t, relire=False)
            jour = info["n1"][3]["date"]
            photos = sorted(x for x in os.listdir(f._dossier_photos()) if x.lower().endswith((".jpg", ".jpeg", ".png")))
            # même photo à chaque mise à jour pour un même match (sauf photo validée dans l'outil)
            photo = f.photo_validee(jour) or (photos[sum(map(ord, jour + t)) % len(photos)] if photos else None)
            print(f"Affiche {t}…", flush=True)
            chemin, det = f.generer_affiche(info, type_affiche=t, photo=os.path.basename(photo) if photo else None, relire=False)
            el = {"type": det.get("type_nom"), "match": det["match"], "date": det["date"], "heure": det.get("heure"),
                  "salle": det.get("salle"), "tour": det.get("tour"), "journee": det.get("journee")}
            for k, nom in (("fichier", f"affiche_{t}.png"), ("fichier_a4", f"affiche_{t}_A4.png"), ("fichier_pdf", f"affiche_{t}_A4.pdf")):
                if det.get(k):
                    shutil.copy(os.path.join(det["dossier"], det[k]), os.path.join(SORTIE, "affiches", nom))
                    el[k] = "affiches/" + nom
            donnees["affiches"].append(el)
        except Exception as e:
            print(f"Pas d'affiche {t} :", e)
    with open(os.path.join(SORTIE, "donnees.json"), "w", encoding="utf-8") as fh:
        json.dump(donnees, fh, ensure_ascii=False, indent=1)
    print("OK :", {k: (len(v["matchs"]), len(v["visuels"])) for k, v in donnees["semaines"].items()})


if __name__ == "__main__":
    main()
