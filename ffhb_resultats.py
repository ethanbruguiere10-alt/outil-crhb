#!/usr/bin/env python3
"""
FFHB Résultats — les scores du dernier week-end, automatiquement
================================================================

Ce programme ouvre les pages de ffhandball.fr dans un vrai navigateur invisible
(Chromium, via Playwright), exactement comme si tu les ouvrais toi-même. Il lit
les scores une fois la page affichée, garde ceux du dernier week-end et les
affiche dans une page web locale.

LANCER
------
    Double-clic sur « Lancer (Windows).bat » ou « Lancer (Mac).command »
    ou :  python ffhb_resultats.py

La première fois, il installe automatiquement ce qui manque (1 à 2 minutes).

AUTRES COMMANDES
----------------
    python ffhb_resultats.py --texte             résultats du dernier week-end dans le terminal
    python ffhb_resultats.py --texte --semaine 1 week-end d'avant
    python ffhb_resultats.py --voir              affiche le navigateur pendant la lecture

EN CAS DE PROBLÈME
------------------
À chaque lecture, le dossier « ffhb_debug » est rempli (capture d'écran, code
de la page, données reçues). Zippe ce dossier et envoie-le à Claude.
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "ffhb_config.json")
DEBUG_DIR = os.path.join(HERE, "ffhb_debug")
PORT = 8765
CLOUD = os.environ.get("FFHB_CLOUD") == "1"   # version en ligne (Hugging Face) : voir le dossier « en_ligne »
PORT_MOBILE = 8766   # accès depuis le téléphone (même Wi-Fi)

CONFIG_VERSION = 6
# anciens liens remplacés automatiquement
URL_REMPLACEES = {
    "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m15-ans-feminin-division-2-aura-30519/": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m15-ans-feminin-division-2-aura-30519/poule-196652/",
}
NOMS_REMPLACES = {"Coupe de France M": "N1 CDF", "Coupe de France F (N3 F)": "N3 F CDF"}
DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,
    "club": "Caluire, Rillieux",
    "competitions": [
        {"nom": "N3 F", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/nationale-3-feminine-aura-30494/equipe-2117124/"},
        {"nom": "SF 2", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/1ere-division-feminine-p16-aura-30500/poule-196354/"},
        {"nom": "-18 F", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m18-ans-feminin-excellence-aura-30507/poule-190309/"},
        {"nom": "-15 F", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m15-ans-feminin-division-2-aura-30519/poule-196652/"},
        {"nom": "-13 F", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m13-ans-feminin-excellence-aura-30510/poule-190367/"},
        {"nom": "N1 M", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/national/nationale-1-masculine-2026-2027-32469/poule-190839/"},
        {"nom": "N3 M", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/national/nationale-3-masculine-2026-2027-32502/poule-190855/"},
        {"nom": "S3 M Région", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/honneur-masculin-aura-30498/poule-190173/"},
        {"nom": "S4 M Départemental", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/2eme-division-masculine-p16-aura-30501/poule-196320/"},
        {"nom": "-18M", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m18-ans-masculin-excellence-aura-30502/poule-191206/"},
        {"nom": "-15M 1", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m15-ans-masculin-excellence-aura-30504/poule-190325/"},
        {"nom": "-15M 2", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m15-ans-masculin-division-1-aura-30512/poule-196976/"},
        {"nom": "-13M 1", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m13-ans-masculin-excellence-aura-30506/poule-190354/"},
        {"nom": "-13M 2", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m13-ans-masculin-division-1-aura-30513/poule-196991/"},
        {"nom": "-13M 3", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m13-ans-masculin-division-2-aura-30518/poule-196712/"},
        {"nom": "-11 (1)", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/departemental/championnat-masculin-11-32912/poule-197308/"},
        {"nom": "-11 (2)", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/departemental/championnat-masculin-11-32912/poule-197211/"},
        {"nom": "-11 (3)", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/departemental/championnat-masculin-11-32912/poule-197217/"},
        {"nom": "-18 M CF (Lyon Métropole)", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/national/u18-masculins-2026-2027-32522/poule-190989/", "club": "Lyon Metropole"},
        {"nom": "-17 M (Entente Est)", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/regional/m17-ans-masculin-excellence-aura-30503/poule-190250/", "club": "Lyon Est, Entente Est"},
        # Coupes de France : lien de la coupe (sans poule) ; l'outil lit chaque tour (1er tour, 2e tour...)
        {"nom": "N1 CDF", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/coupe-de-france/coupe-de-france-caisse-d-epargne-federale-masculine-2026-2027-32510/"},
        {"nom": "N3 F CDF", "url": "https://www.ffhandball.fr/competitions/saison-2026-2027-22/coupe-de-france/coupe-de-france-caisse-d-epargne-regionale-feminine-2026-2027-32661/"},
    ],
}

MOIS = {"janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "mar": 3,
        "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8,
        "septembre": 9, "sept": 9, "sep": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
        "decembre": 12, "dec": 12}


# ==========================================================================
# Installation automatique de Playwright
# ==========================================================================
def contexte_ssl():
    """Certificats SSL fiables : sur Mac, le Python de python.org n'a pas les certificats système
    (erreur CERTIFICATE_VERIFY_FAILED). On utilise ceux de « certifi », installé automatiquement."""
    import ssl
    try:
        import certifi
    except ImportError:
        base = [sys.executable, "-m", "pip", "install", "-q", "certifi"]
        for cmd in (base, base + ["--user"], base + ["--break-system-packages"]):
            if subprocess.call(cmd) == 0:
                break
        try:
            import importlib
            importlib.invalidate_caches()
            import certifi
        except ImportError:
            return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def ensure_playwright():
    ensure_pillow()
    try:
        import playwright.sync_api  # noqa: F401
        return
    except ImportError:
        pass
    print("Première utilisation : installation de Playwright (navigateur automatique)...")
    base = [sys.executable, "-m", "pip", "install", "playwright"]
    for cmd in (base, base + ["--user"], base + ["--break-system-packages"]):
        if subprocess.call(cmd) == 0:
            break
    else:
        sys.exit("Impossible d'installer Playwright. Lance :  pip install playwright")
    install_browser()


def ensure_pillow():
    """Pillow (retouche d'images : détourage des logos, photos, PDF A4) : installé au premier lancement."""
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        pass
    print("Première utilisation : installation de Pillow (retouche des images)...")
    base = [sys.executable, "-m", "pip", "install", "pillow"]
    for cmd in (base, base + ["--user"], base + ["--break-system-packages"]):
        if subprocess.call(cmd) == 0:
            break
    else:
        return False
    import importlib, site
    importlib.invalidate_caches()
    try:
        sys.path.append(site.getusersitepackages())
    except Exception:
        pass
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


_install_tente = False


def install_browser():
    """Télécharge le navigateur de Playwright. Renvoie True si ça a marché."""
    global _install_tente
    if _install_tente:
        return False
    _install_tente = True
    print("\nTéléchargement du navigateur intégré (une seule fois, 1 à 3 minutes)...")
    ok = subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"]) == 0
    # certaines versions séparent le navigateur "sans fenêtre" : on l'installe aussi
    subprocess.call([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ok


MSG_NAVIGATEUR = ("Aucun navigateur utilisable. Ouvre le Terminal et tape :\n"
                  f"   {os.path.basename(sys.executable)} -m playwright install chromium\n"
                  "puis relance le programme. (Installer Google Chrome règle aussi le problème.)")


def launch_browser(pw, visible=False):
    """Essaie : navigateur Playwright -> installation auto -> Google Chrome -> Microsoft Edge."""
    headless = not visible
    if os.environ.get("FFHB_CLOUD") == "1":   # serveur en ligne (conteneur) : mémoire partagée limitée
        return pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--disable-gpu"])
    try:
        return pw.chromium.launch(headless=headless)
    except Exception as e:
        first = e
    if install_browser():
        try:
            return pw.chromium.launch(headless=headless)
        except Exception:
            pass
    for channel in ("chrome", "msedge"):
        try:
            b = pw.chromium.launch(channel=channel, headless=headless)
            print(f"(Utilisation de {'Google Chrome' if channel == 'chrome' else 'Microsoft Edge'} déjà installé)")
            return b
        except Exception:
            pass
    raise RuntimeError(MSG_NAVIGATEUR) from first


def check_browser():
    """Vérifie au démarrage que le navigateur se lance (et l'installe si besoin)."""
    from playwright.sync_api import sync_playwright
    print("Vérification du navigateur...")
    with sync_playwright() as pw:
        try:
            launch_browser(pw).close()
        except RuntimeError as e:
            print("\n" + str(e))
            if sys.stdin and sys.stdin.isatty():
                input("\nAppuie sur Entrée pour fermer.")
            sys.exit(1)
    print("Navigateur OK.")


# ==========================================================================
# Configuration
# ==========================================================================
def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("competitions"):
            # mise à jour : ajoute les nouvelles équipes du club sans toucher aux réglages existants
            if cfg.get("version", 1) < CONFIG_VERSION:
                for c in cfg["competitions"]:
                    c["url"] = URL_REMPLACEES.get(c.get("url", ""), c.get("url", ""))
                known = {c.get("url", "").rstrip("/") for c in cfg["competitions"]}
                cfg["competitions"] += [c for c in DEFAULT_CONFIG["competitions"] if c["url"].rstrip("/") not in known]
                for c in cfg["competitions"]:   # v6 : noms des coupes
                    c["nom"] = NOMS_REMPLACES.get(c.get("nom", ""), c.get("nom", ""))
                cfg["version"] = CONFIG_VERSION
                save_config(cfg)
            return cfg
    except Exception:
        pass
    save_config(DEFAULT_CONFIG)
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def club_keys(cfg):
    return [norm(k) for k in re.split(r"[,;]", cfg.get("club", "")) if k.strip()]


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def is_club(name, keys):
    n = norm(name)
    return bool(keys) and any(k in n for k in keys)


# ==========================================================================
# Dates
# ==========================================================================
def weekend(offset=0, today=None):
    """Vendredi -> dimanche. En semaine : le week-end passé. Ven/sam/dim : le week-end en cours."""
    today = today or date.today()
    wd = today.weekday()  # lundi=0 ... dimanche=6
    fri = today - timedelta(days=(wd - 4) if wd >= 4 else (wd + 3))
    fri -= timedelta(weeks=offset)
    return fri, fri + timedelta(days=2)


def season_years(url):
    m = re.search(r"saison-(\d{4})-(\d{4})", url or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    t = date.today()
    return (t.year, t.year + 1) if t.month >= 7 else (t.year - 1, t.year)


def parse_date(s, url=""):
    """Renvoie (date, 'HH:MM' ou None)."""
    if not s:
        return None, None
    s = str(s)
    heure = None
    mh = re.search(r"\b(\d{1,2})\s*[hH:]\s*(\d{2})\b", s)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", s)
    if m:
        d = date(int(m[1]), int(m[2]), int(m[3]))
        if m[4]:
            heure = f"{m[4]}:{m[5]}"
        elif mh:
            heure = f"{int(mh[1]):02d}:{mh[2]}"
        return d, heure
    if mh:
        heure = f"{int(mh[1]):02d}:{mh[2]}"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s)
    if m:
        y = int(m[3]); y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m[2]), int(m[1])), heure
        except ValueError:
            return None, heure
    n = norm(s)
    m = next((x for x in re.finditer(r"\b(\d{1,2})(?:er)?\s+([a-z]{3,9})\.?(?:\s+(\d{4}))?", n)
              if x[2] in MOIS), None)
    if m:
        mois = MOIS[m[2]]
        if m[3]:
            y = int(m[3])
        else:
            a, b = season_years(url)
            y = a if mois >= 7 else b
        try:
            return date(y, mois, int(m[1])), heure
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", s)
    if m:
        a, b = season_years(url)
        mois = int(m[2])
        try:
            return date(a if mois >= 7 else b, mois, int(m[1])), heure
        except ValueError:
            pass
    return None, heure


# ==========================================================================
# 1) Reconnaissance dans des données JSON (réseau ou attributs de la page)
# ==========================================================================
def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def _name(v):
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        for k in ("libelle", "nom", "name", "shortName", "libelleCourt", "structureLibelle", "equipeLibelle"):
            if isinstance(v.get(k), str) and v[k].strip():
                return v[k].strip()
    return None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d{1,3}\s*", v):
        return int(v)
    return None


def _int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*[-+]?\d+\s*", v):
        return int(v)
    return None


def _find(d, pats, conv):
    for k, v in d.items():
        kl = k.lower()
        if any(re.search(p, kl) for p in pats):
            r = conv(v)
            if r not in (None, ""):
                return r
    return None


P_HOME = [r"^(equipe|team|club)_?(1|dom|home|a|recevant|locale?)_?(libelle|nom|name)?$",
          r"^(equipe|team)_?1.*(libelle|nom|name)", r"^hometeam(name)?$", r"^home$", r"^recevant"]
P_AWAY = [r"^(equipe|team|club)_?(2|ext|away|b|visiteur)_?(libelle|nom|name)?$",
          r"^(equipe|team)_?2.*(libelle|nom|name)", r"^awayteam(name)?$", r"^away$", r"^visiteur"]
P_HS = [r"^(equipe|team)_?(1|dom|home)_?(score|buts)$", r"^score_?(1|dom|home|equipe_?1)$",
        r"^(equipe|team)_?1.*(score|buts)", r"^homescore$", r"^butsdom"]
P_AS = [r"^(equipe|team)_?(2|ext|away)_?(score|buts)$", r"^score_?(2|ext|away|equipe_?2)$",
        r"^(equipe|team)_?2.*(score|buts)", r"^awayscore$", r"^butsext"]
P_DATE = [r"^date$", r"^date_?(rencontre|match|heure|debut)?$", r"^startdate$", r"datetime", r"^horaire"]
P_J = [r"^journee_?(numero|num|number)?$", r"^round$"]
P_ID = [r"^(ext_)?(rencontre|match)_?id$", r"^extrencontreid$", r"^id$"]


def _nested_score(d, rx):
    k = next((k for k in d if re.fullmatch(rx, k.lower())), None)
    v = d.get(k) if k else None
    if isinstance(v, dict):
        for s in ("score", "buts", "points", "goals"):
            n = _num(v.get(s))
            if n is not None:
                return n
    return None


def matches_from_json(data, url):
    out = []
    for d in walk(data):
        home, away = _find(d, P_HOME, _name), _find(d, P_AWAY, _name)
        if not home or not away or home == away:
            continue
        hs, as_ = _find(d, P_HS, _num), _find(d, P_AS, _num)
        if hs is None:
            hs = _nested_score(d, r"(equipe|team)_?1|hometeam|home")
        if as_ is None:
            as_ = _nested_score(d, r"(equipe|team)_?2|awayteam|away")
        raw_date = _find(d, P_DATE, lambda v: v if isinstance(v, str) and re.search(r"\d", v) else None)
        dd, hh = parse_date(raw_date, url)
        out.append({
            "id": _find(d, P_ID, lambda v: str(v) if isinstance(v, (int, str)) and str(v).strip() else None),
            "journee": _find(d, P_J, lambda v: _num(v.get("numero")) if isinstance(v, dict) else _num(v)),
            "date": dd.isoformat() if dd else None, "heure": hh,
            "dom": home, "ext": away, "sd": hs, "se": as_,
        })
    return out


def standings_from_json(data):
    best = []
    for node in walk(data):
        for v in node.values():
            if not (isinstance(v, list) and len(v) >= 4 and all(isinstance(x, dict) for x in v)):
                continue
            rows = []
            for x in v:
                eq = _find(x, [r"^(equipe|team|club)_?(libelle|nom|name)?$", r"^libelle$", r"^nom$",
                               r"structurelibelle", r"equipelibelle"], _name)
                pts = _find(x, [r"^(points?|pts|nbpoints?|point_?total)$"], _num)
                if eq and pts is not None:
                    rows.append({
                        "pos": _find(x, [r"^(position|rang|rank|place|classement)$"], _num),
                        "equipe": eq, "pts": pts,
                        "j": _find(x, [r"^(joues?|matchs?_?joues?|played|nbmatchs?|j)$"], _num),
                        "g": _find(x, [r"^(gagnes?|victoires?|won|g|nbvictoires?)$"], _num),
                        "n": _find(x, [r"^(nuls?|draws?|n|nbnuls?)$"], _num),
                        "p": _find(x, [r"^(perdus?|defaites?|lost|p|nbdefaites?)$"], _num),
                        "diff": _find(x, [r"^(diff|difference|goalaverage|goal_?diff)$"], _int),
                    })
            if len(rows) >= 4 and len(rows) >= 0.8 * len(v) and len(rows) > len(best):
                if all(r["pos"] is None for r in rows):
                    for i, r in enumerate(rows, 1):
                        r["pos"] = i
                rows.sort(key=lambda r: r["pos"] or 99)
                best = rows
    return best


def json_blobs_in_html(html_text):
    """JSON caché dans les attributs des balises (composants web) et scripts JSON."""
    import base64
    import html as H
    from urllib.parse import unquote
    blobs = []
    for m in re.finditer(r'=\s*"([^"]{40,})"|=\s*\'([^\']{40,})\'', html_text):
        raw = m.group(1) or m.group(2)
        for c in (H.unescape(raw), unquote(H.unescape(raw))):
            c = c.strip()
            if c[:1] in "[{":
                try:
                    blobs.append(json.loads(c)); break
                except Exception:
                    pass
            elif re.fullmatch(r"[A-Za-z0-9+/=_\-]{40,}", c):
                try:
                    dec = base64.b64decode(c.replace("-", "+").replace("_", "/") + "=" * (-len(c) % 4)).decode("utf-8")
                    if dec.strip()[:1] in "[{":
                        blobs.append(json.loads(dec)); break
                except Exception:
                    pass
    for m in re.finditer(r"<script[^>]*type=[\"']application/(?:ld\+)?json[\"'][^>]*>(.*?)</script>", html_text, re.S | re.I):
        try:
            blobs.append(json.loads(m.group(1)))
        except Exception:
            pass
    return blobs


# ==========================================================================
# 2) Reconnaissance dans la page affichée (texte visible)
# ==========================================================================
JS_READ_PAGE = r"""
() => {
  const txt = el => (el.innerText || "").replace(/ /g, " ");
  // Cartes de match : blocs qui contiennent un lien vers une page "rencontre"
  const cards = [];
  const seen = new Set();
  document.querySelectorAll('a[href*="rencontre-"]').forEach(a => {
    let el = a;
    for (let i = 0; i < 6 && el.parentElement; i++) {
      const p = el.parentElement;
      if (p.querySelectorAll('a[href*="rencontre-"]').length > 1) break;
      el = p;
      if (txt(el).split("\n").filter(s => s.trim()).length >= 4) break;
    }
    const href = a.href.split("#")[0];
    if (seen.has(href)) return; seen.add(href);
    cards.push({href, text: txt(el).slice(0, 600), aText: txt(a).slice(0, 300), aTitle: a.getAttribute("title") || ""});
  });
  // Tableaux (classement)
  const tables = [...document.querySelectorAll("table")].map(t => ({
    head: [...t.querySelectorAll("thead th, thead td")].map(c => txt(c).trim()),
    rows: [...t.querySelectorAll("tbody tr")].map(r => [...r.children].map(c => txt(c).trim())),
  })).filter(t => t.rows.length >= 3);
  const links = [...document.querySelectorAll("a[href]")].map(a => a.href);
  return {cards, tables, links, title: document.title, body: txt(document.body).slice(0, 20000)};
}
"""

SKIP_LINE = re.compile(
    r"^(journ[ée]e|j\s?\d|voir|d[ée]tail|feuille|match|termin|[àa] venir|report|forfait|vs\.?|contre|score|live|"
    r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|lun|mar|mer|jeu|ven|sam|dim)\b|"
    r"poule|phase|gymnase|salle|complexe|stade|halle|palais|arbitre|r[ée]sultat|classement|calendrier|"
    r"domicile|ext[ée]rieur|[àa]\s|le\s\d)", re.I)


def _team_lines(lines):
    teams = []
    for l in lines:
        if len(l) < 3 or not re.search(r"[A-Za-zÀ-ÿ]{2}", l):
            continue
        if SKIP_LINE.search(l) or re.search(r"\d{1,2}[h:]\d{2}", l) or re.search(r"\d{1,2}/\d{1,2}", l):
            continue
        if any(norm(w) in MOIS for w in re.findall(r"[A-Za-zÀ-ÿ]+", l)) and re.search(r"\d", l):
            continue
        if l not in teams:
            teams.append(l)
    return teams


def match_from_card(card, url):
    text = card["text"]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Format FFHB :  [JOURNÉE N] / SAMEDI 19 SEPTEMBRE 2026 À 20H30 / DOMICILE / 35 / 28 / EXTÉRIEUR / VOIR DÉTAIL
    SC = re.compile(r"^(\d{1,3}|-|–)$")
    for i in range(1, len(lines) - 2):
        if SC.match(lines[i]) and SC.match(lines[i + 1]):
            dom, ext = lines[i - 1], lines[i + 2]
            if SC.match(dom) or SC.match(ext) or norm(ext).startswith("voir"):
                continue
            d, h = parse_date(" ".join(lines[:i - 1]), url)
            mj = re.search(r"journ[ée]e\s*(\d+)", text, re.I)
            mid = re.search(r"rencontre-(\d+)", card["href"])
            num = lambda x: int(x) if x.isdigit() else None
            return {"id": mid.group(1) if mid else None, "journee": int(mj.group(1)) if mj else None,
                    "date": d.isoformat() if d else None, "heure": h, "href": card["href"],
                    "dom": dom, "ext": ext, "sd": num(lines[i]), "se": num(lines[i + 1])}
    sd = se = None
    for l in lines:
        m = re.fullmatch(r"(\d{1,2})\s*[-–:/]\s*(\d{1,2})", l)
        if m:
            sd, se = int(m[1]), int(m[2]); break
    if sd is None:
        m = re.search(r"(?<![\d/:h])(\d{1,2})\s*[-–]\s*(\d{1,2})(?![\d/:h])", text)
        if m:
            sd, se = int(m[1]), int(m[2])
    if sd is None:
        nums = [int(l) for l in lines if re.fullmatch(r"\d{1,2}", l)]
        if len(nums) >= 2:
            sd, se = nums[0], nums[1]
    teams = _team_lines(lines)
    if len(teams) < 2:
        t = card.get("aTitle") or card.get("aText") or ""
        m = re.split(r"\s+(?:vs\.?|contre|-)\s+", t, flags=re.I)
        if len(m) == 2:
            teams = [m[0].strip(), m[1].strip()]
    if len(teams) < 2:
        return None
    d, h = parse_date(text, url)
    mj = re.search(r"journ[ée]e\s*(\d+)|\bJ\s?(\d+)\b", text, re.I)
    mid = re.search(r"rencontre-(\d+)", card["href"])
    return {"id": mid.group(1) if mid else None, "journee": int(mj.group(1) or mj.group(2)) if mj else None,
            "date": d.isoformat() if d else None, "heure": h,
            "dom": teams[0], "ext": teams[1], "sd": sd, "se": se}


def standings_from_tables(tables):
    best = []
    for t in tables:
        head = [norm(h) for h in t["head"]]
        if not head and t["rows"]:
            continue

        def col(*names):
            for i, h in enumerate(head):
                if any(re.fullmatch(n, h) for n in names):
                    return i
            return None
        ci_pts = col(r"pts?", r"points?")
        ci_eq = col(r"equipes?", r"clubs?", r"nom")
        if ci_pts is None:
            continue
        ci_pos = col(r"#", r"pos\.?", r"position", r"rang", r"rg", r"cl\.?", r"place")
        ci = {k: col(*v) for k, v in {"j": [r"j", r"joues?", r"mj"], "g": [r"g", r"v", r"gagnes?", r"victoires?"],
                                     "n": [r"n", r"nuls?"], "p": [r"p", r"d", r"perdus?", r"defaites?"],
                                     "diff": [r"diff\.?", r"\+/-", r"dif", r"ga"]}.items()}
        rows = []
        for i, r in enumerate(t["rows"], 1):
            get = lambda c: r[c] if c is not None and c < len(r) else None
            eq = get(ci_eq)
            if not eq:
                eq = next((c for c in r if re.search(r"[A-Za-zÀ-ÿ]{3}", c)), None)
            pts = _num(get(ci_pts))
            if not eq or pts is None:
                continue
            rows.append({"pos": _num(get(ci_pos)) or i, "equipe": eq.split("\n")[0].strip(), "pts": pts,
                         **{k: (_int(get(c)) if k == "diff" else _num(get(c))) for k, c in ci.items()}})
        if len(rows) > len(best):
            best = rows
    return best


# ==========================================================================
# Lecture d'une page avec le navigateur
# ==========================================================================
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")[:60] or "page"


JS_SIGNATURE = r"""() => { const a = [...document.querySelectorAll('a[href*="rencontre-"]')];
  return a.length + '|' + (a[0] ? a[0].href : '') + '|' + (a.length ? a[a.length-1].href : '') + '|' +
         a.map(x => (x.innerText || '').replace(/\s+/g, ' ')).join('#').length; }"""


def wait_stable(page, avant=None, maxi=15.0):
    """Attend que la liste des matchs soit chargée ET stable (même contenu 3 relevés de suite).
    Si `avant` est donné, attend d'abord que la liste ait changé par rapport à cette signature."""
    t0, prec, stables = time.time(), None, 0
    while time.time() - t0 < maxi:
        try:
            sig = page.evaluate(JS_SIGNATURE)
        except Exception:
            sig = None
        if sig is not None and sig == prec and (avant is None or sig != avant):
            stables += 1
            if stables >= 2:
                return sig
        else:
            stables = 0
        prec = sig
        page.wait_for_timeout(400)
    return prec


JS_FILTRE_CLUB = r"""(action) => {
  // Menu « Filtrer par club » de la FFHB : un bouton-sélecteur suivi d'une liste de boutons (un par club)
  const sel = [...document.querySelectorAll('button')].find(b => /filtrer par club/i.test(b.innerText || b.textContent || ''));
  if (!sel) return null;
  const menu = sel.nextElementSibling;
  if (!menu) return null;
  const opts = [...menu.querySelectorAll('button')];
  if (action && action.click != null) { const b = opts[action.click]; if (b) { b.click(); return true; } return false; }
  const titre = sel.querySelector('[class*="title"]');
  return {courant: ((titre && titre.textContent) || '').trim(),
          options: opts.map(b => (b.textContent || '').trim())};
}"""


class Reader:
    def __init__(self, visible=False):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        try:
            self.browser = launch_browser(self.pw, visible)
        except Exception:
            self.pw.stop()
            raise

    def new_ctx(self):
        """Contexte vierge pour chaque page : la FFHB mémorise le club filtré d'une page à l'autre,
        un contexte neuf évite qu'un filtre resté actif fausse la lecture suivante."""
        ctx = self.browser.new_context(locale="fr-FR", timezone_id="Europe/Paris",
                                       viewport={"width": 1280, "height": 1600},
                                       user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        def filtre(route):
            req = route.request
            hote = urlparse(req.url).hostname or ""
            if req.resource_type in ("image", "media", "font") or not (hote == "ffhandball.fr" or hote.endswith(".ffhandball.fr") or hote in ("localhost", "127.0.0.1")):
                return route.abort()
            return route.continue_()
        ctx.route("**/*", filtre)
        return ctx

    def close(self):
        try:
            self.browser.close()
        finally:
            self.pw.stop()

    def retrouver_lien(self, page, url):
        """Lien renommé par la FFHB : cherche le même numéro de compétition sur la page parente."""
        segs = [x for x in urlparse(url).path.split("/") if x]
        idx = next((i for i, x in enumerate(segs) if re.search(r"-\d{4,}$", x)
                    and not x.startswith(("saison-", "poule-", "rencontre-"))), None)
        if idx is None or idx == 0:
            return None
        num = re.search(r"-(\d{4,})$", segs[idx]).group(1)
        reste = "/".join(segs[idx + 1:])
        for k in range(idx, 0, -1):   # page de la catégorie, puis de la saison
            parent = "https://www.ffhandball.fr/" + "/".join(segs[:k]) + "/"
            try:
                r = page.goto(parent, wait_until="domcontentloaded", timeout=45000)
                if r is not None and r.status >= 400:
                    continue
                try:
                    page.wait_for_selector(f'a[href*="-{num}/"]', timeout=10000)
                except Exception:
                    pass
                liens = page.evaluate("n => [...document.querySelectorAll('a[href]')].map(a => a.href)"
                                      ".filter(h => new RegExp('-' + n + '/?$').test(h.split('#')[0].split('?')[0]))", num)
            except Exception:
                continue
            if liens:
                base = liens[0].split("#")[0].split("?")[0].rstrip("/") + "/"
                return base + (reste + "/" if reste else "")
        return None

    def read(self, url, debug_name=None, keep_open=False):
        page = self.new_ctx().new_page()
        responses = []
        page.on("response", lambda r: responses.append(r))
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            page.context.close()
            raise RuntimeError(f"page inaccessible ({e.__class__.__name__})")
        if resp is not None and resp.status == 404:
            # la FFHB renomme parfois une compétition (ex. ajout du sponsor « caisse-d-epargne ») :
            # le numéro reste le même, on retrouve le nouveau lien sur la page de la catégorie
            nouveau = self.retrouver_lien(page, url)
            if nouveau:
                URLS_CORRIGEES[url] = nouveau
                url = nouveau
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    page.context.close()
                    raise RuntimeError(f"page inaccessible ({e.__class__.__name__})")
        if resp is not None and resp.status >= 400:
            page.context.close()
            raise RuntimeError(f"page introuvable sur ffhandball.fr (erreur {resp.status}) : vérifie le lien")
        # (le site garde des connexions ouvertes en permanence : attendre « réseau inactif » faisait perdre 15 s par page)
        try:  # bandeau cookies éventuel, cliqué sans attendre
            page.evaluate("""() => { const b = document.querySelector('#didomi-notice-agree-button, #axeptio_btn_acceptAll')
              || [...document.querySelectorAll('button')].find(x => /tout accepter|^accepter/i.test((x.textContent || '').trim()));
              if (b) b.click(); }""")
        except Exception:
            pass
        try:  # attend qu'un match ou un tableau apparaisse
            page.wait_for_selector('a[href*="rencontre-"], table', timeout=15000)
        except Exception:
            pass
        wait_stable(page)
        dom = page.evaluate(JS_READ_PAGE)
        html_text = page.content()
        net = []
        for r in responses:
            try:
                ct = (r.headers or {}).get("content-type", "")
                if "json" in ct and r.status == 200:
                    net.append({"url": r.url, "data": r.json()})
            except Exception:
                pass
        if debug_name:
            d = os.path.join(DEBUG_DIR, debug_name)
            os.makedirs(d, exist_ok=True)
            try:
                page.screenshot(path=os.path.join(d, "capture.png"), full_page=True)
            except Exception:
                pass
            with open(os.path.join(d, "page.html"), "w", encoding="utf-8") as f:
                f.write(html_text)
            with open(os.path.join(d, "reseau.json"), "w", encoding="utf-8") as f:
                json.dump([{"url": n["url"], "data": n["data"]} for n in net], f, ensure_ascii=False, indent=1, default=str)
            with open(os.path.join(d, "page_lue.json"), "w", encoding="utf-8") as f:
                json.dump({"url": url, **dom}, f, ensure_ascii=False, indent=1)
        if keep_open:
            return {"html": html_text, "net": net, "dom": dom, "page": page}
        page.context.close()
        return {"html": html_text, "net": net, "dom": dom}

    def club_season(self, page, url, keys):
        """Sélectionne chaque équipe du club dans « Filtrer par club » : la FFHB affiche alors
        TOUTE la saison de cette équipe. Renvoie (matchs, équipes trouvées)."""
        info = page.evaluate(JS_FILTRE_CLUB, None)
        if not info:
            return [], []
        cibles = [i for i, t in enumerate(info["options"]) if i > 0 and is_club(t, keys)]
        noms, got = [], []
        for i in cibles:
            nom = info["options"][i]
            if norm(info["courant"]) == norm(nom):
                # déjà filtré sur cette équipe (lien « equipe-... ») : la page affichée suffit
                dom = page.evaluate(JS_READ_PAGE)
            else:
                avant = page.evaluate(JS_SIGNATURE)
                page.evaluate(JS_FILTRE_CLUB, {"click": i})
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                wait_stable(page, avant=avant)
                dom = page.evaluate(JS_READ_PAGE)
                info2 = page.evaluate(JS_FILTRE_CLUB, None) or {}
                info = dict(info, courant=info2.get("courant", nom))
            ms, _, _ = analyse({"html": "", "net": [], "dom": dom}, url)
            # contrôle : uniquement les matchs de l'équipe choisie (nom exact), jamais ceux d'une autre équipe du club
            ms = [m for m in ms if norm(m["dom"]) == norm(nom) or norm(m["ext"]) == norm(nom)]
            got += ms
            noms.append(nom)
        return got, noms

    def browse_journees(self, page, url, fri, sun, shown):
        """Pages poule FFHB : clique sur les boutons J1, J2... pour trouver la journée du week-end.
        `shown` = matchs actuellement affichés. Renvoie la liste des matchs lus en plus."""
        btns = page.evaluate(r"""() => [...document.querySelectorAll('button')]
            .map(b => ({t: (b.innerText || '').trim(), sel: /selected|active/i.test(b.className)}))
            .filter(x => /^J\d+$/.test(x.t))""")
        if not btns:
            return [], 0
        nums = [int(b["t"][1:]) for b in btns]
        cur = next((int(b["t"][1:]) for b in btns if b["sel"]), nums[0])
        dated = [date.fromisoformat(m["date"]) for m in shown if m["date"]]
        step = 1 if (dated and max(dated) < fri) else -1  # avant le week-end -> on avance, sinon on recule
        got, clicks, n = [], 0, cur
        while clicks < 8:
            n += step
            if n not in nums:
                break
            prev = page.evaluate(JS_SIGNATURE)
            try:
                page.get_by_role("button", name=f"J{n}", exact=True).first.click(timeout=5000)
            except Exception:
                pass
            wait_stable(page, avant=prev, maxi=12)
            clicks += 1
            dom = page.evaluate(JS_READ_PAGE)
            ms, _, _ = analyse({"html": "", "net": [], "dom": dom}, url)
            for m in ms:
                m["journee"] = m["journee"] or n
            got += ms
            d2 = [date.fromisoformat(m["date"]) for m in ms if m["date"]]
            if any(fri <= d <= sun for d in d2):
                break
            if d2 and ((step == -1 and max(d2) < fri) or (step == 1 and min(d2) > sun)):
                break  # on a dépassé le week-end : il n'y a pas eu de match
        return got, clicks


def analyse(raw, url):
    """Extrait matchs + classement d'une page lue. Renvoie (matchs, classement, source)."""
    json_sources = [n["data"] for n in raw["net"]] + json_blobs_in_html(raw["html"])
    m_json, c_json = [], []
    for data in json_sources:
        m_json += matches_from_json(data, url)
        s = standings_from_json(data)
        if len(s) > len(c_json):
            c_json = s
    m_dom = [m for m in (match_from_card(c, url) for c in raw["dom"]["cards"]) if m]
    c_dom = standings_from_tables(raw["dom"]["tables"])

    good_json = [m for m in m_json if m["date"] or m["sd"] is not None]
    if m_dom:
        matchs, source = m_dom, "texte affiché"
    elif good_json:
        matchs, source = m_json, "données de la page"
    else:
        matchs, source = [], "rien reconnu"
    classement = c_json if len(c_json) >= len(c_dom) else c_dom
    return dedupe(matchs), classement, source


def dedupe(ms):
    seen, out = set(), []
    for m in ms:
        k1 = ("id", m["id"]) if m.get("id") else None
        k2 = (norm(m["dom"]), norm(m["ext"]), m["date"] or m["journee"])
        if (k1 and k1 in seen) or k2 in seen:
            continue
        if k1:
            seen.add(k1)
        seen.add(k2)
        out.append(m)
    return out


def in_window(m, fri, sun):
    if not m["date"]:
        return False
    d = date.fromisoformat(m["date"])
    return fri <= d <= sun


# ==========================================================================
# Coupes de France : pas de poule unique mais un tour par « phase » (1er tour, 2e tour...),
# chaque tour ayant sa propre page (poule-XXXX). On relit tous les tours à chaque fois.
# ==========================================================================
JS_MENU_FFHB = r"""(a) => {
  // menus FFHB « Sélectionner une phase » / « Sélectionner une poule » : bouton-sélecteur + liste de boutons
  const rx = new RegExp(a.label, 'i');
  const sel = [...document.querySelectorAll('button')].find(b => rx.test(b.textContent || ''));
  if (!sel) return null;
  const menu = sel.nextElementSibling;
  const opts = menu ? [...menu.querySelectorAll('button')] : [];
  if (a.click != null) { const b = opts[a.click]; if (b) { sel.click(); b.click(); return true; } return false; }
  const t = sel.querySelector('[class*="title"]');
  return {courant: ((t && t.textContent) || '').trim(), options: opts.map(b => (b.textContent || '').trim())};
}"""


def est_coupe(url):
    return "/coupe-de-france/" in (url or "").lower()


def libelle_tour(txt):
    """« CDF FED MAS (2EME TOUR) » -> « 2e tour » ; « 1/8 DE FINALE » -> « 1/8 de finale »."""
    t = (txt or "").strip()
    m = re.search(r"\(([^)]*)\)\s*$", t)
    if m:
        t = m.group(1)
    n = re.search(r"(\d+)\s*(?:ER|ERE|EME|E|°)\s*TOUR", t.upper())
    if n:
        k = int(n.group(1))
        return f"{k}{'er' if k == 1 else 'e'} tour"
    return t.lower().capitalize() if t else ""


def read_coupe(reader, comp, fri, sun, keys=()):
    url = comp["url"].strip()
    m0 = re.match(r"(.*?/coupe-de-france/[^/]+/)", url)
    racine = m0.group(1) if m0 else url
    name = comp.get("nom") or url
    raw = reader.read(racine, slug(name), keep_open=True)
    page = raw.pop("page")
    titre = re.sub(r"\s*[-|]\s*(Calendrier.*|F[ée]d[ée]ration Fran[çc]aise de Handball.*)$", "", raw["dom"]["title"]).strip()
    info = page.evaluate(JS_MENU_FFHB, {"label": "lectionner une phase"})
    phases = (info or {}).get("options") or [None]
    tous, club, tours, pages = [], [], [], 1
    for i, ph in enumerate(phases):
        try:
            cour = page.evaluate(JS_MENU_FFHB, {"label": "lectionner une phase"}) or {}
            if ph is not None and norm(cour.get("courant", "")) != norm(ph):
                avant = page.evaluate(JS_SIGNATURE)
                page.evaluate(JS_MENU_FFHB, {"label": "lectionner une phase", "click": i})
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                wait_stable(page, avant=avant)
                pages += 1
            # un tour peut être découpé en plusieurs poules (zones) : on les lit toutes
            pinfo = page.evaluate(JS_MENU_FFHB, {"label": "lectionner une poule"}) or {}
            poules = pinfo.get("options") or [None]
            for j, po in enumerate(poules):
                if po is not None and len(poules) > 1 and norm(pinfo.get("courant", "")) != norm(po):
                    avant = page.evaluate(JS_SIGNATURE)
                    page.evaluate(JS_MENU_FFHB, {"label": "lectionner une poule", "click": j})
                    wait_stable(page, avant=avant)
                    pages += 1
                    pinfo = page.evaluate(JS_MENU_FFHB, {"label": "lectionner une poule"}) or pinfo
                dom = page.evaluate(JS_READ_PAGE)
                ms, _, _ = analyse({"html": "", "net": [], "dom": dom}, page.url)
                tour = libelle_tour(ph or pinfo.get("courant") or "")
                for m in ms:
                    m["tour"] = tour
                    m["journee"] = None
                tous += ms
                mc = [m for m in ms if is_club(m["dom"], keys) or is_club(m["ext"], keys)] if keys else ms
                club += mc
                tours.append({"tour": tour, "url": page.url, "matchs": len(ms), "club": len(mc)})
        except Exception as e:
            tours.append({"tour": libelle_tour(ph or ""), "erreur": str(e)})
    try:
        page.context.close()
    except Exception:
        pass
    club = dedupe(club)
    club.sort(key=lambda m: (m["date"] or "9999", m["heure"] or ""))
    # la FFHB peut changer le nom du club d'un tour à l'autre : on garde partout le plus récent
    noms = [n for m in club for n in (m["dom"], m["ext"]) if is_club(n, keys)]
    if noms:
        for m in club:
            for k in ("dom", "ext"):
                if is_club(m[k], keys):
                    m[k] = noms[-1]
    equipes = sorted({n for m in club for n in (m["dom"], m["ext"]) if is_club(n, keys)})
    # on ne garde que les matchs du club (un tour régional compte parfois plusieurs centaines de matchs)
    return {"nom": name, "url": url, "titre": titre, "source": "coupe (tours)", "pages_lues": pages,
            "matchs": club, "classement": [], "equipes_club": equipes or ["(aucun match du club)"],
            "saison_club": len(club) or 1, "coupe": True, "tours": tours, "matchs_lus": len(tous)}


def read_competition(reader, comp, fri, sun, keys=()):
    if est_coupe(comp.get("url")):
        return read_coupe(reader, comp, fri, sun, keys)
    url = comp["url"].strip()
    name = comp.get("nom") or url
    base_dbg = slug(name)
    raw = reader.read(url, base_dbg, keep_open=True)
    page = raw.pop("page")
    matchs, classement, source = analyse(raw, url)
    titre = re.sub(r"\s*[-|]\s*(Calendrier.*|F[ée]d[ée]ration Fran[çc]aise de Handball.*)$", "", raw["dom"]["title"]).strip()
    pages_lues = 1

    # 1. Saison complète de chaque équipe du club (menu « Filtrer par club ») : couvre tous les week-ends
    saison, equipes = [], []
    if keys:
        try:
            saison, equipes = reader.club_season(page, url, list(keys))
            matchs = dedupe(saison + matchs)
            pages_lues += len(equipes)
        except Exception:
            pass
    # 2. Secours : pas de filtre club -> navigation J1, J2... jusqu'au week-end demandé
    if not equipes and not any(in_window(m, fri, sun) for m in matchs):
        try:
            extra, clicks = reader.browse_journees(page, url, fri, sun, matchs)
            matchs = dedupe(matchs + extra)
            pages_lues += clicks
        except Exception:
            pass
    try:
        page.context.close()
    except Exception:
        pass

    # Ancien format (liens .../journee-N/) si toujours rien
    if not equipes and not any(in_window(m, fri, sun) for m in matchs):
        base = re.sub(r"/journee-\d+/?$", "", url.split("?")[0].rstrip("/"))
        nums = sorted({int(n) for l in raw["dom"]["links"] for n in re.findall(r"/journee-(\d+)", l)
                       if l.split("?")[0].startswith(base)}, reverse=True)
        for n in nums[:30]:
            try:
                r2 = reader.read(f"{base}/journee-{n}/", f"{base_dbg}-j{n}" if pages_lues < 4 else None)
            except Exception:
                continue
            pages_lues += 1
            m2, c2, _ = analyse(r2, url)
            for m in m2:
                if m["journee"] is None:
                    m["journee"] = n
            matchs = dedupe(matchs + m2)
            if len(c2) > len(classement):
                classement = c2
            dated = [date.fromisoformat(m["date"]) for m in m2 if m["date"]]
            if any(fri <= d <= sun for d in dated):
                break
            if dated and max(dated) < fri:
                break  # on est remonté trop loin

    matchs.sort(key=lambda m: (m["date"] or "9999", m["heure"] or ""))
    return {"nom": name, "url": url, "titre": titre, "source": source, "pages_lues": pages_lues,
            "matchs": matchs, "classement": classement, "equipes_club": equipes, "saison_club": len(saison)}


_lock = threading.Lock()
_cache = {}


NB_LECTEURS = int(os.environ.get("FFHB_LECTEURS") or (3 if os.environ.get("FFHB_CLOUD") == "1" else 6))  # pages FFHB lues en même temps

GROUPES = ["SENIORS", "JEUNES MASCULINS", "JEUNES FÉMININES"]


def infos_categorie(comp):
    """Déduit du nom et du lien : groupe (seniors / jeunes M / jeunes F), âge, niveau, numéro d'équipe.
    Ordre : seniors, puis jeunes masculins, puis jeunes féminines ; des plus âgés aux plus jeunes ;
    à âge égal, le niveau le plus haut d'abord (national > excellence > division 1 > division 2...)."""
    nom, url = comp.get("nom", ""), comp.get("url", "").lower()
    n = norm(nom)
    m = re.search(r"(?:^|[\s(])[-u]\s?(\d{2})(?!\d)", n) or re.search(r"/(?:u|m)(\d{2})-", url) \
        or re.search(r"-(\d{2})-\d{4,}/", url)
    age = int(m.group(1)) if m and 9 <= int(m.group(1)) <= 20 else None
    fem = bool(re.search(r"\bf\b|\bsf\b|\d+f\b|fem|fille", n)) or "feminin" in url
    if age is None:
        groupe = 0
    else:
        groupe = 2 if fem else 1
    niveaux = [(r"nationale-(\d)", None), (r"/national/", 0), (r"pre-?nationale|prenat", 4), (r"excellence", 5),
               (r"honneur", 6), (r"division-1|1ere-division", 7), (r"division-2|2eme-division", 8),
               (r"division-3|3eme-division", 9), (r"departemental", 10)]
    niveau = 11
    for rx, val in niveaux:
        mm = re.search(rx, url)
        if mm:
            niveau = int(mm.group(1)) if val is None else val
            break
    mn = re.search(r"\(?(\d)\)?\s*$", nom.strip())
    num = int(mn.group(1)) if mn and age is not None or (mn and nom.strip().upper().startswith("SF")) else 1
    if age is not None and mn:
        num = int(mn.group(1))
    if est_cdf_n1(comp):   # Coupe de France de la N1 : toujours en premier sur les visuels
        niveau, fem, num = -1, False, 0
    return {"groupe": groupe, "groupe_nom": GROUPES[groupe], "age": age,
            "ordre": (groupe, -(age or 99), niveau, 1 if fem else 0, num)}


def comp_keys(cfg, comp):
    """Mots-clés du club pour une équipe : ceux de l'équipe (ententes) sinon ceux du club."""
    if comp.get("club", "").strip():
        return club_keys(comp)
    return club_keys(cfg)


def _worker(jobs, results, fri, sun, visible):
    reader = None
    try:
        reader = Reader(visible)
    except Exception as e:
        err = str(e)
    while True:
        try:
            i, c = jobs.pop(0)
        except IndexError:
            break
        t0 = time.time()
        r, essais = None, 0
        while essais < 3:  # jusqu'à 3 lectures si la page est incomplète
            essais += 1
            try:
                if reader is None:
                    raise RuntimeError(err)
                r2 = read_competition(reader, c, fri, sun, c.get("_keys", ()))
            except Exception as e:
                r2 = {"nom": c.get("nom") or c["url"], "url": c["url"], "erreur": str(e), "matchs": [], "classement": []}
            if r is None or (r.get("erreur") and not r2.get("erreur")) or \
                    (not r2.get("erreur") and (r2.get("saison_club") or 0, len(r2["matchs"]))
                     > (r.get("saison_club") or 0, len(r["matchs"]))):
                r = r2  # on garde la lecture la plus complète
            if not r.get("erreur") and r["matchs"] and ((r.get("equipes_club") and r.get("saison_club")) or essais >= 2):
                break
            if "introuvable" in (r.get("erreur") or ""):
                break  # lien faux : inutile de réessayer
        r["essais"] = essais
        r["duree"] = round(time.time() - t0, 1)
        results[i] = r
    if reader:
        reader.close()


CACHE_FILE = os.path.join(HERE, "ffhb_cache.json")
URLS_CORRIGEES = {}     # ancien lien FFHB -> nouveau (compétition renommée), enregistré dans la config
SAISON_TTL = 30 * 60      # une équipe est relue sur la FFHB au bout de 30 minutes (ou avec « Actualiser »)
_saisons = None           # clé équipe -> {"t": horodatage, "r": lecture}


def _cle(c):
    return c["url"].strip() + "|" + ",".join(c.get("_keys") or [])


def _charger_saisons():
    global _saisons
    if _saisons is None:
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _saisons = json.load(f)
        except Exception:
            _saisons = {}
    return _saisons


def _sauver_saisons():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_saisons, f, ensure_ascii=False)
    except Exception:
        pass


