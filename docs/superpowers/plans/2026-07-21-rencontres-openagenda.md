# Rencontres OpenAgenda — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher les prochaines rencontres colibre (lues depuis l'API OpenAgenda) dans une section de `/a-propos/contact`, avec des boutons « Ajouter au calendrier » (Google, Outlook, `.ics`) en un clic.

**Architecture :** Un module frontière `src/rencontres/openagenda.py` récupère et normalise les événements (cache 1 h, `[]` si panne). Un module de fonctions pures `src/rencontres/calendrier.py` fabrique les liens Google/Outlook et le texte `.ics`. La page `contact.py` affiche une carte par événement ; une route Flask sert le `.ics`. colibre ne stocke aucune donnée d'événement.

**Tech Stack :** Python, Dash 4.4 + dash-bootstrap-components, `httpx`, `flask_caching` (déjà en place via `src.utils.cache`), stdlib (`datetime`, `urllib.parse`). Aucune nouvelle dépendance.

## Global Constraints

- Les imports internes commencent **toujours** par `src.` (ex. `from src.rencontres…`), jamais `rencontres…` ni `pages…`.
- Avant tout `git add`/`git commit`, lancer `pre-commit run --files <fichiers>` (ruff + prettier) — voir CLAUDE.md.
- Lancer les tests avec `uv run pytest <chemin>` (l'activation de venv n'est pas fiable ici).
- UI en français.
- Cache : réutiliser l'instance partagée `from src.utils.cache import cache`, `@cache.memoize(timeout=3600)` (1 h, comme `src/roadmap/github.py`).
- `Evenement` est le **seul** type qui franchit la frontière du module OpenAgenda : la page et `calendrier.py` ne touchent jamais au JSON brut.

Spec de référence : `docs/superpowers/specs/2026-07-21-rencontres-openagenda-design.md`.

## Structure des fichiers

| Fichier                                 | Responsabilité                                                                         |
| --------------------------------------- | -------------------------------------------------------------------------------------- |
| `src/rencontres/__init__.py`            | package (vide)                                                                         |
| `src/rencontres/openagenda.py`          | fetch + normalisation (frontière API, `dataclass Evenement`, cache 1 h, `[]` si panne) |
| `src/rencontres/calendrier.py`          | liens Google/Outlook + texte `.ics` (fonctions pures)                                  |
| `src/pages/a_propos/contact.py` (modif) | section « Prochaines rencontres » sous le bloc contact                                 |
| `src/app.py` (modif)                    | route `GET /rencontres/<uid>.ics`                                                      |
| `.template.env` (modif)                 | `OPENAGENDA_API_KEY`, `OPENAGENDA_AGENDA_UID`                                          |
| `tests/rencontres/*`                    | tests unitaires + route                                                                |

---

### Task 1: Module OpenAgenda — fetch + normalisation

**Files:**

- Create: `src/rencontres/__init__.py` (vide)
- Create: `src/rencontres/openagenda.py`
- Create: `tests/rencontres/__init__.py` (vide)
- Create: `tests/rencontres/conftest.py`
- Create: `tests/rencontres/event.json` (déplacé depuis la racine du dépôt)
- Test: `tests/rencontres/test_openagenda.py`
- Modify: `.template.env` (ajout des deux variables)

**Interfaces:**

- Produces:

  - `Evenement` dataclass : `uid: str`, `titre: str`, `debut: datetime` (timezone-aware, offset OpenAgenda), `fin: datetime` (idem), `lieu_nom: str | None`, `lieu_ville: str | None`, `description: str | None`, `visio_url: str | None`
  - `fetch_rencontres() -> list[Evenement]` (memoized 1 h ; `.uncached()` pour les tests)
  - `_normaliser(ev: dict) -> Evenement | None` (helper testé directement)

- [ ] **Step 1: Déplacer le payload réel en fixture de test**

