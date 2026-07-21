# Rencontres colibre — boutons « Ajouter au calendrier » depuis OpenAgenda

## Contexte

Les rencontres colibre sont annoncées via [OpenAgenda](https://openagenda.com).
OpenAgenda reste la **source de vérité** : il offre la découvrabilité (agenda
public indexé/relayé) et une interface de saisie pratique, et évite à colibre
d'avoir à stocker les données d'événements.

Le problème : le parcours d'ajout au calendrier proposé par OpenAgenda est
fastidieux (Partager/Exporter → accordéon « Importer dans un calendrier
personnel » → choix du format). On veut présenter les prochaines rencontres
**dans l'interface colibre**, avec des boutons « Ajouter au calendrier » sur
mesure (Google, Outlook, `.ics`) qui fonctionnent en un clic.

Les données sont récupérées à la volée depuis l'API OpenAgenda. colibre ne
stocke aucune donnée d'événement.

## Emplacement : sous-section de `/a-propos/contact`

Plutôt que de créer une nouvelle page, on ajoute une section « Prochaines
rencontres » à la page existante `/a-propos/contact` (`src/pages/a_propos/contact.py`).
Cette page est un peu vide et a déjà du trafic — on la densifie sans nouvelle
route ni entrée dans `SECTIONS`.

## Architecture

Trois unités, chacune avec une responsabilité unique, plus une route.

| Unité                           | Rôle                                                                   | Dépend de                         |
| ------------------------------- | ---------------------------------------------------------------------- | --------------------------------- |
| `src/rencontres/openagenda.py`  | Récupérer + normaliser les événements (frontière API)                  | `httpx`, `flask_caching`          |
| `src/rencontres/calendrier.py`  | Fabriquer les liens Google/Outlook + le texte `.ics` (fonctions pures) | rien (stdlib)                     |
| `src/pages/a_propos/contact.py` | Afficher la section rencontres dans le layout existant                 | les deux modules ci-dessus        |
| Route `.ics` dans `src/app.py`  | Servir le fichier `.ics` d'un événement                                | `openagenda.py` + `calendrier.py` |

### `src/rencontres/openagenda.py` — frontière API

Calqué sur `src/roadmap/github.py` (même pattern httpx + `@cache.memoize`).

```python
@dataclass
class Evenement:
    uid: str
    titre: str
    debut: datetime          # timezone-aware (UTC)
    fin: datetime            # timezone-aware (UTC)
    lieu_nom: str | None
    lieu_ville: str | None
    description: str | None
    visio_url: str | None    # onlineAccessLink

@cache.memoize(timeout=3600)  # 1 h, comme github.py
def fetch_rencontres() -> list[Evenement]:
    ...
```

- Appel `httpx.get` sur
  `https://api.openagenda.com/v2/agendas/{OPENAGENDA_AGENDA_UID}/events`
  avec les paramètres :
  - `key={OPENAGENDA_API_KEY}`
  - filtre « à venir » : `timings[gte]=<maintenant ISO 8601>`
  - tri chronologique : `sort=timings.asc`
  - `detailed=1` (pour obtenir description, location, onlineAccessLink)
- **Normalisation** du JSON OpenAgenda vers `list[Evenement]` (mapping confirmé
  sur un payload réel, cf. `event.json` — l'endpoint liste renvoie
  `{"events": [ … ]}`, chaque élément ayant la même forme) :
  - `uid` → `uid` (entier dans le payload → cast `str`).
  - champs multilingues (`title`, `description`) sont des objets `{"fr": …}` →
    on extrait le français (avec repli sur la première langue disponible).
    `titre = title.fr` ; `description = description.fr` (le **court**, pas
    `longDescription`).
  - dates : on utilise `nextTiming` (déjà calculé par l'API = prochain créneau à
    venir) → `debut = nextTiming.begin`, `fin = nextTiming.end`. Les valeurs
    sont ISO 8601 **avec offset** (ex. `2026-07-27T10:00:00+02:00`), parsées via
    `datetime.fromisoformat`, puis converties en UTC pour les liens calendrier.
  - `location` : **peut être absent** (événements en ligne, `attendanceMode: 2`).
    Quand présent → `location.name`, `location.city` ; sinon `lieu_nom`/
    `lieu_ville = None` et l'affichage du lieu est omis.
  - `onlineAccessLink` → `visio_url` (peut être absent).
  - Réf. structure : <https://developers.openagenda.com/evenements/structure/>
- **Résilience** : toute erreur (réseau, quota, HTTP, parsing) est attrapée,
  loggée, et la fonction renvoie `[]` — la page ne plante jamais. Le cache 1 h
  absorbe la latence et le débit de l'API.

### `src/rencontres/calendrier.py` — fonctions pures

Aucune dépendance externe (pas de lib ICS). Trois fonctions prenant un
`Evenement`. **Lien visio** : quand `visio_url` est présent, il est ajouté au
**corps** de l'événement (`details` Google, `body` Outlook, `DESCRIPTION` ICS,
sous la forme `Visioconférence : <url>`) **en plus** de `location`/`URL`. Ainsi
la visio reste présente et cliquable dans les trois cibles même pour un
événement hybride (lieu physique + visio), où `location` porte l'adresse.