def lire_saisons(cfg, fri, sun, force=False, visible=False):
    """Lit sur la FFHB uniquement les équipes absentes du cache ou trop anciennes.
    Une lecture contient la saison complète du club : elle sert pour tous les week-ends."""
    comps_cfg = [dict(c, _keys=comp_keys(cfg, c)) for c in cfg["competitions"] if c.get("url", "").strip()]
    with _lock:
        cache = _charger_saisons()
        maintenant = time.time()
        def perime(c):
            e = cache.get(_cle(c))
            if force or not e or maintenant - e["t"] > SAISON_TTL:
                return True
            r = e["r"]
            # lecture sans saison complète (secours par journée) : valable seulement pour le week-end lu
            return r.get("erreur") or (not r.get("equipes_club") and e.get("du") != fri.isoformat())
        a_lire = [(i, c) for i, c in enumerate(comps_cfg) if perime(c)]
        if a_lire:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            jobs = list(a_lire)  # list.pop est sûr entre threads
            results = [None] * len(comps_cfg)
            n = 1 if visible else max(1, min(NB_LECTEURS, len(jobs)))
            threads = [threading.Thread(target=_worker, args=(jobs, results, fri, sun, visible)) for _ in range(n)]
            for t in threads:
                t.start()
            # chaque équipe lue est mise en cache tout de suite : la page l'affiche sans attendre les autres
            ranges = set()
            _progression.update(total=len(a_lire), lus=0, debut=time.time())
            while True:
                vivant = any(t.is_alive() for t in threads)
                nouveaux = [(i, c) for i, c in a_lire if i not in ranges and results[i] is not None]
                for i, c in nouveaux:
                    cache[_cle(c)] = {"t": time.time(), "du": fri.isoformat(), "r": results[i]}
                    ranges.add(i)
                if nouveaux:
                    _progression["lus"] = len(ranges)
                    _sauver_saisons()
                if not vivant:
                    break
                time.sleep(0.5)
            for i, c in a_lire:
                if i not in ranges:
                    cache[_cle(c)] = {"t": time.time(), "du": fri.isoformat(), "r": results[i]}
            _progression.update(total=0, lus=0)
            _sauver_saisons()
            if URLS_CORRIGEES:
                corriger_liens_config()
        return comps_cfg, [corriger_horaires(json.loads(json.dumps(cache[_cle(c)]["r"]))) for c in comps_cfg], \
            min(cache[_cle(c)]["t"] for c in comps_cfg) if comps_cfg else time.time()


def _cle_horaire(m):
    return f"{m.get('date')}|{norm(m.get('dom', ''))}|{norm(m.get('ext', ''))}"


def corriger_horaires(r):
    """Horaires corrigés à la main (quand la FFHB n'est pas à jour) : config « horaires_corriges »."""
    corr = load_config().get("horaires_corriges") or {}
    if corr and r:
        for m in r.get("matchs") or []:
            h = corr.get(_cle_horaire(m))
            if h:
                m["heure"] = h
                m["heure_corrigee"] = True
    return r


def corriger_horaire(jour, dom, ext, heure):
    """Enregistre (ou retire si heure vide) l'horaire réel d'un match."""
    heure = (heure or "").strip().upper().replace("H", ":")
    if heure and not re.fullmatch(r"\d{1,2}:\d{2}", heure):
        raise RuntimeError("Horaire invalide : écris par exemple 20h30.")
    if heure:
        heure = heure.zfill(5)
    cfg = load_config()
    corr = cfg.setdefault("horaires_corriges", {})
    cle = _cle_horaire({"date": jour, "dom": dom, "ext": ext})
    if heure:
        corr[cle] = heure
    else:
        corr.pop(cle, None)
    save_config(cfg)
    return {"heure": heure}


def corriger_liens_config():
    """Enregistre dans la config les nouveaux liens des compétitions renommées par la FFHB."""
    try:
        cfg = load_config()
        change = False
        for c in cfg.get("competitions", []):
            u = c.get("url", "").strip()
            for ancien, nouveau in list(URLS_CORRIGEES.items()):
                if u and u.startswith(ancien.rstrip("/")):
                    c["url"] = nouveau.rstrip("/") + u[len(ancien.rstrip("/")):]
                    change = True
        if change:
            save_config(cfg)
    except Exception:
        pass


_maj = {"thread": None, "fin": 0.0}
_progression = {"total": 0, "lus": 0, "debut": 0.0}    # lecture FFHB en cours (pour la page)
_salles_maj = {"thread": None}


def maj_en_cours():
    t = _maj["thread"]
    return bool(t and t.is_alive())


# ---------- Salles des matchs à domicile (lues sur la page du match) ----------
SALLES_FILE = os.path.join(HERE, "ffhb_salles.json")
SALLES_TTL = 3 * 24 * 3600
# nom court affiché sur les visuels : mot-clé trouvé dans le nom FFHB de la salle
SALLES_COURTES = {"CUZIN": "Cuzin", "COSEC": "Cosec", "LACHAISE": "Lachaise", "LASSAGNE": "Lassagne", "SENARD": "Sénard"}
_salles, _salle_lock = None, threading.Lock()


def _charger_salles():
    global _salles
    if _salles is None:
        try:
            with open(SALLES_FILE, encoding="utf-8") as f:
                _salles = json.load(f)
        except Exception:
            _salles = {}
    return _salles


def salle_courte(nom, ville=""):
    n = norm(nom).upper()
    for cle, court in SALLES_COURTES.items():
        if cle in n:
            return court
    mots = [m for m in re.split(r"[\s\-]+", n) if m and m not in
            {"GYMNASE", "SALLE", "HALLE", "COMPLEXE", "SPORTIF", "SPORTIVE", "PALAIS", "DES", "DU", "DE", "LA", "LE", "LES", "SPORTS", "OMNISPORTS", "MUNICIPAL", "MUNICIPALE"}]
    if not mots:  # nom générique (« Halle des sports ») : on affiche la ville
        v = re.sub(r"^\d{5}\s*", "", ville or "").strip()
        return v.title() if v else nom.title()
    return " ".join(mots[-2:]).title()