Le fichier `event.json` (payload réel d'un événement) est à la racine du dépôt. Le déplacer :

```bash
mkdir -p tests/rencontres && mv event.json tests/rencontres/event.json
```

- [ ] **Step 2: Créer les `__init__.py` de package**

```bash
touch src/rencontres/__init__.py tests/rencontres/__init__.py
```

- [ ] **Step 3: Créer le conftest des tests rencontres**

Créer `tests/rencontres/conftest.py` (importe `src.app` en premier pour que la découverte `use_pages` enregistre chaque page/callback une seule fois — même raison que `tests/roadmap/conftest.py`) :

```python
# Importer l'app complète à la collecte : sa découverte use_pages enregistre
# chaque page (et ses @callback) exactement une fois. Voir tests/roadmap/conftest.py.
from src.app import app  # noqa: F401
```

- [ ] **Step 4: Écrire les tests qui échouent**

Créer `tests/rencontres/test_openagenda.py` :

```python
import json
from pathlib import Path

import httpx
import pytest

from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_EVENT = json.loads((Path(__file__).parent / "event.json").read_text())["event"]


def test_normaliser_evenement_en_ligne():
    ev = openagenda._normaliser(_EVENT)
    assert isinstance(ev, Evenement)
    assert ev.uid == "41344161"
    assert ev.titre == "Nouveautés decp.info/colibre et discussion libre"
    assert ev.description.startswith("Rencontre avec les utilisateurs")
    # nextTiming : 2026-07-27T10:00:00+02:00
    assert ev.debut.year == 2026 and ev.debut.hour == 10
    assert ev.debut.utcoffset().total_seconds() == 2 * 3600
    assert ev.fin.hour == 11
    # événement en ligne : pas de lieu
    assert ev.lieu_nom is None
    assert ev.lieu_ville is None
    assert ev.visio_url == "https://kmeet.infomaniak.com/0kywff4pcpetv425cfutesvz"


def test_fetch_rencontres_normalise_la_liste(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"events": [_EVENT]}

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", lambda *a, **k: _FakeResp())
    result = openagenda.fetch_rencontres.uncached()
    assert len(result) == 1
    assert result[0].uid == "41344161"


def test_fetch_rencontres_renvoie_liste_vide_si_api_echoue(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setenv("OPENAGENDA_API_KEY", "k")
    monkeypatch.setenv("OPENAGENDA_AGENDA_UID", "3512069")
    monkeypatch.setattr(openagenda.httpx, "get", _boom)
    assert openagenda.fetch_rencontres.uncached() == []


def test_fetch_rencontres_renvoie_liste_vide_si_non_configure(monkeypatch):
    monkeypatch.delenv("OPENAGENDA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAGENDA_AGENDA_UID", raising=False)
    assert openagenda.fetch_rencontres.uncached() == []
```

- [ ] **Step 5: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/rencontres/test_openagenda.py -v`
Expected: FAIL (`ModuleNotFoundError: src.rencontres.openagenda` ou `AttributeError`)

- [ ] **Step 6: Écrire le module**

Créer `src/rencontres/openagenda.py` :

```python
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from src.utils.cache import cache

logger = logging.getLogger(__name__)

_API_BASE = "https://api.openagenda.com/v2"


@dataclass
class Evenement:
    uid: str
    titre: str
    debut: datetime  # timezone-aware, offset OpenAgenda (non converti en UTC)
    fin: datetime
    lieu_nom: str | None
    lieu_ville: str | None
    description: str | None
    visio_url: str | None


def _fr(champ: dict | None) -> str | None:
    """Extrait le français d'un champ multilingue OpenAgenda ({'fr': …})."""
    if not champ:
        return None
    return champ.get("fr") or next(iter(champ.values()), None)


def _creneau(ev: dict) -> dict | None:
    """Prochain créneau : nextTiming (déjà calculé) sinon premier timing."""
    timing = ev.get("nextTiming")
    if timing:
        return timing
    timings = ev.get("timings") or []
    return timings[0] if timings else None


def _normaliser(ev: dict) -> Evenement | None:
    creneau = _creneau(ev)
    if not creneau:
        return None
    location = ev.get("location") or {}
    return Evenement(
        uid=str(ev["uid"]),
        titre=_fr(ev.get("title")) or "",
        debut=datetime.fromisoformat(creneau["begin"]),
        fin=datetime.fromisoformat(creneau["end"]),
        lieu_nom=location.get("name"),
        lieu_ville=location.get("city"),
        description=_fr(ev.get("description")),
        visio_url=ev.get("onlineAccessLink"),
    )


@cache.memoize(timeout=3600)
def fetch_rencontres() -> list[Evenement]:
    """Événements à venir de l'agenda colibre, normalisés. Cache 1 h.

    Appel à l'API OpenAgenda. Toute erreur (config manquante, réseau, quota,
    parsing) est loggée et renvoie [] : la page ne plante jamais.
    """
    key = os.getenv("OPENAGENDA_API_KEY", "")
    agenda = os.getenv("OPENAGENDA_AGENDA_UID", "")
    if not key or not agenda:
        logger.warning("OPENAGENDA_API_KEY / OPENAGENDA_AGENDA_UID non configurés")
        return []
    try:
        resp = httpx.get(
            f"{_API_BASE}/agendas/{agenda}/events",
            params={
                "key": key,
                "timings[gte]": datetime.now(timezone.utc).isoformat(),
                "sort": "timings.asc",
                "detailed": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json().get("events", [])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Récupération OpenAgenda échouée : %s", exc)
        return []
    resultats: list[Evenement] = []
    for ev in events:
        try:
            norm = _normaliser(ev)
        except (KeyError, ValueError) as exc:
            logger.warning("Événement OpenAgenda ignoré : %s", exc)
            continue
        if norm is not None:
            resultats.append(norm)
    return resultats
```

- [ ] **Step 7: Ajouter les variables à `.template.env`**

Ajouter à la fin de `.template.env` :

```bash
# OpenAgenda (section « Prochaines rencontres » sur /a-propos/contact)
OPENAGENDA_API_KEY=
OPENAGENDA_AGENDA_UID=
```

- [ ] **Step 8: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/rencontres/test_openagenda.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
pre-commit run --files src/rencontres/__init__.py src/rencontres/openagenda.py tests/rencontres/__init__.py tests/rencontres/conftest.py tests/rencontres/test_openagenda.py tests/rencontres/event.json .template.env
git add src/rencontres/__init__.py src/rencontres/openagenda.py tests/rencontres/__init__.py tests/rencontres/conftest.py tests/rencontres/test_openagenda.py tests/rencontres/event.json .template.env
git commit -m "feat(rencontres): module OpenAgenda (fetch + normalisation, cache 1h)"
```

---

### Task 2: Module calendrier — liens Google/Outlook + `.ics`

**Files:**

- Create: `src/rencontres/calendrier.py`
- Test: `tests/rencontres/test_calendrier.py`

**Interfaces:**

- Consumes: `Evenement` (de Task 1)
- Produces:

  - `lien_google(ev: Evenement) -> str`
  - `lien_outlook(ev: Evenement) -> str`
  - `ics_evenement(ev: Evenement) -> str` (texte `text/calendar`, lignes `\r\n`)

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/rencontres/test_calendrier.py` :

```python
from datetime import datetime, timedelta, timezone

from src.rencontres.calendrier import ics_evenement, lien_google, lien_outlook
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev(titre="Rencontre colibre", description="Discussion", visio="https://visio.example/xyz"):
    return Evenement(
        uid="42",
        titre=titre,
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),  # 08:00 UTC
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),  # 09:00 UTC
        lieu_nom=None,
        lieu_ville=None,
        description=description,
        visio_url=visio,
    )


def test_lien_google_convertit_en_utc():
    url = lien_google(_ev())
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert "action=TEMPLATE" in url
    # 10:00+02:00 -> 08:00Z ; les jetons compacts apparaissent littéralement
    assert "20260727T080000Z" in url
    assert "20260727T090000Z" in url
    # le lien visio est aussi dans le corps (details) — "Visioconf" et l'hôte
    # ne sont pas percent-encodés, ils apparaissent littéralement
    assert "Visioconf" in url
    assert "visio.example" in url


def test_lien_outlook_utilise_iso_utc():
    url = lien_outlook(_ev())
    assert url.startswith("https://outlook.live.com/calendar/0/deeplink/compose")
    assert "rru=addevent" in url
    # ISO UTC, encodé (les ':' deviennent %3A)
    assert "2026-07-27T08%3A00%3A00Z" in url
    # le lien visio est aussi dans le corps (body)
    assert "Visioconf" in url
    assert "visio.example" in url


def test_ics_structure_et_dates_utc():
    ics = ics_evenement(_ev())
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "\r\n" in ics
    assert "UID:42@colibre.fr" in ics
    assert "DTSTART:20260727T080000Z" in ics
    assert "DTEND:20260727T090000Z" in ics
    assert "SUMMARY:Rencontre colibre" in ics
    assert "URL:https://visio.example/xyz" in ics
    # le lien visio est aussi dans la DESCRIPTION
    assert "Visioconférence : https://visio.example/xyz" in ics


def test_visio_dans_le_corps_meme_avec_lieu_physique():
    # Cas hybride : lieu physique ET visio. La visio ne doit PAS être perdue.
    ev = _ev()
    ev.lieu_nom = "Mairie"
    ev.lieu_ville = "Nantes"
    google = lien_google(ev)
    assert "Nantes" in google  # location = lieu physique
    assert "visio.example" in google  # visio conservée dans le corps
    outlook = lien_outlook(ev)
    assert "visio.example" in outlook
    ics = ics_evenement(ev)
    assert "LOCATION:Mairie — Nantes" in ics
    assert "URL:https://visio.example/xyz" in ics
    assert "Visioconférence : https://visio.example/xyz" in ics  # dans DESCRIPTION


def test_ics_echappe_les_caracteres_speciaux():
    ics = ics_evenement(_ev(titre="Atelier, DECP; libre", description="a\nb"))
    assert "SUMMARY:Atelier\\, DECP\\; libre" in ics
    # description "a\nb" échappée en tête de DESCRIPTION (avant la ligne visio)
    assert "DESCRIPTION:a\\nb" in ics
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/rencontres/test_calendrier.py -v`
Expected: FAIL (`ModuleNotFoundError: src.rencontres.calendrier`)

- [ ] **Step 3: Écrire le module**

Créer `src/rencontres/calendrier.py` :

```python
from datetime import datetime, timezone
from urllib.parse import quote

from src.rencontres.openagenda import Evenement


def _compact_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lieu(ev: Evenement) -> str:
    return " — ".join(p for p in (ev.lieu_nom, ev.lieu_ville) if p)


def _query(params: dict[str, str]) -> str:
    return "&".join(f"{k}={quote(str(v))}" for k, v in params.items())


def _corps(ev: Evenement) -> str:
    """Corps de l'événement : description + lien visio (si présent).

    Le lien visio est ajouté ici — en plus de location/URL — pour qu'il soit
    présent et cliquable dans le corps des trois cibles, y compris pour un
    événement hybride (lieu physique + visio) où location porte l'adresse.
    """
    parties = []
    if ev.description:
        parties.append(ev.description)
    if ev.visio_url:
        parties.append(f"Visioconférence : {ev.visio_url}")
    return "\n\n".join(parties)


def lien_google(ev: Evenement) -> str:
    params = {
        "action": "TEMPLATE",
        "text": ev.titre,
        "dates": f"{_compact_utc(ev.debut)}/{_compact_utc(ev.fin)}",
        "details": _corps(ev),
        "location": _lieu(ev) or ev.visio_url or "",
    }
    return f"https://calendar.google.com/calendar/render?{_query(params)}"


def lien_outlook(ev: Evenement) -> str:
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": ev.titre,
        "startdt": _iso_utc(ev.debut),
        "enddt": _iso_utc(ev.fin),
        "body": _corps(ev),
        "location": _lieu(ev) or ev.visio_url or "",
    }
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{_query(params)}"