- `lien_google(ev) -> str` →
  `https://calendar.google.com/calendar/render?action=TEMPLATE&text=…&dates=…&details=…&location=…`
  Dates au format UTC `YYYYMMDDTHHMMSSZ`, séparées par `/`.
- `lien_outlook(ev) -> str` →
  `https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose&rru=addevent&subject=…&startdt=…&enddt=…&body=…&location=…`
  Dates au format ISO 8601.
- `ics_evenement(ev) -> str` → assemble un `VCALENDAR`/`VEVENT` à la main
  conforme à la RFC 5545 : `UID`, `DTSTART`, `DTEND`, `SUMMARY`, `DESCRIPTION`,
  `LOCATION`, `URL` (visio si présente). Échappement des caractères `,`, `;`,
  `\`, et des sauts de ligne selon la RFC. Fins de ligne `\r\n`.

Tous les paramètres d'URL sont `urllib.parse.quote`-és.

### `src/pages/a_propos/contact.py` — affichage

`layout()` appelle `fetch_rencontres()` et rend, **sous le bloc contact
actuel**, une section :

- Titre `## Prochaines rencontres`.
- Une carte `dbc.Card` par événement (liste verticale, déjà triée par date) :
  - titre, date/heure formatée en français, lieu (`nom — ville`) **si présent**,
  - description courte,
  - si `visio_url` : un lien « Rejoindre en visio »,
  - une ligne de 3 boutons : **Google Agenda** (`lien_google`), **Outlook**
    (`lien_outlook`), **`.ics`** (pointe vers `/rencontres/<uid>.ics`).
- Si `fetch_rencontres()` renvoie `[]` : message « Prochaines rencontres
  bientôt annoncées ».

Rendu directement dans le layout, **pas de callback** — le cache 1 h absorbe
le coût. Pas de lien vers la fiche OpenAgenda (choix produit).

### Route `.ics` dans `src/app.py`

Enregistrée sur `server` là où vivent déjà robots.txt / sitemap.xml :

```
GET /rencontres/<uid>.ics
  → ev = event d'uid <uid> dans fetch_rencontres() (cache), sinon 404
  → Response(ics_evenement(ev),
             mimetype="text/calendar",
             headers={"Content-Disposition": 'attachment; filename="rencontre.ics"'})
```

Servir le `.ics` par une route (plutôt qu'un lien `data:`) donne un vrai nom de
fichier et fonctionne partout, y compris sur mobile.

## Configuration

Deux variables dans `.env` (et `.template.env`) :

- `OPENAGENDA_API_KEY` — clé API OpenAgenda
- `OPENAGENDA_AGENDA_UID` — UID de l'agenda colibre

## Tests

- **`calendrier.py`** (cœur à ne pas casser, tests purs sans réseau) : à partir
  d'un `Evenement` fixture, vérifier le format des URLs Google et Outlook, et la
  conformité du `.ics` (présence et format de `DTSTART`/`DTEND`, échappement des
  caractères spéciaux, CRLF).
- **`openagenda.py`** : test de normalisation sur une fixture JSON figée à
  partir d'un payload réel (`event.json`), couvrant le cas d'un événement **en
  ligne sans `location`** → `list[Evenement]` attendue ; test que l'échec API
  (mock httpx qui lève) renvoie `[]`.
- **Route `.ics`** : uid connu → `200` + `text/calendar` ; uid inconnu → `404`.
- Pas de test Selenium (rendu statique de données mockées).

## Hors périmètre (YAGNI)

- Historique des rencontres passées (à venir uniquement).
- Image de couverture des événements.
- Boutons Apple/Yahoo dédiés (couverts par le `.ics`).
- Stockage local / fichier JSON / tâche de fond (le cache 1 h suffit).