def lire_salles(hrefs):
    """Lit la salle de chaque match (page « rencontre » FFHB), avec cache de 3 jours."""
    with _salle_lock:
        cache = _charger_salles()
        a_lire = [h for h in dict.fromkeys(hrefs) if h and (h not in cache or time.time() - cache[h]["t"] > SALLES_TTL)]
        if a_lire:
            def travail(liste):
                try:
                    r = Reader()
                except Exception:
                    return
                for h in liste:
                    try:
                        page = r.new_ctx().new_page()
                        page.goto(h, wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_function(r"() => /\nSALLE\n/.test(document.body.innerText)", timeout=12000)
                        except Exception:
                            pass
                        t = page.evaluate("document.body.innerText")
                        m = re.search(r"\nSALLE\n([^\n]+)\n([^\n]*)\n([^\n]*)", t)
                        if m:
                            cache[h] = {"t": time.time(), "nom": m.group(1).strip(), "ville": m.group(3).strip()}
                        page.context.close()
                    except Exception:
                        pass
                r.close()
            paquets = [a_lire[i::4] for i in range(min(4, len(a_lire)))]
            th = [threading.Thread(target=travail, args=(pq,)) for pq in paquets]
            for t in th:
                t.start()
            for t in th:
                t.join()
            try:
                with open(SALLES_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
            except Exception:
                pass
        return {h: cache[h] for h in hrefs if h in cache}


def salles_en_cours():
    t = _salles_maj.get("thread")
    return bool(t and t.is_alive())


def ajoute_salles(comps, attendre=True):
    """Ajoute le nom court de la salle aux matchs du club à domicile du week-end.
    attendre=False : seulement les salles déjà connues, les autres sont lues en arrière-plan."""
    home = [(m, c) for c in comps for m in c.get("weekend_club") or []
            if m.get("href") and is_club(m["dom"], c.get("club_keys") or [])]
    if not home:
        return
    if attendre:
        infos = lire_salles([m["href"] for m, _ in home])
    else:
        infos = dict(_charger_salles())
        manque = [m["href"] for m, _ in home if m["href"] not in infos]
        if manque and not salles_en_cours():
            _salles_maj["thread"] = threading.Thread(target=lambda: lire_salles(manque), daemon=True)
            _salles_maj["thread"].start()
    for m, _ in home:
        i = infos.get(m["href"])
        if i:
            m["salle"] = salle_courte(i["nom"], i.get("ville", ""))
            m["salle_complete"] = i["nom"]


def lancer_maj(cfg, force=False):
    """Relit la FFHB en arrière-plan (sans bloquer la page)."""
    if maj_en_cours():
        return
    def tache():
        try:
            fri, sun = weekend(0)
            lire_saisons(cfg, fri, sun, force)
            for off in (0, -1, -2):
                ajoute_salles(run_all(cfg, off, pour_salles=True)["competitions"])
        except Exception:
            pass
        _maj["fin"] = time.time()
    _maj["thread"] = threading.Thread(target=tache, daemon=True)
    _maj["thread"].start()


def cache_complet(cfg):
    """Vrai si toutes les équipes ont déjà une lecture en cache (même ancienne)."""
    cache = _charger_saisons()
    comps = [dict(c, _keys=comp_keys(cfg, c)) for c in cfg["competitions"] if c.get("url", "").strip()]
    return all(_cle(c) in cache and cache[_cle(c)]["r"].get("equipes_club") for c in comps)


def match_termine(m):
    """Vrai si le match devrait être fini (jour passé, ou aujourd'hui plus de 2 h après le coup d'envoi)."""
    j = date.fromisoformat(m["date"])
    if j != date.today():
        return j < date.today()
    h = re.match(r"(\d{1,2})[:hH](\d{2})", m.get("heure") or "")
    if not h:
        return datetime.now().hour >= 23
    return datetime.now() >= datetime.combine(j, datetime.min.time()).replace(hour=int(h.group(1)), minute=int(h.group(2))) + timedelta(hours=2)


def run_all(cfg, offset=0, visible=False, force=False, arriere_plan=False, pour_salles=False, progressif=False):
    """progressif : réponse immédiate pour la page (cache), les équipes manquantes ou anciennes et les
    salles sont lues en arrière-plan ; la page se met à jour au fur et à mesure."""
    fri, sun = weekend(offset)
    maj = False
    if pour_salles:
        cache = _charger_saisons()
        comps_cfg = [dict(c, _keys=comp_keys(cfg, c)) for c in cfg["competitions"] if c.get("url", "").strip()]
        comps_cfg = [c for c in comps_cfg if _cle(c) in cache]
        results = [json.loads(json.dumps(cache[_cle(c)]["r"])) for c in comps_cfg]
        t_lecture = time.time()
    elif progressif or (arriere_plan and not force and cache_complet(cfg)):
        # réponse immédiate avec le cache ; équipes manquantes ou de plus de 30 min : lecture en arrière-plan
        cache = _charger_saisons()
        comps_cfg = [dict(c, _keys=comp_keys(cfg, c)) for c in cfg["competitions"] if c.get("url", "").strip()]
        entrees = [cache.get(_cle(c)) for c in comps_cfg]
        if force or maj_en_cours() or any(e is None or time.time() - e["t"] > SAISON_TTL for e in entrees):
            lancer_maj(cfg, force=force)  # ne fait rien si une mise à jour tourne déjà
            maj = True
        results = [json.loads(json.dumps(e["r"])) if e else
                   {"nom": c.get("nom") or c["url"], "url": c["url"], "en_lecture": True, "matchs": [], "classement": []}
                   for c, e in zip(comps_cfg, entrees)]
        t_lecture = min([e["t"] for e in entrees if e] or [time.time()])
    else:
        comps_cfg, results, t_lecture = lire_saisons(cfg, fri, sun, force, visible)
    comps = []
    for c, r in zip(comps_cfg, results):
        corriger_horaires(r)
        keys = comp_keys(cfg, c)
        r["club_keys"] = keys
        we = [m for m in r["matchs"] if in_window(m, fri, sun)]
        r["weekend"] = we
        r["weekend_club"] = [m for m in we if is_club(m["dom"], keys) or is_club(m["ext"], keys)]
        for row in r["classement"]:
            row["club"] = is_club(row["equipe"], keys)
        for m in r["matchs"]:
            m["club"] = is_club(m["dom"], keys) or is_club(m["ext"], keys)
        r["club_absent"] = bool(r["matchs"] or r["classement"]) and not (
            any(m["club"] for m in r["matchs"]) or any(x["club"] for x in r["classement"]))
        if r.get("coupe"):
            r["club_absent"] = False
        # Contrôle : statut de chaque équipe pour ce week-end
        wc = r["weekend_club"]
        if r.get("en_lecture"):
            r["statut"] = "lecture"
        elif r.get("erreur"):
            r["statut"] = "echec"
        elif r["club_absent"] or (not r["matchs"] and not r.get("coupe")):
            r["statut"] = "verifier"
        elif any(m["sd"] is None and m["date"] and match_termine(m) for m in wc):
            r["statut"] = "attente"   # match joué mais score pas encore saisi sur la FFHB
        elif wc and all(m["sd"] is None for m in wc):
            r["statut"] = "a_venir"   # match du week-end pas encore joué
        elif wc:
            r["statut"] = "ok"
        else:
            r["statut"] = "aucun"
        r["saison_complete"] = bool(r.get("equipes_club"))
        comps.append(r)
    for c, r in zip(comps_cfg, comps):
        r.update(infos_categorie(c))
        r["logo_comp"] = logo_competition(c)
    comps.sort(key=lambda r: r["ordre"])
    if not pour_salles:
        try:
            ajoute_salles(comps, attendre=not progressif)
        except Exception:
            pass
    compte = {k: sum(1 for c in comps if c["statut"] == k) for k in ("ok", "a_venir", "attente", "aucun", "verifier", "echec", "lecture")}
    res = {"controle": compte, "du": fri.isoformat(), "au": sun.isoformat(), "offset": offset, "maj_en_cours": maj or maj_en_cours(),
           "salles_en_cours": salles_en_cours(), "progression": dict(_progression),
           "genere": datetime.fromtimestamp(t_lecture).strftime("%d/%m/%Y %H:%M"), "club": cfg.get("club", ""),
           "competitions": comps}
    with open(os.path.join(DEBUG_DIR, "resultat.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return res


# ==========================================================================
# Sorties texte / CSV
# ==========================================================================
def issue(m, keys):
    if m["sd"] is None or m["se"] is None:
        return ""
    home = is_club(m["dom"], keys)
    if not home and not is_club(m["ext"], keys):
        return ""
    a, b = (m["sd"], m["se"]) if home else (m["se"], m["sd"])
    return "V" if a > b else "D" if a < b else "N"


def texte_programme(res, keys):
    ms = matchs_pour_visuel(res, "programme")
    if not ms:
        return "Aucun match du club à venir ce week-end."
    L = [f"📅 Programme du week-end ({titre_dates(res['du'], res['au'], ms).lower()})"]
    groupe = None
    for m in ms:
        if m["groupe_nom"] != groupe:
            groupe = m["groupe_nom"]
            L += ["", f"▶ {groupe}"]
        jour = m["jour"].split(" ")[0][:3].capitalize() if m["jour"] else ""
        lieu = m["lieu"].lower() + (f" – {m['salle']}" if m.get("salle") else "")
        L.append(f"{m['categorie']} · {jour} {m['heure'] or '??'} · {m['dom']} vs {m['ext']} ({lieu})")
    return "\n".join(L)


def texte_reseaux(res, keys):
    if res.get("offset", 0) < 0:
        return texte_programme(res, keys)
    fri, sun = date.fromisoformat(res["du"]), date.fromisoformat(res["au"])
    L = [f"🤾 Résultats du week-end ({fri:%d/%m} → {sun:%d/%m})", ""]
    groupe = None
    for c in res["competitions"]:
        ms = c.get("weekend_club") or []
        if not ms:
            continue
        if c.get("groupe_nom") and c["groupe_nom"] != groupe:
            groupe = c["groupe_nom"]
            L += [f"━━ {groupe} ━━", ""]
        L.append(f"▶ {c['nom']}" + (f" ({ms[0]['tour']})" if ms[0].get("tour") else ""))
        for m in ms:
            i = issue(m, c.get("club_keys") or keys)
            ico = {"V": "✅", "D": "❌", "N": "🤝"}.get(i, "🕒" if m["sd"] is None else "•")
            sc = f"{m['sd']} - {m['se']}" if m["sd"] is not None else "(score à venir)"
            L.append(f"{ico} {m['dom']} {sc} {m['ext']}")
        me = next((r for r in c["classement"] if r.get("club")), None)
        if me:
            L.append(f"📊 {me['pos']}{'re' if me['pos'] == 1 else 'e'} — {me['pts']} pts")
        L.append("")
    return "\n".join(L).strip() if len(L) > 2 else "Aucun match du club ce week-end."


def to_csv(res):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Compétition", "Journée", "Date", "Heure", "Domicile", "Score dom", "Score ext", "Extérieur"])
    for c in res["competitions"]:
        for m in c.get("weekend", []):
            w.writerow([c["nom"], m["journee"] or m.get("tour") or "", m["date"] or "", m["heure"] or "", m["dom"],
                        "" if m["sd"] is None else m["sd"], "" if m["se"] is None else m["se"], m["ext"]])
    return "﻿" + buf.getvalue()


# ==========================================================================
# Visuels « Résultats du week-end » (images PNG pour les réseaux)
# ==========================================================================
VISUELS_DIR = os.path.join(HERE, "visuels")
MATCHS_PAR_VISUEL = 6  # au-delà de 5, mise en page compacte
MOIS_FR = ["", "JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOÛT",
           "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DÉCEMBRE"]
JOURS_FR = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]

# Mots retirés des noms d'équipes pour les raccourcir sur le visuel
MOTS_INUTILES = {"HANDBALL", "HAND", "BALL", "HBC", "HB", "HBF", "HC", "CLUB", "ASSOCIATION", "SPORTIVE",
                 "SPORTS", "SPORT", "AL", "AS", "ASL", "US", "ES", "SC", "CS", "UNION", "ENTENTE", "PAYS", "DU",
                 "DE", "DES", "LA", "LE", "LES", "ET", "EN", "SUR", "AUX", "SF", "SF1", "SF2", "P16F", "N3", "-"}


def nom_court(nom, keys):
    """« ST CHAMOND HANDBALL PAYS DU GIER 2 » -> « ST CHAMOND 2 » ; le club -> « CALUIRE-RILLIEUX »."""
    brut = re.sub(r"\s+", " ", (nom or "").upper()).strip()
    # préfixes de catégorie ajoutés par la FFHB : « M17M EXC - », « P16M HON - », « M15F DIV - »...
    brut = re.sub(r"^[A-Z]?\d{2}[A-Z]{0,2}\s+[A-Z]{2,4}\.?\s+-\s+", "", brut)
    num = re.search(r"\s(\d)$", brut)
    suffixe = f" {num.group(1)}" if num else ""
    if is_club(brut, keys) and any(k in ("caluire", "rillieux") for k in keys):
        return "CALUIRE-RILLIEUX" + suffixe
    mots = [m for m in re.split(r"\s+", re.sub(r"\s\d$", "", brut)) if m]
    ent = is_club(brut, keys) and mots and mots[0] in ("ENTENTE", "ENT.", "ENT")
    # on retire aussi les catégories collées au nom : « -15F », « U13G », « M11M », « DIVISION »...
    cat = re.compile(r"^(-?\d{2}[MFG]?|U\d{2}[MFG]?|M\d{2}[MFG]?|DIVISION|EXCELLENCE|HONNEUR)$")
    garde = [m for m in mots if (m not in MOTS_INUTILES and not cat.match(m)) or (ent and m in ("ENTENTE", "ENT."))]
    garde = garde[:3] if garde else mots[:3]
    # adversaire au nom long : 2 mots suffisent (« VALENCE DRÔME GUILHERAND-GRANGES » -> « VALENCE DRÔME »)
    if not is_club(brut, keys) and len(" ".join(garde)) > 18 and len(garde) > 2:
        garde = garde[:2]
    return (" ".join(garde) + suffixe).strip()


def matchs_pour_visuel(res, mode="resultats"):
    """mode « resultats » : matchs avec score ; mode « programme » : matchs pas encore joués."""
    out = []
    for c in res["competitions"]:
        keys = c.get("club_keys") or []
        for m in c.get("weekend_club") or []:
            joue = m["sd"] is not None and m["se"] is not None
            if joue != (mode == "resultats"):
                continue
            dom = is_club(m["dom"], keys)
            d = date.fromisoformat(m["date"]) if m["date"] else None
            out.append({
                "categorie": re.sub(r"\s*\(.*?\)", "", c["nom"]).strip() + (f" {m['tour']}" if m.get("tour") else ""),
                "lieu": "DOMICILE" if dom else "EXTÉRIEUR",
                "salle": m.get("salle", "") if dom else "",
                "jour": f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month]}" if d else "",
                "dom": nom_court(m["dom"], keys), "ext": nom_court(m["ext"], keys),
                "sd": m["sd"], "se": m["se"], "res": issue(m, keys),
                "heure": (m["heure"] or "").replace(":", "H"),
                "groupe": c.get("groupe", 0), "groupe_nom": c.get("groupe_nom", ""),
                "logo": c.get("logo_comp"),
                "ordre": c.get("ordre", ()),
                "date": m["date"],
                "tri": (m["date"] or "", m["heure"] or ""),
            })
    out.sort(key=lambda x: (list(x["ordre"]), x["tri"]))
    return out


def decoupe(items, maxi=MATCHS_PAR_VISUEL):
    """Répartit équitablement : 7 matchs -> 4 + 3 plutôt que 5 + 2."""
    if not items:
        return []
    n = -(-len(items) // maxi)
    taille = -(-len(items) // n)
    return [items[i:i + taille] for i in range(0, len(items), taille)]


def titre_dates(du, au, matchs=()):
    """Dates du titre : celles des matchs réellement joués (ex. « 3-4 OCTOBRE »), sinon ven.-dim."""
    ds = sorted(m["date"] for m in matchs if m.get("date"))
    if ds:
        du, au = ds[0], ds[-1]
    a, b = date.fromisoformat(du), date.fromisoformat(au)
    if a == b:
        return f"{JOURS_FR[a.weekday()]} {a.day} {MOIS_FR[a.month]}"
    if a.month == b.month:
        return f"{a.day}-{b.day} {MOIS_FR[b.month]}"
    return f"{a.day} {MOIS_FR[a.month]} - {b.day} {MOIS_FR[b.month]}"


VISUEL_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<style>
__FONTS__
/* ===== Charte Caluire-Rillieux Handball ===== */
:root{--navy:#061d4e;--jaune:#fddc1d;--blanc:#fff;--win:#0f6b35;--loss:#b3261e;--draw:#061d4e;
  --fond:var(--navy);--titre:var(--blanc);--accent:var(--jaune);--info:var(--blanc);
  --bande:var(--jaune);--texte-bande:var(--navy)}
/* thème fond jaune : bandeaux bleus */
.jaune{--fond:var(--jaune);--titre:var(--navy);--accent:var(--navy);--info:var(--navy);
  --bande:var(--navy);--texte-bande:var(--blanc);--win:#3fd47a;--loss:#ff7766;--draw:var(--jaune)}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1350px;background:#000}
#v{position:relative;width:1080px;height:1350px;overflow:hidden;color:var(--titre);display:flex;flex-direction:column;
  background:var(--fond) center/cover no-repeat;background-image:var(--img-fond);font-family:Montserrat,"Arial Black",Arial,sans-serif}
.logo{position:absolute;top:30px;left:34px;width:122px}
.page{position:absolute;top:44px;right:48px;font-weight:800;font-size:26px;color:var(--accent)}
.head{position:relative;text-align:center;padding-top:40px}
.titre{font-family:Anton,Impact,sans-serif;font-size:156px;line-height:.92;letter-spacing:2px;text-transform:uppercase;color:var(--titre)}
.sous{font-weight:600;font-size:28px;letter-spacing:4px;margin-top:10px;color:var(--titre)}
.dates{font-family:Anton,Impact,sans-serif;font-size:64px;color:var(--accent);margin-top:2px;letter-spacing:1px}
/* filets verticaux décoratifs (comme la référence) */
.filet{position:absolute;top:560px;bottom:230px;width:3px;background:var(--accent);opacity:.9}
.filet:before,.filet:after{content:"";position:absolute;left:-5px;width:13px;height:13px;border-radius:50%;background:var(--accent)}
.filet:before{top:-20px}.filet:after{bottom:-20px}
.filet.g{left:40px}.filet.d{right:40px}
.liste{position:relative;flex:1;min-height:0;margin:26px 78px 170px;display:flex;flex-direction:column;justify-content:center;gap:26px}
.sect{display:flex;align-items:center;gap:18px;color:var(--accent);font-family:Anton,Impact,sans-serif;font-size:32px;letter-spacing:3px;margin-bottom:-10px}
.sect:after{content:"";flex:1;height:3px;background:var(--accent);opacity:.7}
.info{display:flex;align-items:center;gap:14px;font-weight:600;font-size:24px;letter-spacing:.5px;margin-bottom:8px;color:var(--info)}
.info:before{content:"";border-left:12px solid var(--accent);border-top:12px solid transparent;border-bottom:12px solid transparent}
.info .sep{opacity:.6}
.bande{display:grid;grid-template-columns:minmax(0,1fr) 3px 190px 150px;align-items:center;height:112px;background:var(--bande);
  color:var(--texte-bande);clip-path:polygon(0 5%,100% 0,100% 95%,0 100%)}
.eq{display:flex;align-items:baseline;gap:14px;padding:0 22px;white-space:nowrap;overflow:hidden;font-family:Anton,Impact,sans-serif;text-transform:uppercase}
.eq .n{font-size:56px;line-height:1}.eq .vs{font-family:Montserrat,sans-serif;font-weight:800;font-size:22px;opacity:.75}
.trait{height:70%;background:var(--texte-bande);opacity:.5}
.score{text-align:center;font-family:Anton,Impact,sans-serif;font-size:64px;font-style:italic;white-space:nowrap;overflow:hidden}
.score.V{color:var(--win)}.score.D{color:var(--loss)}.score.N{color:var(--draw)}
.score.heure{font-style:normal;color:var(--texte-bande);font-size:56px}
.cat{display:flex;align-items:center;justify-content:center;height:100%;text-align:center;font-family:Anton,Impact,sans-serif;font-size:34px;line-height:1;padding:0 8px;text-transform:uppercase;overflow:hidden}
/* logo de compétition (ballon FFHB + texte) */
.clogo{display:flex;flex-direction:column;align-items:center;justify-content:center;width:118px;height:86px;margin:auto;
  background:#fff;border-radius:8px;font-family:Montserrat,sans-serif;color:#1d3f8f;box-shadow:0 2px 6px rgba(0,0,0,.18)}
.clogo.rose{color:#a3195b}
.clogo img{height:40px}
.clogo .code{font-weight:800;font-size:28px;line-height:1;margin-top:3px}
.clogo .ligne{width:74px;height:2px;background:currentColor;margin:2px 0}
.clogo .csous{font-weight:800;font-size:8.5px;line-height:1.1;letter-spacing:.3px}
.partenaires{position:absolute;left:0;right:0;bottom:0;height:128px;background:var(--img-part) center/100% 100% no-repeat}
/* 6 matchs : version compacte */
#v.compact .titre{font-size:146px}#v.compact .dates{font-size:56px}
#v.compact .liste{gap:14px}#v.compact .info{font-size:21px;margin-bottom:5px}
#v.compact .bande{height:94px}#v.compact .eq .n{font-size:48px}#v.compact .score{font-size:56px}
#v.compact .sect{font-size:27px;margin-bottom:-4px}
.programme .liste{gap:24px}
.programme .bande{height:100px}
.programme .info{font-size:22px;opacity:.9}
.programme .info .lieu{color:var(--accent);font-weight:800}
.info .salle{font-weight:600;text-transform:uppercase;opacity:.95}
#v.compact .clogo{height:78px}#v.compact .clogo img{height:34px}#v.compact .clogo .code{font-size:24px}#v.compact .clogo .csous{font-size:8px}
</style></head><body><div id="v"></div>
<script>
const D = __DATA__;
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const V = document.getElementById("v");
if (D.theme === "jaune") V.classList.add("jaune");
if (D.mode === "programme") V.classList.add("programme");
if (D.matchs.length > 5) V.classList.add("compact");
V.style.setProperty("--img-fond", `url(${D.fond})`);
V.style.setProperty("--img-part", `url(${D.partenaires})`);
const cat = m => m.logo
  ? `<div class="clogo ${m.logo.rose ? "rose" : ""}"><img src="${m.logo.rose ? D.ballon_rose : D.ballon_bleu}"><div class="code">${esc(m.logo.code)}</div></div>`
  : `<div class="cat">${esc(m.categorie)}</div>`;
V.innerHTML = `
  <img class="logo" src="${D.logo}">
  ${D.total > 1 ? `<div class="page">${D.num}/${D.total}</div>` : ""}
  <div class="head"><div class="titre">${esc(D.titre)}</div><div class="sous">${esc(D.sous)}</div><div class="dates">${esc(D.dates)}</div></div>
  <div class="filet g"></div><div class="filet d"></div>
  <div class="liste">${D.matchs.map((m, i) => (i === 0 || m.groupe_nom !== D.matchs[i-1].groupe_nom ? `<div class="sect">${esc(m.groupe_nom)}</div>` : "") + `
    <div><div class="info">${D.mode === "programme" ? `${esc(m.jour)} <span class="sep">·</span> <span class="lieu">${esc(m.lieu)}${m.salle ? ` <span class="salle">· ${esc(m.salle)}</span>` : ""}</span>` : `${esc(m.lieu)}${m.salle ? ` <span class="salle">(${esc(m.salle)})</span>` : ""} <span class="sep">/</span> ${esc(m.jour)}`}</div>
    <div class="bande"><div class="eq"><span class="n">${esc(m.dom)}</span><span class="vs">vs</span><span class="n">${esc(m.ext)}</span></div>
    <div class="trait"></div>${D.mode === "programme"
      ? `<div class="score heure">${esc(m.heure || "À FIXER")}</div>`
      : `<div class="score ${m.res}">${m.sd}-${m.se}</div>`}${cat(m)}</div></div>`).join("")}
  </div>
  <div class="partenaires"></div>`;
function ajuste(){
  document.querySelectorAll(".eq").forEach(eq => { const ns = eq.querySelectorAll(".n"); let t = parseInt(getComputedStyle(ns[0]).fontSize);
    while (eq.scrollWidth > eq.clientWidth && t > 24) { t -= 2; ns.forEach(n => n.style.fontSize = t + "px"); } });
  document.querySelectorAll(".score").forEach(c => { let t = parseInt(getComputedStyle(c).fontSize); while (c.scrollWidth > c.clientWidth && t > 24) { t -= 2; c.style.fontSize = t + "px"; } });
  document.querySelectorAll(".cat").forEach(c => { let t = 34; while ((c.scrollWidth > c.clientWidth || c.scrollHeight > c.clientHeight) && t > 14) { t -= 2; c.style.fontSize = t + "px"; } });
  const L = document.querySelector(".liste"), bas = () => Math.max(...[...L.children].map(e => e.getBoundingClientRect().bottom));
  const limite = document.querySelector(".partenaires").getBoundingClientRect().top - 30;
  if (bas() > limite) { L.style.justifyContent = "flex-start"; const haut = L.children[0].getBoundingClientRect().top;
    L.style.transformOrigin = "top center"; L.style.transform = `scale(${Math.max(0.6, (limite - haut) / (bas() - haut))})`; }
  document.body.dataset.pret = "1"; }
Promise.all([...document.images].map(im => im.complete ? 0 : new Promise(r => { im.onload = im.onerror = r; })))
  .then(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 4000))])).then(ajuste);
</script></body></html>"""

POLICES_DIR = os.path.join(HERE, "polices")
CHARTE_DIR = os.path.join(HERE, "charte")


def charte_assets(theme="bleu"):
    """Images de la charte (dossier « charte ») intégrées en data URI."""
    import base64
    def uri(nom):
        chemin = os.path.join(CHARTE_DIR, nom)
        if not os.path.exists(chemin):
            return ""
        mime = "image/png" if nom.endswith(".png") else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(open(chemin, "rb").read()).decode()
    return {"theme": theme, "logo": uri("logo.png"), "fond": uri(f"fond_{theme}.jpg"),
            "partenaires": uri("partenaires.png"), "ballon_bleu": uri("ballon_bleu.png"),
            "ballon_rose": uri("ballon_rose.png")}


def logo_competition(comp):
    """Logo FFHB pour les championnats de France / nationales : code (N1, N3, U18...) + couleur."""
    url, n = comp.get("url", "").lower(), norm(comp.get("nom", ""))
    info = infos_categorie(comp)
    fem = info["ordre"][3] == 1
    m = re.search(r"nationale-(\d)", url)
    if m:
        return {"code": f"N{m.group(1)}", "sous": "CHAMPIONNAT DE FRANCE", "rose": fem}
    if "/national/" in url and info["age"]:
        return {"code": f"U{info['age']}", "sous": "CHAMPIONNAT DE FRANCE", "rose": fem}
    return None


def polices_css():
    """Polices intégrées (dossier « polices ») pour ne pas dépendre d'internet."""
    import base64
    css = []
    for fichier, famille, poids in (("Anton.woff2", "Anton", 400), ("Montserrat-600.woff2", "Montserrat", 600),
                                   ("Montserrat-800.woff2", "Montserrat", 800)):
        chemin = os.path.join(POLICES_DIR, fichier)
        if os.path.exists(chemin):
            b64 = base64.b64encode(open(chemin, "rb").read()).decode()
            css.append(f"@font-face{{font-family:'{famille}';font-weight:{poids};font-display:block;"
                       f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "\n".join(css)


_visuel_lock = threading.Lock()
_visuels_cache = {}


def generer_visuels(res, mode="resultats", club_nom="CALUIRE-RILLIEUX HANDBALL", theme=None):
    """Crée les PNG (mode « resultats » ou « programme »). Renvoie la liste des chemins
    (aussi enregistrés dans le dossier « visuels »)."""
    matchs = matchs_pour_visuel(res, mode)
    # liste triée par catégorie, répartie équitablement ; un titre de section sépare les catégories
    groupes = decoupe(matchs, 5 if mode == "programme" else MATCHS_PAR_VISUEL)
    theme = theme or load_config().get("theme_visuel", "bleu")
    prefixe = f"{mode}_{res['du']}_"
    cle = mode + theme + json.dumps(matchs, sort_keys=True, default=str) + res["du"]
    if cle in _visuels_cache and all(os.path.exists(p) for p in _visuels_cache[cle]):
        return _visuels_cache[cle]
    os.makedirs(VISUELS_DIR, exist_ok=True)
    for f in os.listdir(VISUELS_DIR):  # on remplace les images du même week-end
        if f.startswith(prefixe):
            os.remove(os.path.join(VISUELS_DIR, f))
    chemins = []
    if not groupes:
        return chemins
    from playwright.sync_api import sync_playwright
    with _visuel_lock, sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            fonts = polices_css()
            assets = charte_assets(theme)
            for i, g in enumerate(groupes, 1):
                page = browser.new_page(viewport={"width": 1080, "height": 1350})
                data = {"mode": mode, "titre": "Résultats" if mode == "resultats" else "Programme",
                        "sous": "DU WEEK-END" if mode == "resultats" else "MATCHS DU WEEK-END",

                        "dates": titre_dates(res["du"], res["au"], matchs), "num": i, "total": len(groupes),
                        "club": club_nom, "matchs": [{k: v for k, v in m.items() if k not in ("tri", "ordre")} for m in g],
                        **assets}
                page.set_content(VISUEL_HTML.replace("__FONTS__", fonts)
                                 .replace("__DATA__", json.dumps(data, ensure_ascii=False)), wait_until="load")
                try:
                    page.wait_for_selector("body[data-pret='1']", timeout=10000)
                except Exception:
                    pass
                chemin = os.path.join(VISUELS_DIR, f"{prefixe}{i}.png")
                page.locator("#v").screenshot(path=chemin)
                page.close()
                chemins.append(chemin)
        finally:
            browser.close()
    _visuels_cache[cle] = chemins
    return chemins



# ==========================================================================
# Affiche « NEXT GAME » du prochain match de N1 à domicile (+ match d'ouverture N3)
# ==========================================================================
AFFICHE_DIR = os.path.join(HERE, "affiche")
AFFICHE_ETAT = os.path.join(HERE, "ffhb_affiche.json")   # photos déjà utilisées (rotation)
JOURS_MIN = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS_MIN = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
            "octobre", "novembre", "décembre"]


def _data_uri(chemin):
    import base64
    if not chemin or not os.path.exists(chemin):
        return ""
    ext = chemin.lower().rsplit(".", 1)[-1]
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
            "ttf": "font/ttf", "otf": "font/otf", "woff2": "font/woff2"}.get(ext, "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(open(chemin, "rb").read()).decode()


def _logo_uri(chemin):
    """Logo recadré au plus près (marges transparentes retirées) pour que tous aient la même taille visuelle."""
    if not chemin or not os.path.exists(chemin):
        return ""
    try:
        from PIL import Image
        import io, base64
        im = Image.open(chemin).convert("RGBA")
        bb = im.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
        if bb:
            im = im.crop(bb)
        b = io.BytesIO()
        im.save(b, "PNG")
        return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return _data_uri(chemin)


def logo_equipe(nom, keys):
    """Logo d'une équipe : celui du club, sinon celui listé dans affiche/logos/logos.json."""
    if is_club(nom, keys):
        return os.path.join(CHARTE_DIR, "logo.png")
    dossier = os.path.join(AFFICHE_DIR, "logos")
    try:
        table = json.load(open(os.path.join(dossier, "logos.json"), encoding="utf-8"))
    except Exception:
        table = {}
    n = " " + re.sub(r"[^a-z0-9]+", " ", norm(nom)) + " "
    meilleur = None
    for cle, fichier in table.items():
        if cle.startswith("_"):
            continue
        k = " " + re.sub(r"[^a-z0-9]+", " ", norm(cle)).strip() + " "
        if k in n and os.path.exists(os.path.join(dossier, fichier)) and (not meilleur or len(k) > len(meilleur[0])):
            meilleur = (k, fichier)
    return os.path.join(dossier, meilleur[1]) if meilleur else None


def _etat_affiche():
    try:
        return json.load(open(AFFICHE_ETAT, encoding="utf-8"))
    except Exception:
        return {}


def _sauver_etat_affiche(etat):
    try:
        json.dump(etat, open(AFFICHE_ETAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass


def _dossier_photos():
    return os.path.join(AFFICHE_DIR, "photos")


def photo_suivante():
    """Une photo différente à chaque affiche, tirée au hasard parmi celles pas encore utilisées
    (on fait le tour de tout le dossier affiche/photos avant d'en reprendre une), jamais une des 5 dernières."""
    import random
    dossier = _dossier_photos()
    photos = sorted(f for f in os.listdir(dossier) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))) \
        if os.path.isdir(dossier) else []
    if not photos:
        raise RuntimeError("Aucune photo dans le dossier affiche/photos.")
    etat = _etat_affiche()
    deja = [f for f in etat.get("utilisees", []) if f in photos]
    recentes = [f for f in etat.get("recentes", []) if f in photos][-min(5, len(photos) - 1):] if len(photos) > 1 else []
    reste = [f for f in photos if f not in deja and f not in recentes]
    if not reste:                         # tout le dossier a servi : nouveau tour
        deja = []
        reste = [f for f in photos if f not in recentes] or photos
    choix = random.choice(reste)
    etat.update({"utilisees": deja + [choix], "derniere": choix, "recentes": (recentes + [choix])[-5:]})
    _sauver_etat_affiche(etat)
    return os.path.join(dossier, choix)


def photo_validee(jour):
    """Photo validée pour le match de ce jour (elle ne change plus), sinon None."""
    f = (_etat_affiche().get("validees") or {}).get(jour)
    chemin = os.path.join(_dossier_photos(), f) if f else None
    return chemin if chemin and os.path.exists(chemin) else None


def valider_photo(jour, photo, valider=True):
    etat = _etat_affiche()
    v = etat.setdefault("validees", {})
    if valider:
        if not os.path.exists(os.path.join(_dossier_photos(), os.path.basename(photo))):
            raise RuntimeError("Photo introuvable : " + photo)
        v[jour] = os.path.basename(photo)
    else:
        v.pop(jour, None)
    if (etat.get("derniere_affiche") or {}).get("date") == jour:
        etat["derniere_affiche"]["photo_validee"] = valider
    for d in (etat.get("dernieres_affiches") or {}).values():
        if d.get("date") == jour:
            d["photo_validee"] = valider
    _sauver_etat_affiche(etat)
    return {"date": jour, "photo": os.path.basename(photo), "photo_validee": valider}


def _photo_pour_affiche(chemin):
    """Photo réduite (2400 px max, orientation corrigée) pour l'affiche."""
    try:
        from PIL import Image, ImageOps
        import io, base64
        im = ImageOps.exif_transpose(Image.open(chemin)).convert("RGB")
        im.thumbnail((2400, 2400))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return _data_uri(chemin)   # sans Pillow : photo d'origine


def partenaire_du_match(jour):
    """Logo du partenaire du match (affiche/partenaires/partenaires_matchs.json : date -> fichier)."""
    d = os.path.join(AFFICHE_DIR, "partenaires")
    try:
        f = json.load(open(os.path.join(d, "partenaires_matchs.json"), encoding="utf-8")).get(jour)
    except Exception:
        f = None
    return os.path.join(d, f) if f and os.path.exists(os.path.join(d, f)) else None


def _nom_affiche(nom, keys):
    return "CALUIRE-RILLIEUX HB" if is_club(nom, keys) else nom_court(nom, keys)


TYPES_AFFICHE = {"n1": "Nationale 1 (championnat)", "cdf": "N1 – Coupe de France"}


def est_cdf_n1(c):
    """Coupe de France jouée par la N1 (nommée « N1 CDF » dans les réglages)."""
    u, n = c.get("url", "").lower(), norm(c.get("nom", ""))
    return est_coupe(u) and (n.startswith("n1") or "federale-masculine" in u)


def prochain_match_affiche(cfg=None, type_affiche="n1", relire=True):
    """Relit la FFHB et renvoie le prochain match à domicile de la N1 (championnat ou Coupe de France)
    et son match d'ouverture (N3 M jouée le même jour à domicile, juste avant)."""
    cfg = cfg or load_config()
    equipes = []   # (comp, logo, rôle) rôle = "principal" ou "ouverture"
    for c in cfg["competitions"]:
        if not c.get("url", "").strip():
            continue
        lc = logo_competition(c)
        if type_affiche == "cdf" and est_cdf_n1(c):
            equipes.append((c, {"code": "N1", "rose": False, "coupe": True}, "principal"))
        elif type_affiche != "cdf" and lc and lc["code"] == "N1" and not est_coupe(c["url"]):
            equipes.append((c, lc, "principal"))
        # ouverture : N3 masculine uniquement (la N3 F n'est pas prise en compte)
        elif lc and lc["code"] == "N3" and not lc.get("rose") and not est_coupe(c["url"]):
            equipes.append((c, lc, "ouverture"))
    if not any(r == "principal" for _, _, r in equipes):
        raise RuntimeError("Aucune « N1 CDF » (Coupe de France) dans les réglages." if type_affiche == "cdf"
                           else "Aucune équipe de Nationale 1 dans les réglages.")
    sous = dict(cfg, competitions=[c for c, _, _ in equipes])
    fri, sun = weekend(0)
    comps, resultats, _ = lire_saisons(sous, fri, sun, force=relire)   # lecture fraîche : horaires à jour
    aujourdhui = date.today().isoformat()
    a_dom = []   # (comp, logo, keys, match, rôle)
    for (c0, lc, role), c, r in zip(equipes, comps, resultats):
        keys = comp_keys(cfg, c)
        for m in r.get("matchs") or []:
            if m.get("date") and m["date"] >= aujourdhui and m["sd"] is None and is_club(m["dom"], keys):
                a_dom.append((c, lc, keys, m, role))
    princ = sorted([x for x in a_dom if x[4] == "principal"], key=lambda x: (x[3]["date"], x[3].get("heure") or ""))
    if not princ:
        raise RuntimeError("Aucun match de Coupe de France de la N1 à domicile à venir sur la FFHB." if type_affiche == "cdf"
                           else "Aucun match de Nationale 1 à domicile à venir sur la FFHB.")
    c, lc, keys, m, _ = princ[0]
    # match d'ouverture : N3 M à domicile le même jour, avant le match principal ; le plus proche
    ouv = [x[:4] for x in a_dom if x[4] == "ouverture" and x[3]["date"] == m["date"]
           and (x[3].get("heure") or "00:00") < (m.get("heure") or "23:59")]
    ouv.sort(key=lambda x: x[3].get("heure") or "")
    ouverture = ouv[-1] if ouv else None
    # salle relue sur la page du match
    hrefs = [x[3]["href"] for x in [princ[0]] + ([ouverture] if ouverture else []) if x[3].get("href")]
    cache = _charger_salles()
    for h in hrefs:
        cache.pop(h, None)
    salles = lire_salles(hrefs)
    return {"n1": (c, lc, keys, m), "ouverture": ouverture, "salles": salles, "type": type_affiche,
            "lu_a": datetime.now().strftime("%H:%M")}


# ---------- logos ajoutés depuis l'outil et infos en plus sur l'affiche ----------
def detourer_logo(im, mode="auto", tol=52):
    """Retire le fond d'un logo. mode « auto » : le fond qui touche les bords (le blanc à l'intérieur
    du logo est gardé) ; « tout » : aussi les zones de la couleur du fond à l'intérieur (lettres O, A…).
    Gère fond blanc, fond de couleur, faux damier « transparent » et JPG. Renvoie (image RGBA recadrée, détouré ?)."""
    from PIL import Image, ImageDraw, ImageChops, ImageFilter
    im = im.convert("RGBA")
    if max(im.size) > 1400:
        im.thumbnail((1400, 1400))
    W, H = im.size
    a = im.getchannel("A")
    pas = max(1, (2 * (W + H)) // 1500)
    bord = [(x, 0) for x in range(0, W, pas)] + [(x, H - 1) for x in range(0, W, pas)] + \
           [(0, y) for y in range(0, H, pas)] + [(W - 1, y) for y in range(0, H, pas)]
    pa = a.load()
    rgb = Image.new("RGB", im.size, (255, 255, 255))
    rgb.paste(im, mask=a)
    px = rgb.load()
    transp = sum(1 for p in bord if pa[p] < 200) / len(bord)
    proche = lambda c, d, t=tol: abs(c[0] - d[0]) <= t and abs(c[1] - d[1]) <= t and abs(c[2] - d[2]) <= t
    # couleurs du fond : groupes de couleurs les plus présents sur le pourtour (2 pour un faux damier)
    opaques = [px[p] for p in bord if pa[p] >= 200]
    fonds = []
    if opaques and transp < 0.6:
        compte = {}
        for c in opaques:
            q = tuple(v // 24 for v in c)
            compte[q] = compte.get(q, []) + [c]
        for q, cs in sorted(compte.items(), key=lambda kv: -len(kv[1]))[:3]:
            if len(cs) >= len(bord) * 0.10:
                fonds.append(tuple(sorted(c[i] for c in cs)[len(cs) // 2] for i in range(3)))
        # coins : s'ils se ressemblent, c'est le fond (logo qui touche les bords)
        coins = [px[(1, 1)], px[(W - 2, 1)], px[(1, H - 2)], px[(W - 2, H - 2)]]
        for c in coins:
            if sum(proche(c, d) for d in coins) >= 2 and not any(proche(c, f, 20) for f in fonds):
                fonds.append(c)
    if not fonds and transp >= 0.2:
        # PNG déjà transparent autour, mais logo posé sur une « plaque » (carré, rectangle arrondi…) :
        # couleur dominante du contour de la partie opaque, si elle remplit presque tout son cadre
        opaque = a.point(lambda v: 255 if v >= 200 else 0)
        bb = opaque.getbbox()
        if bb:
            hist = opaque.crop(bb).histogram()
            remplissage = hist[255] / max(1, (bb[2] - bb[0]) * (bb[3] - bb[1]))
            contour = ImageChops.subtract(opaque, opaque.filter(ImageFilter.MinFilter(3)))
            cp = contour.load()
            pts = [(x, y) for y in range(0, H, 2) for x in range(0, W, 2) if cp[x, y] == 255]
            if remplissage >= 0.85 and len(pts) > 20:
                compte = {}
                for p in pts:
                    q = tuple(v // 24 for v in px[p])
                    compte[q] = compte.get(q, []) + [px[p]]
                q, cs = max(compte.items(), key=lambda kv: len(kv[1]))
                if len(cs) >= len(pts) * 0.6:
                    fonds.append(tuple(sorted(c[i] for c in cs)[len(cs) // 2] for i in range(3)))
    if not fonds:
        bb = a.point(lambda v: 255 if v > 12 else 0).getbbox()
        return (im.crop(bb) if bb else im), transp >= 0.2
    # écart de couleur avec le fond le plus proche (0 = fond, 255 = logo)
    ecart = None
    for f in fonds:
        e = ImageChops.difference(rgb, Image.new("RGB", rgb.size, f))
        er, eg, eb = e.split()
        e = ImageChops.lighter(ImageChops.lighter(er, eg), eb)
        ecart = e if ecart is None else ImageChops.darker(ecart, e)
    # zones « couleur du fond » reliées au bord (remplissage sur un masque noir/blanc : le faux damier passe)
    # (les zones déjà transparentes laissent passer le remplissage)
    semblable = ImageChops.lighter(ImageChops.darker(ecart.point(lambda v: 255 if v <= tol else 0),
                                                     a.point(lambda v: 255 if v >= 200 else 0)),
                                   a.point(lambda v: 255 if v < 200 else 0))
    # les petites coupures du contour du logo (reflets, liseré fin) sont refermées pour que le fond
    # ne « coule » pas à l'intérieur : on remplit sur un contour épaissi puis on rend les 3 px retirés
    ferme = ImageChops.invert(ImageChops.invert(semblable).filter(ImageFilter.MaxFilter(7)))
    fp = ferme.load()
    for p in bord:
        if fp[p] == 255:
            ImageDraw.floodfill(ferme, p, 128, thresh=0)
    dehors = ferme.point(lambda v: 255 if v == 128 else 0).filter(ImageFilter.MaxFilter(7))
    masque = ImageChops.darker(dehors, semblable)
    # sécurité : si un bord entier n'a pas été atteint (logo fin), remplissage simple
    if masque.getbbox() is None:
        sp = semblable.load()
        for p in bord:
            if sp[p] == 255:
                ImageDraw.floodfill(semblable, p, 128, thresh=0)
        masque = semblable.point(lambda v: 255 if v == 128 else 0)
    if mode == "tout":   # zones de la couleur du fond à l'intérieur du logo
        masque = ImageChops.lighter(masque, ecart.point(lambda v: 255 if v <= tol * 0.6 else 0))
    if masque.getbbox() is None:
        return im, False
    doux = ecart.point(lambda v: min(255, v * 255 // (tol * 2)))
    alpha = ImageChops.invert(masque)
    bande = ImageChops.subtract(masque.filter(ImageFilter.MaxFilter(5)), masque)
    alpha = Image.composite(ImageChops.darker(alpha, doux), alpha, bande)   # bords sans liseré
    alpha = ImageChops.darker(alpha, a).filter(ImageFilter.GaussianBlur(0.6))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    bb = alpha.point(lambda v: 255 if v > 20 else 0).getbbox()
    return (out.crop(bb) if bb else out), True


def enregistrer_logo(nom, data_uri, detourer="auto"):
    """Logo d'une équipe envoyé depuis l'outil : PNG dans affiche/logos + ligne dans logos.json."""
    import base64, io
    if not nom or "," not in (data_uri or ""):
        raise RuntimeError("Logo ou nom d'équipe manquant.")
    brut = base64.b64decode(data_uri.split(",", 1)[1])
    dossier = os.path.join(AFFICHE_DIR, "logos")
    os.makedirs(dossier, exist_ok=True)
    cle = re.sub(r"[^a-z0-9]+", " ", norm(nom)).strip()
    fichier = (slug(nom) or "logo")[:60] + ".png"
    detoure = False
    if not ensure_pillow():
        raise RuntimeError("Pillow (retouche d'images) n'a pas pu s'installer : ouvre un terminal et lance « pip install pillow », puis relance l'outil.")
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(brut))).convert("RGBA")
        im.thumbnail((1200, 1200))
        if detourer in (True, "auto", "tout"):
            im, detoure = detourer_logo(im, "tout" if detourer == "tout" else "auto")
        else:
            bb = im.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
            im = im.crop(bb) if bb else im
        im.save(os.path.join(dossier, fichier), "PNG")
    except Exception:
        raise RuntimeError("Image illisible : envoie un PNG, un JPG ou un WEBP.")
    chemin_table = os.path.join(dossier, "logos.json")
    try:
        table = json.load(open(chemin_table, encoding="utf-8"))
    except Exception:
        table = {}
    table[cle] = fichier
    json.dump(table, open(chemin_table, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"nom": nom, "fichier": fichier, "detoure": detoure,
            "apercu": _logo_uri(os.path.join(dossier, fichier))}


def _cle_infos(type_affiche, jour):
    return f"{type_affiche}_{jour}"


def infos_affiche(type_affiche, jour):
    """Infos en plus enregistrées pour l'affiche de ce match : {texte, image}."""
    i = ((_etat_affiche().get("infos") or {}).get(_cle_infos(type_affiche, jour))) or {}
    if i.get("image") and not os.path.exists(os.path.join(AFFICHE_DIR, "infos", i["image"])):
        i = dict(i, image=None)
    return i


def enregistrer_infos(type_affiche, jour, texte, image=None, sans_image=False):
    import base64, io
    etat = _etat_affiche()
    infos = etat.setdefault("infos", {})
    cle = _cle_infos(type_affiche, jour)
    ancien = infos.get(cle) or {}
    nouv = {"texte": (texte or "").strip(), "image": None if sans_image else ancien.get("image")}
    if image and "," in image:
        dossier = os.path.join(AFFICHE_DIR, "infos")
        os.makedirs(dossier, exist_ok=True)
        fichier = f"{cle}_{datetime.now():%H%M%S}.png"
        brut = base64.b64decode(image.split(",", 1)[1])
        try:
            from PIL import Image, ImageOps
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(brut))).convert("RGBA")
            im.thumbnail((800, 800))
            im.save(os.path.join(dossier, fichier), "PNG")
        except ImportError:
            open(os.path.join(dossier, fichier), "wb").write(brut)
        except Exception:
            raise RuntimeError("Image illisible : envoie un PNG ou un JPG.")
        nouv["image"] = fichier
    if nouv["texte"] or nouv["image"]:
        infos[cle] = nouv
    else:
        infos.pop(cle, None)
    _sauver_etat_affiche(etat)
    return nouv


def generer_affiche(info=None, type_affiche="n1", photo=None, relire=True):
    """Crée l'affiche du prochain match à domicile de la N1 (type « n1 » : championnat, « cdf » : Coupe de France).
    photo : garder cette photo (ex. quand on ajoute des infos) ; relire=False : lecture FFHB de moins de 30 min acceptée.
    Renvoie (chemin, détails)."""
    info = info or prochain_match_affiche(type_affiche=type_affiche, relire=relire)
    type_affiche = info.get("type", type_affiche)
    c, lc, keys, m = info["n1"]
    coupe = bool(lc.get("coupe"))
    d = date.fromisoformat(m["date"])
    heure = (m.get("heure") or "").replace(":", "H") or "HORAIRE À FIXER"
    s = info["salles"].get(m.get("href")) or {}
    salle = ("SALLE " + salle_courte(s["nom"], s.get("ville", "")).upper()) if s.get("nom") else ""
    garder = os.path.join(_dossier_photos(), os.path.basename(photo)) if photo else None
    photo = (garder if garder and os.path.exists(garder) else None) or photo_validee(m["date"]) or photo_suivante()
    inf = infos_affiche(type_affiche, m["date"])
    data = {"date": f"{JOURS_MIN[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS_MIN[d.month]}",
            "nom_dom": _nom_affiche(m["dom"], keys), "nom_ext": _nom_affiche(m["ext"], keys),
            "competition": "COUPE DE FRANCE" if coupe else "NATIONALE " + lc["code"][1:],
            "journee": (m.get("tour") or "").upper() if coupe else (f"JOURNÉE {m['journee']}" if m.get("journee") else ""),
            "infos": {"lignes": [l.strip() for l in (inf.get("texte") or "").splitlines() if l.strip()][:5],
                      "image": _logo_uri(os.path.join(AFFICHE_DIR, "infos", inf["image"])) if inf.get("image") else ""},
            "heure": heure, "salle": salle,
            "logo_dom": _logo_uri(logo_equipe(m["dom"], keys)), "logo_ext": _logo_uri(logo_equipe(m["ext"], keys)),
            "ballon": _data_uri(os.path.join(CHARTE_DIR, "ballon_rose.png" if lc.get("rose") else "ballon_bleu.png")),
            "motif": _data_uri(os.path.join(AFFICHE_DIR, "motif.png")),
            "partenaires": _data_uri(os.path.join(CHARTE_DIR, "partenaires.png")),
            "photo": _photo_pour_affiche(photo), "ouverture": None,
            "partenaire_match": _data_uri(partenaire_du_match(m["date"]))}
    details = {"match": f"{m['dom']} – {m['ext']}", "date": m["date"], "heure": m.get("heure"),
               "dom": m["dom"], "ext": m["ext"], "heure_corrigee": bool(m.get("heure_corrigee")),
               "salle": s.get("nom", ""), "journee": m.get("journee"), "photo": os.path.basename(photo),
               "lu_a": info.get("lu_a"), "ouverture": None, "logos_manquants": [],
               "partenaire": os.path.basename(partenaire_du_match(m["date"]) or "") or None,
               "photo_validee": bool(photo_validee(m["date"])), "type": type_affiche,
               "type_nom": TYPES_AFFICHE.get(type_affiche, ""), "tour": m.get("tour") if coupe else None,
               "infos": {"texte": inf.get("texte", ""), "image": inf.get("image")},
               "equipes": [{"nom": n, "logo": bool(logo_equipe(n, keys)), "club": is_club(n, keys)}
                           for n in (m["dom"], m["ext"])]}
    for nom in (m["dom"], m["ext"]):
        if not logo_equipe(nom, keys):
            details["logos_manquants"].append(nom)
    if info["ouverture"]:
        oc, olc, okeys, om = info["ouverture"]
        adv = om["ext"]
        data["ouverture"] = {"categorie": "N3 M",
                             "logo": _logo_uri(logo_equipe(adv, okeys)), "nom": _nom_affiche(adv, okeys),
                             "heure": (om.get("heure") or "").replace(":", "H")}
        details["ouverture"] = f"{oc.get('nom', '')} : {om['dom']} – {adv} à {om.get('heure')}"
        details["equipes"].append({"nom": adv, "logo": bool(logo_equipe(adv, okeys)), "club": False, "ouverture": True})
        if not logo_equipe(adv, okeys):
            details["logos_manquants"].append(adv)
    page_html = open(os.path.join(AFFICHE_DIR, "modele_affiche.html"), encoding="utf-8").read()
    page_html = (page_html.replace("__ANTON__", _data_uri(os.path.join(POLICES_DIR, "Anton-Regular.ttf")))
                 .replace("__COLO__", _data_uri(os.path.join(POLICES_DIR, "Colo-Pro.otf"))))
    os.makedirs(VISUELS_DIR, exist_ok=True)
    base = os.path.join(VISUELS_DIR, f"affiche_{'CDF' if coupe else 'N1'}_{m['date']}_{datetime.now():%H%M%S}")
    chemin, chemin_a4, chemin_pdf = base + ".png", base + "_A4.png", base + "_A4.pdf"
    from playwright.sync_api import sync_playwright
    with _visuel_lock, sync_playwright() as pw:
        b = launch_browser(pw)
        try:
            # 4:5 (réseaux) en 2160 × 2700, puis A4 portrait à 300 dpi (2480 × 3508)
            for fmt, sortie, larg, haut, echelle in (("reseaux", chemin, 1080, 1350, 2),
                                                     ("a4", chemin_a4, 1080, 1528, 2480 / 1080)):
                pg = b.new_page(viewport={"width": larg, "height": haut}, device_scale_factor=echelle)
                pg.set_content(page_html.replace("__DATA__", json.dumps(dict(data, format=fmt), ensure_ascii=False)),
                               wait_until="load")
                pg.wait_for_selector("body[data-pret='1']", timeout=90000)
                err = pg.evaluate("document.body.dataset.erreur")
                if err:
                    raise RuntimeError("Photo illisible (" + os.path.basename(photo) + ") : " + err)
                pg.locator("#a").screenshot(path=sortie)
                pg.close()
        finally:
            b.close()
    try:  # PDF A4 prêt à imprimer
        from PIL import Image
        Image.open(chemin_a4).convert("RGB").save(chemin_pdf, "PDF", resolution=300.0)
    except Exception:
        chemin_pdf = None
    details.update(fichier=os.path.basename(chemin), fichier_a4=os.path.basename(chemin_a4),
                   fichier_pdf=os.path.basename(chemin_pdf) if chemin_pdf else None, dossier=VISUELS_DIR)
    etat = _etat_affiche()
    etat["derniere_affiche"] = details
    etat.setdefault("dernieres_affiches", {})[type_affiche] = details
    _sauver_etat_affiche(etat)
    return chemin, details


# ==========================================================================
# Écran géant : vidéo « PROCHAIN MATCH » (1920 × 1080, 10 s en boucle) pour chaque Nationale
# ==========================================================================
ECRAN_DIR = os.path.join(HERE, "ecran")
ECRAN_FPS = 25
ECRAN_DUREE = 10


def chemin_ffmpeg():
    """ffmpeg du système, sinon celui du paquet imageio-ffmpeg (installé automatiquement)."""
    import shutil
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import imageio_ffmpeg
    except ImportError:
        base = [sys.executable, "-m", "pip", "install", "imageio-ffmpeg"]
        for cmd in (base, base + ["--user"], base + ["--break-system-packages"]):
            if subprocess.call(cmd) == 0:
                break
        import importlib
        importlib.invalidate_caches()
        import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def prochains_matchs_ecran(cfg=None):
    """Relit la FFHB et renvoie le prochain match à domicile de chaque Nationale (N1, N3 M, N3 F)."""
    cfg = cfg or load_config()
    equipes = {}
    for c in cfg["competitions"]:
        lc = logo_competition(c)
        if lc and lc["code"].startswith("N") and c.get("url", "").strip() and not est_coupe(c["url"]):
            equipes.setdefault((lc["code"], bool(lc.get("rose"))), (c, lc))
    if not equipes:
        raise RuntimeError("Aucune équipe de Nationale dans les réglages.")
    sous = dict(cfg, competitions=[c for c, _ in equipes.values()])
    fri, sun = weekend(0)
    comps, resultats, _ = lire_saisons(sous, fri, sun, force=True)
    aujourdhui = date.today().isoformat()
    out = []
    for c, r in zip(comps, resultats):
        lc = logo_competition(c)
        keys = comp_keys(cfg, c)
        dom = sorted((m for m in r.get("matchs") or [] if m.get("date") and m["date"] >= aujourdhui
                      and m["sd"] is None and is_club(m["dom"], keys)), key=lambda m: (m["date"], m.get("heure") or ""))
        out.append({"comp": c, "lc": lc, "keys": keys, "match": dom[0] if dom else None})
    hrefs = [x["match"]["href"] for x in out if x["match"] and x["match"].get("href")]
    cache = _charger_salles()
    for h in hrefs:
        cache.pop(h, None)
    salles = lire_salles(hrefs)
    for x in out:
        x["salle"] = salles.get((x["match"] or {}).get("href")) or {}
    ordre = {("N1", False): 0, ("N2", False): 1, ("N3", False): 2, ("N1", True): 3, ("N2", True): 4, ("N3", True): 5}
    out.sort(key=lambda x: ordre.get((x["lc"]["code"], bool(x["lc"].get("rose"))), 9))
    return out


def generer_video_ecran(x):
    """Crée la vidéo MP4 d'un match. Renvoie (chemin, détails)."""
    c, lc, keys, m = x["comp"], x["lc"], x["keys"], x["match"]
    nom_eq = lc["code"] + (" F" if lc.get("rose") else " M" if lc["code"] != "N1" else "")
    if not m:
        return None, {"equipe": nom_eq, "erreur": "Pas de match à domicile à venir sur la FFHB."}
    d = date.fromisoformat(m["date"])
    s = x["salle"]
    salle = salle_courte(s["nom"], s.get("ville", "")).upper() if s.get("nom") else ""
    data = {"nom_dom": _nom_affiche(m["dom"], keys), "nom_ext": _nom_affiche(m["ext"], keys),
            "logo_dom": _logo_uri(logo_equipe(m["dom"], keys)), "logo_ext": _logo_uri(logo_equipe(m["ext"], keys)),
            "ballon": _data_uri(os.path.join(CHARTE_DIR, "ballon_rose.png" if lc.get("rose") else "ballon_bleu.png")),
            "code": lc["code"], "rose": bool(lc.get("rose")),
            "heure": (m.get("heure") or "").replace(":", "H") or "HORAIRE À FIXER",
            "date": f"{d.day}{'ER' if d.day == 1 else ''} {MOIS_FR[d.month]}", "salle": salle, "duree": ECRAN_DUREE}
    page_html = (open(os.path.join(ECRAN_DIR, "modele_ecran.html"), encoding="utf-8").read()
                 .replace("__ANTON__", _data_uri(os.path.join(POLICES_DIR, "Anton-Regular.ttf")))
                 .replace("__COLO__", _data_uri(os.path.join(POLICES_DIR, "Colo-Pro.otf")))
                 .replace("__FOND__", _data_uri(os.path.join(ECRAN_DIR, "fond.jpg")))
                 .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    os.makedirs(VISUELS_DIR, exist_ok=True)
    nom = f"ecran_{nom_eq.replace(' ', '')}_{m['date']}"
    chemin, apercu = os.path.join(VISUELS_DIR, nom + ".mp4"), os.path.join(VISUELS_DIR, nom + ".jpg")
    ff = chemin_ffmpeg()
    from playwright.sync_api import sync_playwright
    with _visuel_lock, sync_playwright() as pw:
        b = launch_browser(pw)
        proc = None
        try:
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.set_content(page_html, wait_until="load")
            pg.wait_for_selector("body[data-pret='1']", timeout=60000)
            proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(ECRAN_FPS),
                                     "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                                     "-preset", "medium", "-movflags", "+faststart", chemin], stdin=subprocess.PIPE)
            for i in range(ECRAN_FPS * ECRAN_DUREE):
                pg.evaluate(f"frame({i / ECRAN_FPS})")
                img = pg.screenshot(type="jpeg", quality=95)
                proc.stdin.write(img)
                if i == int(4 * ECRAN_FPS):
                    with open(apercu, "wb") as f:
                        f.write(img)
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError("ffmpeg n'a pas pu créer la vidéo.")
        finally:
            if proc and proc.poll() is None:
                proc.kill()
            b.close()
    det = {"equipe": nom_eq, "match": f"{m['dom']} – {m['ext']}", "date": m["date"], "heure": m.get("heure"),
           "salle": s.get("nom", ""), "fichier": os.path.basename(chemin), "apercu": os.path.basename(apercu),
           "logos_manquants": [n for n in (m["dom"], m["ext"]) if not logo_equipe(n, keys)]}
    return chemin, det


def generer_videos_ecran():
    lus = prochains_matchs_ecran()
    heure = datetime.now().strftime("%H:%M")
    videos = []
    for x in lus:
        try:
            _, det = generer_video_ecran(x)
        except Exception as e:
            det = {"equipe": x["lc"]["code"], "erreur": str(e)}
        videos.append(det)
    etat = _etat_affiche()
    etat["ecran"] = {"lu_a": heure, "videos": videos}
    _sauver_etat_affiche(etat)
    return {"lu_a": heure, "videos": videos, "dossier": VISUELS_DIR}

# ==========================================================================
# Publication sur le site WordPress du club (rubrique Actualités)
# ==========================================================================
WP_ETAT_FILE = os.path.join(HERE, "ffhb_wordpress.json")   # articles déjà publiés (pour mettre à jour au lieu de dupliquer)
WP_DEFAUT = {"site": "https://caluirerillieuxhandball.fr", "utilisateur": "", "mot_de_passe": "",
             "categorie": "Matchs", "statut": "draft"}


def wp_config():
    wp = dict(WP_DEFAUT, **(load_config().get("wordpress") or {}))
    # mode automatique (GitHub) : accès fournis par des variables d'environnement secrètes
    for cle, var in (("site", "FFHB_WP_SITE"), ("utilisateur", "FFHB_WP_USER"),
                     ("mot_de_passe", "FFHB_WP_PASSWORD"), ("statut", "FFHB_WP_STATUT")):
        if os.environ.get(var, "").strip():
            wp[cle] = os.environ[var].strip()
    return wp


class WPErreur(Exception):
    pass


def wp_requete(wp, methode, chemin, donnees=None, entetes=None, brut=None):
    import base64
    import urllib.error
    import urllib.request
    url = wp["site"].rstrip("/") + "/wp-json/wp/v2/" + chemin.lstrip("/")
    jeton = base64.b64encode(f'{wp["utilisateur"]}:{wp["mot_de_passe"]}'.encode()).decode()
    # « X-FFHB-Auth » : copie de l'identifiant pour les hébergeurs qui suppriment l'en-tête Authorization
    # (récupérée côté site par le petit code « Outil FFHB » à ajouter avec l'extension WPCode)
    h = {"Authorization": "Basic " + jeton, "X-FFHB-Auth": "Basic " + jeton,
         "User-Agent": "FFHB-Resultats/1.0", "Accept": "application/json"}
    corps = brut
    if donnees is not None:
        corps = json.dumps(donnees).encode("utf-8")
        h["Content-Type"] = "application/json"
    h.update(entetes or {})
    req = urllib.request.Request(url, data=corps, headers=h, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=60, context=contexte_ssl()) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("message", "")
        except Exception:
            msg = ""
        if e.code in (401, 403) and ("pas connect" in msg or "not logged in" in msg.lower()):
            raise WPErreur("le site n'a pas reçu l'identifiant : l'hébergeur bloque l'en-tête d'authentification. "
                           "Ajoute la règle « SetEnvIf Authorization » dans le fichier .htaccess (voir LISEZMOI, section 7).")
        if e.code == 403 and not msg:
            raise WPErreur(f"le pare-feu de l'hébergeur a bloqué la demande ({methode} {chemin.split('?')[0]}). "
                           "Envoie ce message à Claude.")
        if e.code in (401, 403):
            raise WPErreur("identifiant ou mot de passe d'application refusé par le site"
                           + (f" ({msg})" if msg else "") + ". Vérifie-les dans Réglages.")
        raise WPErreur(f"le site a répondu erreur {e.code}" + (f" : {msg}" if msg else ""))
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
            raise WPErreur("certificats de sécurité de Python manquants sur ce Mac. Ouvre le Finder > Applications > "
                           "Python 3.x et double-clique sur « Install Certificates.command », puis réessaie.")
        raise WPErreur(f"site injoignable ({e.reason}). Vérifie l'adresse du site et ta connexion.")


def wp_articles(n=60):
    """Derniers articles du site (publiés, brouillons, programmés) pour le menu « Articles du site »."""
    wp = wp_config()
    if not wp["utilisateur"] or not wp["mot_de_passe"]:
        raise WPErreur("renseigne l'identifiant et le mot de passe d'application dans Réglages.")
    posts = wp_requete(wp, "GET", f"posts?per_page={n}&status=publish,draft,future,pending,private&context=edit"
                                  "&orderby=date&order=desc&_fields=id,title,status,date,link,categories") or []
    noms = {}
    try:
        for c in wp_requete(wp, "GET", "categories?per_page=100&_fields=id,name") or []:
            noms[c["id"]] = html_texte(c.get("name", ""))
    except WPErreur:
        pass
    return [{"id": p["id"], "titre": html_texte((p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered", "")) or "(sans titre)",
             "statut": p.get("status"), "date": (p.get("date") or "")[:16], "lien": p.get("link"),
             "rubrique": ", ".join(noms.get(c, "") for c in p.get("categories") or [] if noms.get(c)),
             "edition": wp["site"].rstrip("/") + f"/wp-admin/post.php?post={p['id']}&action=edit"} for p in posts]


def _wp_supprimer_objet(wp, chemin):
    try:
        return wp_requete(wp, "DELETE", chemin)
    except WPErreur as e:
        # certains hébergeurs bloquent la méthode DELETE : WordPress accepte aussi POST + _method=DELETE
        if "405" in str(e) or "pare-feu" in str(e) or "501" in str(e):
            return wp_requete(wp, "POST", chemin + ("&" if "?" in chemin else "?") + "_method=DELETE")
        raise


def wp_supprimer_article(post_id, definitif=False):
    """Met l'article à la corbeille (récupérable dans WordPress) ou le supprime définitivement avec ses images."""
    wp = wp_config()
    post_id = int(post_id)
    medias = set()
    if definitif:
        try:
            p = wp_requete(wp, "GET", f"posts/{post_id}?context=edit&_fields=featured_media")
            if p and p.get("featured_media"):
                medias.add(p["featured_media"])
            for m in wp_requete(wp, "GET", f"media?parent={post_id}&per_page=100&_fields=id") or []:
                medias.add(m["id"])
        except WPErreur:
            pass
    _wp_supprimer_objet(wp, f"posts/{post_id}" + ("?force=true" if definitif else ""))
    for mid in medias:
        try:
            _wp_supprimer_objet(wp, f"media/{mid}?force=true")
        except WPErreur:
            pass
    # l'outil oublie cet article : la prochaine publication du week-end en recréera un
    try:
        etat = _etat_wp()
        etat = {k: v for k, v in etat.items() if v.get("id") != post_id}
        with open(WP_ETAT_FILE, "w", encoding="utf-8") as f:
            json.dump(etat, f)
    except Exception:
        pass
    return {"id": post_id, "definitif": definitif, "images": len(medias)}


# ---------- Publication automatique (GitHub Actions) : activer / désactiver depuis l'outil ----------
WORKFLOW_AUTO = "publication.yml"
VARS_AUTO = {"resultats": "FFHB_AUTO_RESULTATS", "programme": "FFHB_AUTO_PROGRAMME"}


class GHErreur(Exception):
    pass


def gh_config():
    g = dict(load_config().get("github") or {})
    if os.environ.get("FFHB_GITHUB_DEPOT"):
        g.update(depot=os.environ["FFHB_GITHUB_DEPOT"], jeton=os.environ.get("FFHB_GITHUB_TOKEN", ""))
    depot = re.sub(r"^https?://github\.com/", "", (g.get("depot") or "").strip()).strip("/")
    depot = re.sub(r"\.git$", "", depot)
    return {"depot": depot, "jeton": (g.get("jeton") or "").strip()}


def gh_requete(methode, chemin, donnees=None):
    import urllib.error
    import urllib.request
    g = gh_config()
    if not g["depot"] or not g["jeton"]:
        raise GHErreur("renseigne le dépôt GitHub et le jeton d'accès (encadré « Connexion à GitHub »).")
    url = os.environ.get("FFHB_GH_API", "https://api.github.com") + "/repos/" + g["depot"] + chemin
    h = {"Authorization": "Bearer " + g["jeton"], "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "FFHB-Resultats"}
    corps = None
    if donnees is not None:
        corps = json.dumps(donnees).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=corps, headers=h, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=30, context=contexte_ssl()) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt.strip() else None
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("message", "")
        except Exception:
            msg = ""
        if e.code == 401:
            raise GHErreur("jeton GitHub refusé (expiré ou mal copié) : crée-en un nouveau.")
        if e.code == 403:
            raise GHErreur("le jeton GitHub n'a pas les droits nécessaires (Actions et Variables en lecture/écriture)."
                           + (f" ({msg})" if msg else ""))
        if e.code == 404:
            raise GHErreur("introuvable sur GitHub : vérifie le nom du dépôt (ex. pseudo/outil-ffhb) et que le jeton y a accès."
                           , 404)
        raise GHErreur(f"GitHub a répondu erreur {e.code}" + (f" : {msg}" if msg else ""))
    except urllib.error.URLError as e:
        raise GHErreur(f"GitHub injoignable ({e.reason}).")


def _gh_variable(nom):
    try:
        return (gh_requete("GET", f"/actions/variables/{nom}") or {}).get("value")
    except GHErreur as e:
        if len(e.args) > 1 and e.args[1] == 404:
            return None
        raise


def auto_etat():
    """État de la publication automatique : interrupteurs, workflow actif, dernières exécutions."""
    wf = gh_requete("GET", f"/actions/workflows/{WORKFLOW_AUTO}")
    modes = {}
    for mode, var in VARS_AUTO.items():
        v = _gh_variable(var)
        modes[mode] = (v or "on").lower() not in ("off", "non", "false", "0")
    runs = (gh_requete("GET", f"/actions/workflows/{WORKFLOW_AUTO}/runs?per_page=8") or {}).get("workflow_runs", [])
    statut = _gh_variable("FFHB_WP_STATUT") or "draft"
    return {"workflow_actif": wf.get("state") == "active", "modes": modes, "statut_publication": statut,
            "lien": f"https://github.com/{gh_config()['depot']}/actions/workflows/{WORKFLOW_AUTO}",
            "executions": [{"date": r.get("created_at"), "declencheur": r.get("event"), "statut": r.get("status"),
                            "resultat": r.get("conclusion"), "lien": r.get("html_url")} for r in runs]}


def _gh_ecrire_variable(nom, valeur):
    try:
        gh_requete("PATCH", f"/actions/variables/{nom}", {"name": nom, "value": valeur})
    except GHErreur as e:
        if len(e.args) > 1 and e.args[1] == 404:
            gh_requete("POST", "/actions/variables", {"name": nom, "value": valeur})
        else:
            raise


def auto_regler(mode, actif):
    """Active / désactive la publication automatique des résultats ou du programme."""
    if mode not in VARS_AUTO:
        raise GHErreur("mode inconnu")
    _gh_ecrire_variable(VARS_AUTO[mode], "on" if actif else "off")
    if actif:   # workflow désactivé sur GitHub (ex. 60 jours sans activité) : on le réactive
        try:
            gh_requete("PUT", f"/actions/workflows/{WORKFLOW_AUTO}/enable")
        except GHErreur:
            pass
    return auto_etat()


def auto_statut(statut):
    """Brouillon ou publication directe pour les articles automatiques."""
    _gh_ecrire_variable("FFHB_WP_STATUT", "publish" if statut == "publish" else "draft")
    return auto_etat()


def auto_lancer(mode):
    """Lance tout de suite la publication automatique (sur GitHub, l'ordinateur peut être éteint ensuite)."""
    branche = (gh_requete("GET", "") or {}).get("default_branch") or "main"
    gh_requete("POST", f"/actions/workflows/{WORKFLOW_AUTO}/dispatches",
               {"ref": branche, "inputs": {"mode": "programme" if mode == "programme" else "resultats"}})
    return {"lance": True}


def wp_tester():
    wp = wp_config()
    if not wp["utilisateur"] or not wp["mot_de_passe"]:
        raise WPErreur("renseigne l'identifiant et le mot de passe d'application dans Réglages.")
    moi = wp_requete(wp, "GET", "users/me?context=edit")
    cat = wp_categorie(wp)
    return {"nom": moi.get("name"), "roles": moi.get("roles", []),
            "categorie": cat["name"] if cat else None}


# les 4 rubriques filtrables de la page Actualités : Matchs, Équipes jeunes, Vie du club, Partenaires
RUBRIQUE_RESULTATS = "Matchs"      # résultats et programme du week-end vont toujours dans « Matchs »


def wp_categorie(wp, nom=RUBRIQUE_RESULTATS):
    from urllib.parse import quote
    for c in wp_requete(wp, "GET", f"categories?per_page=100&search={quote(nom)}") or []:
        if norm(html_texte(c.get("name", ""))) == norm(nom):
            return c
    return None


def html_texte(s):
    import html as H
    return H.unescape(re.sub(r"<[^>]+>", "", s or ""))


def _etat_wp():
    try:
        with open(WP_ETAT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def contenu_article(res, mode, medias):
    """Corps de l'article au format blocs WordPress : intro, visuels, puis le détail par catégorie."""
    import html as H
    e = lambda s: H.escape(str(s))
    ms = matchs_pour_visuel(res, mode)
    dates = titre_dates(res["du"], res["au"], ms).lower()
    blocs = []
    intro = (f"Retrouvez les résultats de nos équipes pour le week-end du {dates}." if mode == "resultats"
             else f"Voici le programme de nos équipes pour le week-end du {dates}. Venez nombreux les encourager !")
    blocs.append(f"<!-- wp:paragraph -->\n<p>{e(intro)}</p>\n<!-- /wp:paragraph -->")
    for m in medias:
        blocs.append(f'<!-- wp:image {{"id":{m["id"]},"sizeSlug":"full","linkDestination":"none"}} -->\n'
                     f'<figure class="wp-block-image size-full"><img src="{e(m["url"])}" alt="{e(m["alt"])}" class="wp-image-{m["id"]}"/></figure>\n'
                     f'<!-- /wp:image -->')
    groupe = None
    lignes = []
    for m in ms:
        if m["groupe_nom"] != groupe:
            if lignes:
                blocs.append("<!-- wp:list -->\n<ul>" + "".join(lignes) + "</ul>\n<!-- /wp:list -->")
                lignes = []
            groupe = m["groupe_nom"]
            blocs.append(f"<!-- wp:heading {{\"level\":3}} -->\n<h3>{e(groupe.capitalize())}</h3>\n<!-- /wp:heading -->")
        if mode == "resultats":
            txt = f"<strong>{e(m['categorie'])}</strong> : {e(m['dom'])} {m['sd']} - {m['se']} {e(m['ext'])}"
        else:
            lieu = m["lieu"].lower() + (f" – {m['salle']}" if m.get("salle") else "")
            txt = (f"<strong>{e(m['categorie'])}</strong> : {e(m['jour'].capitalize())} à {e(m['heure'] or '?')}"
                   f" – {e(m['dom'])} vs {e(m['ext'])} ({e(lieu)})")
        lignes.append(f"<li>{txt}</li>")
    if lignes:
        blocs.append("<!-- wp:list -->\n<ul>" + "".join(lignes) + "</ul>\n<!-- /wp:list -->")
    return "\n\n".join(blocs), dates


COUVERTURE_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
__FONTS__
*{margin:0;padding:0;box-sizing:border-box}
body{width:1200px;height:675px}
#c{position:relative;width:1200px;height:675px;overflow:hidden;background:#061d4e center/cover no-repeat;font-family:Montserrat,sans-serif;color:#fff;
  display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#c:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(6,29,78,.55),rgba(6,29,78,.35) 45%,rgba(2,11,34,.8)),radial-gradient(55% 65% at 50% 50%,rgba(6,29,78,.55),transparent 80%)}
.in{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center}
img{width:150px;margin-bottom:18px;filter:drop-shadow(0 8px 18px rgba(0,0,0,.5))}
.t{font-family:Anton,Impact,sans-serif;font-size:150px;line-height:.95;letter-spacing:4px;text-transform:uppercase;text-shadow:0 10px 30px rgba(0,0,0,.45)}
.f{width:140px;height:5px;background:#fddc1d;margin:22px 0 18px;border-radius:3px}
.d{font-family:Anton,Impact,sans-serif;font-size:64px;letter-spacing:2px;color:#fddc1d}
</style></head><body><div id="c" style="background-image:url(__FOND__)"><div class="in">
<img src="__LOGO__"><div class="t">__TITRE__</div><div class="f"></div><div class="d">__DATES__</div></div></div></body></html>"""


def generer_couverture(res, mode):
    """Image mise en avant de l'article : « RÉSULTATS » (ou « PROGRAMME ») + dates du week-end, format 16:9."""
    import html as H
    a = charte_assets("bleu")
    # photo de fond : une des images du dossier charte/couvertures (change chaque semaine)
    dossier = os.path.join(CHARTE_DIR, "couvertures")
    photos = sorted(f for f in os.listdir(dossier) if f.lower().endswith((".jpg", ".jpeg", ".png"))) if os.path.isdir(dossier) else []
    if photos:
        import base64
        num = date.fromisoformat(res["du"]).isocalendar()[1] + (0 if mode == "resultats" else 1)
        f = photos[num % len(photos)]
        mime = "image/png" if f.lower().endswith(".png") else "image/jpeg"
        a["fond"] = f"data:{mime};base64," + base64.b64encode(open(os.path.join(dossier, f), "rb").read()).decode()
    dates = titre_dates(res["du"], res["au"], matchs_pour_visuel(res, mode))
    page_html = (COUVERTURE_HTML.replace("__FONTS__", polices_css()).replace("__FOND__", a["fond"])
                 .replace("__LOGO__", a["logo"]).replace("__TITRE__", "Résultats" if mode == "resultats" else "Programme")
                 .replace("__DATES__", H.escape(dates)))
    os.makedirs(VISUELS_DIR, exist_ok=True)
    chemin = os.path.join(VISUELS_DIR, f"couverture_{mode}_{res['du']}.png")
    from playwright.sync_api import sync_playwright
    with _visuel_lock, sync_playwright() as pw:
        b = launch_browser(pw)
        try:
            pg = b.new_page(viewport={"width": 1200, "height": 675})
            pg.set_content(page_html, wait_until="load")
            pg.wait_for_timeout(600)
            pg.locator("#c").screenshot(path=chemin)
        finally:
            b.close()
    return chemin


def wp_envoyer_image(wp, chemin, nom, alt, donnees=None, mime="image/png"):
    import uuid
    borne = "----FFHB" + uuid.uuid4().hex
    contenu = donnees if donnees is not None else open(chemin, "rb").read()
    corps = (f"--{borne}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nom}\"\r\n"
             f"Content-Type: {mime}\r\n\r\n").encode() + contenu + f"\r\n--{borne}--\r\n".encode()
    m = wp_requete(wp, "POST", "media", brut=corps, entetes={"Content-Type": f"multipart/form-data; boundary={borne}"})
    try:
        wp_requete(wp, "POST", f"media/{m['id']}", {"alt_text": alt})
    except WPErreur:
        pass
    return {"id": m["id"], "url": m.get("source_url", ""), "alt": alt}


def wp_publier(res, mode, theme=None):
    """Envoie les visuels et crée (ou met à jour) l'article du week-end. Renvoie le lien et le statut."""
    wp = wp_config()
    if not wp["utilisateur"] or not wp["mot_de_passe"]:
        raise WPErreur("renseigne l'identifiant et le mot de passe d'application dans Réglages.")
    chemins = generer_visuels(res, mode, theme=theme)
    if not chemins:
        raise WPErreur("aucun match à publier pour ce week-end.")
    etat = _etat_wp()
    cle = f"{mode}_{res['du']}"
    ancien = etat.get(cle)
    # 1) envoi des images dans la médiathèque
    medias = []
    for i, ch in enumerate(chemins, 1):
        nom = f"{mode}-{res['du']}-{i}.png"
        # envoi en « multipart/form-data » (comme un formulaire) : le pare-feu de l'hébergeur bloque l'envoi binaire brut
        import uuid
        borne = "----FFHB" + uuid.uuid4().hex
        corps = (f"--{borne}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nom}\"\r\n"
                 f"Content-Type: image/png\r\n\r\n").encode() + open(ch, "rb").read() + f"\r\n--{borne}--\r\n".encode()
        m = wp_requete(wp, "POST", "media", brut=corps,
                       entetes={"Content-Type": f"multipart/form-data; boundary={borne}"})
        alt = ("Résultats" if mode == "resultats" else "Programme") + f" du week-end – visuel {i}/{len(chemins)}"
        try:
            wp_requete(wp, "POST", f"media/{m['id']}", {"alt_text": alt})
        except WPErreur:
            pass
        medias.append({"id": m["id"], "url": m.get("source_url", ""), "alt": alt})
    # 2) article
    contenu, dates = contenu_article(res, mode, medias)
    titre = ("Résultats du week-end – " if mode == "resultats" else "Programme du week-end – ") + dates
    # image mise en avant dédiée : « RÉSULTATS / PROGRAMME » + dates (n'apparaît pas dans le corps de l'article)
    try:
        couv = wp_envoyer_image(wp, generer_couverture(res, mode), f"couverture-{mode}-{res['du']}.png",
                                ("Résultats" if mode == "resultats" else "Programme") + " du week-end – " + dates)
    except Exception:
        couv = medias[0]
    article = {"title": titre, "content": contenu, "featured_media": couv["id"]}
    cat = wp_categorie(wp)
    if cat:
        article["categories"] = [cat["id"]]
    post = None
    if not ancien:
        try:
            from urllib.parse import quote
            for p in wp_requete(wp, "GET", f"posts?search={quote(titre)}&status=draft,publish,pending&context=edit&per_page=10") or []:
                if html_texte((p.get("title") or {}).get("raw") or (p.get("title") or {}).get("rendered", "")).strip() == titre:
                    ancien = {"id": p["id"], "medias": []}
                    break
        except WPErreur:
            pass
    if ancien:  # déjà publié pour ce week-end : mise à jour de l'article existant
        try:
            post = wp_requete(wp, "POST", f"posts/{ancien['id']}", article)
        except WPErreur:
            post = None
        if post:  # on retire les anciennes images de la médiathèque
            for mid in ancien.get("medias", []):
                try:
                    wp_requete(wp, "DELETE", f"media/{mid}?force=true")
                except WPErreur:
                    pass
    if not post:
        post = wp_requete(wp, "POST", "posts", dict(article, status=wp["statut"] if wp["statut"] in ("draft", "publish") else "draft"))
    etat[cle] = {"id": post["id"], "medias": list({m["id"] for m in medias + [couv]}), "t": time.time()}
    with open(WP_ETAT_FILE, "w", encoding="utf-8") as f:
        json.dump(etat, f)
    return {"lien": post.get("link"), "statut": post.get("status"), "titre": titre, "mise_a_jour": bool(ancien),
            "edition": wp["site"].rstrip("/") + f"/wp-admin/post.php?post={post['id']}&action=edit",
            "categorie": cat["name"] if cat else None, "images": len(medias)}



# ==========================================================================
# Rédaction d'articles : texte brut + photos -> texte retravaillé par Claude -> brouillon WordPress
# ==========================================================================
CLAUDE_API = "https://api.anthropic.com/v1/"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/"
MOTEURS_IA = {"gemini": "Google Gemini (gratuit)", "claude": "Claude (payant)"}
TYPES_ARTICLE = {"match": "Matchs : compte rendu ou annonce d'un match (équipes seniors)",
                 "jeunes": "Équipes jeunes : matchs, tournois, stages ou école de handball des jeunes",
                 "club": "Vie du club : événements, bénévoles, assemblée, animations, vie associative",
                 "partenaire": "Partenaires : article sur un partenaire du club ou un partenariat"}


class IAErreur(Exception):
    pass


ClaudeErreur = IAErreur  # ancien nom


def ia_config():
    """{"moteur": "gemini"|"claude", "cles": {...}, "modeles": {...}} (+ clés en variables d'environnement)."""
    cfg = load_config()
    ia = json.loads(json.dumps(cfg.get("ia") or {}))
    ia.setdefault("moteur", "gemini")
    ia.setdefault("cles", {})
    ia.setdefault("modeles", {})
    ancien = cfg.get("claude") or {}          # réglage de la version précédente
    if ancien.get("cle") and not ia["cles"].get("claude"):
        ia["cles"]["claude"] = ancien["cle"]
    for m, var in (("gemini", "FFHB_GEMINI_KEY"), ("claude", "FFHB_CLAUDE_KEY")):
        if os.environ.get(var, "").strip():
            ia["cles"][m] = os.environ[var].strip()
    if os.environ.get("FFHB_IA_MOTEUR", "").strip():
        ia["moteur"] = os.environ["FFHB_IA_MOTEUR"].strip()
    for m in ("gemini", "claude"):
        if os.environ.get(f"FFHB_IA_MODELE_{m.upper()}", "").strip():
            ia["modeles"][m] = os.environ[f"FFHB_IA_MODELE_{m.upper()}"].strip()
    if ia["moteur"] not in MOTEURS_IA:
        ia["moteur"] = "gemini"
    return ia


def _http_json(url, methode="GET", donnees=None, entetes=None, timeout=120):
    import urllib.error
    import urllib.request
    h = {"content-type": "application/json"}
    h.update(entetes or {})
    corps = json.dumps(donnees).encode("utf-8") if donnees is not None else None
    req = urllib.request.Request(url, data=corps, headers=h, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=contexte_ssl()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error") or {}
        except Exception:
            err = {}
        raise _ErreurHTTP(e.code, err.get("message", "") if isinstance(err, dict) else str(err),
                          err.get("status", "") if isinstance(err, dict) else "")
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
            raise IAErreur("certificats de sécurité de Python manquants (même solution que pour WordPress, voir LISEZMOI).")
        raise IAErreur(f"service d'IA injoignable ({e.reason}). Vérifie ta connexion.")


class _ErreurHTTP(Exception):
    def __init__(self, code, msg, statut=""):
        super().__init__(msg)
        self.code, self.msg, self.statut = code, msg, statut


def _cle_ia(moteur, cle=None):
    cle = cle or ia_config()["cles"].get(moteur, "") or os.environ.get(f"FFHB_{moteur.upper()}_KEY", "")
    if not cle:
        raise IAErreur(f"renseigne la clé API {MOTEURS_IA[moteur].split(' (')[0]} dans Réglages (section « Rédaction d'articles »).")
    return cle


# ---------- Google Gemini ----------
def _gemini(methode, chemin, donnees=None, cle=None, timeout=120):
    try:
        return _http_json(GEMINI_API + chemin, methode, donnees, {"x-goog-api-key": _cle_ia("gemini", cle)}, timeout)
    except _ErreurHTTP as e:
        m = (e.msg or "").lower()
        if e.code in (400, 401, 403) and ("api key" in m or "api_key" in m or "permission" in m or e.code != 400):
            raise IAErreur("clé API Gemini refusée : vérifie-la dans Réglages (aistudio.google.com > Get API key).")
        if e.code == 429:
            raise IAErreur("limite gratuite de Gemini atteinte pour le moment : réessaie dans une minute (ou demain si c'est la limite du jour).")
        if e.code in (500, 503):
            raise IAErreur("Gemini est surchargé : réessaie dans quelques minutes.")
        if e.code == 404:
            raise IAErreur("modèle Gemini introuvable : laisse le champ « Modèle » vide dans Réglages.")
        raise IAErreur(f"Gemini : erreur {e.code}" + (f" : {e.msg}" if e.msg else ""))


def gemini_modele(cle=None):
    choisi = ia_config()["modeles"].get("gemini")
    if choisi:
        return choisi
    noms = []
    page = ""
    for _ in range(5):
        r = _gemini("GET", "models?pageSize=200" + (f"&pageToken={page}" if page else ""), cle=cle) or {}
        for m in r.get("models") or []:
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                noms.append(m.get("name", "").replace("models/", ""))
        page = r.get("nextPageToken")
        if not page:
            break
    if "gemini-flash-latest" in noms:
        return "gemini-flash-latest"
    exclus = ("lite", "preview", "exp", "tts", "image", "audio", "live", "thinking", "8b", "embedding", "native")
    def version(n):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(v.group(1)) if v else 0
    flash = sorted((n for n in noms if "flash" in n and not any(x in n for x in exclus)), key=version, reverse=True)
    if flash:
        return flash[0]
    if noms:
        return noms[0]
    raise IAErreur("aucun modèle Gemini disponible avec cette clé.")


def _b64_image(d):
    """data URL ou base64 -> (type, base64)."""
    if d.startswith("data:"):
        entete, b = d.split(",", 1)
        return entete[5:].split(";")[0] or "image/jpeg", b
    return "image/jpeg", d


def gemini_generer(systeme, texte, images=()):
    modele = gemini_modele()
    parts = [{"inline_data": {"mime_type": t, "data": b}} for t, b in map(_b64_image, images)] + [{"text": texte}]
    r = _gemini("POST", f"models/{modele}:generateContent", {
        "systemInstruction": {"parts": [{"text": systeme}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}}, timeout=180)
    cands = r.get("candidates") or []
    if not cands:
        raise IAErreur("Gemini n'a pas répondu (texte bloqué par ses filtres ?). Reformule un peu et réessaie.")
    return "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts") or []), modele


# ---------- Claude ----------
def _claude(methode, chemin, donnees=None, cle=None, timeout=120):
    try:
        return _http_json(CLAUDE_API + chemin, methode, donnees,
                          {"x-api-key": _cle_ia("claude", cle), "anthropic-version": "2023-06-01"}, timeout)
    except _ErreurHTTP as e:
        m = (e.msg or "").lower()
        if e.code == 401:
            raise IAErreur("clé API Claude refusée : vérifie-la dans Réglages.")
        if e.code == 402 or "credit" in m or "billing" in m:
            raise IAErreur("plus de crédit sur le compte Claude : recharge-le sur console.anthropic.com (Billing).")
        if e.code == 429:
            raise IAErreur("trop de demandes d'un coup : réessaie dans une minute.")
        if e.code in (500, 529):
            raise IAErreur("le service Claude est surchargé : réessaie dans quelques minutes.")
        raise IAErreur(f"Claude : erreur {e.code}" + (f" : {e.msg}" if e.msg else ""))


def claude_modele(cle=None):
    choisi = ia_config()["modeles"].get("claude")
    if choisi:
        return choisi
    liste = (_claude("GET", "models?limit=100", cle=cle) or {}).get("data") or []
    liste.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    for m in liste:
        if "sonnet" in m.get("id", ""):
            return m["id"]
    if liste:
        return liste[0]["id"]
    raise IAErreur("aucun modèle disponible sur ce compte Claude.")


def claude_generer(systeme, texte, images=()):
    modele = claude_modele()
    contenu = [{"type": "image", "source": {"type": "base64", "media_type": t, "data": b}} for t, b in map(_b64_image, images)]
    contenu.append({"type": "text", "text": texte})
    r = _claude("POST", "messages", {"model": modele, "max_tokens": 4000, "system": systeme,
                                     "messages": [{"role": "user", "content": contenu}]}, timeout=180)
    return "".join(b.get("text", "") for b in r.get("content") or [] if b.get("type") == "text"), modele


def ia_tester():
    ia = ia_config()
    modele = gemini_modele() if ia["moteur"] == "gemini" else claude_modele()
    return {"moteur": MOTEURS_IA[ia["moteur"]], "modele": modele}


CONSIGNES_ARTICLE = """Tu es le rédacteur du site internet de Caluire-Rillieux Handball (club de handball de la métropole de Lyon :
équipe fanion en Nationale 1 masculine, N3 masculine, N3 féminine, et de nombreuses équipes jeunes).
On te donne un texte brut écrit rapidement (notes, phrases en vrac, fautes). Tu le transformes en article prêt à publier.

Règles :
- Corrige l'orthographe, la grammaire et la ponctuation ; écris en français correct et fluide.
- Ton dynamique et chaleureux : vivant, fier de nos joueurs et joueuses, proche des supporters, sans excès ni clichés à répétition.
- Structure : un chapeau accrocheur (1 à 2 phrases), puis 2 à 6 paragraphes courts ; ajoute 1 ou 2 intertitres seulement si l'article est long.
- Enrichis la forme (transitions, mise en contexte, conclusion qui donne rendez-vous ou remercie), MAIS n'invente JAMAIS de fait :
  aucun score, nom, chiffre, date, lieu, citation ou détail qui ne figure pas dans le texte fourni.
- Garde toutes les informations du texte d'origine (noms, scores, dates, horaires, lieux, remerciements).
- Écris les noms propres tels qu'ils sont donnés ; « Caluire-Rillieux Handball » ou « le CRHB » pour le club.
- Pas d'emojis, pas de hashtags, pas de signature.
- Des photos peuvent être jointes : lis attentivement TOUT texte visible (affiche, flyer, tableau d'affichage du score,
  feuille de match, programme, banderole) et utilise ces informations dans l'article : elles comptent comme des faits fournis.
  Ne décris pas l'apparence des personnes et n'identifie personne d'après son visage. Si une information lue sur une image
  contredit le texte, garde celle du texte et signale-le dans « remarques ».
- Le texte brut peut être très court (ou vide) si l'essentiel est sur les images.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour :
{"titre": "titre court et accrocheur (70 caractères max)",
 "extrait": "résumé de 1 à 2 phrases pour l'aperçu de l'article",
 "blocs": [{"type": "chapeau", "texte": "..."}, {"type": "intertitre", "texte": "..."}, {"type": "paragraphe", "texte": "..."}],
 "visuel": {"titre": "accroche très courte pour l'image de couverture (35 caractères max)",
            "sous_titre": "l'info clé en quelques mots : score, date, horaire ou lieu (45 caractères max), sinon chaîne vide"},
 "remarques": "ce que tu n'as pas pu vérifier ou qui semble manquer (ex. score absent), sinon chaîne vide"}"""


def rediger_article(texte, type_article="match", images=()):
    texte = (texte or "").strip()
    images = [i for i in images if i][:6]
    if len(texte) < 15 and not images:
        raise IAErreur("le texte est trop court : écris au moins quelques phrases (ou ajoute une image avec les infos).")
    demande = (f"Type d'article : {TYPES_ARTICLE.get(type_article, TYPES_ARTICLE['match'])}\n"
               f"Photos jointes : {len(images)}\n\n"
               f"Texte brut :\n<<<\n{texte or '(pas de texte : utilise les informations lisibles sur les images)'}\n>>>")
    moteur = ia_config()["moteur"]
    brut, modele = (gemini_generer if moteur == "gemini" else claude_generer)(CONSIGNES_ARTICLE, demande, images)
    try:
        art = json.loads(brut[brut.index("{"):brut.rindex("}") + 1])
    except Exception:
        raise IAErreur("réponse de l'IA illisible, réessaie.")
    if not art.get("titre") or not art.get("blocs"):
        raise IAErreur("réponse de l'IA incomplète, réessaie.")
    art["modele"] = modele
    return art


def html_article(art, medias):
    """Contenu WordPress (blocs Gutenberg) : texte puis galerie de toutes les photos."""
    import html as H
    out = []
    for b in art.get("blocs") or []:
        t = H.escape((b.get("texte") or "").strip())
        if not t:
            continue
        if b.get("type") == "intertitre":
            out.append(f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{t}</h2>\n<!-- /wp:heading -->')
        elif b.get("type") == "chapeau":
            out.append(f'<!-- wp:paragraph -->\n<p><strong>{t}</strong></p>\n<!-- /wp:paragraph -->')
        else:
            out.append(f'<!-- wp:paragraph -->\n<p>{t}</p>\n<!-- /wp:paragraph -->')
    galerie = medias
    if len(galerie) == 1:
        m = galerie[0]
        out.append(f'<!-- wp:image {{"id":{m["id"]},"sizeSlug":"large","linkDestination":"media"}} -->\n'
                   f'<figure class="wp-block-image size-large"><a href="{m["url"]}"><img src="{m["url"]}" alt="{H.escape(m["alt"])}" '
                   f'class="wp-image-{m["id"]}"/></a></figure>\n<!-- /wp:image -->')
    elif galerie:
        imgs = "\n".join(
            f'<!-- wp:image {{"id":{m["id"]},"sizeSlug":"large","linkDestination":"media"}} -->\n'
            f'<figure class="wp-block-image size-large"><a href="{m["url"]}"><img src="{m["url"]}" alt="{H.escape(m["alt"])}" '
            f'class="wp-image-{m["id"]}"/></a></figure>\n<!-- /wp:image -->' for m in galerie)
        out.append('<!-- wp:gallery {"linkTo":"media"} -->\n<figure class="wp-block-gallery has-nested-images columns-default is-cropped">\n'
                   + imgs + '\n</figure>\n<!-- /wp:gallery -->')
    return "\n\n".join(out)


COUVERTURE_ARTICLE_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
__FONTS__
*{margin:0;padding:0;box-sizing:border-box}
body{width:1200px;height:675px;background:#061d4e}
#c{position:relative;width:1200px;height:675px;overflow:hidden;background:#061d4e;font-family:Montserrat,sans-serif;color:#fff}
.l{position:absolute;inset:0}
#flou{background-size:cover;background-position:center;filter:blur(28px) saturate(1.1);transform:scale(1.15)}
#plein{background-size:cover;background-position:center 30%}
#cadre{position:absolute;right:46px;top:46px;bottom:46px;width:540px;display:flex;align-items:center;justify-content:center}
#cadre img{max-width:100%;max-height:100%;object-fit:contain;border-radius:10px;box-shadow:0 18px 40px rgba(0,0,0,.55);border:4px solid #fff}
.voile-g{background:linear-gradient(90deg,rgba(6,29,78,.96) 0%,rgba(6,29,78,.88) 38%,rgba(6,29,78,.35) 62%,rgba(6,29,78,0) 80%)}
.voile-b{background:linear-gradient(180deg,rgba(2,11,34,.15),rgba(2,11,34,.55))}
.txt{position:absolute;left:60px;top:0;bottom:0;width:560px;display:flex;flex-direction:column;justify-content:center}
.txt img{width:96px;margin-bottom:22px;filter:drop-shadow(0 6px 14px rgba(0,0,0,.45))}
#t{font-family:Anton,Impact,sans-serif;font-size:76px;line-height:1.08;letter-spacing:1.5px;text-transform:uppercase;text-shadow:0 6px 22px rgba(0,0,0,.4);max-height:260px;padding-top:4px;overflow:hidden;flex-shrink:0}
.barre{width:120px;height:6px;background:#fddc1d;border-radius:3px;margin:22px 0 18px}
#s{font-weight:800;font-size:30px;line-height:1.15;color:#fddc1d;text-transform:uppercase;letter-spacing:1px}
</style></head><body><div id="c">
 <div class="l" id="flou"></div><div class="l" id="plein"></div><div id="cadre"></div>
 <div class="l voile-b"></div><div class="l voile-g"></div>
 <div class="txt"><img src="__LOGO__"><div id="t"></div><div class="barre"></div><div id="s"></div></div>
</div><script>
const D=__DATA__, $=i=>document.getElementById(i);
$("t").textContent=D.titre; $("s").textContent=D.sous_titre||""; if(!D.sous_titre)document.querySelector(".barre").style.marginBottom="0";
const fin=()=>{let f=76;const t=$("t");while(t.scrollHeight>250&&f>36){f-=3;t.style.fontSize=f+"px"}
 let g=30;const s=$("s");while(s.scrollHeight>80&&g>18){g-=2;s.style.fontSize=g+"px"}document.body.dataset.pret="1"};
if(!D.photo){$("flou").style.background="url("+D.fond+") center/cover";$("flou").style.filter="none";$("flou").style.transform="none";
 document.fonts.ready.then(fin)}
else{const im=new Image();im.onload=()=>{const r=im.width/im.height;
  if(r>=1.25){$("plein").style.backgroundImage="url("+D.photo+")"}            // photo paysage : plein cadre
  else{$("flou").style.backgroundImage="url("+D.photo+")";$("cadre").appendChild(im)} // portrait / carré / affiche : entière, sur fond flouté
  document.fonts.ready.then(fin)};im.onerror=()=>document.fonts.ready.then(fin);im.src=D.photo}
</script></body></html>"""


def generer_couverture_article(art, photo=None):
    """Image à la une 1200 × 675 (format du site) : photo choisie + accroche + info clé."""
    v = art.get("visuel") or {}
    data = {"titre": (v.get("titre") or art["titre"]).strip(), "sous_titre": (v.get("sous_titre") or "").strip(),
            "photo": photo or "", "fond": charte_assets("bleu")["fond"]}
    page_html = (COUVERTURE_ARTICLE_HTML.replace("__FONTS__", polices_css()).replace("__LOGO__", charte_assets("bleu")["logo"])
                 .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    os.makedirs(VISUELS_DIR, exist_ok=True)
    chemin = os.path.join(VISUELS_DIR, f"article_{slug(art['titre'])[:40] or 'article'}_{datetime.now():%Y%m%d_%H%M%S}.png")
    from playwright.sync_api import sync_playwright
    with _visuel_lock, sync_playwright() as pw:
        b = launch_browser(pw)
        try:
            pg = b.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=1)
            pg.set_content(page_html, wait_until="load")
            pg.wait_for_selector("body[data-pret='1']", state="attached", timeout=30000)
            pg.locator("#c").screenshot(path=chemin, type="png")   # PNG : le site affiche les .png en entier (les .jpg sont recadrés)
        finally:
            b.close()
    return chemin


def creer_article(texte, type_article="match", categorie_id=None, photos=(), couverture=True):
    """Rédige (en lisant aussi le texte des images), crée le visuel de couverture au bon format,
    envoie les photos et crée un BROUILLON WordPress. photos = [{"nom", "data" (2000 px), "ia" (réduite)}]."""
    import base64
    wp = wp_config()
    if not wp["utilisateur"] or not wp["mot_de_passe"]:
        raise WPErreur("renseigne l'identifiant et le mot de passe d'application WordPress dans Réglages.")
    photos = list(photos or [])
    art = rediger_article(texte, type_article, [p.get("ia") or p.get("data") for p in photos])
    medias = []
    base = slug(art["titre"])[:40] or "article"
    for i, ph in enumerate(photos, 1):
        donnees = base64.b64decode(ph["data"].split(",", 1)[-1])
        alt = art["titre"] + (f" – photo {i}" if len(photos) > 1 else "")
        medias.append(wp_envoyer_image(wp, None, f"{base}-{i}.jpg", alt, donnees=donnees, mime="image/jpeg"))
    couv, couv_fichier = None, None
    if couverture:
        ch = generer_couverture_article(art, photos[0]["data"] if photos else None)
        couv_fichier = os.path.basename(ch)
        couv = wp_envoyer_image(wp, ch, f"{base}-couverture.png", art["titre"], mime="image/png")
    article = {"title": art["titre"], "excerpt": art.get("extrait", ""), "content": html_article(art, medias), "status": "draft"}
    if couv or medias:
        article["featured_media"] = (couv or medias[0])["id"]
    cat = categorie_actualites(wp, type_article)
    if cat:
        article["categories"] = [cat]
    post = wp_requete(wp, "POST", "posts", article)
    return {"titre": art["titre"], "extrait": art.get("extrait", ""), "blocs": art["blocs"], "remarques": art.get("remarques", ""),
            "visuel": art.get("visuel") or {}, "couverture": couv_fichier,
            "modele": art["modele"], "images": len(medias), "statut": post.get("status"),
            "edition": wp["site"].rstrip("/") + f"/wp-admin/post.php?post={post['id']}&action=edit",
            "apercu": post.get("link"), "id": post["id"]}


# catégories affichées sur la page Actualités du site : le type d'article choisit la bonne
CATEGORIE_PAR_TYPE = {"match": "Matchs", "jeunes": "Équipes jeunes", "club": "Vie du club", "partenaire": "Partenaires"}


def categorie_actualites(wp, type_article):
    voulu = CATEGORIE_PAR_TYPE.get(type_article, "Matchs")
    try:
        cats = wp_requete(wp, "GET", "categories?per_page=100&hide_empty=false") or []
    except WPErreur:
        return None
    for nom in (voulu, "Matchs"):
        for c in cats:
            if norm(html_texte(c.get("name", ""))) == norm(nom):
                return c["id"]
    return None


def visible_actualites(post_id):
    """L'article apparaît-il sur la page Actualités du site ? (None si la page est illisible)"""
    import urllib.request
    wp = wp_config()
    url = wp["site"].rstrip("/") + "/" + (wp.get("page_actualites") or "actualites").strip("/") + f"/?v={int(time.time())}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=30, context=contexte_ssl()) as r:
            return f"post-{post_id}" in r.read().decode("utf-8", "ignore")
    except Exception:
        return None


def publier_article(post_id):
    wp = wp_config()
    post = wp_requete(wp, "POST", f"posts/{int(post_id)}", {"status": "publish"})
    return {"lien": post.get("link"), "statut": post.get("status"), "visible": visible_actualites(post["id"]),
            "page_actualites": wp["site"].rstrip("/") + "/" + (wp.get("page_actualites") or "actualites").strip("/") + "/"}


def wp_categories():
    wp = wp_config()
    if not wp["utilisateur"] or not wp["mot_de_passe"]:
        return []
    return [{"id": c["id"], "nom": html_texte(c.get("name", ""))}
            for c in wp_requete(wp, "GET", "categories?per_page=100&hide_empty=false") or []]

# ==========================================================================
# Page web locale
# ==========================================================================
PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Outil CRHB</title>
<link rel="icon" href="/logo.png"><link rel="apple-touch-icon" href="/logo.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="CRHB"><meta name="theme-color" content="#061d4e">
<style>
:root{--bg:#f3f5f9;--card:#fff;--ink:#141a26;--muted:#667085;--line:#e2e6ee;--accent:#0b4fa8;--accent2:#061d4e;--jaune:#fddc1d;--on:#fff;
 --win:#137a3f;--loss:#b42318;--draw:#8a6100;--hl:#edf3ff;--soft:#f0f3f8;--nav:#061d4e;--navink:#c9d4ec;--navon:#fddc1d;--shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08)}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b23;--ink:#e6e9ef;--muted:#98a2b3;--line:#2a313c;--accent:#6aa6ff;--on:#0d1117;
 --win:#4cc27a;--loss:#ff7a6b;--draw:#e0b545;--hl:#18233a;--soft:#1c222c;--nav:#050d22;--shadow:none}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
h1{font-size:20px;margin:0;line-height:1.2}h2{font-size:17px;margin:0}
h3{font-size:12px;margin:16px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
/* ---- mise en page : menu à gauche (ordinateur), barre en haut (téléphone) ---- */
.app{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}
.app>div{min-width:0}
nav.side{background:var(--nav);color:var(--navink);position:sticky;top:0;height:100vh;overflow-y:auto;padding:18px 12px 24px;display:flex;flex-direction:column;gap:2px}
.brand{display:flex;align-items:center;gap:10px;padding:0 8px 16px;color:#fff;text-decoration:none}
.brand img{width:44px;height:44px;object-fit:contain}.brand b{display:block;font-size:15px;line-height:1.15}.brand small{color:var(--navink);font-size:12px}
.grp{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#8193bd;margin:14px 10px 4px}
.nv{display:flex;align-items:center;justify-content:flex-start;gap:10px;width:100%;text-align:left;background:transparent;color:var(--navink);border:0;border-radius:9px;padding:9px 10px;font:500 14px system-ui;cursor:pointer}
.nv:hover{background:rgba(255,255,255,.07);color:#fff}
.nv.on{background:rgba(253,220,29,.14);color:var(--navon);font-weight:700}
.nv .ic{width:20px;text-align:center;flex-shrink:0;font-size:15px}
.nv .bz{margin-left:auto;width:8px;height:8px;border-radius:50%;background:var(--navon);display:none;animation:pulse 1.2s ease-in-out infinite}
.nv.busy .bz{display:block}
@keyframes pulse{50%{opacity:.25}}
.side .bas{margin-top:auto;padding:16px 10px 0;font-size:12px;color:#8193bd}
main{padding:22px 28px 64px;max-width:1180px;width:100%}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.top .titre h1{display:flex;align-items:center;gap:8px}
.etat{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.etat .pt{width:8px;height:8px;border-radius:50%;background:var(--win)}.etat .pt.maj{background:var(--draw);animation:pulse 1.2s infinite}
.we{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.we b{font-size:15px;min-width:200px;text-align:center}
.mobnav{display:none}
@media(max-width:900px){
 .app{grid-template-columns:minmax(0,1fr)}
 nav.side{display:none}
 .mobnav{display:block;position:sticky;top:0;z-index:20;background:var(--nav);padding:8px 10px calc(8px);box-shadow:0 2px 8px rgba(0,0,0,.2)}
 .mobnav .l1{display:flex;align-items:center;gap:8px;color:#fff;margin-bottom:6px}.mobnav .l1 img{width:30px;height:30px}.mobnav .l1 b{font-size:15px}
 .mobnav .l1 button{margin-left:auto}
 .chips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;padding-bottom:2px}.chips::-webkit-scrollbar{display:none}
 .chips .nv{width:auto;white-space:nowrap;padding:7px 11px;font-size:13px;background:rgba(255,255,255,.06)}
 .chips .nv .ic{width:auto}
 main{padding:14px 12px 56px}
 .we b{min-width:0;flex:1;font-size:14px}.we{width:100%}
 .top{margin-bottom:12px}
 #refresh{display:none}
}
/* ---- éléments ---- */
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px;box-shadow:var(--shadow)}
.card.soft{background:var(--soft);box-shadow:none}
.head{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
button,.btn{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:9px 14px;font:600 14px system-ui;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px;justify-content:center}
@media (prefers-color-scheme:dark){button,.btn{color:#0d1117}}
button.g,.btn.g{background:transparent;color:var(--accent);border:1px solid var(--line)}
button.mini{padding:4px 10px;font-size:13px}
button:disabled{opacity:.5;cursor:wait}
.nv{color:var(--navink)}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--card)}
.seg button{border-radius:0;background:transparent;color:var(--ink);font-weight:500}.seg button.on{background:var(--accent);color:#fff}
@media (prefers-color-scheme:dark){.seg button.on{color:#0d1117}}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}
th{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
td.sc{text-align:center;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums}tr.me td{background:var(--hl)}
.V{color:var(--win)}.D{color:var(--loss)}.N{color:var(--draw)}
.muted{color:var(--muted)}.err{color:var(--loss)}.small{font-size:13px}.ok{color:var(--win)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.hero{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;padding:14px;border-radius:10px;background:var(--soft);margin-top:10px}
.hero .t{font-weight:600;font-size:15px}.hero .t.r{text-align:right}.hero .me{font-weight:800}
.hero .s{font-size:32px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:center}
.hero .d{grid-column:1/-1;text-align:center;color:var(--muted);font-size:13px}
@media(max-width:560px){.hero{grid-template-columns:1fr;gap:4px}.hero .t.r,.hero .t{text-align:center}.hero .s{font-size:26px}}
pre{white-space:pre-wrap;background:var(--soft);border-radius:8px;padding:12px;font:15px/1.55 system-ui;margin:12px 0 0}
input,textarea,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--ink);font:inherit}
input[type=file]{padding:6px}input[type=checkbox]{width:auto}
.row{display:grid;grid-template-columns:140px 1fr auto;gap:6px 8px;margin-bottom:14px}
@media(max-width:640px){.row{grid-template-columns:1fr}}
.loader{display:flex;gap:10px;align-items:center;color:var(--muted)}
.spin{width:18px;height:18px;border:3px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:s 1s linear infinite;flex-shrink:0}
.spin.p{display:inline-block;vertical-align:middle;width:14px;height:14px;border-width:2px;margin-right:4px}
@keyframes s{to{transform:rotate(360deg)}}
details summary{cursor:pointer;color:var(--muted);font-size:13px;margin-top:10px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;align-items:start}
.gridv{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.img{width:100%;border-radius:10px;border:1px solid var(--line);display:block;background:var(--soft)}
.pills{display:flex;gap:6px;flex-wrap:wrap}.pill{font-size:12px;padding:2px 9px;border-radius:99px;background:var(--soft);color:var(--muted)}
.pill.r{background:#fde8e6;color:#b42318}.pill.v{background:#e5f5ec;color:#137a3f}.pill.o{background:#fff4d6;color:#8a6100}
@media (prefers-color-scheme:dark){.pill.r{background:#3a1d1a;color:#ff9c90}.pill.v{background:#16301f;color:#6fd59a}.pill.o{background:#33290f;color:#e9c46a}}
.sw{position:relative;display:inline-flex;align-items:center;gap:10px;cursor:pointer;user-select:none}
.sw input{position:absolute;opacity:0;width:0;height:0}
.sw i{width:46px;height:26px;border-radius:99px;background:var(--line);position:relative;transition:.2s;flex-shrink:0}
.sw i:after{content:"";position:absolute;left:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.3);transition:.2s}
.sw input:checked+i{background:var(--win)}.sw input:checked+i:after{left:23px}
.sw input:disabled+i{opacity:.5}
.autol{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 0;border-bottom:1px solid var(--line)}
.autol:last-child{border-bottom:0}
.vue{display:none}.vue.on{display:block;animation:fade .15s ease}
@keyframes fade{from{opacity:.4}to{opacity:1}}
.toast{position:fixed;right:16px;bottom:16px;z-index:50;display:flex;flex-direction:column;gap:8px;max-width:min(380px,calc(100vw - 32px))}
.toast div{background:var(--accent2);color:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 8px 24px rgba(0,0,0,.25);font-size:14px;cursor:pointer;animation:fade .2s}
.toast div b{color:var(--jaune)}
.guide h2{margin-top:4px}.guide p,.guide li{max-width:780px}.guide li{margin:4px 0}
.guide .etape{display:grid;grid-template-columns:34px 1fr;gap:10px;margin:12px 0}
.guide .etape i{font-style:normal;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700}
.kbd{font:600 12px system-ui;padding:1px 7px;border-radius:6px;border:1px solid var(--line);background:var(--soft)}
.tuiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:10px}
.tuile{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--card);cursor:pointer;text-align:left;color:var(--ink);font:inherit;display:block}
.tuile:hover{border-color:var(--accent)}.tuile b{display:block;margin-bottom:2px}.tuile span{font-size:13px;color:var(--muted)}
@media (prefers-color-scheme:dark){.tuile{color:var(--ink)}}
</style></head><body>
<div class="app">
<nav class="side" id="side">
 <a class="brand" href="#" data-go="accueil"><img src="/logo.png" alt=""><div><b>Caluire-Rillieux HB</b><small>Outil résultats &amp; com'</small></div></a>
 <button class="nv" data-v="accueil"><span class="ic">⌂</span>Accueil<span class="bz"></span></button>
 <div class="grp">Résultats</div>
 <button class="nv" data-v="club"><span class="ic">★</span>Matchs du club<span class="bz"></span></button>
 <button class="nv" data-v="all"><span class="ic">≡</span>Tous les matchs<span class="bz"></span></button>
 <div class="grp">Réseaux sociaux</div>
 <button class="nv" data-v="visuel"><span class="ic">▣</span>Visuels programme / résultats<span class="bz"></span></button>
 <button class="nv" data-v="post"><span class="ic">✎</span>Texte réseaux<span class="bz"></span></button>
 <button class="nv" data-v="affiche"><span class="ic">◆</span>Affiche prochain match<span class="bz"></span></button>
 <button class="nv" data-v="ecran"><span class="ic">▶</span>Écran géant<span class="bz"></span></button>
 <div class="grp">Site du club</div>
 <button class="nv" data-v="article"><span class="ic">✦</span>Écrire un article<span class="bz"></span></button>
 <button class="nv" data-v="articles"><span class="ic">☰</span>Articles du site<span class="bz"></span></button>
 <button class="nv" data-v="auto"><span class="ic">⏱</span>Publication auto<span class="bz"></span></button>
 <div class="grp">Outils</div>
 <button class="nv" data-v="cfg"><span class="ic">⚙</span>Réglages<span class="bz"></span></button>
 <button class="nv" data-v="mobile"><span class="ic">▯</span>Sur téléphone<span class="bz"></span></button>
 <button class="nv" data-v="aide"><span class="ic">?</span>Mode d'emploi<span class="bz"></span></button>
 <div class="bas" id="sidemeta"></div>
</nav>
<div>
<div class="mobnav"><div class="l1"><img src="/logo.png" alt=""><b>Outil CRHB</b><button class="g mini" id="mrefresh" style="color:#fff;border-color:rgba(255,255,255,.3)">Actualiser</button></div>
 <div class="chips" id="chips"></div></div>
<main>
 <div class="top"><div class="titre"><h1 id="vtitre">Accueil</h1><div class="etat" id="etat"><span class="pt"></span><span>Chargement…</span></div></div>
  <div class="bar" style="margin:0"><div class="we" id="webar"><button class="g mini" id="prev" title="Week-end précédent">◀</button><b id="wlabel">…</b><button class="g mini" id="next" title="Week-end suivant">▶</button><button class="g mini" id="avenir">À venir</button><button class="g mini" id="dernier">Dernier</button></div>
  <button class="g" id="refresh" title="Relire toutes les pages FFHB">↻ Actualiser</button></div></div>
 <section class="vue" id="v-accueil"></section>
 <section class="vue" id="v-club"></section>
 <section class="vue" id="v-all"></section>
 <section class="vue" id="v-visuel"></section>
 <section class="vue" id="v-post"></section>
 <section class="vue" id="v-affiche"></section>
 <section class="vue" id="v-ecran"></section>
 <section class="vue" id="v-article"></section>
 <section class="vue" id="v-articles"></section>
 <section class="vue" id="v-auto"></section>
 <section class="vue" id="v-cfg"></section>
 <section class="vue" id="v-mobile"></section>
 <section class="vue" id="v-aide"></section>
</main></div></div>
<div class="toast" id="toast"></div>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sec=v=>document.getElementById("v-"+v);
const LS={get:(k,d)=>{try{return localStorage.getItem(k)??d}catch(e){return d}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}}};
const TITRES={accueil:"Accueil",club:"Matchs du club",all:"Tous les matchs du week-end",visuel:"Visuels programme / résultats",post:"Texte pour les réseaux",
 affiche:"Affiche du prochain match",ecran:"Écran géant",article:"Écrire un article",articles:"Articles du site",auto:"Publication automatique",cfg:"Réglages",aide:"Mode d'emploi",mobile:"Ouvrir sur le téléphone"};
const VUES_WE=["club","all","visuel","post","accueil"];          // vues qui dépendent du week-end choisi
let offset=0,data=null,dataV=0,view="accueil",cfg=null,vmode=null,charge=null;
const rendu={},init={};
const spin='<span class="spin p"></span>';
const fmt=(iso,h)=>{if(!iso)return"";const d=new Date(iso+"T12:00");return d.toLocaleDateString("fr-FR",{weekday:"short",day:"2-digit",month:"2-digit"})+(h?" "+h.replace(":","h"):"")};
const dd=iso=>new Date(iso+"T12:00").toLocaleDateString("fr-FR",{day:"numeric",month:"long"});
const jourLong=iso=>new Date(iso+"T12:00").toLocaleDateString("fr-FR",{weekday:"long",day:"numeric",month:"long"});
const norm=s=>String(s||"").normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();
const keys=()=>(data?.club||"").split(/[,;]/).map(s=>norm(s.trim())).filter(Boolean);
function res(m,K){if(m.sd==null||m.se==null||!m.club)return"";const c=K.some(k=>norm(m.dom).includes(k));const a=c?m.sd:m.se,b=c?m.se:m.sd;return a>b?"V":a<b?"D":"N"}
const api=async(u,o)=>{const r=await fetch(u,o);const t=await r.text();try{return JSON.parse(t)}catch(e){throw new Error("réponse illisible de l'outil")}};
const post=(u,b)=>api(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});
// ---- tâches en cours (pastille dans le menu) et notifications ----
const occupe={};
function setBusy(v,on,fin){occupe[v]=on;document.querySelectorAll(`.nv[data-v="${v}"]`).forEach(b=>b.classList.toggle("busy",!!on));
 if(!on&&fin&&view!==v)toast(fin,v)}
function toast(txt,v){const d=document.createElement("div");d.innerHTML=txt+(v?' <span style="opacity:.75">— ouvrir</span>':"");
 d.onclick=()=>{if(v)go(v);d.remove()};$("#toast").appendChild(d);setTimeout(()=>d.remove(),7000)}
function msg(el,cls,html){if(!el)return;el.className="small "+(cls||"muted");el.innerHTML=html}
// ---- navigation ----
function construireChips(){$("#chips").innerHTML=[...document.querySelectorAll("#side .nv")].map(b=>`<button class="nv" data-v="${b.dataset.v}">${b.innerHTML}</button>`).join("");
 document.querySelectorAll(".nv").forEach(b=>b.onclick=()=>go(b.dataset.v));
 document.querySelectorAll("[data-go]").forEach(a=>a.onclick=e=>{e.preventDefault();go(a.dataset.go)})}
function go(v){if(!TITRES[v])v="accueil";view=v;LS.set("ffhb_vue",v);
 if(location.hash!=="#"+v)history.replaceState(null,"","#"+v);
 document.querySelectorAll(".nv").forEach(b=>b.classList.toggle("on",b.dataset.v===v));
 document.querySelectorAll(".vue").forEach(s=>s.classList.toggle("on",s.id==="v-"+v));
 $("#vtitre").textContent=TITRES[v];
 $("#webar").style.display=VUES_WE.includes(v)&&v!=="accueil"?"":"none";
 const c=document.querySelector(`.chips .nv[data-v="${v}"]`);if(c)c.scrollIntoView({inline:"center",block:"nearest",behavior:"smooth"});
 afficher(v);window.scrollTo({top:0})}
function afficher(v){
 if(v==="affiche"){if(!init.affiche){init.affiche=1;renderAffiche()}return}
 if(v==="ecran"){if(!init.ecran){init.ecran=1;renderEcran()}return}
 if(v==="article"){if(!init.article){init.article=1;renderArticle()}return}
 if(v==="aide"){if(!init.aide){init.aide=1;renderAide()}return}
 if(v==="mobile"){renderMobile();return}
 if(v==="articles"){if(!init.articles){init.articles=1;renderArticles()}return}
 if(v==="auto"){if(!init.auto){init.auto=1;renderAuto()}return}
 if(v==="cfg"){if(cfg&&!init.cfg){init.cfg=1;renderCfg()}else if(!cfg)sec("cfg").innerHTML='<div class="card loader"><div class="spin"></div>Chargement…</div>';return}
 if(v==="visuel"){renderVisuel();return}
 if(!data){sec(v).innerHTML='<div class="card loader"><div class="spin"></div>Chargement des résultats…</div>';return}
 if(rendu[v]===dataV)return;rendu[v]=dataV;
 if(v==="accueil")renderAccueil();else if(v==="post")renderPost();else renderMatchs(v)}
// ---- tableaux ----
function mtable(ms,K){if(!ms.length)return'<p class="muted">Aucun match ce week-end.</p>';K=K||keys();
 return`<div class="scroll"><table><thead><tr><th>Date</th><th>Domicile</th><th style="text-align:center">Score</th><th>Extérieur</th></tr></thead><tbody>${ms.map(m=>`<tr>
 <td style="white-space:nowrap">${fmt(m.date,m.heure)}${m.journee?` <span class="muted small">J${m.journee}</span>`:""}${m.tour?` <span class="muted small">${esc(m.tour)}</span>`:""}</td>
 <td>${K.some(k=>norm(m.dom).includes(k))?"<b>"+esc(m.dom)+"</b>":esc(m.dom)}</td>
 <td class="sc ${res(m,K)}">${m.sd==null?'<span class="muted">à venir</span>':m.sd+" - "+m.se}</td>
 <td>${K.some(k=>norm(m.ext).includes(k))?"<b>"+esc(m.ext)+"</b>":esc(m.ext)}</td></tr>`).join("")}</tbody></table></div>`}
function stable(rows){if(!rows.length)return'<p class="muted small">Classement non trouvé.</p>';
 const cols=[["j","J"],["g","G"],["n","N"],["p","P"],["diff","Diff"]].filter(([k])=>rows.some(r=>r[k]!=null));
 return`<div class="scroll"><table><thead><tr><th>#</th><th>Équipe</th><th class="num">Pts</th>${cols.map(c=>`<th class="num">${c[1]}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr class="${r.club?"me":""}"><td>${r.pos??""}</td><td>${esc(r.equipe)}</td><td class="num"><b>${r.pts}</b></td>${cols.map(c=>`<td class="num">${r[c[0]]??""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`}
// ---- accueil ----
function renderAccueil(){const o=sec("accueil");if(!data)return;
 const cl=data.competitions.flatMap(c=>(c.weekend_club||[]).map(m=>({m,c})));
 const joues=cl.filter(x=>x.m.sd!=null),avenir=cl.filter(x=>x.m.sd==null);
 const K=keys();const bilan={V:0,D:0,N:0};joues.forEach(x=>{const r=res(x.m,x.c.club_keys||K);if(r)bilan[r]++});
 const prochains=avenir.sort((a,b)=>(a.m.date+(a.m.heure||"")).localeCompare(b.m.date+(b.m.heure||""))).slice(0,6);
 const ctl=data.controle||{},pb=data.competitions.filter(c=>["attente","verifier","echec"].includes(c.statut));
 o.innerHTML=`<div class="card"><div class="head"><h2>Week-end du ${dd(data.du)} au ${dd(data.au)}</h2>
   <div class="seg"><button class="${offset===0?"on":""}" data-off="0">${new Date().toISOString().slice(0,10)>=data.du&&offset===0?"Ce week-end":"Dernier week-end"}</button><button class="${offset===-1?"on":""}" data-off="-1">Week-end à venir</button></div></div>
  <div class="pills" style="margin-top:10px">${joues.length?`<span class="pill v">${bilan.V} victoire${bilan.V>1?"s":""}</span><span class="pill r">${bilan.D} défaite${bilan.D>1?"s":""}</span>${bilan.N?`<span class="pill o">${bilan.N} nul${bilan.N>1?"s":""}</span>`:""}`:""}
   <span class="pill">${cl.length} match${cl.length>1?"s":""} du club</span>${avenir.length?`<span class="pill">${avenir.length} à venir</span>`:""}
   ${pb.length?`<span class="pill r">${pb.length} équipe(s) à vérifier</span>`:ctl.lecture?"":`<span class="pill v">toutes les équipes lues</span>`}${ctl.lecture?`<span class="pill o">${ctl.lecture} en lecture…</span>`:""}</div>
  ${prochains.length?`<h3>Prochains matchs</h3>${prochains.map(({m,c})=>`<div class="small" style="padding:6px 0;border-bottom:1px solid var(--line)"><b>${esc(c.nom)}</b> · ${fmt(m.date,m.heure)} · ${esc(m.dom)} – ${esc(m.ext)}${m.salle?" · "+esc(m.salle):""}</div>`).join("")}`:""}
  ${joues.length?`<h3>Résultats</h3>${joues.map(({m,c})=>{const r=res(m,c.club_keys||K);return`<div class="small" style="padding:6px 0;border-bottom:1px solid var(--line)"><b>${esc(c.nom)}</b> · ${esc(m.dom)} <b class="${r}">${m.sd} – ${m.se}</b> ${esc(m.ext)}</div>`}).join("")}`:""}
 </div>
 <div class="tuiles">
  ${[["club","Matchs du club","Scores, horaires et salles du week-end"],["visuel","Visuels","Programme ou résultats en images, publication sur le site"],
    ["affiche","Affiche","Affiche N1 (championnat ou Coupe de France)"],["post","Texte réseaux","Le texte prêt à copier"],["ecran","Écran géant","Vidéos des prochains matchs"],
    ["article","Écrire un article","Rédaction avec l'IA pour le site"],["articles","Articles du site","Voir ou supprimer un article"],["auto","Publication auto","Activer / couper la publication automatique"],["mobile","Sur téléphone","Ouvrir l'outil sur ton téléphone"],["aide","Mode d'emploi","Comment utiliser l'outil"]].map(t=>`<button class="tuile" data-go="${t[0]}"><b>${t[1]}</b><span>${t[2]}</span></button>`).join("")}
 </div>`;
 o.querySelectorAll("[data-off]").forEach(b=>b.onclick=()=>changerWE(+b.dataset.off));
 o.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go))}
// ---- matchs ----
function renderMatchs(v){const o=sec(v);
 const sansMatch=[];
 const K=data.controle||{},pb=data.competitions.filter(c=>["attente","verifier","echec"].includes(c.statut));
 const lib={attente:"match joué, score pas encore saisi sur la FFHB",verifier:"club introuvable sur la page (lien à vérifier)",echec:"page FFHB illisible"};
 const ctrl=`<div class="card" style="border-color:${pb.length?"var(--loss)":K.lecture?"var(--line)":"var(--win)"}"><div class="head"><h2>${pb.length?"⚠️ "+pb.length+" équipe(s) à vérifier":K.lecture?"⏳ Lecture FFHB en cours ("+(data.competitions.length-K.lecture)+"/"+data.competitions.length+")":"✅ Toutes les équipes ont été lues"}</h2>
  <span class="muted small">${data.competitions.length} équipes · ${K.ok||0} avec score · ${K.aucun||0} sans match${K.a_venir?" · "+K.a_venir+" à venir":""}${K.attente?" · "+K.attente+" score en attente":""}${K.lecture?" · "+K.lecture+" en lecture":""}</span></div>
  ${pb.length?`<ul style="margin:10px 0 0;padding-left:20px">${pb.map(c=>`<li><b>${esc(c.nom)}</b> : ${lib[c.statut]}${c.statut==="echec"&&c.erreur?` <span class="muted small">(${esc(c.erreur).slice(0,120)})</span>`:""}</li>`).join("")}</ul>
   <p class="muted small" style="margin:8px 0 0">« Actualiser » relit toutes les pages. Un score en attente apparaîtra dès que le club l'aura saisi sur la FFHB.</p>`:""}</div>`;
 o.innerHTML=ctrl+data.competitions.map(c=>{
  if(c.statut==="lecture")return`<div class="card loader"><div class="spin"></div><div><b>${esc(c.nom)}</b><br><span class="small">Lecture de la FFHB en cours…</span></div></div>`;
  const ms=v==="club"?c.weekend_club:c.weekend;const CK=c.club_keys||keys();
  if(v==="club"&&c.statut==="aucun"){sansMatch.push(c);return""}
  let h=`<div class="card"><div class="head"><h2><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.nom)}</a></h2><span class="muted small">${esc(c.titre||"")}</span></div>`;
  if(c.erreur)h+=`<p class="err">Lecture impossible : ${esc(c.erreur)}</p>`;
  else{
   if(v==="club"){
    h+=(ms||[]).length?ms.map(m=>{const r=res(m,CK);const me=n=>CK.some(k=>norm(n).includes(k));
     return`<div class="hero"><div class="t r ${me(m.dom)?"me":""}">${esc(m.dom)}</div>
     <div class="s ${r}">${m.sd==null?(m.date&&m.date<new Date().toISOString().slice(0,10)?'<span class="muted" style="font-size:16px">score non saisi</span>':`<span style="font-size:26px">${m.heure?m.heure.replace(":","h"):'<span class="muted" style="font-size:16px">horaire à fixer</span>'}</span>`):m.sd+" – "+m.se}</div>
     <div class="t ${me(m.ext)?"me":""}">${esc(m.ext)}</div>
     <div class="d">${fmt(m.date,m.heure)}${m.heure_corrigee?" (horaire corrigé)":""}${m.salle?" · 📍 "+esc(m.salle):""}${m.journee?" · Journée "+m.journee:""}${m.tour?" · "+esc(m.tour):""}${r?" · "+{V:"Victoire",D:"Défaite",N:"Match nul"}[r]:""}</div></div>`}).join("")
     :'<p class="muted">Pas de match du club ce week-end.</p>'}
   else h+=`<h3>Matchs du week-end</h3>`+mtable(ms||[],CK);
   if(c.coupe&&!c.matchs.length)h+=`<p class="muted small">Le club n'apparaît dans aucun tour de cette coupe pour l'instant.</p>`;
   if(c.club_absent)h+=`<p class="err small">Le club n'apparaît pas sur cette page : ce n'est sans doute pas la bonne poule. Ouvre le lien, choisis la poule du club (ou « Filtrer par club »), puis colle la nouvelle adresse dans Réglages.</p>`;
   if(!c.matchs.length&&!c.coupe)h+=`<p class="err small">Aucun match reconnu sur la page. Zippe le dossier <b>ffhb_debug</b> (à côté du programme) et envoie-le à Claude.</p>`;
   else if(!(ms||[]).length){const last=[...c.matchs].filter(m=>m.date&&m.date<data.du&&m.sd!=null).slice(-3);
     if(last.length)h+=`<details><summary>Derniers résultats connus</summary>${mtable(last,CK)}</details>`}
   if(!c.coupe)h+=`<details><summary>Classement</summary>${stable(c.classement)}</details>`;
   else h+=`<details><summary>Tours lus</summary><p class="small">${(c.tours||[]).map(t=>`<a href="${esc(t.url||"#")}" target="_blank" rel="noopener">${esc(t.tour||"?")}</a> : ${t.erreur?'<span class="err">'+esc(t.erreur)+'</span>':t.club+" match(s) du club / "+t.matchs}`).join("<br>")}</p></details>`;
   h+=`<p class="muted small" style="margin:10px 0 0">${c.coupe?(c.tours||[]).length+" tour(s) lu(s), "+c.matchs.length+" match(s) du club":c.matchs.length+" matchs lus"+(c.saison_complete?" (saison complète du club)":"")} · ${c.pages_lues||0} page(s) · ${c.duree||"?"}s</p>`}
  return h+"</div>"}).join("")
  +(sansMatch.length?`<div class="card"><h2>Pas de match ce week-end</h2><p class="muted" style="margin:8px 0 0">${sansMatch.map(c=>
    `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.nom)}</a>`).join(" · ")}</p></div>`:"")}
// ---- texte réseaux ----
function renderPost(){const o=sec("post");
 o.innerHTML=`<div class="card"><div class="head"><h2>Texte prêt à publier</h2><div class="bar" style="margin:0"><button class="g" id="cp">Copier</button><a class="btn g" href="/api/csv?offset=${offset}">Export CSV</a></div></div><pre id="posttxt">${esc(data.texte)}</pre></div>`;
 $("#cp").onclick=()=>navigator.clipboard.writeText($("#posttxt").textContent).then(()=>{$("#cp").textContent="Copié ✓";setTimeout(()=>{const b=$("#cp");if(b)b.textContent="Copier"},2000)})}
// ---- visuels (gardés en mémoire : changer d'onglet ne les recrée pas) ----
const vcache={};
function renderVisuel(){const o=sec("visuel");
 if(!vmode)vmode=offset<0||(data&&!data.competitions.some(c=>(c.weekend_club||[]).some(m=>m.sd!=null)))?"programme":"resultats";
 const vth=LS.get("ffhb_theme","bleu"),cle=offset+"|"+vmode+"|"+vth,e=vcache[cle];
 const choix=`<div class="card"><div class="bar" style="margin:0"><div class="seg"><button class="${vmode==="resultats"?"on":""}" data-vm="resultats">Résultats</button><button class="${vmode==="programme"?"on":""}" data-vm="programme">Programme</button></div>
   <div class="seg"><button class="${vth==="bleu"?"on":""}" data-th="bleu">Fond bleu</button><button class="${vth==="jaune"?"on":""}" data-th="jaune">Fond jaune</button></div>
   <button class="g" id="vregen">↻ Recréer</button><span class="muted small">${data?"Week-end du "+dd(data.du)+" au "+dd(data.au):""}</span></div></div>`;
 let corps;
 if(!e||e.etat==="encours")corps=`<div class="card loader"><div class="spin"></div>Création des visuels… (quelques secondes)</div>`;
 else if(e.etat==="err")corps=`<div class="card err">Erreur : ${esc(e.err)}</div>`;
 else{const v=e.v,t=e.t;
  corps=!v.fichiers.length?`<div class="card muted">${vmode==="programme"?"Aucun match du club à venir sur ce week-end.":"Aucun score du club ce week-end."}</div>`:
  `<div class="card"><div class="head"><h2>${v.fichiers.length} visuel${v.fichiers.length>1?"s":""} (1080 × 1350)</h2>
    <div class="bar" style="margin:0"><button id="wp">Publier dans les actualités du site</button></div></div><div id="wpmsg" class="small" style="margin:6px 0"></div>
    <p class="muted small" style="margin:0 0 12px">Aussi enregistrés dans : ${esc(v.dossier)}</p>
    <div class="gridv">${v.fichiers.map(f=>`<div><img class="img" loading="lazy" src="/api/visuel.png?f=${encodeURIComponent(f)}&t=${t}" alt="${esc(f)}">
     <a class="btn g" style="margin-top:6px;width:100%" href="/api/visuel.png?f=${encodeURIComponent(f)}" download="${esc(f)}">Télécharger</a></div>`).join("")}</div></div>`}
 o.innerHTML=choix+corps;
 o.querySelectorAll("[data-vm]").forEach(b=>b.onclick=()=>{vmode=b.dataset.vm;renderVisuel()});
 o.querySelectorAll("[data-th]").forEach(b=>b.onclick=()=>{LS.set("ffhb_theme",b.dataset.th);renderVisuel()});
 $("#vregen").onclick=()=>{delete vcache[cle];renderVisuel()};
 const wp=$("#wp");if(wp)wp.onclick=async()=>{const m=$("#wpmsg");wp.disabled=true;msg(m,"muted",spin+"Envoi des images et création de l'article…");setBusy("visuel",true);
  try{const r=await api(`/api/wordpress/publier?offset=${offset}&mode=${vmode}&theme=${vth}`,{method:"POST"});
   if(r.erreur){msg(m,"err",esc(r.erreur)+' — <a href="#cfg" data-go="cfg">Réglages</a>');m.querySelector("[data-go]").onclick=x=>{x.preventDefault();go("cfg")}}
   else msg(m,"ok",`✅ ${r.mise_a_jour?"Article mis à jour":"Article créé"} ${r.statut==="publish"?"et publié":"en brouillon"} (${r.images} image${r.images>1?"s":""}${r.categorie?", catégorie "+esc(r.categorie):""}) : <a href="${esc(r.statut==="publish"?r.lien:r.edition)}" target="_blank" rel="noopener">${r.statut==="publish"?"voir l'article":"ouvrir le brouillon"}</a>`)}
  catch(x){msg(m,"err","Erreur : "+esc(x.message))}finally{wp.disabled=false;setBusy("visuel",false,"Article du week-end envoyé sur le site")}};
 if(!e){vcache[cle]={etat:"encours"};setBusy("visuel",true);
  api("/api/visuels?offset="+offset+"&mode="+vmode+"&theme="+vth).then(v=>{vcache[cle]=v.erreur?{etat:"err",err:v.erreur}:{etat:"ok",v,t:Date.now()}})
   .catch(x=>{vcache[cle]={etat:"err",err:x.message}})
   .finally(()=>{setBusy("visuel",false,"<b>Visuels prêts</b>");const cur=offset+"|"+vmode+"|"+LS.get("ffhb_theme","bleu");if(view==="visuel"&&cur===cle)renderVisuel()})}}
let affType="n1";
function renderAffiche(){const o=sec("affiche");
 o.innerHTML=`<div class="card"><h2>Affiche du prochain match à domicile</h2>
  <div class="seg" style="margin:10px 0 4px"><button id="aft_n1" data-t="n1">N1 – Championnat</button><button id="aft_cdf" data-t="cdf">N1 – Coupe de France</button></div>
  <p class="muted small" style="margin:6px 0 12px">À chaque clic, l'outil relit la FFHB (horaires, salle, match d'ouverture N3 M). Tant que la photo n'est pas validée, une nouvelle photo du dossier <b>affiche/photos</b> est prise à chaque fois ; une fois validée, elle reste pour ce match, même après avoir fermé le programme.</p>
  <div class="bar"><button id="mkaff">Créer l'affiche</button><button class="g" id="valaff" style="display:none">Valider cette photo</button><button class="g" id="infaff" style="display:none">Rajouter infos sur l'affiche</button><span id="affmsg" class="small muted"></span></div>
  <div id="affinf" class="card" style="display:none;margin-top:12px;background:var(--soft)">
   <h3>Infos en plus sur l'affiche</h3>
   <p class="muted small" style="margin:4px 0 8px">Une info par ligne (5 lignes max). S'il y a plusieurs lignes, la 1re sert de titre (en jaune). Elles s'affichent dans un encadré en haut à droite, avec la petite image à côté. Elles restent pour ce match.</p>
   <textarea id="inftxt" rows="4" style="width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit" placeholder="Ex. :&#10;Soirée spéciale&#10;Entrée gratuite&#10;Buvette et food truck sur place"></textarea>
   <div class="bar" style="margin-top:8px;align-items:center"><label class="small">Petite image (logo, QR code…) : <input type="file" id="infimg" accept="image/*"></label>
    <span id="infimgnow" class="small muted"></span></div>
   <div class="bar" style="margin-top:10px"><button id="infsave">Enregistrer et mettre à jour l'affiche</button><button class="g" id="infclear">Tout effacer</button></div></div>
  <div id="affres"></div></div>`;
 let cur=null, infImg=null, sansImg=false, logoPrev="";
 const u=f=>"/api/visuel.png?f="+encodeURIComponent(f);
 const lire=f=>new Promise((ok,ko)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=ko;r.readAsDataURL(f)});
 const types=()=>["n1","cdf"].forEach(t=>{$("#aft_"+t).className=affType===t?"on":""});types();
 const remplirInfos=r=>{const i=r.infos||{};$("#inftxt").value=i.texte||"";infImg=null;sansImg=false;$("#infimg").value="";
  $("#infimgnow").innerHTML=i.image?`Image actuelle : ${esc(i.image)} <button class="g" id="infnoimg" style="padding:2px 8px">Retirer l'image</button>`:"";
  const b=$("#infnoimg");if(b)b.onclick=()=>{sansImg=true;$("#infimgnow").textContent="L'image sera retirée."}};
 const show=r=>{cur=r;const b=$("#mkaff"),v=$("#valaff");
  b.textContent=r.photo_validee?"Mettre à jour l'affiche (même photo)":"Refaire avec une autre photo";
  v.style.display="";v.textContent=r.photo_validee?"✓ Photo validée — changer de photo":"Valider cette photo";v.className=r.photo_validee?"g":"";
  $("#infaff").style.display="";remplirInfos(r);
  const t=Date.now(), eqs=(r.equipes||[]).filter(e=>!e.club);
  $("#affres").innerHTML=`<div class="grid2" style="margin-top:8px">
   <div><div class="muted small" style="margin-bottom:4px">Réseaux (4:5)</div><img src="${u(r.fichier)}&t=${t}" class="img">
    <a href="${u(r.fichier)}" download="${esc(r.fichier)}"><button class="g" style="margin-top:6px;width:100%">Télécharger (PNG)</button></a></div>
   ${r.fichier_a4?`<div><div class="muted small" style="margin-bottom:4px">A4 (impression)</div><img src="${u(r.fichier_a4)}&t=${t}" class="img">
    <a href="${u(r.fichier_a4)}" download="${esc(r.fichier_a4)}"><button class="g" style="margin-top:6px;width:100%">Télécharger A4 (PNG)</button></a>
    ${r.fichier_pdf?`<a href="/api/visuel.pdf?f=${encodeURIComponent(r.fichier_pdf)}"><button class="g" style="margin-top:6px;width:100%">Télécharger A4 (PDF)</button></a>`:""}</div>`:""}
   <div class="small"><p><b>${esc(r.match)}</b>${r.type_nom?`<br><span class="muted">${esc(r.type_nom)}</span>`:""}<br>${esc(new Date(r.date+"T12:00").toLocaleDateString("fr-FR",{weekday:"long",day:"numeric",month:"long"}))} à ${esc((r.heure||"?").replace(":","h"))}${r.tour?" · "+esc(r.tour):r.journee?" · Journée "+r.journee:""}<br>${esc(r.salle||"salle non trouvée")}</p>
   <div style="margin:8px 0" class="bar"><label class="small">Horaire réel${r.heure_corrigee?" (corrigé)":""} : <input id="affh" value="${esc((r.heure||"").replace(":","h"))}" style="width:80px;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit"></label><button class="g" id="affhok" style="padding:4px 10px">Corriger</button></div>
   <p class="muted" style="margin-top:-4px">Si la FFHB n'affiche pas le bon horaire. Il est aussi corrigé sur les visuels programme et résultats ; vide = horaire de la FFHB.</p>
   <p>${r.ouverture?"Ouverture : "+esc(r.ouverture):"Pas de match de N3 M en ouverture ce jour-là."}</p>
   <p>${r.partenaire?"Partenaire du match : "+esc(r.partenaire):'<span class="err">Pas de logo de partenaire pour ce match (affiche/partenaires).</span>'}</p>
   <div style="margin:10px 0"><b>Logos des adversaires</b>${eqs.map((e,k)=>`<div style="margin-top:6px">${e.logo?"✓":'<span class="err">✗ manquant</span>'} ${esc(e.nom)}${e.ouverture?' <span class="muted">(ouverture)</span>':""}<br>
     <label class="small">${e.logo?"Changer le logo":"Ajouter le logo"} : <input type="file" accept="image/*" data-logo="${k}"></label></div>`).join("")}
     <label class="small" style="display:block;margin-top:8px">Détourage : <select id="logodet" style="padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit">
      <option value="auto">Fond autour du logo (recommandé)</option><option value="tout">Tout le fond, même dans les lettres</option><option value="non">Aucun (logo déjà détouré)</option></select></label>
     <div id="logoprev"></div>
     <p class="muted" style="margin-top:4px">PNG ou JPG (fond blanc, de couleur ou faux damier). Le logo est gardé pour les prochaines affiches. Si le résultat ne va pas, change le mode et renvoie le logo.</p></div>
   <p class="muted">Photo : ${esc(r.photo)}${r.photo_validee?" (validée)":""}<br>Horaires vérifiés à ${esc(r.lu_a||"?")}<br>Enregistrée dans : ${esc(r.dossier)}</p></div></div>`;
  $("#affhok").onclick=async()=>{const msg=$("#affmsg");
   const r2=await (await fetch("/api/horaire",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({date:cur.date,dom:cur.dom,ext:cur.ext,heure:$("#affh").value})})).json();
   if(r2.erreur){msg.className="small err";msg.textContent=r2.erreur;return}
   creer({photo:cur.photo,relire:0},"Horaire enregistré, mise à jour de l'affiche…")};
  if(logoPrev&&$("#logoprev"))$("#logoprev").innerHTML=logoPrev;
  document.querySelectorAll("[data-logo]").forEach(inp=>inp.onchange=async()=>{const f=inp.files[0];if(!f)return;const e=eqs[+inp.dataset.logo],msg=$("#affmsg");
   try{const r2=await (await fetch("/api/affiche/logo",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nom:e.nom,data:await lire(f),detourer:$("#logodet").value})})).json();
    if(r2.erreur){msg.className="small err";msg.textContent=r2.erreur;return}
    logoPrev=`<div class="small" style="margin-top:8px">Logo enregistré${r2.detoure?" (détouré)":""} :<div style="margin-top:4px;display:inline-block;padding:10px;border-radius:8px;background:#061d4e"><img src="${r2.apercu}" style="height:90px;display:block"></div></div>`;$("#logoprev").innerHTML=logoPrev;
    creer({photo:cur.photo,relire:0},"Logo de "+e.nom+(r2.detoure?" détouré et":"")+" enregistré, mise à jour de l'affiche…")}catch(x){msg.className="small err";msg.textContent="Erreur : "+x.message}})};
 const charger=()=>{cur=null;$("#affres").innerHTML="";["valaff","infaff"].forEach(i=>$("#"+i).style.display="none");$("#affinf").style.display="none";$("#mkaff").textContent="Créer l'affiche";$("#affmsg").textContent="";
  fetch("/api/affiche/derniere?type="+affType).then(r=>r.json()).then(r=>{if(r&&r.fichier){show(r);$("#affmsg").className="small muted";$("#affmsg").textContent="Dernière affiche créée."}}).catch(()=>{})};
 const creer=async(opt,texte)=>{opt=opt||{};const b=$("#mkaff"),v=$("#valaff"),msg=$("#affmsg");b.disabled=v.disabled=true;setBusy("affiche",true);let fin="";msg.className="small muted";
  msg.innerHTML='<span class="spin" style="display:inline-block;vertical-align:middle;width:14px;height:14px"></span> '+esc(texte||"Relecture de la FFHB et création des deux formats… (environ 1 minute)");
  try{const r=await (await fetch("/api/affiche?type="+affType+(opt.photo?"&photo="+encodeURIComponent(opt.photo):"")+(opt.relire===0?"&relire=0":""))).json();
   if(r.erreur){msg.className="small err";msg.textContent="Erreur : "+r.erreur;return}
   msg.className="small";msg.textContent="✅ Affiche à jour (FFHB vérifiée à "+r.lu_a+")";show(r);fin="<b>Affiche prête</b>"}
  catch(e){msg.className="small err";msg.textContent="Erreur : "+e.message}finally{b.disabled=v.disabled=false;setBusy("affiche",false,fin)}};
 ["n1","cdf"].forEach(t=>$("#aft_"+t).onclick=()=>{if(affType===t||occupe.affiche)return;affType=t;types();charger()});
 charger();
 $("#mkaff").onclick=()=>creer();
 $("#infaff").onclick=()=>{const p=$("#affinf");p.style.display=p.style.display==="none"?"":"none";if(p.style.display==="")$("#inftxt").focus()};
 $("#infimg").onchange=async()=>{const f=$("#infimg").files[0];infImg=f?await lire(f):null;if(f){sansImg=false;$("#infimgnow").textContent="Nouvelle image : "+f.name}};
 const envoyerInfos=async(texte,image,sans)=>{if(!cur)return;const msg=$("#affmsg");
  const r=await (await fetch("/api/affiche/infos",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:affType,date:cur.date,texte,image,sans_image:sans})})).json();
  if(r.erreur){msg.className="small err";msg.textContent=r.erreur;return}
  creer({photo:cur.photo,relire:0},"Infos enregistrées, mise à jour de l'affiche…")};
 $("#infsave").onclick=()=>envoyerInfos($("#inftxt").value,infImg,sansImg);
 $("#infclear").onclick=()=>{if(confirm("Retirer toutes les infos en plus de cette affiche ?"))envoyerInfos("",null,true)};
 $("#valaff").onclick=async()=>{if(!cur)return;const msg=$("#affmsg");
  if(!cur.photo_validee){const r=await (await fetch(`/api/affiche/valider?date=${cur.date}&photo=${encodeURIComponent(cur.photo)}`,{method:"POST"})).json();
   if(r.erreur){msg.className="small err";msg.textContent=r.erreur;return}
   show(Object.assign(cur,{photo_validee:true}));msg.className="small";msg.textContent="✅ Photo validée : elle restera sur l'affiche de ce match."}
  else{await fetch(`/api/affiche/devalider?date=${cur.date}`,{method:"POST"});cur.photo_validee=false;creer()}};
}
function renderEcran(){const o=sec("ecran");
 o.innerHTML=`<div class="card"><h2>Écran géant : vidéos « Prochain match »</h2>
  <p class="muted small" style="margin:6px 0 12px">Une vidéo par Nationale (N1, N3 M, N3 F) pour le prochain match à domicile : 1920 × 1080, 10 secondes, en boucle, sans son. L'outil relit la FFHB (horaires, salle) avant de les créer.</p>
  <div class="bar"><button id="mkec">Créer les vidéos</button><span id="ecmsg" class="small muted"></span></div><div id="ecres"></div></div>`;
 const show=r=>{const t=Date.now();
  $("#ecres").innerHTML=`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-top:8px">${r.videos.map(v=>v.erreur?
   `<div class="card"><h3 style="margin-top:0">${esc(v.equipe)}</h3><p class="muted small">${esc(v.erreur)}</p></div>`:
   `<div><h3 style="margin:0 0 6px">${esc(v.equipe)}</h3>
    <video src="/api/visuel.mp4?f=${encodeURIComponent(v.fichier)}&t=${t}" poster="/api/visuel.jpg?f=${encodeURIComponent(v.apercu)}&t=${t}" controls loop muted playsinline style="width:100%;border-radius:8px;border:1px solid var(--line);background:#000"></video>
    <a href="/api/visuel.mp4?f=${encodeURIComponent(v.fichier)}&dl=1" download="${esc(v.fichier)}"><button class="g" style="margin-top:6px;width:100%">Télécharger la vidéo (MP4)</button></a>
    <p class="small" style="margin:8px 0 0"><b>${esc(v.match)}</b><br>${esc(new Date(v.date+"T12:00").toLocaleDateString("fr-FR",{weekday:"long",day:"numeric",month:"long"}))} à ${esc((v.heure||"?").replace(":","h"))} · ${esc(v.salle||"salle non trouvée")}</p>
    ${v.logos_manquants&&v.logos_manquants.length?`<p class="err small">Logo introuvable pour : ${v.logos_manquants.map(esc).join(", ")} (affiche/logos + logos.json).</p>`:""}</div>`).join("")}</div>
   <p class="muted small" style="margin-top:10px">Enregistrées dans : ${esc(r.dossier||"")}</p>`};
 fetch("/api/ecran/dernieres").then(r=>r.json()).then(r=>{if(r.videos&&r.videos.length){show(r);$("#ecmsg").textContent="Dernières vidéos créées (horaires vérifiés à "+r.lu_a+")."}}).catch(()=>{});
 $("#mkec").onclick=async()=>{const b=$("#mkec"),msg=$("#ecmsg");b.disabled=true;setBusy("ecran",true);let fin="";msg.className="small muted";msg.innerHTML='<span class="spin" style="display:inline-block;vertical-align:middle;width:14px;height:14px"></span> Relecture de la FFHB puis création des vidéos… (2 à 4 minutes)';
  try{const r=await (await fetch("/api/ecran")).json();
   if(r.erreur){msg.className="small err";msg.textContent="Erreur : "+r.erreur;return}
   msg.className="small";msg.textContent="✅ Horaires vérifiés sur la FFHB à "+r.lu_a;show(r);fin="<b>Vidéos écran géant prêtes</b>"}
  catch(e){msg.className="small err";msg.textContent="Erreur : "+e.message}finally{b.disabled=false;setBusy("ecran",false,fin)}};
}
function renderArticle(){const o=sec("article");let photos=[];
 o.innerHTML=`<div class="card"><h2>Nouvel article pour le site</h2>
  <p class="muted small" style="margin:6px 0 12px">Écris ce que tu veux dire, même en vrac et avec des fautes, et ajoute tes photos. L'IA (Gemini ou Claude, au choix dans Réglages) corrige et rédige l'article (sans inventer de faits), puis le crée <b>en brouillon</b> sur le site : l'IA lit aussi le texte présent sur les images (affiche, score, feuille de match). Un <b>visuel de couverture au format du site</b> est créé avec la photo choisie et l'info principale ; toutes les photos vont dans la galerie.</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">
   <div><h3>Rubrique (Actualités)</h3><select id="atype" style="width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit">
    <option value="match" selected>Matchs</option><option value="jeunes">Équipes jeunes</option><option value="club">Vie du club</option><option value="partenaire">Partenaires</option></select></div>
</div>
  <h3>Ton texte</h3><textarea id="atexte" rows="10" placeholder="ex. : victoire des -15 filles contre bron samedi 24-18, super match défense, merci aux parents pour le gouter, prochain match le 7 nov a lachaise"></textarea>
  <h3>Photos</h3><input type="file" id="aphotos" accept="image/*" multiple style="padding:6px">
  <div id="avign" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px"></div>
  <label class="small" style="display:flex;gap:8px;align-items:center;margin-top:12px"><input type="checkbox" id="acouv" checked style="width:auto"> Créer le visuel de couverture (image à la une au bon format)</label>
  <div class="bar" style="margin-top:14px"><button id="ago">Rédiger et créer le brouillon</button><span id="amsg" class="small muted"></span></div>
  <div id="ares"></div></div>`;
 
 // photos réduites à 2000 px (JPEG) dans le navigateur avant l'envoi
 const reduire=f=>new Promise((ok,ko)=>{const u=URL.createObjectURL(f),im=new Image();im.onload=()=>{const k=Math.min(1,2000/Math.max(im.width,im.height));
  const c=document.createElement("canvas");c.width=Math.round(im.width*k);c.height=Math.round(im.height*k);c.getContext("2d").drawImage(im,0,0,c.width,c.height);const k2=Math.min(1,1280/Math.max(im.width,im.height)),c2=document.createElement("canvas");c2.width=Math.round(im.width*k2);c2.height=Math.round(im.height*k2);c2.getContext("2d").drawImage(im,0,0,c2.width,c2.height);
  URL.revokeObjectURL(u);ok({nom:f.name,data:c.toDataURL("image/jpeg",.86),ia:c2.toDataURL("image/jpeg",.8)})};im.onerror=ko;im.src=u});
 const vign=()=>{$("#avign").innerHTML=photos.map((p,i)=>`<div style="position:relative"><img src="${p.data}" style="height:90px;border-radius:6px;border:${i===0?"3px solid var(--accent)":"1px solid var(--line)"}">
   ${i===0?'<span class="small" style="position:absolute;left:4px;bottom:4px;background:var(--accent);color:var(--on);padding:0 4px;border-radius:4px;font-size:10px">couverture</span>':`<button class="g" data-une="${i}" style="position:absolute;left:4px;bottom:4px;padding:0 4px;font-size:10px">couverture</button>`}
   <button class="g" data-del="${i}" style="position:absolute;right:4px;top:4px;padding:0 6px">✕</button></div>`).join("");
  o.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{photos.splice(+b.dataset.del,1);vign()});
  o.querySelectorAll("[data-une]").forEach(b=>b.onclick=()=>{const [p]=photos.splice(+b.dataset.une,1);photos.unshift(p);vign()})};
 $("#aphotos").onchange=async e=>{const m=$("#amsg");m.className="small muted";m.textContent="Préparation des photos…";
  for(const f of e.target.files){try{photos.push(await reduire(f))}catch(x){}}e.target.value="";m.textContent="";vign()};
 $("#ago").onclick=async()=>{const b=$("#ago"),m=$("#amsg"),t=$("#atexte").value.trim();
  if(t.length<15&&!photos.length){m.className="small err";m.textContent="Écris au moins quelques phrases (ou ajoute une image avec les infos).";return}
  b.disabled=true;setBusy("article",true);m.className="small muted";m.innerHTML='<span class="spin" style="display:inline-block;vertical-align:middle;width:14px;height:14px"></span> Rédaction puis envoi'+(photos.length?" des "+photos.length+" photo(s)":"")+"…";
  try{const r=await (await fetch("/api/article",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texte:t,type:$("#atype").value,photos,couverture:$("#acouv").checked})})).json();
   if(r.erreur){m.className="small err";m.innerHTML=esc(r.erreur)+(/Réglages/.test(r.erreur)?' — <a href="#" id="goreg">Réglages</a>':"");const g=$("#goreg");if(g)g.onclick=e=>{e.preventDefault();go("cfg")};return}
   m.className="small";m.innerHTML=`✅ Brouillon créé (${r.images} photo${r.images>1?"s":""}). Relis ci-dessous, puis <button id="apub" style="padding:4px 10px">Publier sur le site</button> ou <a href="${esc(r.edition)}" target="_blank" rel="noopener">modifier dans WordPress</a>`;
   $("#apub").onclick=async()=>{const pb=$("#apub");pb.disabled=true;pb.textContent="Publication…";
    try{const q=await (await fetch("/api/article/publier?id="+r.id,{method:"POST"})).json();
     if(q.erreur){m.className="small err";m.textContent="Erreur : "+q.erreur;return}
     m.className="small";m.innerHTML=`✅ Publié : <a href="${esc(q.lien)}" target="_blank" rel="noopener">voir l'article sur le site</a> · `+
      (q.visible===true?`visible sur la page <a href="${esc(q.page_actualites)}" target="_blank" rel="noopener">Actualités</a>`:
       q.visible===false?`<span class="err">⚠️ n'apparaît pas sur la page <a href="${esc(q.page_actualites)}" target="_blank" rel="noopener">Actualités</a> : vérifie le bloc de la page Actualités dans WordPress.</span>`:
       `vérifie la page <a href="${esc(q.page_actualites)}" target="_blank" rel="noopener">Actualités</a>`)}
    catch(e){m.className="small err";m.textContent="Erreur : "+e.message}};
   $("#ares").innerHTML=(r.couverture?`<div style="margin-top:12px"><div class="muted small" style="margin-bottom:4px">Image à la une créée :</div><img src="/api/visuel.png?f=${encodeURIComponent(r.couverture)}&t=${Date.now()}" style="width:100%;max-width:600px;border-radius:8px;border:1px solid var(--line)"></div>`:"")+`<div class="card" style="margin-top:12px;background:var(--soft)"><h2>${esc(r.titre)}</h2><p class="muted small" style="margin:4px 0 10px">${esc(r.extrait)}</p>
    ${r.blocs.map(x=>x.type==="intertitre"?`<h3 style="text-transform:none;font-size:15px;color:var(--ink)">${esc(x.texte)}</h3>`:`<p>${x.type==="chapeau"?"<b>"+esc(x.texte)+"</b>":esc(x.texte)}</p>`).join("")}
    ${r.remarques?`<p class="small" style="color:var(--draw)">⚠️ À vérifier : ${esc(r.remarques)}</p>`:""}</div>`}
  catch(e){m.className="small err";m.textContent="Erreur : "+e.message}finally{b.disabled=false;setBusy("article",false,m.className==="small"?"<b>Brouillon d'article créé</b>":"")}};
}
function carteGH(){if(!GH)return"";const ok=GHWEB.connecte();
 return`<div class="card" style="border-color:${ok?"var(--win)":"var(--draw)"}"><h2>Connexion administrateur</h2>
 <p class="muted small" style="margin:6px 0 10px">${ok?"✅ Ce téléphone / navigateur est connecté : tu peux créer, publier et régler.":"Pour créer des affiches, publier, écrire des articles ou changer les réglages, connecte ce téléphone une fois avec ton <b>jeton GitHub</b> (il reste uniquement dans ce navigateur)."}</p>
 ${ok?`<div class="bar"><button class="g mini" id="ghout">Déconnecter ce navigateur</button><span class="small muted" id="ghinfo"></span></div>`:`
 <details><summary style="font-size:14px;color:var(--ink);font-weight:600;margin:0 0 8px">Comment créer le jeton (2 minutes)</summary><ol class="small" style="padding-left:18px;margin:6px 0 10px">
  <li>Ouvre <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">github.com/settings/personal-access-tokens/new</a> (connecté à GitHub).</li>
  <li><b>Token name</b> : outil-crhb · <b>Expiration</b> : la plus longue proposée (ou « No expiration »).</li>
  <li><b>Repository access</b> : « Only select repositories » → <b>outil-crhb</b>.</li>
  <li><b>Permissions</b> → « Repository permissions » : <b>Actions</b>, <b>Contents</b>, <b>Secrets</b> et <b>Variables</b> sur « Read and write ».</li>
  <li><b>Generate token</b>, copie le texte qui commence par <b>github_pat_</b> et colle-le ci-dessous.</li></ol></details>
 <div class="bar"><input id="ghtokp" type="password" placeholder="github_pat_..." autocomplete="off" style="flex:1;min-width:200px"><button id="ghin">Connecter</button></div><div id="ghinfo" class="small"></div>`}</div>`}
function lierGH(){if(!GH)return;const o=$("#ghout");if(o)o.onclick=()=>{GHWEB.deconnecter();init.cfg=0;renderCfg()};
 const b=$("#ghin");if(b)b.onclick=async()=>{const m=$("#ghinfo");msg(m,"muted",spin+"Vérification…");
  try{await GHWEB.connecter($("#ghtokp").value.trim());init.cfg=0;renderCfg();toast("<b>Connecté</b> : toutes les fonctions sont disponibles.")}catch(x){msg(m,"err",esc(x.message))}}}
function renderCfg(){const c=cfg||{club:"",competitions:[]};const w=Object.assign({site:"https://caluirerillieuxhandball.fr",utilisateur:"",mot_de_passe:"",categorie:"Matchs",statut:"draft"},c.wordpress||{});
 sec("cfg").innerHTML=carteGH()+`<div class="card"><h2>Site du club (WordPress)</h2>
 <p class="muted small" style="margin:6px 0 0">Mot de passe d'application : dans WordPress, <b>Utilisateurs → Profil → Mots de passe d'application</b>, nom « Outil FFHB », puis <b>Ajouter</b>. Il reste sur ton ordinateur.</p>
 <div class="grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:10px">
  <div><h3>Adresse du site</h3><input id="wsite" value="${esc(w.site)}"></div>
  <div><h3>Identifiant WordPress</h3><input id="wuser" value="${esc(w.utilisateur)}" autocomplete="off"></div>
  <div><h3>Mot de passe d'application</h3><input id="wpass" type="password" value="${esc(w.mot_de_passe)}" placeholder="xxxx xxxx xxxx xxxx xxxx xxxx" autocomplete="new-password"></div>
  <div><h3>À la publication</h3><select id="wstat" style="width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit">
   <option value="draft" ${w.statut!=="publish"?"selected":""}>Brouillon (je valide sur le site)</option><option value="publish" ${w.statut==="publish"?"selected":""}>Publier directement</option></select></div></div>
 <div class="bar" style="margin-top:12px"><button id="wsave">Enregistrer et tester la connexion</button><span id="wtest" class="small"></span></div></div>
 <div class="card"><h2>Rédaction d'articles (IA)</h2>
 <p class="muted small" style="margin:6px 0 0" id="iaaide"></p>
 <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:10px">
  <div><h3>Moteur</h3><select id="imot" style="width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit">
   <option value="gemini">Google Gemini (gratuit)</option><option value="claude">Claude (payant)</option></select></div>
  <div><h3>Clé API</h3><input id="ikey" type="password" autocomplete="new-password"></div>
  <div><h3>Modèle (vide = automatique)</h3><input id="imod" placeholder="automatique"></div></div>
 <div class="bar" style="margin-top:12px"><button id="isave">Enregistrer et tester</button><span id="itest" class="small"></span></div></div>
 <div class="card"><h2>Réglages</h2><h3>Club (mots-clés séparés par des virgules)</h3><input id="club" value="${esc(c.club)}">
 <h3>Compétitions (lien d'une page poule ou équipe sur ffhandball.fr)</h3><div id="rows">${c.competitions.map((x,i)=>`<div class="row"><input data-i="${i}" data-k="nom" value="${esc(x.nom)}" placeholder="Nom"><input data-i="${i}" data-k="url" value="${esc(x.url)}" placeholder="https://www.ffhandball.fr/competitions/..."><button class="g" data-del="${i}">✕</button><span></span><input data-i="${i}" data-k="club" value="${esc(x.club||"")}" placeholder="Nom de l'équipe si entente (sinon laisser vide)" style="font-size:13px"><span></span></div>`).join("")}</div>
 <div class="bar"><button class="g" id="add">+ Ajouter</button><button id="save">Enregistrer et lire</button></div></div>`;
 lierGH();
 const sync=()=>{c.club=$("#club").value;document.querySelectorAll("#rows input").forEach(i=>c.competitions[i.dataset.i][i.dataset.k]=i.value)};
 $("#add").onclick=()=>{sync();c.competitions.push({nom:"",url:""});renderCfg()};
 document.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{sync();c.competitions.splice(+b.dataset.del,1);renderCfg()});
 $("#save").onclick=async()=>{sync();c.competitions=c.competitions.filter(x=>x.url.trim());
  await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(c)});cfg=c;rendu.club=rendu.all=rendu.accueil=-1;go("club");load(true)};
 const ia=Object.assign({moteur:"gemini",cles:{},modeles:{}},c.ia||{});ia.cles=Object.assign({},ia.cles);ia.modeles=Object.assign({},ia.modeles);
 if(!ia.cles.claude&&(c.claude||{}).cle)ia.cles.claude=c.claude.cle;
 const AIDE={gemini:"Gratuit : va sur <b>aistudio.google.com</b> avec un compte Google → <b>Get API key</b> → <b>Create API key</b>, puis colle la clé ici. Elle reste sur ton ordinateur ; ne l'envoie à personne.",
  claude:"Payant (quelques centimes par article) : <b>console.anthropic.com</b> → <b>API Keys</b> → <b>Create Key</b>, compte à créditer dans <b>Billing</b>. La clé reste sur ton ordinateur."};
 const montre=()=>{const m=$("#imot").value;$("#ikey").value=ia.cles[m]||"";$("#imod").value=ia.modeles[m]||"";$("#ikey").placeholder=m==="gemini"?"AIza...":"sk-ant-...";$("#iaaide").innerHTML=AIDE[m]};
 const lit=()=>{const m=$("#imot").value;ia.cles[m]=$("#ikey").value.trim();ia.modeles[m]=$("#imod").value.trim()};
 $("#imot").value=ia.moteur;montre();
 $("#imot").onchange=()=>{const anc=ia.moteur;ia.cles[anc]=$("#ikey").value.trim();ia.modeles[anc]=$("#imod").value.trim();ia.moteur=$("#imot").value;montre()};
 $("#isave").onclick=async()=>{const t=$("#itest");t.className="small muted";t.textContent="Test en cours…";lit();ia.moteur=$("#imot").value;c.ia=ia;
  await fetch("/api/ia/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(ia)});
  try{const r=await (await fetch("/api/ia/test",{method:"POST"})).json();
   if(r.erreur){t.className="small err";t.textContent=r.erreur}else{t.className="small";t.textContent="✅ "+r.moteur+" connecté · modèle : "+r.modele}}
  catch(e){t.className="small err";t.textContent="Erreur : "+e.message}};
 $("#wsave").onclick=async()=>{const t=$("#wtest");t.className="small muted";t.textContent="Test en cours…";
  const nw={site:$("#wsite").value.trim(),utilisateur:$("#wuser").value.trim(),mot_de_passe:$("#wpass").value.trim(),categorie:"Matchs",statut:$("#wstat").value};
  c.wordpress=nw;await fetch("/api/wordpress/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(nw)});
  try{const r=await (await fetch("/api/wordpress/test",{method:"POST"})).json();
   if(r.erreur){t.className="small err";t.textContent=r.erreur}
   else{t.className="small";t.textContent=`✅ Connecté en tant que ${r.nom}`+(r.categorie?` · catégorie « ${r.categorie} » trouvée`:` · ⚠️ catégorie « ${nw.categorie} » introuvable (l'article ira dans la catégorie par défaut)`)}}
  catch(e){t.className="small err";t.textContent="Erreur : "+e.message}};
}
// ---- articles du site : liste + suppression ----
function renderArticles(){const o=sec("articles");
 o.innerHTML=`<div class="card"><div class="head"><h2>Articles publiés sur le site</h2><button class="g mini" id="arecharger">↻ Recharger la liste</button></div>
  <p class="muted small" style="margin:6px 0 12px">Les 60 derniers articles du site (publiés, brouillons, programmés). Choisis-en un pour le voir, le modifier dans WordPress ou le supprimer.</p>
  <select id="asel"><option>Chargement…</option></select>
  <div id="adet" style="margin-top:12px"></div><div id="amsg2" class="small"></div></div>`;
 let liste=[];const ST={publish:"publié",draft:"brouillon",future:"programmé",pending:"en attente",private:"privé"};
 const detail=()=>{const a=liste.find(x=>String(x.id)===$("#asel").value);const d=$("#adet");if(!a){d.innerHTML="";return}
  d.innerHTML=`<div class="card soft" style="margin:0"><b>${esc(a.titre)}</b><div class="pills" style="margin:6px 0 10px"><span class="pill ${a.statut==="publish"?"v":"o"}">${ST[a.statut]||a.statut}</span><span class="pill">${esc(a.date.replace("T"," à "))}</span>${a.rubrique?`<span class="pill">${esc(a.rubrique)}</span>`:""}</div>
   <div class="bar" style="margin:0"><a class="btn g" href="${esc(a.lien)}" target="_blank" rel="noopener">Voir sur le site</a><a class="btn g" href="${esc(a.edition)}" target="_blank" rel="noopener">Modifier dans WordPress</a>
   <button id="adel" style="background:var(--loss)">Supprimer l'article</button></div>
   <label class="small" style="display:flex;gap:8px;align-items:center;margin-top:10px"><input type="checkbox" id="adef"> Supprimer définitivement, avec ses images (sinon : corbeille de WordPress, récupérable 30 jours)</label></div>`;
  $("#adel").onclick=async()=>{const def=$("#adef").checked,m=$("#amsg2");
   if(!confirm(`${def?"Supprimer DÉFINITIVEMENT":"Mettre à la corbeille"} l'article « ${a.titre} » ?`))return;
   $("#adel").disabled=true;msg(m,"muted",spin+"Suppression…");
   try{const r=await post("/api/wp/supprimer",{id:a.id,definitif:def});
    if(r.erreur){msg(m,"err","Erreur : "+esc(r.erreur));$("#adel").disabled=false;return}
    msg(m,"ok",`✅ « ${esc(a.titre)} » ${def?"supprimé définitivement"+(r.images?" (avec "+r.images+" image"+(r.images>1?"s":"")+")":""):"mis à la corbeille (récupérable dans WordPress > Articles > Corbeille)"}.`);charger()}
   catch(x){msg(m,"err","Erreur : "+esc(x.message));$("#adel").disabled=false}}};
 const charger=async()=>{const s=$("#asel");s.innerHTML="<option>Chargement…</option>";s.disabled=true;
  try{const r=await api("/api/wp/articles");
   if(r.erreur){s.innerHTML="<option>—</option>";$("#adet").innerHTML=`<p class="err small">${esc(r.erreur)} — <a href="#cfg" data-go="cfg">Réglages</a></p>`;$("#adet [data-go]").onclick=e=>{e.preventDefault();go("cfg")};return}
   liste=r.articles;s.innerHTML=`<option value="">— Choisis un article (${liste.length}) —</option>`+liste.map(a=>`<option value="${a.id}">${esc(a.date.slice(0,10).split("-").reverse().join("/"))} · ${esc(a.titre)}${a.statut!=="publish"?" ("+(ST[a.statut]||a.statut)+")":""}</option>`).join("");
   s.disabled=false;s.onchange=detail;detail()}
  catch(x){s.innerHTML="<option>—</option>";$("#adet").innerHTML=`<p class="err small">Erreur : ${esc(x.message)}</p>`}};
 $("#arecharger").onclick=charger;charger()}
// ---- publication automatique (GitHub) ----
function renderAuto(){const o=sec("auto");
 o.innerHTML=`<div class="card"><h2>Où se fait la publication automatique ?</h2>
  <p class="muted small" style="margin:6px 0 10px">Résultats chaque <b>mardi à 10 h</b>, programme chaque <b>mercredi à 18 h</b>, sans ouvrir l'outil.</p>
  <div class="seg"><button data-ou="local">${CLOUD?"Sur le serveur en ligne":"Sur cet ordinateur"}</button><button data-ou="github">Sur GitHub</button></div>
  <p class="small muted" id="oudesc" style="margin:10px 0 0"></p></div>
  <div id="locpanel" style="display:none"><div class="card"><h2>Publication depuis ${CLOUD?"le serveur en ligne":"cet ordinateur"}</h2><div id="locc"><div class="loader" style="margin-top:12px"><div class="spin"></div>Chargement…</div></div><div id="locmsg" class="small" style="margin-top:8px"></div></div></div>
  <div id="ghpanel" style="display:none">
  <div class="card"><h2>Publication automatique sur GitHub</h2>
  <p class="muted small" style="margin:6px 0 4px">Ces publications tournent sur GitHub : elles se font même quand ton ordinateur est éteint et l'outil fermé. Ici tu peux les activer ou les couper, choisir brouillon ou publication directe, et en lancer une tout de suite.</p>
  <div id="autoc"><div class="loader" style="margin-top:12px"><div class="spin"></div>Lecture de l'état sur GitHub…</div></div><div id="automsg" class="small" style="margin-top:8px"></div></div>
  <div class="card"><details id="ghdet"><summary style="font-size:15px;color:var(--ink);font-weight:600;margin:0">Connexion à GitHub</summary>
   <p class="muted small">Une seule fois. 1) Sur GitHub : photo de profil → <b>Settings</b> → <b>Developer settings</b> → <b>Personal access tokens</b> → <b>Fine-grained tokens</b> → <b>Generate new token</b>. 2) Nom « Outil CRHB », expiration la plus longue possible, <b>Repository access</b> : « Only select repositories » → ton dépôt de l'outil. 3) <b>Permissions</b> du dépôt : <b>Actions</b> = Read and write, <b>Variables</b> = Read and write. 4) <b>Generate token</b>, copie-le et colle-le ci-dessous. Il reste sur ton ordinateur : ne l'envoie à personne.</p>
   <div class="grid2" style="margin-top:8px"><div><h3>Dépôt (pseudo/nom-du-dépôt)</h3><input id="ghdep" placeholder="ex. ethan-crhb/outil-ffhb"></div>
   <div><h3>Jeton d'accès</h3><input id="ghtok" type="password" autocomplete="new-password" placeholder="github_pat_..."></div></div>
   <div class="bar" style="margin-top:12px"><button id="ghsave">Enregistrer et tester</button><span id="ghmsg" class="small"></span></div></details></div></div>`;
 const DESC={local:CLOUD?"Le serveur en ligne publie tout seul, même ordinateur éteint. Une publication ratée (serveur arrêté ou en veille) est rattrapée jusqu'au jeudi soir.":"L'ordinateur doit être <b>allumé ou en veille</b> à ces heures (pas éteint) ; l'outil et Chrome n'ont pas besoin d'être ouverts. Une publication ratée parce que l'ordinateur était éteint est rattrapée au prochain démarrage (jusqu'au jeudi soir). Pas de compte GitHub nécessaire.",
  github:GH?"GitHub publie tout seul sur le site, même ordinateur éteint.":"Publie même quand l'ordinateur est <b>éteint</b>. Demande un dépôt GitHub (déjà préparé dans FFHB_GitHub.zip) et un jeton d'accès."};
 const HEURE={resultats:"Résultats du week-end — chaque <b>mardi à 10 h</b>",programme:"Programme du week-end suivant — chaque <b>mercredi à 18 h</b>"};
 let ou="github";
 const choisir=(v,enreg)=>{ou=v;o.querySelectorAll("[data-ou]").forEach(b=>b.classList.toggle("on",b.dataset.ou===v));$("#oudesc").innerHTML=DESC[v];
  $("#locpanel").style.display=v==="local"?"":"none";$("#ghpanel").style.display=v==="github"?"":"none";
  if(enreg)post("/api/auto/local",{mode_auto:v}).then(montrerLoc).catch(()=>{});
  if(v==="github"&&!ghCharge){ghCharge=1;charger()}};
 let ghCharge=0;
 o.querySelectorAll("[data-ou]").forEach(b=>b.onclick=()=>choisir(b.dataset.ou,true));
 const montrerLoc=e=>{const c=$("#locc");if(!c)return;if(e.erreur)msg($("#locmsg"),"err",esc(e.erreur));
  c.innerHTML=`${e.avertissement?`<p class="err small">⚠️ ${esc(e.avertissement)}</p>`:""}
   ${["resultats","programme"].map(m=>`<div class="autol"><label class="sw"><input type="checkbox" data-loc="${m}" ${e.modes[m]?"checked":""}><i></i><span><b>${m==="resultats"?"Résultats":"Programme"}</b> · <span class="small">${e.modes[m]?'<span class="ok">activée</span>':'<span class="muted">désactivée</span>'}</span><br><span class="small muted">${HEURE[m]}</span></span></label>
    <button class="g mini" data-locnow="${m}">Publier maintenant</button></div>`).join("")}
   <div class="autol"><span><b>Les articles automatiques sont…</b><br><span class="small muted">Brouillon : tu valides sur le site. Publiés : en ligne directement.</span></span>
    <div class="seg"><button data-locst="draft" class="${e.statut_publication!=="publish"?"on":""}">En brouillon</button><button data-locst="publish" class="${e.statut_publication==="publish"?"on":""}">Publiés directement</button></div></div>
   <p class="small ${e.planificateur?"ok":"muted"}" style="margin:10px 0 0">${CLOUD?"✅ Le serveur vérifie toutes les 5 minutes s'il y a une publication à faire.":e.planificateur?`✅ Programmé dans ${e.systeme==="Windows"?"le Planificateur de tâches de Windows":e.systeme==="Mac"?"macOS (lancement automatique)":"le système"}.`:"Aucune publication programmée sur cet ordinateur."}</p>
   <h3>Dernières publications</h3>${(e.journal||[]).length?e.journal.map(j=>`<div class="small" style="padding:5px 0;border-bottom:1px solid var(--line)">${esc(j.date.split(" ")[0].split("-").reverse().join("/"))} ${esc(j.date.split(" ")[1]||"")} · ${j.mode==="resultats"?"Résultats":"Programme"} · ${esc(j.source||"")} · ${j.ok?'<span class="ok">✅ '+esc(j.message)+'</span>':'<span class="err">❌ '+esc(j.message)+'</span>'}${j.lien?` · <a href="${esc(j.lien)}" target="_blank" rel="noopener">voir</a>`:""}</div>`).join(""):'<p class="muted small">Aucune pour l\'instant.</p>'}`;
  c.querySelectorAll("[data-loc]").forEach(i=>i.onchange=async()=>{const m=$("#locmsg");msg(m,"muted",spin+"Enregistrement…");
   try{const r=await post("/api/auto/local",{mode:i.dataset.loc,actif:i.checked,mode_auto:"local"});montrerLoc(r);
    if(!r.erreur)msg(m,"ok",`✅ Publication automatique ${i.dataset.loc==="resultats"?"des résultats":"du programme"} ${i.checked?"activée sur cet ordinateur":"désactivée"}.`)}catch(x){msg(m,"err",esc(x.message))}});
  c.querySelectorAll("[data-locst]").forEach(b=>b.onclick=async()=>{try{montrerLoc(await post("/api/auto/local",{statut:b.dataset.locst}));msg($("#locmsg"),"ok","✅ Enregistré.")}catch(x){}});
  c.querySelectorAll("[data-locnow]").forEach(b=>b.onclick=async()=>{const md=b.dataset.locnow,m=$("#locmsg");
   if(!confirm(`Publier ${md==="resultats"?"les résultats":"le programme"} sur le site maintenant ? (environ 2 minutes, garde l'outil ouvert)`))return;
   b.disabled=true;setBusy("auto",true);msg(m,"muted",spin+"Lecture de la FFHB et publication… (environ 2 minutes)");
   try{await post("/api/auto/local/maintenant",{mode:md});const n0=(e.journal||[]).length;
    const t=setInterval(async()=>{const r=await api("/api/auto/local");if((r.journal||[]).length>n0||(r.journal[0]&&r.journal[0].date!==(e.journal[0]||{}).date)){clearInterval(t);montrerLoc(r);setBusy("auto",false,"<b>Publication terminée</b>");
      const j=r.journal[0];msg($("#locmsg"),j.ok?"ok":"err",(j.ok?"✅ ":"❌ ")+esc(j.message))}},5000)}
   catch(x){msg(m,"err",esc(x.message));b.disabled=false;setBusy("auto",false)}})};
 if(GH){o.querySelector('[data-ou="local"]').style.display="none";const d=$("#ghdet");if(d)d.closest(".card").innerHTML='<p class="small muted" style="margin:0">Connexion à GitHub : <b>Réglages → Connexion administrateur</b>.</p>';setTimeout(()=>choisir("github"))}
 else api("/api/auto/local").then(e=>{choisir(e.mode_auto==="local"?"local":"github");montrerLoc(e)}).catch(()=>choisir("github"));
 const fdate=d=>d?new Date(d).toLocaleString("fr-FR",{weekday:"short",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"";
 const RES={success:'<span class="ok">✅ réussie</span>',failure:'<span class="err">❌ échec</span>',cancelled:"annulée",skipped:"ignorée"};
 const montrer=e=>{const c=$("#autoc");
  if(e.depot)$("#ghdep").value=e.depot;$("#ghtok").placeholder=e.jeton?"jeton enregistré (laisser vide pour le garder)":"github_pat_...";
  if(e.non_configure||e.erreur){$("#ghdet").open=true;
   c.innerHTML=`<p class="${e.erreur?"err":"muted"} small" style="margin-top:12px">${e.erreur?esc(e.erreur):"Pour piloter la publication automatique depuis l'outil, connecte d'abord GitHub (encadré ci-dessous)."}</p>`;return}
  c.innerHTML=`${!e.workflow_actif?`<p class="err small">⚠️ La publication automatique est en pause sur GitHub (c'est automatique après 60 jours sans activité) : réactive un interrupteur pour la relancer.</p>`:""}
   ${["resultats","programme"].map(m=>`<div class="autol"><label class="sw"><input type="checkbox" data-auto="${m}" ${e.modes[m]&&e.workflow_actif?"checked":""}><i></i><span><b>${m==="resultats"?"Résultats":"Programme"}</b> · <span class="small">${e.modes[m]&&e.workflow_actif?'<span class="ok">activée</span>':'<span class="muted">désactivée</span>'}</span><br><span class="small muted">${HEURE[m]}</span></span></label>
    <button class="g mini" data-lancer="${m}">Publier maintenant</button></div>`).join("")}
   <div class="autol"><span><b>Les articles automatiques sont…</b><br><span class="small muted">Brouillon : tu valides sur le site. Publiés : en ligne directement.</span></span>
    <div class="seg"><button data-st="draft" class="${e.statut_publication!=="publish"?"on":""}">En brouillon</button><button data-st="publish" class="${e.statut_publication==="publish"?"on":""}">Publiés directement</button></div></div>
   <h3>Dernières exécutions</h3>${e.executions.length?e.executions.map(r=>`<div class="small" style="padding:5px 0;border-bottom:1px solid var(--line)">${fdate(r.date)} · ${r.declencheur==="schedule"?"automatique":"lancée à la main"} · ${r.statut!=="completed"?spin+"en cours…":(RES[r.resultat]||esc(r.resultat||""))} · <a href="${esc(r.lien)}" target="_blank" rel="noopener">détails</a></div>`).join(""):'<p class="muted small">Aucune exécution pour l\'instant.</p>'}
   <p class="small" style="margin-top:10px"><a href="${esc(e.lien)}" target="_blank" rel="noopener">Ouvrir sur GitHub</a></p>`;
  c.querySelectorAll("[data-auto]").forEach(i=>i.onchange=async()=>{const m=$("#automsg");c.querySelectorAll("input,button").forEach(x=>x.disabled=true);
   msg(m,"muted",spin+"Enregistrement sur GitHub…");
   try{const r=await post("/api/auto/regler",{mode:i.dataset.auto,actif:i.checked});if(r.erreur){msg(m,"err",esc(r.erreur));charger();return}
    msg(m,"ok",`✅ Publication automatique ${i.dataset.auto==="resultats"?"des résultats":"du programme"} ${i.checked?"activée":"désactivée"}.`);montrer(r)}
   catch(x){msg(m,"err","Erreur : "+esc(x.message));charger()}});
  c.querySelectorAll("[data-st]").forEach(b=>b.onclick=async()=>{const m=$("#automsg");msg(m,"muted",spin+"Enregistrement…");
   try{const r=await post("/api/auto/statut",{statut:b.dataset.st});if(r.erreur){msg(m,"err",esc(r.erreur));return}msg(m,"ok","✅ Enregistré.");montrer(r)}catch(x){msg(m,"err",esc(x.message))}});
  c.querySelectorAll("[data-lancer]").forEach(b=>b.onclick=async()=>{const md=b.dataset.lancer,m=$("#automsg");
   if(!confirm(`Publier ${md==="resultats"?"les résultats":"le programme"} sur le site maintenant (via GitHub, 3 à 5 minutes) ?`))return;
   b.disabled=true;msg(m,"muted",spin+"Lancement…");
   try{const r=await post("/api/auto/lancer",{mode:md});if(r.erreur){msg(m,"err",esc(r.erreur));b.disabled=false;return}
    msg(m,"ok","✅ Lancé sur GitHub : l'article sera sur le site dans 3 à 5 minutes (tu peux fermer l'outil).");setTimeout(charger,4000)}
   catch(x){msg(m,"err",esc(x.message));b.disabled=false}})};
 const charger=async()=>{try{montrer(await api("/api/auto/etat"))}catch(x){$("#autoc").innerHTML=`<p class="err small">Erreur : ${esc(x.message)}</p>`}};
 $("#ghsave").onclick=async()=>{ghCharge=1;const m=$("#ghmsg");msg(m,"muted",spin+"Test…");
  try{const r=await post("/api/github/config",{depot:$("#ghdep").value,jeton:$("#ghtok").value});$("#ghtok").value="";
   if(r.erreur){msg(m,"err",esc(r.erreur));return}msg(m,"ok","✅ Connecté à GitHub");$("#ghdet").open=false;montrer(Object.assign(r,{depot:$("#ghdep").value,jeton:true}))}
  catch(x){msg(m,"err",esc(x.message))}};
}
// ---- ouvrir sur le téléphone ----
const CLOUD=__CLOUD__,GH=typeof window.GHWEB!=="undefined";
const surTel=CLOUD||!["localhost","127.0.0.1","::1","[::1]"].includes(location.hostname);
function renderMobile(){const o=sec("mobile");
 if(surTel||GH){o.innerHTML=`<div class="card"><h2>✅ ${CLOUD||GH?"Version en ligne : ouvrable partout, ordinateur éteint":"Tu es sur ton téléphone"}</h2><p class="small">Pour retrouver l'outil en un geste, ajoute-le à l'écran d'accueil :<br>• <b>iPhone (Safari)</b> : bouton Partager <span class="kbd">⬆</span> → « Sur l'écran d'accueil ».<br>• <b>Android (Chrome)</b> : menu <span class="kbd">⋮</span> → « Ajouter à l'écran d'accueil ».</p>
  <p class="muted small">${GH?"Cette version tourne sur GitHub : elle s'ouvre partout (Wi-Fi ou 4G), même ordinateur éteint. Les actions (affiche, article, publication…) prennent 2 à 3 minutes, le temps que GitHub fasse le travail.":CLOUD?"Cette version tourne sur un serveur en ligne : elle s'ouvre partout (Wi-Fi ou 4G), même ordinateur éteint.":"L'outil tourne sur l'ordinateur : il doit être allumé, avec l'outil ouvert, et le téléphone sur le même Wi-Fi."}</p></div>`;return}
 o.innerHTML=`<div class="card"><div class="loader"><div class="spin"></div>Chargement…</div></div>`;
 const montrer=e=>{o.innerHTML=`<div class="card"><div class="autol" style="padding-top:0"><label class="sw"><input type="checkbox" id="mact" ${e.actif?"checked":""}><i></i><span><b>Accès depuis le téléphone</b> · <span class="small">${e.actif?'<span class="ok">activé</span>':'<span class="muted">désactivé</span>'}</span><br><span class="small muted">Le téléphone doit être sur le <b>même Wi-Fi</b> que cet ordinateur, et l'outil ouvert ici.</span></span></label></div>
  ${e.erreur?`<p class="err small">${esc(e.erreur)}</p>`:""}
  ${e.actif?`<div class="grid2" style="margin-top:14px;align-items:center">
    <div style="text-align:center">${e.qr?`<div style="display:inline-block;background:#fff;padding:10px;border-radius:14px;line-height:0">${e.qr}</div>`:'<p class="muted small">(QR code indisponible : tape l\'adresse à la main)</p>'}</div>
    <div><div class="etape" style="display:grid;grid-template-columns:30px 1fr;gap:10px;margin:0 0 12px"><b class="pill v" style="height:fit-content">1</b><div>Ouvre l'<b>appareil photo</b> du téléphone et vise le QR code, puis touche le lien.</div></div>
     <div style="display:grid;grid-template-columns:30px 1fr;gap:10px;margin:0 0 12px"><b class="pill v" style="height:fit-content">2</b><div>Ou tape dans le navigateur du téléphone :<br><b style="font-size:17px">${esc(e.adresse)}</b><br>puis le code <b style="font-size:20px;letter-spacing:3px">${esc(e.code)}</b></div></div>
     <div style="display:grid;grid-template-columns:30px 1fr;gap:10px;margin:0"><b class="pill v" style="height:fit-content">3</b><div>Ajoute-le à l'écran d'accueil (iPhone : Partager → « Sur l'écran d'accueil » ; Android : ⋮ → « Ajouter à l'écran d'accueil »). Le code n'est demandé qu'une fois.</div></div></div></div>
   <div class="bar" style="margin-top:14px"><button class="g mini" id="mcode">Nouveau code</button><span class="muted small">déconnecte les téléphones déjà connectés</span></div>`:""}
  </div>
  <div class="card soft"><h2>Si le téléphone n'arrive pas à se connecter</h2><ul class="small" style="margin:8px 0 0;padding-left:18px">
   <li>Vérifie que le téléphone est sur le <b>Wi-Fi</b> (pas en 4G/5G) et sur le même réseau que l'ordinateur.</li>
   ${e.systeme==="Windows"?`<li><b>Windows</b> : à l'activation, une fenêtre « Pare-feu Windows » peut s'ouvrir : coche <b>Réseaux privés</b> puis <b>Autoriser l'accès</b>. Le Wi-Fi doit être en profil « Privé » (Paramètres → Réseau → Wi-Fi → ton réseau → Réseau privé).</li>`:
    `<li><b>Mac</b> : si une fenêtre demande d'« accepter les connexions entrantes » pour Python, clique <b>Autoriser</b> (Réglages Système → Réseau → Coupe-feu).</li>`}
   <li>Les Wi-Fi publics ou d'entreprise bloquent souvent ce type d'accès : utilise le Wi-Fi de la maison ou le partage de connexion du téléphone.</li>
   <li>Le téléphone ne peut pas voir les mots de passe et les clés enregistrés (site, IA, GitHub).</li></ul></div>`;
  $("#mact").onchange=async()=>{const r=await post("/api/mobile",{actif:$("#mact").checked});montrer(r)};
  const b=$("#mcode");if(b)b.onclick=async()=>{if(confirm("Créer un nouveau code ? Les téléphones déjà connectés devront le retaper."))montrer(await post("/api/mobile",{nouveau_code:true}))}};
 api("/api/mobile").then(montrer).catch(x=>{o.innerHTML=`<div class="card err">Erreur : ${esc(x.message)}</div>`})}
// ---- mode d'emploi ----
function renderAide(){sec("aide").innerHTML=`<div class="guide">
 <div class="card"><h2>À quoi sert l'outil ?</h2>
  <p>L'outil lit tout seul les pages de la FFHB pour toutes les équipes du club, puis prépare ce dont la com' a besoin : résultats et programme du week-end, visuels pour les réseaux, affiche du prochain match de N1, vidéos pour l'écran géant, et articles pour le site. Rien n'est publié sans que tu cliques (sauf la publication automatique sur GitHub, voir plus bas).</p>
  <p class="muted small">Les données sont gardées en mémoire : la page s'ouvre tout de suite avec la dernière lecture, puis se met à jour toute seule en arrière-plan (point orange en haut = lecture en cours, point vert = à jour).</p></div>
 <div class="card"><h2>La semaine type</h2>
  <div class="etape"><i>1</i><div><b>Lundi – résultats.</b> Onglet <b>Visuels</b> → « Résultats » sur le « Dernier » week-end. Télécharge les images pour Instagram, ou « Publier dans les actualités du site ». Le <b>Texte réseaux</b> donne la légende prête à copier.</div></div>
  <div class="etape"><i>2</i><div><b>Mercredi – programme.</b> Bouton « À venir » en haut, puis <b>Visuels</b> → « Programme ». Si un horaire FFHB est faux, corrige-le depuis l'onglet <b>Affiche</b> (champ « Horaire réel ») : il est corrigé partout.</div></div>
  <div class="etape"><i>3</i><div><b>Avant un match de N1 à domicile – affiche.</b> Onglet <b>Affiche</b>, choisis « Championnat » ou « Coupe de France », puis « Créer l'affiche ». Chaque clic prend une nouvelle photo ; « Valider cette photo » la garde. Ajoute un logo manquant, des infos (entrée gratuite, buvette…) ou corrige l'horaire, l'affiche se refait seule.</div></div>
  <div class="etape"><i>4</i><div><b>Jour de match – écran géant.</b> Onglet <b>Écran géant</b> → « Créer les vidéos » (une par Nationale), à lancer sur l'écran en boucle.</div></div>
  <div class="etape"><i>5</i><div><b>Quand tu veux – article.</b> Onglet <b>Article</b> : écris en vrac, ajoute des photos, choisis la rubrique. L'IA rédige, l'outil crée le brouillon sur le site avec l'image à la une, puis « Publier sur le site ».</div></div></div>
 <div class="card"><h2>Les onglets en détail</h2><ul>
  <li><b>Accueil</b> : le résumé du week-end choisi (bilan, prochains matchs) et l'accès rapide à tout.</li>
  <li><b>Matchs du club</b> : scores, horaires, salles et classements de chaque équipe. Les équipes sans match sont regroupées en bas. Le cadre « contrôle » signale une équipe dont la page FFHB pose problème.</li>
  <li><b>Tous les matchs</b> : tous les matchs des poules du club ce week-end.</li>
  <li><b>Visuels</b> : images 1080 × 1350 (fond bleu ou jaune). Elles restent en mémoire : tu peux changer d'onglet pendant la création, une pastille jaune clignote dans le menu tant que ça travaille, et un message te prévient quand c'est prêt.</li>
  <li><b>Texte réseaux</b> : la légende du week-end, à copier.</li>
  <li><b>Affiche</b> : N1 championnat ou Coupe de France, formats réseaux (4:5) et A4 (PNG + PDF). Match d'ouverture N3 M et partenaire du match ajoutés tout seuls.</li>
  <li><b>Écran géant</b> : vidéos 1920 × 1080 de 10 s en boucle, une par Nationale.</li>
  <li><b>Écrire un article</b> : rédaction par IA (Gemini gratuit ou Claude), brouillon sur le site, vérification qu'il apparaît dans Actualités.</li>
  <li><b>Articles du site</b> : menu déroulant des derniers articles du site, pour les voir, les modifier ou les supprimer (corbeille ou définitivement avec leurs images).</li>
  <li><b>Publication auto</b> : choisis où elle se fait — <b>sur cet ordinateur</b> (allumé ou en veille, outil fermé, rattrapage au démarrage) ou <b>sur GitHub</b> (même ordinateur éteint) — puis active ou coupe les résultats (mardi 10 h) et le programme (mercredi 18 h), brouillon ou publication directe, « Publier maintenant ».</li>
  <li><b>Réglages</b> : connexion au site WordPress, clé IA, liste des équipes et liens FFHB.</li></ul></div>
 <div class="card"><h2>Astuces</h2><ul>
  <li><b>Changer de week-end</b> : flèches ◀ ▶ en haut, « À venir » ou « Dernier ».</li>
  <li><b>Actualiser</b> relit toutes les pages FFHB (environ 1 minute) ; la page reste utilisable pendant ce temps et se complète au fur et à mesure.</li>
  <li><b>Coupes de France</b> : rien à changer d'un tour à l'autre, l'outil suit les tours tout seul.</li>
  <li><b>Logos</b> : envoie-les depuis l'onglet Affiche, même avec un fond (blanc, couleur, damier) : il est retiré automatiquement.</li>
  <li><b>Photos d'affiche</b> : ajoute tes photos de match dans le dossier <span class="kbd">affiche/photos</span>.</li>
  <li><b>Partenaire du match</b> : fichier <span class="kbd">affiche/partenaires/partenaires_matchs.json</span> (date → logo).</li>
  <li><b>Sur téléphone</b> : onglet « Sur téléphone » sur l'ordinateur → active l'accès et scanne le QR code avec le téléphone (même Wi-Fi). L'ordinateur doit rester allumé avec l'outil ouvert.</li></ul></div>
 <div class="card"><h2>Publication automatique (GitHub)</h2>
  <p>Le dépôt GitHub publie tout seul les résultats le mardi à 10 h et le programme le mercredi à 18 h, <b>même ordinateur éteint</b>. Tu l'actives ou la coupes dans l'onglet <b>Publication auto</b>. Après une mise à jour de l'outil, remplace aussi <span class="kbd">ffhb_resultats.py</span> (et le dossier <span class="kbd">.github</span>) dans le dépôt.</p></div>
 <div class="card"><h2>En cas de problème</h2><ul>
  <li><b>Une équipe « à vérifier »</b> : le lien FFHB n'est plus le bon (nouvelle phase). Ouvre-le, choisis la bonne poule et colle le lien dans Réglages.</li>
  <li><b>Score non saisi</b> : le club adverse ne l'a pas encore entré sur la FFHB ; il apparaîtra à la prochaine lecture.</li>
  <li><b>Page FFHB illisible</b> : clique sur « Actualiser ». Si ça continue, zippe le dossier <span class="kbd">ffhb_debug</span> et envoie-le à Claude.</li>
  <li><b>L'outil ne s'ouvre pas</b> : relance « Lancer (Mac) » ou « Lancer (Windows) » ; la fenêtre noire doit rester ouverte pendant l'utilisation.</li></ul></div>
</div>`}
// ---- chargement des données, état, mises à jour en arrière-plan ----
function etat(){if(!data)return;const p=data.progression||{},enCours=data.maj_en_cours||data.salles_en_cours;
 const txt=enCours?(p.total?`Lecture FFHB : ${p.lus}/${p.total} équipe${p.total>1?"s":""}…`:"Mise à jour en cours…"):`À jour · lecture du ${esc(data.genere)}`;
 $("#etat").innerHTML=`<span class="pt ${enCours?"maj":""}"></span><span>${txt}</span>`;
 $("#sidemeta").innerHTML=`${esc(data.club||"")}<br>${txt}`;
 const auj=new Date().toISOString().slice(0,10);
 $("#wlabel").textContent=(offset===0?(auj>=data.du&&auj<=data.au?"Ce week-end : ":"Dernier : "):offset===-1?"À venir : ":offset<0?"Dans "+(-offset)+" sem. : ":"")+dd(data.du)+" → "+dd(data.au)}
let suivi=null,dernierLus=-1;
function surveille(){if(suivi)return;suivi=setInterval(async()=>{try{const e=await api("/api/etat");
  const lus=(e.progression||{}).lus||0;
  if(data){data.progression=e.progression;data.maj_en_cours=e.maj_en_cours;data.salles_en_cours=e.salles_en_cours;etat()}
  if(!e.maj_en_cours&&!e.salles_en_cours){clearInterval(suivi);suivi=null;dernierLus=-1;load(false,true);return}
  if(lus!==dernierLus){dernierLus=lus;if(lus>0)load(false,true)}}catch(x){}},2500)}
async function load(force,silencieux){const n=charge=(charge||0)+1;
 if(!silencieux){["club","all","post"].forEach(v=>{if(rendu[v]!==-1){rendu[v]=-1;sec(v).innerHTML='<div class="card loader"><div class="spin"></div>Chargement…</div>'}})}
 $("#refresh").disabled=$("#mrefresh").disabled=!!force;
 try{const d=await api(`/api/resultats?offset=${offset}${force?"&force=1":""}`);if(n!==charge)return;   // réponse d'un ancien clic : ignorée
  if(d.erreur)throw new Error(d.erreur);
  const chg=!data||d.du!==data.du;data=d;dataV++;etat();
  if(chg){vmode=null}
  if(["club","all","post","accueil"].includes(view))afficher(view);
  else if(view==="visuel"&&chg)renderVisuel();
  if(d.maj_en_cours||d.salles_en_cours)surveille()}
 catch(e){if(n!==charge)return;$("#etat").innerHTML=`<span class="pt" style="background:var(--loss)"></span><span class="err">${esc(e.message)}</span>`;
  ["club","all","post","accueil"].forEach(v=>{rendu[v]=-1;sec(v).innerHTML=`<div class="card err">Erreur : ${esc(e.message)}</div>`})}
 finally{if(n===charge){$("#refresh").disabled=$("#mrefresh").disabled=false;$("#next").disabled=offset<=-4}}}
function changerWE(o){if(o===offset)return;offset=Math.max(-4,Math.min(8,o));vmode=null;load()}
$("#prev").onclick=()=>changerWE(offset+1);$("#next").onclick=()=>changerWE(offset-1);
$("#avenir").onclick=()=>changerWE(-1);$("#dernier").onclick=()=>changerWE(0);
$("#refresh").onclick=$("#mrefresh").onclick=()=>{load(true);toast("Relecture de toutes les pages FFHB lancée : la page se complète au fur et à mesure.")};
construireChips();
api("/api/config").then(c=>{cfg=c;if(view==="cfg"&&!init.cfg){init.cfg=1;renderCfg()}}).catch(()=>{});
go((location.hash||"").slice(1)||LS.get("ffhb_vue","accueil"));
window.addEventListener("hashchange",()=>{const v=location.hash.slice(1);if(v&&v!==view)go(v)});
load();
</script></body></html>
"""


# ==========================================================================
# VERSION EN LIGNE (Hugging Face Spaces) : mot de passe, sauvegarde des changements, publication planifiée
# ==========================================================================
DONNEES_PERSO = ["ffhb_config.json", "ffhb_affiche.json", "ffhb_wordpress.json", "ffhb_auto_local.json",
                 "affiche/logos", "affiche/infos", "affiche/photos", "affiche/partenaires"]
_essais = {}


def mdp_cloud():
    return os.environ.get("FFHB_MOT_DE_PASSE", "").strip()


def jeton_cloud():
    import hashlib
    return hashlib.sha256(("crhb-outil|" + mdp_cloud()).encode()).hexdigest()[:40]


def _depot_donnees():
    return os.environ.get("FFHB_DATASET", "").strip(), os.environ.get("HF_TOKEN", "").strip()


def donnees_telecharger():
    """Au démarrage : récupère les changements sauvegardés (logos ajoutés, horaires, photos validées...)."""
    depot, tok = _depot_donnees()
    if not depot or not tok:
        print("Sauvegarde en ligne non configurée (FFHB_DATASET / HF_TOKEN) : les changements seront perdus au redémarrage.")
        return
    try:
        from huggingface_hub import HfApi, snapshot_download
        import shutil
        HfApi(token=tok).create_repo(depot, repo_type="dataset", private=True, exist_ok=True)
        tmp = snapshot_download(depot, repo_type="dataset", token=tok, local_dir=os.path.join(HERE, ".donnees_tmp"))
        n = 0
        for racine, _, fichiers in os.walk(tmp):
            if ".cache" in racine or ".git" in racine:
                continue
            for f in fichiers:
                src = os.path.join(racine, f)
                rel = os.path.relpath(src, tmp)
                if rel.startswith(".") or not any(rel == d or rel.startswith(d + "/") for d in DONNEES_PERSO):
                    continue
                os.makedirs(os.path.dirname(os.path.join(HERE, rel)) or HERE, exist_ok=True)
                shutil.copy2(src, os.path.join(HERE, rel))
                n += 1
        print(f"Sauvegarde en ligne récupérée : {n} fichier(s).")
    except Exception as e:
        print("Récupération de la sauvegarde impossible :", e)


def _fichiers_perso():
    out = {}
    for d in DONNEES_PERSO:
        p = os.path.join(HERE, d)
        if os.path.isfile(p):
            out[d] = os.path.getmtime(p)
        elif os.path.isdir(p):
            for racine, _, fichiers in os.walk(p):
                for f in fichiers:
                    q = os.path.join(racine, f)
                    out[os.path.relpath(q, HERE).replace(os.sep, "/")] = os.path.getmtime(q)
    return out


def boucle_sauvegarde():
    """Toutes les 30 s : envoie dans le dépôt privé les fichiers modifiés (un seul envoi groupé)."""
    depot, tok = _depot_donnees()
    if not depot or not tok:
        return
    from huggingface_hub import HfApi, CommitOperationAdd
    api = HfApi(token=tok)
    vus = _fichiers_perso()
    premier = True
    while True:
        time.sleep(30)
        try:
            maintenant = _fichiers_perso()
            changes = [k for k, t in maintenant.items() if premier and k.endswith(".json") or vus.get(k) != t]
            premier = False
            if changes:
                api.create_commit(depot, repo_type="dataset", commit_message=f"Outil CRHB : {len(changes)} fichier(s)",
                                  operations=[CommitOperationAdd(path_in_repo=k, path_or_fileobj=os.path.join(HERE, k))
                                              for k in changes])
            vus = maintenant
        except Exception as e:
            print("Sauvegarde en ligne :", e)


def boucle_publication_serveur():
    """En ligne : vérifie toutes les 5 minutes si une publication automatique est due."""
    time.sleep(60)
    while True:
        try:
            if load_config().get("auto_mode") == "local" and publications_dues():
                lancer_publications_dues("serveur en ligne")
        except Exception as e:
            print("Publication automatique :", e)
        time.sleep(300)


PAGE_MDP = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outil CRHB</title><link rel="apple-touch-icon" href="/logo.png"><meta name="theme-color" content="#061d4e">
<style>body{margin:0;font:16px system-ui;background:#061d4e;color:#fff;display:flex;min-height:100vh;align-items:center;justify-content:center}
form{background:#0d2a66;padding:28px 22px;border-radius:16px;width:min(340px,90vw);text-align:center}img{width:70px}
input{width:100%;box-sizing:border-box;font:16px system-ui;padding:13px;border-radius:10px;border:0;margin:14px 0}
button{width:100%;padding:13px;border:0;border-radius:10px;background:#fddc1d;color:#061d4e;font:700 16px system-ui}p{color:#c9d4ec;font-size:14px}.e{color:#ff9c90}</style></head>
<body><form method="post" action="/connexion"><img src="/logo.png" alt=""><h2>Outil CRHB</h2>__ERR__
<input type="password" name="mdp" placeholder="Mot de passe" autocomplete="current-password" autofocus><button>Entrer</button>
<p>Le mot de passe est celui choisi dans les réglages du serveur (secret FFHB_MOT_DE_PASSE).</p></form></body></html>"""


# ==========================================================================
# Accès depuis le téléphone (même Wi-Fi) : 2e serveur ouvert au réseau local, protégé par un code
# ==========================================================================
_mobile = {"srv": None, "port": None}
SECRETS = (("wordpress", "mot_de_passe"), ("github", "jeton"), ("claude", "cle"))


def mobile_cfg():
    m = load_config().get("acces_mobile") or {}
    return {"actif": bool(m.get("actif")), "code": m.get("code") or ""}


def ip_locale():
    import socket
    try:
        so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        so.connect(("192.168.1.1", 80))   # aucun envoi réel : sert à connaître l'adresse Wi-Fi de l'ordinateur
        ip = so.getsockname()[0]
        so.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def ensure_segno():
    try:
        import segno  # noqa: F401
        return True
    except ImportError:
        pass
    base = [sys.executable, "-m", "pip", "install", "segno"]
    for cmd in (base, base + ["--user"], base + ["--break-system-packages"]):
        if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            break
    import importlib, site
    importlib.invalidate_caches()
    try:
        sys.path.append(site.getusersitepackages())
        import segno  # noqa: F401
        return True
    except Exception:
        return False


def qr_svg(texte):
    if not ensure_segno():
        return ""
    import segno, io
    b = io.BytesIO()
    segno.make(texte, error="m").save(b, kind="svg", scale=6, border=2, dark="#061d4e", light="#ffffff")
    return b.getvalue().decode("utf-8")


def demarrer_mobile(port):
    if _mobile["srv"]:
        return None
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        return f"le port {port} est déjà utilisé ({e})"
    _mobile.update(srv=srv, port=port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return None


def arreter_mobile():
    srv = _mobile.get("srv")
    _mobile.update(srv=None)
    if srv:
        threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()


def mobile_etat(regenerer=False, actif=None):
    import secrets as _s
    cfg = load_config()
    m = cfg.get("acces_mobile") or {}
    if regenerer or not m.get("code"):
        m["code"] = f"{_s.randbelow(900000) + 100000}"
    if actif is not None:
        m["actif"] = bool(actif)
    cfg["acces_mobile"] = m
    save_config(cfg)
    port = (_mobile.get("port") or PORT_MOBILE)
    err = None
    if m.get("actif"):
        if regenerer:
            pass
        err = demarrer_mobile(port)
    else:
        arreter_mobile()
    adresse = f"http://{ip_locale()}:{port}"
    lien = f"{adresse}/?code={m['code']}"
    return {"actif": bool(m.get("actif")), "code": m["code"], "adresse": adresse, "lien": lien,
            "qr": qr_svg(lien) if m.get("actif") else "", "erreur": err,
            "systeme": "Windows" if os.name == "nt" else "Mac" if sys.platform == "darwin" else "Linux"}


PAGE_CODE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outil CRHB</title><style>body{margin:0;font:16px system-ui;background:#061d4e;color:#fff;display:flex;min-height:100vh;align-items:center;justify-content:center}
form{background:#0d2a66;padding:28px 22px;border-radius:16px;width:min(340px,90vw);text-align:center}img{width:70px}
input{width:100%;box-sizing:border-box;font:600 28px system-ui;letter-spacing:6px;text-align:center;padding:12px;border-radius:10px;border:0;margin:14px 0}
button{width:100%;padding:13px;border:0;border-radius:10px;background:#fddc1d;color:#061d4e;font:700 16px system-ui}p{color:#c9d4ec;font-size:14px}.e{color:#ff9c90}</style></head>
<body><form method="get" action="/"><img src="/logo.png" alt=""><h2>Outil CRHB</h2><p>Entre le code affiché sur l'ordinateur<br>(onglet « Sur téléphone »).</p>__ERR__
<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus><button>Ouvrir</button></form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local(self):
        if CLOUD:
            return False
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _ip(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def _autorise(self):
        """Ordinateur : toujours. Téléphone : seulement avec le bon code (cookie). En ligne : mot de passe."""
        if CLOUD:
            import http.cookies
            c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            return bool(mdp_cloud()) and "crhb_session" in c and c["crhb_session"].value == jeton_cloud()
        if self._local():
            return True
        m = mobile_cfg()
        if not m["actif"] or not m["code"]:
            return False
        import http.cookies
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return "crhb" in c and c["crhb"].value == m["code"]

    def _barriere(self):
        """Renvoie True si la requête a été traitée (page de code, redirection ou refus)."""
        u = urlparse(self.path)
        if u.path == "/ping":   # pour garder le serveur éveillé (cron-job.org)
            self._send(200, "ok", "text/plain")
            return True
        if self._autorise():
            return False
        if CLOUD:
            return self._barriere_cloud(u)
        q = parse_qs(u.query)
        m = mobile_cfg()
        if u.path == "/logo.png":
            return False
        if m["actif"] and q.get("code", [""])[0].strip() == m["code"]:
            self.send_response(302)
            self.send_header("Set-Cookie", f"crhb={m['code']}; Path=/; Max-Age=31536000; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return True
        if u.path.startswith("/api/"):
            self._send(401, json.dumps({"erreur": "accès refusé : rouvre l'outil avec le code"}), "application/json")
            return True
        err = '<p class="e">Code incorrect.</p>' if q.get("code") else ""
        if not m["actif"]:
            err = '<p class="e">L\'accès téléphone est désactivé sur l\'ordinateur.</p>'
        self._send(200, PAGE_CODE.replace("__ERR__", err), "text/html; charset=utf-8")
        return True

    def _barriere_cloud(self, u):
        if u.path == "/logo.png":
            return False
        err = ""
        if not mdp_cloud():
            err = '<p class="e">Mot de passe pas encore choisi : ajoute le secret FFHB_MOT_DE_PASSE dans les réglages du Space.</p>'
        elif u.path == "/connexion" and self.command == "POST":
            ip, t = self._ip(), time.time()
            essais = [x for x in _essais.get(ip, []) if t - x < 900]
            if len(essais) >= 10:
                err = '<p class="e">Trop d\'essais : réessaie dans 15 minutes.</p>'
            else:
                n = int(self.headers.get("Content-Length", 0) or 0)
                mdp = parse_qs(self.rfile.read(n).decode("utf-8")).get("mdp", [""])[0]
                import hmac
                if hmac.compare_digest(mdp.strip(), mdp_cloud()):
                    _essais.pop(ip, None)
                    self.send_response(303)
                    self.send_header("Set-Cookie", f"crhb_session={jeton_cloud()}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax")
                    self.send_header("Location", "/")
                    self.end_headers()
                    return True
                _essais[ip] = essais + [t]
                err = '<p class="e">Mot de passe incorrect.</p>'
        if u.path.startswith("/api/"):
            self._send(401, json.dumps({"erreur": "session expirée : recharge la page"}), "application/json")
            return True
        self._send(200, PAGE_MDP.replace("__ERR__", err), "text/html; charset=utf-8")
        return True

    def _send(self, code, body, ctype, headers=None):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self._barriere():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/mobile":
            if not self._local():
                return self._send(403, "{}", "application/json")
            return self._send(200, json.dumps(mobile_etat(), ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/":
            return self._send(200, PAGE.replace("__CLOUD__", "true" if CLOUD else "false", 1), "text/html; charset=utf-8")
        if u.path == "/api/etat":
            return self._send(200, json.dumps({"maj_en_cours": maj_en_cours(), "fin": _maj["fin"],
                                               "salles_en_cours": salles_en_cours(),
                                               "progression": dict(_progression)}), "application/json")
        if u.path == "/api/auto/local":
            return self._send(200, json.dumps(auto_local_etat(), ensure_ascii=False), "application/json; charset=utf-8")
        if u.path in ("/api/wp/articles", "/api/auto/etat"):
            try:
                if u.path == "/api/wp/articles":
                    out = {"articles": wp_articles()}
                else:
                    g = gh_config()
                    out = dict(auto_etat(), depot=g["depot"], jeton=bool(g["jeton"])) if g["depot"] and g["jeton"] \
                        else {"non_configure": True, "depot": g["depot"], "jeton": bool(g["jeton"])}
            except (WPErreur, GHErreur) as e:
                out = {"erreur": str(e.args[0]), "depot": gh_config()["depot"]}
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/logo.png":
            f = os.path.join(CHARTE_DIR, "logo.png")
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    return self._send(200, fh.read(), "image/png", {"Cache-Control": "max-age=86400"})
            return self._send(404, "", "text/plain")
        if u.path == "/api/config":
            c = load_config()
            if not self._local():   # le téléphone ne reçoit jamais les mots de passe ni les clés
                for sec_, cle in SECRETS:
                    if (c.get(sec_) or {}).get(cle):
                        c[sec_][cle] = ""
                if (c.get("ia") or {}).get("cles"):
                    c["ia"]["cles"] = {k: "" for k in c["ia"]["cles"]}
                c.pop("acces_mobile", None)
            return self._send(200, json.dumps(c, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/visuel.png":
            f = os.path.join(VISUELS_DIR, os.path.basename(q.get("f", [""])[0]))
            if not f.endswith(".png") or not os.path.exists(f):
                return self._send(404, "introuvable", "text/plain")
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "image/png", {"Cache-Control": "no-store"})
        if u.path == "/api/wp/categories":
            try:
                out = {"categories": wp_categories(), "defaut": wp_config().get("categorie", "")}
            except Exception as e:
                out = {"categories": [], "erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/ecran":
            try:
                out = generer_videos_ecran()
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/ecran/dernieres":
            e = _etat_affiche().get("ecran") or {}
            e["videos"] = [v for v in e.get("videos", []) if v.get("erreur") or os.path.exists(os.path.join(VISUELS_DIR, v.get("fichier", "")))]
            return self._send(200, json.dumps(dict(e, dossier=VISUELS_DIR), ensure_ascii=False), "application/json; charset=utf-8")
        if u.path in ("/api/visuel.mp4", "/api/visuel.jpg"):
            f = os.path.join(VISUELS_DIR, os.path.basename(q.get("f", [""])[0]))
            if not f.endswith(u.path[-4:]) or not os.path.exists(f):
                return self._send(404, "introuvable", "text/plain")
            data = open(f, "rb").read()
            ctype = "video/mp4" if f.endswith(".mp4") else "image/jpeg"
            plage = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
            if plage and f.endswith(".mp4"):   # lecture vidéo dans le navigateur (Safari exige les plages)
                a = int(plage.group(1) or 0)
                z = int(plage.group(2)) if plage.group(2) else len(data) - 1
                morceau = data[a:z + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {a}-{z}/{len(data)}")
                self.send_header("Content-Length", str(len(morceau)))
                self.end_headers()
                self.wfile.write(morceau)
                return
            h = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
            if q.get("dl"):
                h["Content-Disposition"] = f'attachment; filename="{os.path.basename(f)}"'
            return self._send(200, data, ctype, h)
        if u.path == "/api/affiche":
            try:
                chemin, det = generer_affiche(type_affiche="cdf" if q.get("type", [""])[0] == "cdf" else "n1",
                                              photo=q.get("photo", [""])[0] or None,
                                              relire=q.get("relire", ["1"])[0] != "0")
            except Exception as e:
                return self._send(200, json.dumps({"erreur": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")
            return self._send(200, json.dumps(det, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/affiche/derniere":
            t = "cdf" if q.get("type", [""])[0] == "cdf" else "n1"
            e = _etat_affiche()
            d = (e.get("dernieres_affiches") or {}).get(t) or \
                (e.get("derniere_affiche") if t == "n1" and not (e.get("derniere_affiche") or {}).get("type") else None)
            if d and d.get("fichier") and os.path.exists(os.path.join(VISUELS_DIR, d["fichier"])):
                d["photo_validee"] = (_etat_affiche().get("validees") or {}).get(d["date"]) == d.get("photo")
                return self._send(200, json.dumps(d, ensure_ascii=False), "application/json; charset=utf-8")
            return self._send(200, "{}", "application/json")
        if u.path in ("/api/affiche/valider", "/api/affiche/devalider"):
            try:
                out = valider_photo(q.get("date", [""])[0], q.get("photo", [""])[0], u.path.endswith("/valider"))
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/visuel.pdf":
            f = os.path.join(VISUELS_DIR, os.path.basename(q.get("f", [""])[0]))
            if not f.endswith(".pdf") or not os.path.exists(f):
                return self._send(404, "introuvable", "text/plain")
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "application/pdf",
                                  {"Content-Disposition": f'attachment; filename="{os.path.basename(f)}"'})
        if u.path in ("/api/resultats", "/api/csv", "/api/visuels"):
            cfg = load_config()
            off = max(-8, int(q.get("offset", ["0"])[0] or 0))  # négatif = week-ends à venir
            try:
                res = run_all(cfg, off, force=q.get("force", ["0"])[0] == "1", arriere_plan=True,
                              progressif=u.path == "/api/resultats")
            except Exception as e:
                return self._send(200, json.dumps({"erreur": str(e)}), "application/json")
            if u.path == "/api/visuels":
                try:
                    mode = "programme" if q.get("mode", [""])[0] == "programme" else "resultats"
                    theme = "jaune" if q.get("theme", [""])[0] == "jaune" else "bleu"
                    chemins = generer_visuels(res, mode, theme=theme)
                except Exception as e:
                    return self._send(200, json.dumps({"erreur": str(e)}), "application/json")
                return self._send(200, json.dumps({"fichiers": [os.path.basename(c) for c in chemins],
                                                   "dossier": VISUELS_DIR}, ensure_ascii=False),
                                  "application/json; charset=utf-8")
            if u.path == "/api/csv":
                return self._send(200, to_csv(res), "text/csv; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="resultats_{res["du"]}.csv"'})
            out = dict(res, texte=texte_reseaux(res, club_keys(cfg)))
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        self._send(404, "introuvable", "text/plain")

    def do_POST(self):
        if self._barriere():
            return
        if urlparse(self.path).path in ("/api/affiche/valider", "/api/affiche/devalider"):
            return self.do_GET()
        u = urlparse(self.path)
        q = parse_qs(u.query)
        n = int(self.headers.get("Content-Length", 0) or 0)
        corps = self.rfile.read(n).decode("utf-8") if n else ""
        if u.path == "/api/mobile":
            if not self._local():
                return self._send(403, "{}", "application/json")
            d = json.loads(corps or "{}")
            out = mobile_etat(bool(d.get("nouveau_code")), d.get("actif"))
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path in ("/api/github/config",) and not self._local():
            return self._send(200, json.dumps({"erreur": "en ligne : ajoute les secrets FFHB_GITHUB_DEPOT et FFHB_GITHUB_TOKEN dans le Space"
                                               if CLOUD else "à régler depuis l'ordinateur"}, ensure_ascii=False), "application/json")
        if u.path == "/api/auto/local":
            try:
                d = json.loads(corps or "{}")
                out = auto_local_regler(d.get("mode"), d.get("actif"), d.get("mode_auto"), d.get("statut"))
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/auto/local/maintenant":
            d = json.loads(corps or "{}")
            mode = "programme" if d.get("mode") == "programme" else "resultats"
            def tache():
                _auto_msg.clear()
                ligne = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "mode": mode, "source": "à la main"}
                try:
                    publication_auto(mode)
                    ligne.update(ok=True, message=_auto_msg.get("dernier", "fait"), lien=_auto_msg.get("lien"))
                except Exception as ex:
                    ligne.update(ok=False, message=str(ex)[:300])
                e = _auto_local_etat()
                e.setdefault("journal", []).append(ligne)
                _auto_local_sauver(e)
            threading.Thread(target=tache, daemon=True).start()
            return self._send(200, json.dumps({"lance": True}), "application/json")
        if u.path in ("/api/wp/supprimer", "/api/github/config", "/api/auto/regler", "/api/auto/lancer", "/api/auto/statut"):
            try:
                d = json.loads(corps or "{}")
                if u.path == "/api/wp/supprimer":
                    out = wp_supprimer_article(d.get("id"), bool(d.get("definitif")))
                elif u.path == "/api/github/config":
                    cfg = load_config()
                    g = cfg.get("github") or {}
                    g["depot"] = (d.get("depot") or "").strip()
                    if d.get("jeton"):
                        g["jeton"] = d["jeton"].strip()
                    cfg["github"] = g
                    save_config(cfg)
                    out = auto_etat()
                elif u.path == "/api/auto/regler":
                    out = auto_regler(d.get("mode"), bool(d.get("actif")))
                elif u.path == "/api/auto/statut":
                    out = auto_statut(d.get("statut"))
                else:
                    out = auto_lancer(d.get("mode"))
            except (WPErreur, GHErreur) as e:
                out = {"erreur": str(e.args[0])}
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/horaire":
            try:
                d = json.loads(corps or "{}")
                out = corriger_horaire(d.get("date", ""), d.get("dom", ""), d.get("ext", ""), d.get("heure", ""))
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path in ("/api/affiche/logo", "/api/affiche/infos"):
            try:
                d = json.loads(corps or "{}")
                if u.path.endswith("/logo"):
                    out = enregistrer_logo(d.get("nom", ""), d.get("data", ""), d.get("detourer", "auto"))
                else:
                    out = enregistrer_infos("cdf" if d.get("type") == "cdf" else "n1", d.get("date", ""),
                                            d.get("texte", ""), d.get("image"), bool(d.get("sans_image")))
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/ia/config":
            cfg = load_config()
            d = json.loads(corps or "{}")
            ia = cfg.get("ia") or {}
            ia["moteur"] = d.get("moteur", ia.get("moteur", "gemini"))
            ia.setdefault("cles", {}).update({k: v for k, v in (d.get("cles") or {}).items() if v})
            ia.setdefault("modeles", {}).update(d.get("modeles") or {})
            cfg["ia"] = ia
            save_config(cfg)
            return self._send(200, "{}", "application/json")
        if u.path == "/api/article/publier":
            try:
                out = publier_article(q.get("id", ["0"])[0])
            except Exception as e:
                out = {"erreur": str(e)}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path in ("/api/ia/test", "/api/article"):
            try:
                if u.path.endswith("test"):
                    out = ia_tester()
                else:
                    d = json.loads(corps or "{}")
                    out = creer_article(d.get("texte", ""), d.get("type", "match"), None, d.get("photos") or [],
                                       d.get("couverture", True))
            except (IAErreur, WPErreur) as e:
                out = {"erreur": str(e)}
            except Exception as e:
                out = {"erreur": f"{e.__class__.__name__} : {e}"}
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/wordpress/config":
            cfg = load_config()
            nouv = json.loads(corps or "{}")
            if not nouv.get("mot_de_passe"):
                nouv.pop("mot_de_passe", None)
            cfg["wordpress"] = dict(cfg.get("wordpress") or {}, **nouv)
            save_config(cfg)
            return self._send(200, "{}", "application/json")
        if u.path in ("/api/wordpress/test", "/api/wordpress/publier"):
            try:
                if u.path.endswith("test"):
                    out = wp_tester()
                else:
                    off = max(-8, int(q.get("offset", ["0"])[0] or 0))
                    mode = "programme" if q.get("mode", [""])[0] == "programme" else "resultats"
                    theme = "jaune" if q.get("theme", [""])[0] == "jaune" else "bleu"
                    out = wp_publier(run_all(load_config(), off, arriere_plan=True), mode, theme)
                return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
            except WPErreur as e:
                return self._send(200, json.dumps({"erreur": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(200, json.dumps({"erreur": f"{e.__class__.__name__} : {e}"}, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/config":
            # Réglages n'enregistre que le club et les équipes : le reste (accès, horaires corrigés,
            # publication auto...) est gardé tel quel
            d = json.loads(corps)
            cfg = load_config()
            cfg["club"] = d.get("club", cfg.get("club", ""))
            cfg["competitions"] = d.get("competitions", cfg.get("competitions", []))
            save_config(cfg)
            _charger_saisons().clear()
            return self._send(200, "{}", "application/json")
        self._send(404, "introuvable", "text/plain")


# ==========================================================================
# Point d'entrée
# ==========================================================================
def print_text(res, keys):
    fri, sun = date.fromisoformat(res["du"]), date.fromisoformat(res["au"])
    print(f"\nWeek-end du {fri:%d/%m/%Y} au {sun:%d/%m/%Y}\n")
    for c in res["competitions"]:
        print(f"== {c['nom']} — {c.get('titre', '')}")
        if c.get("erreur"):
            print("   Erreur :", c["erreur"]); continue
        for m in c["weekend"]:
            sc = f"{m['sd']:>2} - {m['se']:<2}" if m["sd"] is not None else " à venir"
            print(f"   {m['date'] or '':<10} {m['heure'] or '':<5}  {m['dom'][:32]:<32} {sc}  {m['ext']}")
        if not c["weekend"]:
            print("   (aucun match ce week-end)")
        print(f"   [{len(c['matchs'])} matchs lus, source : {c.get('source')}, {c.get('pages_lues')} page(s)]\n")
    print("---- Texte réseaux ----")
    print(texte_reseaux(res, keys))


def publication_auto(mode, heure_paris=None):
    from zoneinfo import ZoneInfo
    maintenant = datetime.now(ZoneInfo("Europe/Paris"))
    # GitHub lance 2 créneaux (heure d'été / d'hiver) et peut avoir du retard : on accepte H et H+1
    if heure_paris is not None and not (heure_paris <= maintenant.hour <= heure_paris + 1):
        print(f"Il est {maintenant:%H:%M} à Paris : hors du créneau prévu ({heure_paris}h), rien à faire.")
        _auto_msg["dernier"] = "hors créneau"
        return 0
    ensure_playwright()
    cfg = load_config()
    # du lundi au jeudi : résultats du week-end passé, programme du week-end suivant ;
    # vendredi : résultats du week-end passé, programme de ce week-end ; samedi-dimanche : ce week-end
    j = date.today().weekday()
    if mode == "resultats":
        offset = 1 if j == 4 else 0
    else:
        offset = 0 if j >= 4 else -1
    print(f"Lecture de la FFHB ({len(cfg['competitions'])} équipes)...")
    res = run_all(cfg, offset, force=True)
    print("Contrôle :", res["controle"])
    if not matchs_pour_visuel(res, mode):
        print("Aucun match du club à publier pour ce week-end : pas d'article.")
        _auto_msg["dernier"] = "aucun match du club ce week-end : pas d'article"
        return 0
    # déjà publié par le créneau précédent ? on ne republie pas
    ms = matchs_pour_visuel(res, mode)
    titre = ("Résultats du week-end – " if mode == "resultats" else "Programme du week-end – ") + titre_dates(res["du"], res["au"], ms).lower()
    try:
        from urllib.parse import quote
        wp = wp_config()
        for p in wp_requete(wp, "GET", f"posts?search={quote(titre)}&status=draft,publish,pending&context=edit&per_page=10") or []:
            if html_texte((p.get("title") or {}).get("raw", "")).strip() == titre:
                print(f"L'article « {titre} » existe déjà : rien à faire.")
                _auto_msg["dernier"] = f"« {titre} » était déjà sur le site"
                return 0
    except WPErreur as e:
        print("Vérification de l'article existant impossible :", e)
    out = wp_publier(res, mode, theme="bleu")
    print(f"{'Mis à jour' if out['mise_a_jour'] else 'Créé'} ({out['statut']}) : {out['titre']} -> {out['lien']}")
    _auto_msg["dernier"] = f"« {out['titre']} » {'publié' if out['statut'] == 'publish' else 'créé en brouillon'}"
    _auto_msg["lien"] = out.get("lien")
    return 0


# ==========================================================================
# Publication automatique SUR CET ORDINATEUR (sans GitHub)
# Le système (Planificateur de tâches Windows / launchd sur Mac) lance « --auto-local » le mardi à 10 h,
# le mercredi à 18 h et à l'ouverture de session ; l'outil n'a pas besoin d'être ouvert.
# Une publication ratée (ordinateur éteint) est rattrapée au prochain démarrage, jusqu'au jeudi soir.
# ==========================================================================
_auto_msg = {}
AUTO_LOCAL_ETAT = os.path.join(HERE, "ffhb_auto_local.json")
AUTO_LOCAL_LOG = os.path.join(HERE, "ffhb_auto.log")
NOM_TACHE = "Publication CRHB (outil FFHB)"
LAUNCHD_ID = "fr.crhb.outil-ffhb.publication"
HORAIRES_AUTO = {"resultats": (1, 10), "programme": (2, 18)}   # (jour : 0 = lundi, heure) — mardi 10 h, mercredi 18 h


def auto_local_cfg():
    a = load_config().get("auto_local") or {}
    return {"resultats": bool(a.get("resultats")), "programme": bool(a.get("programme"))}


def _auto_local_etat():
    try:
        return json.load(open(AUTO_LOCAL_ETAT, encoding="utf-8"))
    except Exception:
        return {"faits": {}, "journal": []}


def _auto_local_sauver(e):
    e["journal"] = e.get("journal", [])[-30:]
    with open(AUTO_LOCAL_ETAT, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=1)


def publications_dues(maintenant=None):
    """Publications à faire maintenant : créneau passé cette semaine, pas encore faite, avant vendredi."""
    maintenant = maintenant or datetime.now()
    lundi = (maintenant - timedelta(days=maintenant.weekday())).date()
    faits = _auto_local_etat().get("faits", {})
    actifs = auto_local_cfg()
    dues = []
    for mode, (jour, heure) in HORAIRES_AUTO.items():
        debut = datetime.combine(lundi + timedelta(days=jour), datetime.min.time()).replace(hour=heure)
        fin = datetime.combine(lundi + timedelta(days=4), datetime.min.time())   # jusqu'au jeudi soir
        cle = f"{mode}_{lundi.isoformat()}"
        if actifs[mode] and debut <= maintenant < fin and cle not in faits:
            dues.append((mode, cle))
    return dues


def lancer_publications_dues(source="planificateur"):
    """Fait les publications dues (une seule exécution à la fois). Renvoie la liste des messages."""
    verrou = os.path.join(HERE, "ffhb_auto.lock")
    try:
        if os.path.exists(verrou) and time.time() - os.path.getmtime(verrou) < 1800:
            return []
        open(verrou, "w").write(str(os.getpid()))
    except Exception:
        pass
    msgs = []
    try:
        for mode, cle in publications_dues():
            _auto_msg.clear()
            ligne = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "mode": mode, "source": source}
            try:
                publication_auto(mode)
                ligne.update(ok=True, message=_auto_msg.get("dernier", "fait"), lien=_auto_msg.get("lien"))
                e = _auto_local_etat()
                e.setdefault("faits", {})[cle] = ligne["date"]
            except Exception as ex:
                ligne.update(ok=False, message=str(ex)[:300])
                e = _auto_local_etat()   # échec : on réessaiera au prochain lancement
            e.setdefault("journal", []).append(ligne)
            _auto_local_sauver(e)
            msgs.append(ligne)
    finally:
        try:
            os.remove(verrou)
        except Exception:
            pass
    return msgs


def _python_sans_fenetre():
    exe = sys.executable
    if os.name == "nt":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            return w
    return exe


def _tache_xml():
    """Tâche Windows : mardi 10 h, mercredi 18 h, à l'ouverture de session ; réveille l'ordinateur ;
    rattrape une exécution manquée."""
    from xml.sax.saxutils import escape
    script = os.path.abspath(__file__)
    debut = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT")
    user = escape((os.environ.get("USERDOMAIN", "") + "\\" if os.environ.get("USERDOMAIN") else "") + os.environ.get("USERNAME", ""))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <RegistrationInfo><Description>Publie les résultats (mardi 10 h) et le programme (mercredi 18 h) sur le site du club.</Description></RegistrationInfo>
 <Triggers>
  <CalendarTrigger><StartBoundary>{debut}10:00:00</StartBoundary><ScheduleByWeek><DaysOfWeek><Tuesday/></DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>
  <CalendarTrigger><StartBoundary>{debut}18:00:00</StartBoundary><ScheduleByWeek><DaysOfWeek><Wednesday/></DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>
  <LogonTrigger><UserId>{user}</UserId><Delay>PT3M</Delay></LogonTrigger>
 </Triggers>
 <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
 <Settings><StartWhenAvailable>true</StartWhenAvailable><WakeToRun>true</WakeToRun><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
  <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT1H</ExecutionTimeLimit><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable></Settings>
 <Actions><Exec><Command>{escape(_python_sans_fenetre())}</Command><Arguments>"{escape(script)}" --auto-local</Arguments><WorkingDirectory>{escape(HERE)}</WorkingDirectory></Exec></Actions>
</Task>"""


def _plist_chemin():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHD_ID}.plist")


def planificateur_installe():
    if CLOUD:
        return True
    if os.name == "nt":
        return any(subprocess.call(["schtasks", "/Query", "/TN", n], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
                   for n in (NOM_TACHE, f"{NOM_TACHE} TUE"))
    if sys.platform == "darwin":
        return os.path.exists(_plist_chemin())
    return _cron_present()


def _cron_lignes():
    try:
        return subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
    except Exception:
        return []


def _cron_present():
    return any(LAUNCHD_ID in l for l in _cron_lignes())


def installer_planificateur(actif=True):
    """Ajoute (ou retire) la tâche planifiée du système. Renvoie un message d'erreur ou None."""
    if CLOUD:
        return None   # en ligne : le serveur vérifie lui-même toutes les 5 minutes (boucle_publication_serveur)
    script = os.path.abspath(__file__)
    try:
        if os.name == "nt":
            if not actif:
                for n in (NOM_TACHE, f"{NOM_TACHE} TUE", f"{NOM_TACHE} WED"):
                    subprocess.call(["schtasks", "/Delete", "/TN", n, "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return None
            xml = os.path.join(HERE, "ffhb_tache.xml")
            with open(xml, "w", encoding="utf-16") as f:
                f.write(_tache_xml())
            r = subprocess.run(["schtasks", "/Create", "/TN", NOM_TACHE, "/XML", xml, "/F"], capture_output=True, text=True)
            try:
                os.remove(xml)
            except Exception:
                pass
            if r.returncode == 0:
                return None
            # secours : deux tâches hebdomadaires simples (sans rattrapage à l'ouverture de session)
            cmd = f'"{_python_sans_fenetre()}" "{script}" --auto-local'
            ok = all(subprocess.call(["schtasks", "/Create", "/TN", f"{NOM_TACHE} {j}", "/TR", cmd, "/SC", "WEEKLY", "/D", j,
                                      "/ST", h, "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
                     for j, h in (("TUE", "10:00"), ("WED", "18:00")))
            return None if ok else (r.stderr or r.stdout or "échec de la création de la tâche").strip()
        if sys.platform == "darwin":
            plist = _plist_chemin()
            uid = str(os.getuid())
            subprocess.call(["launchctl", "bootout", f"gui/{uid}", plist], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not actif:
                if os.path.exists(plist):
                    os.remove(plist)
                return None
            import plistlib
            os.makedirs(os.path.dirname(plist), exist_ok=True)
            with open(plist, "wb") as f:
                plistlib.dump({"Label": LAUNCHD_ID, "ProgramArguments": [sys.executable, script, "--auto-local"],
                               "WorkingDirectory": HERE, "RunAtLoad": True,
                               "StartCalendarInterval": [{"Weekday": 2, "Hour": 10, "Minute": 0},
                                                         {"Weekday": 3, "Hour": 18, "Minute": 0}],
                               "StandardOutPath": AUTO_LOCAL_LOG, "StandardErrorPath": AUTO_LOCAL_LOG}, f)
            r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist], capture_output=True, text=True)
            if r.returncode != 0:
                r = subprocess.run(["launchctl", "load", "-w", plist], capture_output=True, text=True)
            return None if r.returncode == 0 else (r.stderr or "échec de launchctl").strip()
        # Linux : crontab
        lignes = [l for l in _cron_lignes() if LAUNCHD_ID not in l]
        if actif:
            cmd = f'cd "{HERE}" && "{sys.executable}" "{script}" --auto-local >> "{AUTO_LOCAL_LOG}" 2>&1 # {LAUNCHD_ID}'
            lignes += [f"0 10 * * 2 {cmd}", f"0 18 * * 3 {cmd}", f"@reboot {cmd}"]
        r = subprocess.run(["crontab", "-"], input="\n".join(lignes) + "\n", capture_output=True, text=True)
        return None if r.returncode == 0 else r.stderr.strip()
    except Exception as e:
        return str(e)


def auto_local_etat():
    e = _auto_local_etat()
    plat = "en ligne" if CLOUD else "Windows" if os.name == "nt" else "Mac" if sys.platform == "darwin" else "Linux"
    avert = ""
    if sys.platform == "darwin" and any(os.path.abspath(HERE).startswith(os.path.expanduser(d))
                                        for d in ("~/Documents", "~/Desktop", "~/Downloads")):
        avert = ("Sur Mac, la publication planifiée ne peut pas lire un dossier rangé dans Documents, Bureau ou "
                 "Téléchargements. Déplace le dossier de l'outil dans ton dossier personnel (Finder > Aller > Départ), "
                 "relance l'outil puis réactive l'interrupteur.")
    return {"modes": auto_local_cfg(), "planificateur": planificateur_installe(), "systeme": plat, "avertissement": avert,
            "statut_publication": (load_config().get("wordpress") or {}).get("statut", "draft"),
            "mode_auto": load_config().get("auto_mode", "github"),
            "journal": list(reversed(e.get("journal", [])))[:10], "dues": [m for m, _ in publications_dues()]}


def auto_local_regler(mode=None, actif=None, mode_auto=None, statut=None):
    cfg = load_config()
    if statut in ("draft", "publish"):
        cfg.setdefault("wordpress", {})["statut"] = statut
    a = cfg.get("auto_local") or {}
    if mode in HORAIRES_AUTO and actif is not None:
        a[mode] = bool(actif)
    cfg["auto_local"] = a
    if mode_auto in ("local", "github"):
        cfg["auto_mode"] = mode_auto
    save_config(cfg)
    besoin = cfg.get("auto_mode") == "local" and any(a.get(m) for m in HORAIRES_AUTO)
    err = installer_planificateur(besoin)
    out = auto_local_etat()
    if err:
        out["erreur"] = "le système n'a pas accepté la tâche planifiée : " + err
    return out


def lancer_en_ligne():
    """Serveur en ligne (Hugging Face Spaces) : écoute sur le port donné par l'hébergeur."""
    global CLOUD
    CLOUD = True
    os.environ["FFHB_CLOUD"] = "1"
    donnees_telecharger()
    threading.Thread(target=boucle_sauvegarde, daemon=True).start()
    threading.Thread(target=boucle_publication_serveur, daemon=True).start()
    try:
        lancer_maj(load_config())
    except Exception:
        pass
    port = int(os.environ.get("PORT", "7860"))
    srv = ThreadingHTTPServer((os.environ.get("FFHB_HOTE", "0.0.0.0"), port), Handler)
    print(f"Outil CRHB en ligne sur le port {port}" + ("" if mdp_cloud() else " — ATTENTION : secret FFHB_MOT_DE_PASSE manquant"))
    srv.serve_forever()


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Scores FFHB du dernier week-end")
    ap.add_argument("--texte", action="store_true", help="Affiche les résultats dans le terminal (sans page web)")
    ap.add_argument("--semaine", type=int, default=0, help="0 = dernier week-end, 1 = celui d'avant, ...")
    ap.add_argument("--voir", action="store_true", help="Montre le navigateur pendant la lecture")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--auto", choices=["resultats", "programme"],
                    help="Publication automatique : resultats = week-end passé, programme = week-end suivant")
    ap.add_argument("--heure-paris", type=int, default=None,
                    help="Ne publie que s'il est cette heure-là à Paris (gestion heure d'été / d'hiver)")
    ap.add_argument("--ecran", action="store_true", help="Crée les vidéos « Prochain match » pour l'écran géant")
    ap.add_argument("--affiche", action="store_true", help="Crée l'affiche du prochain match de N1 à domicile")
    ap.add_argument("--cloud", action="store_true", help="Version en ligne (Hugging Face) : serveur ouvert, mot de passe")
    ap.add_argument("--auto-local", action="store_true", help="Publication automatique planifiée sur cet ordinateur")
    ap.add_argument("--cdf", action="store_true", help="Avec --affiche : affiche du prochain match de Coupe de France de la N1")
    a = ap.parse_args()

    if a.auto_local:
        if not publications_dues():
            return 0
        try:   # sortie dans le journal (lancement sans fenêtre)
            sys.stdout = sys.stderr = open(AUTO_LOCAL_LOG, "a", encoding="utf-8", buffering=1)
            print(f"\n=== {datetime.now():%Y-%m-%d %H:%M} ===")
        except Exception:
            pass
        ensure_playwright()
        for m in lancer_publications_dues():
            print(m)
        return 0
    if a.ecran:
        ensure_playwright()
        print(json.dumps(generer_videos_ecran(), ensure_ascii=False, indent=1))
        return 0
    if a.affiche:
        ensure_playwright()
        chemin, det = generer_affiche(type_affiche="cdf" if a.cdf else "n1")
        print(json.dumps(det, ensure_ascii=False, indent=1))
        print("Affiche :", chemin)
        return 0
    if a.auto:
        return publication_auto(a.auto, a.heure_paris)
    if CLOUD or a.cloud:
        return lancer_en_ligne()

    ensure_playwright()
    check_browser()
    cfg = load_config()
    if a.texte:
        res = run_all(cfg, a.semaine, visible=a.voir, force=True)
        print_text(res, club_keys(cfg))
        print(f"\n(Détails de lecture : {DEBUG_DIR})")
        return
    try:   # la FFHB est relue dès le lancement : les résultats sont prêts quand la page s'ouvre
        lancer_maj(cfg)
    except Exception:
        pass
    if cfg.get("auto_mode") == "local" and publications_dues():   # publication ratée : rattrapage
        threading.Thread(target=lambda: lancer_publications_dues("rattrapage à l'ouverture de l'outil"), daemon=True).start()
    global PORT_MOBILE
    PORT_MOBILE = a.port + 1
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    if mobile_cfg()["actif"]:
        e = demarrer_mobile(PORT_MOBILE)
        print("Accès téléphone :", e or f"http://{ip_locale()}:{PORT_MOBILE}")
    url = f"http://localhost:{a.port}"
    print(f"FFHB Résultats est ouvert dans ton navigateur : {url}")
    print("Laisse cette fenêtre ouverte. Ctrl+C pour arrêter.")
    lancer_maj(load_config())  # mise à jour des scores dès l'ouverture, en arrière-plan
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