def _echapper(texte: str) -> str:
    # RFC 5545 : backslash d'abord, puis ; , et sauts de ligne.
    return (
        texte.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ics_evenement(ev: Evenement) -> str:
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//colibre//rencontres//FR",
        "BEGIN:VEVENT",
        f"UID:{ev.uid}@colibre.fr",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_compact_utc(ev.debut)}",
        f"DTEND:{_compact_utc(ev.fin)}",
        f"SUMMARY:{_echapper(ev.titre)}",
    ]
    corps = _corps(ev)
    if corps:
        lignes.append(f"DESCRIPTION:{_echapper(corps)}")
    lieu = _lieu(ev) or ev.visio_url
    if lieu:
        lignes.append(f"LOCATION:{_echapper(lieu)}")
    if ev.visio_url:
        lignes.append(f"URL:{ev.visio_url}")
    lignes += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lignes) + "\r\n"
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/rencontres/test_calendrier.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/rencontres/calendrier.py tests/rencontres/test_calendrier.py
git add src/rencontres/calendrier.py tests/rencontres/test_calendrier.py
git commit -m "feat(rencontres): liens Google/Outlook et génération .ics"
```

---

### Task 3: Route Flask `/rencontres/<uid>.ics`

**Files:**

- Modify: `src/app.py` (ajouter la route après la route `/llms.txt`, ~ligne 225)
- Test: `tests/rencontres/test_route_ics.py`

**Interfaces:**

- Consumes: `openagenda.fetch_rencontres()` (Task 1), `ics_evenement()` (Task 2)
- Produces: endpoint HTTP `GET /rencontres/<uid>.ics`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/rencontres/test_route_ics.py` :

```python
from datetime import datetime, timedelta, timezone

from src.app import app
from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev(uid="42"):
    return Evenement(
        uid=uid,
        titre="Rencontre colibre",
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),
        lieu_nom=None,
        lieu_ville=None,
        description="Discussion",
        visio_url="https://visio.example/xyz",
    )


def test_route_ics_uid_connu(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev("42")])
    resp = app.server.test_client().get("/rencontres/42.ics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/calendar"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert b"BEGIN:VCALENDAR" in resp.data


def test_route_ics_uid_inconnu(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev("42")])
    resp = app.server.test_client().get("/rencontres/999.ics")
    assert resp.status_code == 404
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/rencontres/test_route_ics.py -v`
Expected: FAIL (404 pour l'uid connu — la route n'existe pas encore)

- [ ] **Step 3: Ajouter la route dans `src/app.py`**

Repérer la route `/llms.txt` (`@app.server.route("/llms.txt")`, ~ligne 223-225). Juste **après** cette fonction, ajouter :

```python
# Fichier .ics d'une rencontre (voir src.rencontres). La route appelle
# openagenda.fetch_rencontres() via le module pour rester monkeypatchable.
from src.rencontres import openagenda as _openagenda  # noqa: E402
from src.rencontres.calendrier import ics_evenement as _ics_evenement  # noqa: E402


@app.server.route("/rencontres/<uid>.ics")
def rencontre_ics(uid: str):
    for ev in _openagenda.fetch_rencontres():
        if ev.uid == uid:
            return Response(
                _ics_evenement(ev),
                mimetype="text/calendar",
                headers={
                    "Content-Disposition": 'attachment; filename="rencontre.ics"'
                },
            )
    return Response("Not found", status=404)
```

(`Response` est déjà importé en tête de `src/app.py` : `from flask import Flask, Response, redirect`.)

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/rencontres/test_route_ics.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/app.py tests/rencontres/test_route_ics.py
git add src/app.py tests/rencontres/test_route_ics.py
git commit -m "feat(rencontres): route Flask /rencontres/<uid>.ics"
```

---

### Task 4: Section « Prochaines rencontres » dans `/a-propos/contact`

**Files:**

- Modify: `src/pages/a_propos/contact.py`
- Test: `tests/rencontres/test_contact_page.py`

**Interfaces:**

- Consumes: `openagenda.fetch_rencontres()` (Task 1), `lien_google`, `lien_outlook` (Task 2), route `.ics` (Task 3)
- Produces: section rendue dans le `layout()` existant (pas de nouvel export)

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/rencontres/test_contact_page.py` :

```python
from datetime import datetime, timedelta, timezone

from src.pages.a_propos import contact
from src.rencontres import openagenda
from src.rencontres.openagenda import Evenement

_PARIS = timezone(timedelta(hours=2))


def _ev():
    return Evenement(
        uid="42",
        titre="Rencontre colibre juillet",
        debut=datetime(2026, 7, 27, 10, 0, tzinfo=_PARIS),
        fin=datetime(2026, 7, 27, 11, 0, tzinfo=_PARIS),
        lieu_nom=None,
        lieu_ville=None,
        description="Discussion libre",
        visio_url="https://visio.example/xyz",
    )


def test_section_affiche_les_evenements(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [_ev()])
    rendu = str(contact.layout())
    assert "Prochaines rencontres" in rendu
    assert "Rencontre colibre juillet" in rendu
    assert "27 juillet 2026 à 10h00" in rendu
    assert "/rencontres/42.ics" in rendu
    assert "Rejoindre en visio" in rendu


def test_section_message_si_aucun_evenement(monkeypatch):
    monkeypatch.setattr(openagenda, "fetch_rencontres", lambda: [])
    rendu = str(contact.layout())
    assert "bientôt annoncées" in rendu
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/rencontres/test_contact_page.py -v`
Expected: FAIL (`AssertionError` — la section n'existe pas encore)

- [ ] **Step 3: Modifier `src/pages/a_propos/contact.py`**

Remplacer intégralement le contenu par (le bloc contact d'origine est conservé, la section rencontres est ajoutée dessous) :

```python
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.rencontres import openagenda
from src.rencontres.calendrier import lien_google, lien_outlook
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/contact",
    title="Contact | À propos | colibre",
    description="Contactez Colin Maudry, développeur de colibre.",
    image_url=META_CONTENT["image_url"],
)

_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _format_creneau(debut: datetime) -> str:
    return (
        f"{debut.day} {_MOIS[debut.month - 1]} {debut.year} "
        f"à {debut.hour}h{debut.minute:02d}"
    )


def _carte(ev) -> dbc.Card:
    corps = [
        html.H5(ev.titre, className="card-title"),
        html.P(_format_creneau(ev.debut), className="text-muted mb-1"),
    ]
    if ev.lieu_nom or ev.lieu_ville:
        lieu = " — ".join(p for p in (ev.lieu_nom, ev.lieu_ville) if p)
        corps.append(html.P(lieu, className="mb-1"))
    if ev.description:
        corps.append(html.P(ev.description))
    if ev.visio_url:
        corps.append(
            html.P(html.A("Rejoindre en visio", href=ev.visio_url, target="_blank"))
        )
    corps.append(
        html.Div(
            [
                dbc.Button(
                    "Google Agenda",
                    href=lien_google(ev),
                    target="_blank",
                    color="primary",
                    outline=True,
                    size="sm",
                    class_name="me-2",
                ),
                dbc.Button(
                    "Outlook",
                    href=lien_outlook(ev),
                    target="_blank",
                    color="primary",
                    outline=True,
                    size="sm",
                    class_name="me-2",
                ),
                dbc.Button(
                    ".ics",
                    href=f"/rencontres/{ev.uid}.ics",
                    color="secondary",
                    outline=True,
                    size="sm",
                ),
            ],
            className="mt-2",
        )
    )
    return dbc.Card(dbc.CardBody(corps), class_name="mb-3")


def _section_rencontres():
    evenements = openagenda.fetch_rencontres()
    if not evenements:
        return html.P(
            "Prochaines rencontres bientôt annoncées.", className="text-muted"
        )
    return html.Div([_carte(ev) for ev in evenements])


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Contact"),
            dcc.Markdown(
                """
- Chat en direct (💬 en bas à droite de l'écran)
- Email : [colin@colmo.tech](mailto:colin@colmo.tech)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""
            ),
            html.H2("Prochaines rencontres", className="mt-4"),
            _section_rencontres(),
        ]
    )
    return apropos_shell("contact", contenu)
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/rencontres/test_contact_page.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/a_propos/contact.py tests/rencontres/test_contact_page.py
git add src/pages/a_propos/contact.py tests/rencontres/test_contact_page.py
git commit -m "feat(rencontres): section Prochaines rencontres sur /a-propos/contact"
```

---

### Task 5: Vérification finale de la suite

**Files:** aucun (validation)

- [ ] **Step 1: Lancer toute la suite rencontres**

Run: `uv run pytest tests/rencontres/ -v`
Expected: PASS (12 tests : 4 openagenda + 4 calendrier + 2 route + 2 page)

- [ ] **Step 2: Lancer la suite complète (non-régression)**

Run: `uv run pytest`
Expected: aucune régression (mêmes résultats qu'avant la branche ; les tests Selenium existants requièrent Chrome).

---

## Self-Review (rempli par l'auteur du plan)

**Couverture de la spec :**

- Frontière API + normalisation + cache 1 h + `[]` si panne → Task 1 ✓
- Mapping confirmé (nextTiming, `title.fr`, `description.fr`, lieu optionnel, `onlineAccessLink`) → Task 1 (`_normaliser` + test sur `event.json`) ✓
- Liens Google/Outlook + `.ics` RFC 5545 + échappement → Task 2 ✓
- Route `.ics` `text/calendar`, 200/404 → Task 3 ✓
- Affichage sous le bloc contact, cartes, boutons, lien visio, état vide → Task 4 ✓
- Config `.env` → Task 1 Step 7 ✓
- Tests (unitaires + route, pas de Selenium) → Tasks 1-4 ✓
- Hors périmètre (passées, image, Apple/Yahoo, stockage local) → non implémentés ✓

**Cohérence des types :** `Evenement` (8 champs) défini en Task 1, réutilisé à l'identique en Tasks 2-4. `fetch_rencontres` / `lien_google` / `lien_outlook` / `ics_evenement` nommés de façon cohérente partout.

**Placeholders :** aucun — tout le code est complet.
