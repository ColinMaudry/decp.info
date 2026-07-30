# Pagination et rendu serveur des pages SEO — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre explorable sans JavaScript la chaîne qui va du sitemap aux 1,5 M de fiches marché, et rendre les fiches organisme réellement indexables sur les requêtes par nom.

**Architecture:** Les pages de liste (index d'organismes par département, listes de marchés par organisme) deviennent des routes Flask rendues côté serveur via un blueprint `src/seo/`, avec un gabarit Jinja partagé. Les pages Dash restent inchangées, mais leur `<title>`, `description`, `canonical` et JSON-LD minimal sont injectés côté serveur dans `interpolate_index`.

**Tech Stack:** Flask (blueprint + Jinja), DuckDB, Dash 4.4, flask-caching, pytest.

**Spec:** `docs/superpowers/specs/2026-07-30-pagination-pages-seo-design.md`

## Global Constraints

- Tous les modules s'importent avec le préfixe `src.` (`from src.db import ...`), jamais `from db import ...`.
- Interface en français : titres, textes, messages d'erreur, noms de tests.
- Avant tout `git add` ou `git commit`, exécuter `pre-commit run --files <fichiers>` pour que ruff formate.
- Les tests se lancent avec `uv run pytest`, jamais `pytest` seul.
- 100 entrées par page, exposé par la constante `PAGE_SIZE` dans `src/seo/pagination.py`. Les tests la monkeypatchent plutôt que de créer 100 lignes de données. L'accès se fait toujours par `pagination.PAGE_SIZE` : un `from src.seo.pagination import PAGE_SIZE` figerait la valeur à l'import et rendrait le monkeypatch inopérant.
- **La connexion DuckDB du processus est ouverte en lecture seule** (`src/db.py:218`, pour que plusieurs workers gunicorn partagent le fichier). Aucun test ne peut insérer via `get_cursor()`, et DuckDB refuse une seconde connexion en écriture sur le même fichier. Les tests qui ont besoin de données supplémentaires substituent le curseur — `monkeypatch.setattr("src.seo.queries.get_cursor", lambda: conn.cursor())` sur une base `:memory:` qu'ils peuplent — plutôt que de modifier `src/db.py` ou `_TEST_DATA` dans `tests/conftest.py`.
- Tout ajout de page publique doit être couvert par le sitemap ou listé dans les exclusions de `src/utils/sitemap.py` (le test-garde `test_sitemap_couvre_toutes_les_pages_publiques` ne voit que les pages Dash, pas les routes Flask).
- Ne pas introduire de mécanisme de cache concurrent de `flask-caching` : le backend Redis arrive par #123 puis #62.

## Structure des fichiers

| Fichier                        | Responsabilité                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `src/seo/__init__.py`          | package vide                                                                                                        |
| `src/seo/pagination.py`        | `PAGE_SIZE`, `parse_page()`, `page_count()` — arithmétique de pagination, sans dépendance à Flask ni DuckDB         |
| `src/seo/queries.py`           | requêtes DuckDB paginées : marchés d'un organisme, organismes d'un département                                      |
| `src/seo/routes.py`            | blueprint Flask `seo_bp` : les 4 routes SSR et les 2 redirections                                                   |
| `src/templates/seo_liste.html` | gabarit Jinja partagé par toutes les pages de liste                                                                 |
| `src/utils/page_meta.py`       | résolution `chemin → (titre, description)` via `dash._pages._path_to_page`, partagée par `app.py` et `not_found.py` |
| `tests/seo/`                   | nouveau package de tests (`__init__.py` requis)                                                                     |

`tests/cache/` est le répertoire de cache flask-caching (`CACHE_DIR=tests/cache` dans `pyproject.toml`), **pas** un package de tests. Ne rien y écrire.

## Ordre d'exécution

Task 1 → 2 → 3 → 4 → 5 → 6, puis 7 → 8, puis 9. Les tâches 7, 8 et 9 ne dépendent pas des précédentes et peuvent être faites en parallèle des autres si besoin.

---

### Task 1: Matérialiser `nb_marches` dans les tables d'organismes

**Files:**

- Modify: `src/db.py:160-169`
- Test: `tests/seo/test_tables_nb_marches.py` (créer), `tests/seo/__init__.py` (créer, vide)

**Interfaces:**

- Consumes: rien.
- Produces: les tables `acheteurs_departement` et `titulaires_departement` gagnent une colonne `nb_marches BIGINT`. Colonnes finales : `(acheteur_id, acheteur_nom, acheteur_departement_code, nb_marches)` et l'équivalent titulaire.

- [ ] **Step 1: Créer le package de tests**

```bash
mkdir -p tests/seo && touch tests/seo/__init__.py
```

- [ ] **Step 2: Écrire le test qui échoue**

Créer `tests/seo/test_tables_nb_marches.py` :

```python
"""Les tables d'index portent le nombre de marchés par organisme."""


def test_acheteurs_departement_a_nb_marches():
    from src.db import get_cursor

    rows = get_cursor().execute(
        "SELECT acheteur_id, nb_marches FROM acheteurs_departement "
        "WHERE acheteur_id = '123'"
    ).fetchall()
    assert rows == [("123", 1)]


def test_titulaires_departement_a_nb_marches():
    from src.db import get_cursor

    rows = get_cursor().execute(
        "SELECT titulaire_id, nb_marches FROM titulaires_departement "
        "WHERE titulaire_id = '345'"
    ).fetchall()
    assert rows == [("345", 1)]


def test_une_ligne_par_organisme_et_departement():
    """Le GROUP BY ne doit pas dupliquer les organismes."""
    from src.db import get_cursor

    total, distincts = get_cursor().execute(
        "SELECT COUNT(*), COUNT(DISTINCT (acheteur_id, acheteur_departement_code)) "
        "FROM acheteurs_departement"
    ).fetchone()
    assert total == distincts
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/seo/test_tables_nb_marches.py -v`
Expected: FAIL avec `Binder Error: Referenced column "nb_marches" not found`

- [ ] **Step 4: Implémenter**

Dans `src/db.py`, remplacer les deux `CREATE TABLE ... acheteurs_departement` / `titulaires_departement` (lignes 160-169) par :

```python
            w.execute(
                "CREATE TABLE acheteurs_departement AS "
                "SELECT acheteur_id, any_value(acheteur_nom) AS acheteur_nom, "
                "acheteur_departement_code, COUNT(DISTINCT uid) AS nb_marches "
                "FROM decp GROUP BY acheteur_id, acheteur_departement_code "
                "ORDER BY nb_marches DESC, acheteur_id"
            )
            w.execute(
                "CREATE TABLE titulaires_departement AS "
                "SELECT titulaire_id, any_value(titulaire_nom) AS titulaire_nom, "
                "titulaire_departement_code, COUNT(DISTINCT uid) AS nb_marches "
                "FROM decp GROUP BY titulaire_id, titulaire_departement_code "
                "ORDER BY nb_marches DESC, titulaire_id"
            )
```

`any_value(nom)` remplace le `DISTINCT` sur le nom : un même identifiant peut porter plusieurs graphies de raison sociale dans les données source, ce qui produirait sinon plusieurs lignes par organisme et fausserait la pagination.

Le `ORDER BY nb_marches DESC, acheteur_id` matérialise directement l'ordre d'affichage voulu (organismes les plus actifs en page 1) ; le second critère garantit le déterminisme en cas d'égalité.

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/seo/test_tables_nb_marches.py tests/test_seo.py -v`
Expected: PASS. `tests/test_seo.py` est inclus parce que `sitemap._org_ids` lit ces mêmes tables.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/db.py tests/seo/test_tables_nb_marches.py tests/seo/__init__.py
git add src/db.py tests/seo/test_tables_nb_marches.py tests/seo/__init__.py
git commit -m "Matérialise le nombre de marchés par organisme et département (#128)"
```

---

### Task 2: Arithmétique de pagination et gabarit partagé

**Files:**

- Create: `src/seo/__init__.py` (vide), `src/seo/pagination.py`, `src/templates/seo_liste.html`
- Test: `tests/seo/test_pagination.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `src.seo.pagination.PAGE_SIZE: int` (= 100)
  - `src.seo.pagination.parse_page(raw: str | None) -> int` — lève `ValueError` si invalide
  - `src.seo.pagination.page_count(total: int) -> int` — au moins 1
  - `src.seo.pagination.offset(page: int) -> int`
  - le gabarit `seo_liste.html` attend les variables : `titre`, `description`, `canonical`, `titre_h1`, `chapeau`, `entrees` (liste d'objets avec `.href`, `.libelle`, `.suffixe`, `.lien_secondaire`), `page`, `pages`, `url_page` (fonction `n -> url`), `retour_href`, `retour_libelle`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/seo/test_pagination.py` :

```python
"""Arithmétique de pagination des pages SEO."""

import pytest

from src.seo.pagination import PAGE_SIZE, offset, page_count, parse_page


def test_page_absente_vaut_un():
    assert parse_page(None) == 1


def test_page_valide():
    assert parse_page("3") == 3


@pytest.mark.parametrize("brut", ["0", "-1", "abc", "", "1.5", " 2"])
def test_page_invalide_leve_valueerror(brut):
    with pytest.raises(ValueError):
        parse_page(brut)


def test_page_count_arrondit_au_superieur():
    assert page_count(PAGE_SIZE + 1) == 2
    assert page_count(PAGE_SIZE) == 1


def test_page_count_vaut_au_moins_un_si_vide():
    assert page_count(0) == 1


def test_offset():
    assert offset(1) == 0
    assert offset(3) == 2 * PAGE_SIZE
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/seo/test_pagination.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.seo'`

- [ ] **Step 3: Implémenter le module**

```bash
mkdir -p src/seo src/templates && touch src/seo/__init__.py
```

Créer `src/seo/pagination.py` :

```python
"""Arithmétique de pagination des pages SEO rendues côté serveur.

Isolée de Flask et de DuckDB pour être testable seule. `PAGE_SIZE` est une
constante de module afin que les tests puissent la monkeypatcher plutôt que de
fabriquer des centaines de lignes de données.
"""

PAGE_SIZE = 100


def parse_page(raw: str | None) -> int:
    """Numéro de page depuis la query string.

    Lève `ValueError` sur toute valeur non strictement positive ou non
    numérique ; l'appelant traduit en 404.
    """
    if raw is None:
        return 1
    if not raw.isdigit():
        raise ValueError(f"numéro de page invalide : {raw!r}")
    page = int(raw)
    if page < 1:
        raise ValueError(f"numéro de page invalide : {raw!r}")
    return page


def page_count(total: int) -> int:
    """Nombre de pages nécessaires pour `total` entrées (au moins 1)."""
    return max(1, -(-total // PAGE_SIZE))


def offset(page: int) -> int:
    """OFFSET SQL correspondant à une page 1-indexée."""
    return (page - 1) * PAGE_SIZE
```

`"1.5".isdigit()` et `" 2".isdigit()` valent `False`, donc ces cas lèvent bien `ValueError`.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/seo/test_pagination.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Créer le gabarit Jinja**

Créer `src/templates/seo_liste.html` :

```html
<!DOCTYPE html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ titre }}</title>
    <meta name="description" content="{{ description }}" />
    <link rel="canonical" href="{{ canonical }}" />
    <link rel="stylesheet" href="/assets/css/bootstrap.simplex.css" />
    <link rel="stylesheet" href="/assets/css/style.css" />
  </head>
  <body>
    <div class="container py-4">
      <h1>{{ titre_h1 }}</h1>
      <p>{{ chapeau }}</p>
      <ul>
        {% for e in entrees %}
        <li>
          <a href="{{ e.href }}">{{ e.libelle }}</a>
          {%- if e.suffixe %} <span class="text-muted">{{ e.suffixe }}</span>{%
          endif %} {%- if e.lien_secondaire %} —
          <a href="{{ e.lien_secondaire }}">liste des marchés</a>{% endif %}
        </li>
        {% else %}
        <li>Aucun résultat.</li>
        {% endfor %}
      </ul>
      {% if pages > 1 %}
      <nav aria-label="Pagination">
        <p>Page {{ page }} sur {{ pages }}</p>
        <ul class="pagination">
          {% for n in range(1, pages + 1) %}
          <li class="page-item {% if n == page %}active{% endif %}">
            <a class="page-link" href="{{ url_page(n) }}">{{ n }}</a>
          </li>
          {% endfor %}
        </ul>
      </nav>
      {% endif %}
      <p><a href="{{ retour_href }}">{{ retour_libelle }}</a></p>
    </div>
  </body>
</html>
```

Le bloc `{% else %}` d'un `{% for %}` Jinja s'affiche quand la liste est vide : c'est le message du cas « organisme sans aucun marché » exigé par le spec.

Tous les numéros de page sont rendus en dur, sans fenêtre glissante : c'est volontaire, un crawler doit pouvoir atteindre la page N sans exécuter de JS. Pour les 154 pages de Ville de Paris cela reste quelques kilo-octets.

`server = Flask(__name__)` avec `__name__ == "src.app"`, donc Flask cherche ses gabarits dans `src/templates/` : aucune configuration à ajouter.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/seo/__init__.py src/seo/pagination.py src/templates/seo_liste.html tests/seo/test_pagination.py
git add src/seo/ src/templates/ tests/seo/test_pagination.py
git commit -m "Ajoute l'arithmétique de pagination et le gabarit des pages SEO (#128)"
```

---

### Task 3: Listes de marchés par organisme

**Files:**

- Create: `src/seo/queries.py`, `src/seo/routes.py`
- Modify: `src/app.py` (enregistrement du blueprint)
- Test: `tests/seo/test_liste_marches.py`

**Interfaces:**

- Consumes: `src.seo.pagination.{PAGE_SIZE, parse_page, page_count, offset}`
- Produces:

  - `src.seo.queries.marches_org(org_type: str, org_id: str, page: int) -> tuple[list[tuple[str, str]], int]` — renvoie `(lignes (uid, objet), total)`
  - `src.seo.queries.org_nom(org_type: str, org_id: str) -> str | None` — `None` si l'organisme est inconnu
  - `src.seo.routes.seo_bp: Blueprint`
  - routes `/acheteurs/<org_id>/marches` et `/titulaires/<org_id>/marches`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/seo/test_liste_marches.py` :

```python
"""Listes de marchés par organisme, rendues côté serveur."""

import pytest

from src.seo import pagination


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


@pytest.fixture
def acheteur_a_5_marches(monkeypatch):
    """5 marchés pour un acheteur dédié, sur une base DuckDB en mémoire.

    La connexion DuckDB du processus est ouverte en lecture seule
    (`src/db.py:218`) : insérer via `get_cursor()` lève
    `InvalidInputException`, et ouvrir une seconde connexion en écriture sur
    le même fichier est refusé par DuckDB. On substitue donc le curseur
    utilisé par les requêtes. La base meurt avec la fixture.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_marches "
        "(uid VARCHAR, objet VARCHAR, acheteur_id VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    conn.execute(
        "INSERT INTO acheteurs_departement VALUES ('999', 'ACHETEUR 999', '75', 5)"
    )
    for i in range(5):
        conn.execute(
            "INSERT INTO acheteurs_marches VALUES (?, ?, '999')",
            [f"uid-{i:02d}", f"Objet {i}"],
        )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: conn.cursor())
    yield "999"
    conn.close()


def test_liste_rendue_cote_serveur(client):
    """Le HTML servi contient les liens, sans exécution de JavaScript."""
    body = client.get("/acheteurs/123/marches").get_data(as_text=True)
    assert '<a href="/marches/1">' in body
    assert "Objet test" in body


def test_lien_de_retour_vers_la_fiche(client):
    body = client.get("/acheteurs/123/marches").get_data(as_text=True)
    assert '<a href="/acheteurs/123">' in body


def test_canonical_auto_referent_sur_page_2(client, acheteur_a_5_marches, monkeypatch):
    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    body = client.get("/acheteurs/999/marches?page=2").get_data(as_text=True)
    assert 'rel="canonical"' in body
    assert "/acheteurs/999/marches?page=2" in body


def test_pagination_deterministe(client, acheteur_a_5_marches, monkeypatch):
    """Deux pages consécutives ne partagent aucun uid et couvrent tout.

    C'est le défaut que la pagination introduirait sans ORDER BY : un même
    marché sur deux pages, un autre sur aucune.
    """
    import re

    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    vus = []
    for page in (1, 2, 3):
        body = client.get(f"/acheteurs/999/marches?page={page}").get_data(as_text=True)
        vus.extend(re.findall(r'href="/marches/(uid-\d+)"', body))
    assert len(vus) == len(set(vus)) == 5


def test_organisme_inconnu_404(client):
    assert client.get("/acheteurs/inexistant/marches").status_code == 404


@pytest.mark.parametrize("page", ["0", "abc", "-1"])
def test_page_invalide_404(client, page):
    assert client.get(f"/acheteurs/123/marches?page={page}").status_code == 404


def test_page_hors_limites_404(client):
    assert client.get("/acheteurs/123/marches?page=99").status_code == 404


def test_titulaire_aussi_servi(client):
    body = client.get("/titulaires/345/marches").get_data(as_text=True)
    assert '<a href="/marches/1">' in body
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/seo/test_liste_marches.py -v`
Expected: FAIL — toutes les routes répondent 404 (le catch-all Dash sert `assets/404.html`).

- [ ] **Step 3: Écrire les requêtes**

Créer `src/seo/queries.py` :

```python
"""Requêtes DuckDB paginées des pages SEO.

Toutes les requêtes portent un ORDER BY explicite : sans ordre déterministe,
LIMIT/OFFSET peut afficher une même ligne sur deux pages et en omettre une
autre.
"""

from src.db import get_cursor
from src.seo import pagination

_TABLES_MARCHES = {
    "acheteur": "acheteurs_marches",
    "titulaire": "titulaires_marches",
}
_TABLES_ORGS = {
    "acheteur": "acheteurs_departement",
    "titulaire": "titulaires_departement",
}


def marches_org(org_type: str, org_id: str, page: int) -> tuple[list, int]:
    """Marchés d'un organisme pour la page demandée, et total toutes pages."""
    table = _TABLES_MARCHES[org_type]
    cur = get_cursor()
    total = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {org_type}_id = ?", [org_id]
    ).fetchone()[0]
    rows = cur.execute(
        f"SELECT uid, objet FROM {table} WHERE {org_type}_id = ? "
        "ORDER BY uid LIMIT ? OFFSET ?",
        [org_id, pagination.PAGE_SIZE, pagination.offset(page)],
    ).fetchall()
    return rows, total


def org_nom(org_type: str, org_id: str) -> str | None:
    """Raison sociale d'un organisme, ou None s'il est inconnu."""
    table = _TABLES_ORGS[org_type]
    row = (
        get_cursor()
        .execute(
            f"SELECT {org_type}_nom FROM {table} WHERE {org_type}_id = ? LIMIT 1",
            [org_id],
        )
        .fetchone()
    )
    return row[0] if row else None
```

L'accès se fait **toujours** par `pagination.PAGE_SIZE`, jamais par `from src.seo.pagination import PAGE_SIZE` : un import direct fige la valeur au chargement du module, et le monkeypatch des tests ne serait pas vu. Même règle dans `routes.py` et dans le sitemap.

- [ ] **Step 4: Écrire le blueprint**

Créer `src/seo/routes.py` :

```python
"""Pages SEO rendues côté serveur.

Ces pages sont des listes de liens pures : aucune interactivité, aucun
graphique. Les servir en Flask plutôt qu'en pages Dash les rend explorables
par les crawlers qui n'exécutent pas de JavaScript — ce qui est leur unique
raison d'être. `src/not_found.py` documente le fait que les vraies routes
Flask échappent au catch-all de Dash.
"""

from flask import Blueprint, abort, render_template, request

from src.seo import pagination, queries

seo_bp = Blueprint("seo", __name__)

_LIBELLES = {
    "acheteur": ("attribués par", "acheteurs"),
    "titulaire": ("remportés par", "titulaires"),
}


class Entree:
    """Une ligne de liste. Attributs lus par `seo_liste.html`."""

    def __init__(self, href, libelle, suffixe=None, lien_secondaire=None):
        self.href = href
        self.libelle = libelle
        self.suffixe = suffixe
        self.lien_secondaire = lien_secondaire


def _marches_org(org_type: str, org_id: str):
    try:
        page = pagination.parse_page(request.args.get("page"))
    except ValueError:
        abort(404)

    nom = queries.org_nom(org_type, org_id)
    if nom is None:
        abort(404)

    rows, total = queries.marches_org(org_type, org_id, page)
    pages = pagination.page_count(total)
    if page > pages:
        abort(404)

    verbe, segment = _LIBELLES[org_type]
    base = f"/{segment}/{org_id}/marches"
    rang = f" (page {page} sur {pages})" if pages > 1 else ""

    return render_template(
        "seo_liste.html",
        titre=f"Les {total} marchés publics {verbe} {nom}{rang} | colibre",
        description=(
            f"Liste complète des {total} marchés publics {verbe} {nom}, "
            "publiée par colibre."
        ),
        canonical=request.base_url + (f"?page={page}" if page > 1 else ""),
        titre_h1=f"Marchés publics {verbe} {nom}",
        chapeau=f"{total} marchés publics {verbe} {nom}.",
        entrees=[
            Entree(href=f"/marches/{uid}", libelle=objet or uid) for uid, objet in rows
        ],
        page=page,
        pages=pages,
        url_page=lambda n: base if n == 1 else f"{base}?page={n}",
        retour_href=f"/{segment}/{org_id}",
        retour_libelle=f"Retour à la fiche de {nom}",
    )


@seo_bp.route("/acheteurs/<org_id>/marches")
def marches_acheteur(org_id: str):
    return _marches_org("acheteur", org_id)


@seo_bp.route("/titulaires/<org_id>/marches")
def marches_titulaire(org_id: str):
    return _marches_org("titulaire", org_id)
```

- [ ] **Step 5: Enregistrer le blueprint**

Dans `src/app.py`, juste **avant** la ligne `init_not_found(app.server)` (ligne 199), insérer :

```python
# Pages SEO rendues côté serveur (voir src/seo/routes.py). Enregistrées avant
# init_not_found pour être de vraies règles Flask, donc hors du catch-all Dash.
from src.seo.routes import seo_bp  # noqa: E402

app.server.register_blueprint(seo_bp)
```

- [ ] **Step 6: Lancer les tests**

Run: `uv run pytest tests/seo/ -v`
Expected: PASS (les 9 tests de `test_liste_marches.py` plus ceux des tâches 1 et 2)

- [ ] **Step 7: Vérifier qu'aucune page Dash n'est cassée**

Run: `uv run pytest tests/test_seo.py tests/test_page_loads.py tests/test_404.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
pre-commit run --files src/seo/queries.py src/seo/routes.py src/app.py tests/seo/test_liste_marches.py
git add src/seo/queries.py src/seo/routes.py src/app.py tests/seo/test_liste_marches.py
git commit -m "Sert les listes de marchés par organisme en HTML paginé (#128)"
```

---

### Task 4: Index d'organismes par département

**Files:**

- Modify: `src/seo/queries.py`, `src/seo/routes.py`
- Test: `tests/seo/test_index_departements.py`

**Interfaces:**

- Consumes: Task 3 (`seo_bp`, `Entree`, `queries`)
- Produces:

  - `src.seo.queries.orgs_departement(org_type: str, code: str | None, page: int) -> tuple[list[tuple[str, str, int]], int]` — lignes `(id, nom, nb_marches)`. `code=None` cible les organismes sans département.
  - routes `/departements`, `/departements/<code>/acheteurs`, `/departements/<code>/titulaires`
  - le segment réservé `non-renseigne` désigne les organismes sans département

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/seo/test_index_departements.py` :

```python
"""Index d'organismes par département, rendus côté serveur."""

import pytest

from src.seo import pagination


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


@pytest.fixture
def departement_99(monkeypatch):
    """3 acheteurs dans un département dédié, sur une base DuckDB en mémoire.

    La connexion DuckDB du processus est ouverte en lecture seule
    (`src/db.py:218`) : on ne peut donc PAS insérer via `get_cursor()`. On
    substitue le curseur utilisé par les requêtes, pas la base réelle — même
    précédent que `tests/seo/test_tables_nb_marches.py`. La base meurt avec la
    fixture, donc aucun nettoyage à faire.
    """
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE acheteurs_departement ("
        "acheteur_id VARCHAR, acheteur_nom VARCHAR, "
        "acheteur_departement_code VARCHAR, nb_marches BIGINT)"
    )
    for i, nb in enumerate([7, 3, 42]):
        conn.execute(
            "INSERT INTO acheteurs_departement VALUES (?, ?, '99', ?)",
            [f"org-{i}", f"ORGANISME {i}", nb],
        )
    monkeypatch.setattr("src.seo.queries.get_cursor", lambda: conn.cursor())
    yield "99"
    conn.close()


def test_hub_liste_les_departements(client):
    body = client.get("/departements").get_data(as_text=True)
    assert '<a href="/departements/75/acheteurs">' in body
    assert '<a href="/departements/75/titulaires">' in body


def test_index_porte_les_deux_liens_par_organisme(client):
    """Chaque ligne mène à la fiche ET à la liste de marchés."""
    body = client.get("/departements/75/acheteurs").get_data(as_text=True)
    assert '<a href="/acheteurs/123">' in body
    assert '<a href="/acheteurs/123/marches">' in body


def test_index_affiche_le_nombre_de_marches(client):
    body = client.get("/departements/75/acheteurs").get_data(as_text=True)
    assert "1 marché" in body


def test_tri_par_nombre_de_marches_decroissant(client, departement_99):
    body = client.get("/departements/99/acheteurs").get_data(as_text=True)
    assert body.index("ORGANISME 2") < body.index("ORGANISME 0") < body.index(
        "ORGANISME 1"
    )


def test_pagination_de_l_index(client, departement_99, monkeypatch):
    monkeypatch.setattr(pagination, "PAGE_SIZE", 2)
    page1 = client.get("/departements/99/acheteurs").get_data(as_text=True)
    page2 = client.get("/departements/99/acheteurs?page=2").get_data(as_text=True)
    assert "ORGANISME 2" in page1 and "ORGANISME 1" not in page1
    assert "ORGANISME 1" in page2


def test_departement_inconnu_404(client):
    assert client.get("/departements/zz/acheteurs").status_code == 404


def test_type_inconnu_404(client):
    assert client.get("/departements/75/autre").status_code == 404


def test_segment_non_renseigne_servi(client):
    """Les organismes sans département ont un chemin explorable."""
    assert client.get("/departements/non-renseigne/titulaires").status_code == 200
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/seo/test_index_departements.py -v`
Expected: FAIL — `/departements/75/acheteurs` répond 404, et `/departements` sert encore la coquille Dash.

- [ ] **Step 3: Ajouter la requête**

Ajouter à la fin de `src/seo/queries.py` :

```python
def orgs_departement(org_type: str, code: str | None, page: int) -> tuple[list, int]:
    """Organismes d'un département, triés par nombre de marchés décroissant.

    `code=None` cible les organismes sans département renseigné : la colonne
    vaut NULL, et `= ?` ne matche jamais NULL, d'où le IS NULL explicite.
    """
    table = _TABLES_ORGS[org_type]
    filtre = (
        f"{org_type}_departement_code IS NULL"
        if code is None
        else f"{org_type}_departement_code = ?"
    )
    params = [] if code is None else [code]
    cur = get_cursor()
    total = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {filtre}", params
    ).fetchone()[0]
    rows = cur.execute(
        f"SELECT {org_type}_id, {org_type}_nom, nb_marches FROM {table} "
        f"WHERE {filtre} ORDER BY nb_marches DESC, {org_type}_id "
        "LIMIT ? OFFSET ?",
        [*params, pagination.PAGE_SIZE, pagination.offset(page)],
    ).fetchall()
    return rows, total
```

- [ ] **Step 4: Ajouter les routes**

Ajouter à `src/seo/routes.py`, après les routes de marchés :

```python
from src.utils.data import DEPARTEMENTS  # à ajouter en haut du fichier

_SEGMENT_SANS_DEPARTEMENT = "non-renseigne"


@seo_bp.route("/departements")
def hub_departements():
    entrees = []
    for code, d in DEPARTEMENTS.items():
        entrees.append(
            Entree(
                href=f"/departements/{code}/acheteurs",
                libelle=f"{d['departement']} — acheteurs",
            )
        )
        entrees.append(
            Entree(
                href=f"/departements/{code}/titulaires",
                libelle=f"{d['departement']} — titulaires",
            )
        )
    entrees.append(
        Entree(
            href=f"/departements/{_SEGMENT_SANS_DEPARTEMENT}/acheteurs",
            libelle="Département non renseigné — acheteurs",
        )
    )
    entrees.append(
        Entree(
            href=f"/departements/{_SEGMENT_SANS_DEPARTEMENT}/titulaires",
            libelle="Département non renseigné — titulaires",
        )
    )
    return render_template(
        "seo_liste.html",
        titre="Marchés publics par département | colibre",
        description=(
            "Acheteurs publics et titulaires de marchés publics, "
            "classés par département."
        ),
        canonical=request.base_url,
        titre_h1="Marchés publics par département",
        chapeau=f"{len(DEPARTEMENTS)} départements.",
        entrees=entrees,
        page=1,
        pages=1,
        url_page=lambda n: "/departements",
        retour_href="/",
        retour_libelle="Retour à l'accueil",
    )


@seo_bp.route("/departements/<code>/<type_org>")
def index_departement(code: str, type_org: str):
    if type_org not in ("acheteurs", "titulaires"):
        abort(404)
    org_type = type_org[:-1]  # "acheteurs" -> "acheteur"

    if code == _SEGMENT_SANS_DEPARTEMENT:
        code_sql, nom_dept = None, "département non renseigné"
    elif code in DEPARTEMENTS:
        code_sql, nom_dept = code, DEPARTEMENTS[code]["departement"]
    else:
        abort(404)

    try:
        page = pagination.parse_page(request.args.get("page"))
    except ValueError:
        abort(404)

    rows, total = queries.orgs_departement(org_type, code_sql, page)
    pages = pagination.page_count(total)
    if page > pages:
        abort(404)

    base = f"/departements/{code}/{type_org}"
    rang = f" (page {page} sur {pages})" if pages > 1 else ""
    libelle_type = "Acheteurs publics" if org_type == "acheteur" else "Titulaires"

    return render_template(
        "seo_liste.html",
        titre=f"{libelle_type} de {nom_dept}{rang} | colibre",
        description=(
            f"Les {total} {libelle_type.lower()} de marchés publics "
            f"de {nom_dept}, avec leur nombre de marchés."
        ),
        canonical=request.base_url + (f"?page={page}" if page > 1 else ""),
        titre_h1=f"{libelle_type} de {nom_dept}",
        chapeau=f"{total} organismes dans {nom_dept}.",
        entrees=[
            Entree(
                href=f"/{type_org}/{org_id}",
                libelle=nom or org_id,
                suffixe=f"{nb} marché{'s' if nb > 1 else ''}",
                lien_secondaire=f"/{type_org}/{org_id}/marches",
            )
            for org_id, nom, nb in rows
        ],
        page=page,
        pages=pages,
        url_page=lambda n: base if n == 1 else f"{base}?page={n}",
        retour_href="/departements",
        retour_libelle="Retour à la liste des départements",
    )
```

La route `/departements/<code>/<type_org>` doit être déclarée **après** `/acheteurs/<org_id>/marches` : Flask ne route pas par ordre de déclaration mais par spécificité, donc l'ordre n'a en réalité pas d'importance ici, les préfixes étant disjoints.

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/seo/ -v`
Expected: PASS

`/departements` est encore servie par la page Dash `src/pages/arbre/departements.py` à ce stade : le blueprint est enregistré avant le catch-all Dash, donc c'est bien la route Flask qui répond. La page Dash devient morte et sera supprimée en Task 5.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/seo/queries.py src/seo/routes.py tests/seo/test_index_departements.py
git add src/seo/queries.py src/seo/routes.py tests/seo/test_index_departements.py
git commit -m "Sert les index d'organismes par département en HTML paginé (#128)"
```

---

### Task 5: Supprimer les pages Dash de l'arbre et poser les redirections

**Files:**

- Delete: `src/pages/arbre/departement.py`, `src/pages/arbre/departements.py`, `src/pages/arbre/liste_marches_org.py`
- Modify: `src/seo/routes.py`
- Test: `tests/seo/test_redirections.py`

**Interfaces:**

- Consumes: Tasks 3 et 4
- Produces: redirections 301 depuis les anciennes URLs. Plus aucune page Dash sous `/departements`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/seo/test_redirections.py` :

```python
"""Redirections depuis les anciennes URLs de l'arbre départemental."""

import pytest


@pytest.fixture(scope="module")
def client():
    from src.app import app

    return app.server.test_client()


def test_ancienne_liste_marches_301_vers_la_nouvelle(client):
    resp = client.get("/departements/06/acheteur/123")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/acheteurs/123/marches")


def test_ancienne_liste_marches_titulaire(client):
    resp = client.get("/departements/35/titulaire/345")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/titulaires/345/marches")


def test_ancienne_page_departement_301(client):
    resp = client.get("/departements/75")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/departements/75/acheteurs")


def test_type_inconnu_dans_l_ancienne_url_404(client):
    assert client.get("/departements/06/autre/123").status_code == 404


def test_plus_aucune_page_dash_sous_departements():
    from dash import page_registry

    chemins = {p["path"] for p in page_registry.values()}
    gabarits = {p.get("path_template") for p in page_registry.values()}
    assert not any(c.startswith("/departements") for c in chemins)
    assert not any(g and g.startswith("/departements") for g in gabarits)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/seo/test_redirections.py -v`
Expected: FAIL — les anciennes URLs répondent 200 (pages Dash encore présentes).

- [ ] **Step 3: Supprimer les pages Dash**

`src/pages/arbre/` ne contient que ces trois pages et un `__init__.py` vide : le répertoire entier disparaît.

```bash
git rm -r src/pages/arbre/
```

- [ ] **Step 4: Ajouter les redirections**

Ajouter à `src/seo/routes.py` :

```python
from flask import redirect  # à ajouter à l'import flask existant


@seo_bp.route("/departements/<code>/<org_type>/<org_id>")
def redirige_ancienne_liste(code: str, org_type: str, org_id: str):
    """L'ancien arbre plaçait la liste de marchés sous le département.

    Le segment `code` n'était déjà pas utilisé par l'ancien callback : la
    correspondance vers la nouvelle URL est donc exacte.
    """
    if org_type not in ("acheteur", "titulaire"):
        abort(404)
    return redirect(f"/{org_type}s/{org_id}/marches", code=301)


@seo_bp.route("/departements/<code>")
def redirige_ancien_departement(code: str):
    return redirect(f"/departements/{code}/acheteurs", code=301)
```

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/seo/ tests/test_404.py tests/test_page_loads.py -v`
Expected: PASS

- [ ] **Step 6: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS. La suppression de pages Dash a un rayon d'action large (registre de pages, sitemap, tests Selenium) : c'est le moment de tout vérifier.

- [ ] **Step 7: Commit**

```bash
pre-commit run --files src/seo/routes.py tests/seo/test_redirections.py
git add -A src/pages/arbre src/seo/routes.py tests/seo/test_redirections.py
git commit -m "Remplace l'arbre départemental Dash par les routes SSR et des 301 (#128)"
```

---

### Task 6: Déclarer les pages d'index dans le sitemap

**Files:**

- Modify: `src/utils/sitemap.py`, `src/app.py`
- Test: `tests/test_seo.py`

**Interfaces:**

- Consumes: Task 4 (routes d'index), Task 1 (`nb_marches`)
- Produces:

  - `src.utils.sitemap.build_arbre() -> str`
  - route `/sitemap-arbre.xml`
  - `/sitemap-arbre.xml` référencé dans `build_index()`

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_seo.py` :

```python
def test_sitemap_index_reference_l_arbre(client):
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "https://colibre.fr/sitemap-arbre.xml" in body


def test_sitemap_arbre_liste_le_hub_et_les_index(client):
    body = client.get("/sitemap-arbre.xml").get_data(as_text=True)
    assert "<loc>https://colibre.fr/departements</loc>" in body
    assert "<loc>https://colibre.fr/departements/75/acheteurs</loc>" in body


def test_sitemap_arbre_declare_chaque_page_paginee(monkeypatch):
    """Un département de plus d'une page déclare chacune de ses pages.

    On appelle `_arbre_locs.uncached` : la fonction est mémoïsée, donc un appel
    par la route renverrait un résultat calculé avec l'ancien PAGE_SIZE.
    """
    from src.seo import pagination
    from src.utils.sitemap import _arbre_locs

    monkeypatch.setattr(pagination, "PAGE_SIZE", 1)
    locs = _arbre_locs.uncached()
    assert "/departements" in locs
    assert "/departements/75/acheteurs" in locs


def test_sitemap_arbre_couvre_les_organismes_sans_departement(monkeypatch):
    from src.utils.sitemap import _arbre_locs

    locs = _arbre_locs.uncached()
    assert any("non-renseigne" in loc for loc in locs)


def test_sitemap_pages_ne_contient_pas_les_listes_de_marches(client):
    """Les listes de marchés sont atteignables depuis les index, pas déclarées."""
    body = client.get("/sitemap-pages.xml").get_data(as_text=True)
    assert "/marches" not in body
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_seo.py -v -k arbre`
Expected: FAIL — `/sitemap-arbre.xml` répond 404.

- [ ] **Step 3: Retirer `/departements` des exclusions**

Dans `src/utils/sitemap.py`, retirer la ligne suivante de `NON_INDEXABLE_PREFIXES` :

```python
    "/departements",  # navigation par arbre, on met en avant marchés et organismes
```

Le commentaire est devenu faux : l'arbre est désormais le maillage interne explorable vers les fiches organisme.

- [ ] **Step 4: Ajouter le constructeur du sous-sitemap**

Ajouter à `src/utils/sitemap.py` :

```python
@cache.memoize(timeout=3600 * 24)
def _arbre_locs() -> list[str]:
    """Chemins du hub et de toutes les pages d'index par département.

    Une entrée par page paginée : un crawler qui part du sitemap atteint
    chaque page d'index sans avoir à suivre la pagination.
    """
    from src.db import get_cursor
    from src.seo import pagination
    from src.utils.data import DEPARTEMENTS

    locs = ["/departements"]
    for org_type, segment in (("acheteur", "acheteurs"), ("titulaire", "titulaires")):
        table = f"{org_type}s_departement"
        rows = (
            get_cursor()
            .execute(
                f"SELECT {org_type}_departement_code, COUNT(*) FROM {table} GROUP BY 1"
            )
            .fetchall()
        )
        for code, total in rows:
            segment_code = code if code in DEPARTEMENTS else "non-renseigne"
            base = f"/departements/{segment_code}/{segment}"
            for n in range(1, pagination.page_count(total) + 1):
                locs.append(base if n == 1 else f"{base}?page={n}")
    return locs


def build_arbre() -> str:
    """Sous-sitemap du hub et des index d'organismes par département."""
    return _urlset([f"{BASE_URL}{loc}" for loc in _arbre_locs()])
```

Un `code` valant `None` (organismes sans département) n'appartient pas à `DEPARTEMENTS`, donc bascule sur le segment `non-renseigne` — comme un code inattendu qui serait présent dans les données sans l'être dans `data/departements.json`.

- [ ] **Step 5: Référencer le sous-sitemap dans l'index**

Dans `build_index()`, remplacer la ligne `children = ["/sitemap-pages.xml"]` par :

```python
    children = ["/sitemap-pages.xml", "/sitemap-arbre.xml"]
```

- [ ] **Step 6: Ajouter la route Flask**

Dans `src/app.py`, après la route `sitemap_pages` :

```python
@app.server.route("/sitemap-arbre.xml")
def sitemap_arbre():
    return Response(_sitemap.build_arbre(), mimetype="application/xml")
```

- [ ] **Step 7: Lancer les tests**

Run: `uv run pytest tests/test_seo.py tests/seo/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
pre-commit run --files src/utils/sitemap.py src/app.py tests/test_seo.py
git add src/utils/sitemap.py src/app.py tests/test_seo.py
git commit -m "Déclare le hub et les index départementaux dans le sitemap (#128)"
```

---

### Task 7: Rendre `<title>`, `description` et `canonical` côté serveur

**Files:**

- Create: `src/utils/page_meta.py`
- Modify: `src/app.py` (index_string, interpolate_index, ProxyFix), `src/not_found.py`, `src/pages/acheteur.py`, `src/pages/titulaire.py`, `src/pages/marche.py`
- Test: `tests/test_seo.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `src.utils.page_meta.resolve(path: str) -> tuple[str | None, str | None]` — `(titre, description)` résolus pour un chemin, `(None, None)` si le chemin ne correspond à aucune page Dash
  - `src.utils.page_meta.page_for_path(path: str) -> tuple[dict, dict | None]` — accès brut à `_path_to_page`, utilisé par `not_found.py`
  - `src.pages.acheteur.get_description(acheteur_id)` et l'équivalent titulaire/marché

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_seo.py` :

```python
def test_title_servi_contient_le_nom_de_l_organisme(client):
    """Le <title> est le signal principal pour une requête « nom d'organisme »."""
    import re

    from src.utils.data import DF_ACHETEURS

    org_id = DF_ACHETEURS.item(0, "acheteur_id")
    nom = DF_ACHETEURS.item(0, "acheteur_nom")
    body = client.get(f"/acheteurs/{org_id}").get_data(as_text=True)
    titre = re.findall(r"<title>(.*?)</title>", body)[0]
    assert nom in titre


def test_title_generique_hors_page_connue(client):
    import re

    body = client.get("/").get_data(as_text=True)
    assert re.findall(r"<title>(.*?)</title>", body)[0]


def test_descriptions_distinctes_entre_deux_organismes(client):
    import re

    def description(url):
        body = client.get(url).get_data(as_text=True)
        return re.findall(r'<meta name="description" content="(.*?)"', body)[0]

    assert description("/acheteurs/123") != description("/titulaires/345")


def test_canonical_servi_dans_le_html(client):
    """Plus de href posé par JavaScript : la balise est servie remplie."""
    body = client.get("/tableau").get_data(as_text=True)
    assert 'rel="canonical" href="http://localhost/tableau"' in body


def test_canonical_ignore_la_query_string(client):
    body = client.get("/tableau?acheteur=X").get_data(as_text=True)
    assert 'href="http://localhost/tableau"' in body
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_seo.py -v -k "title or description or canonical"`
Expected: FAIL — `<title>` vaut `Colibre`, les descriptions sont identiques, le canonical n'a pas de `href`.

- [ ] **Step 3: Créer le module de résolution**

Créer `src/utils/page_meta.py` :

```python
"""Résolution chemin → métadonnées de page Dash, côté serveur.

Dash résout déjà titre et description par requête pour ses balises sociales
(`dash/_pages.py:_page_meta_tags`), mais passe `app.title` à `{%title%}` : le
`<title>` servi est donc générique sur toutes les pages. Ce module rejoue la
même résolution pour qu'`app.py` puisse la poser dans le HTML.

`_path_to_page` est une API privée de Dash, assumée : c'est la fonction que
Dash utilise lui-même pour router, et `src/not_found.py` s'y appuie déjà. Les
tests épinglent son comportement, donc une montée de version qui la
déplacerait casse la CI avant le déploiement.
"""

from dash._pages import _path_to_page


def page_for_path(path: str):
    """(page, variables de chemin) pour un chemin de requête."""
    return _path_to_page(path.strip("/"))


def resolve(path: str) -> tuple[str | None, str | None]:
    """(titre, description) résolus pour un chemin, (None, None) si inconnu."""
    page, path_variables = page_for_path(path)
    if not page:
        return None, None

    def _call(value):
        if not callable(value):
            return value
        return value(**path_variables) if path_variables else value()

    return _call(page.get("title")), _call(page.get("description"))
```

- [ ] **Step 4: Faire pointer `not_found.py` sur le module partagé**

Dans `src/not_found.py`, remplacer l'import :

```python
from dash._pages import _path_to_page
```

par :

```python
from src.utils.page_meta import page_for_path
```

et dans `page_exists`, remplacer :

```python
    page, _ = _path_to_page(pathname.strip("/"))
```

par :

```python
    page, _ = page_for_path(pathname)
```

Adapter le commentaire au-dessus de l'import pour renvoyer vers `src/utils/page_meta.py`, qui porte désormais la justification de l'API privée.

- [ ] **Step 5: Poser title et canonical dans l'index**

Dans `src/app.py`, **supprimer entièrement** de `index_string` le commentaire, la balise canonical vide et le script qui la remplit (lignes 303-311) — de `<!-- canonical auto-référent ...` jusqu'à `</script>` inclus. Aucun marqueur ne les remplace : `index_string` n'accepte que les marqueurs de Dash (`{%metas%}`, `{%title%}`…), et le canonical passe désormais par `metas`.

Puis, dans `_interpolate_index_per_request`, après le calcul de `og_url_tag` :

```python
    from src.utils.page_meta import resolve

    titre, _description = resolve(_request.path)
    if titre:
        kwargs["title"] = str(_escape(titre))

    canonical_tag = (
        f'<link rel="canonical" href="{_escape(_request.base_url)}"/>'
    )
    kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {canonical_tag}"
```

Deux points :

- `request.base_url` est l'URL sans query string, exactement ce que calculait le script JavaScript supprimé.
- La description n'est pas posée ici : Dash l'émet déjà par requête via `_page_meta_tags`, et elle deviendra spécifique dès que les pages déclareront une description callable (Step 7). La récupérer ici ne servirait qu'à la dupliquer.

- [ ] **Step 6: Ajouter ProxyFix**

Dans `src/app.py`, juste après `server = Flask(__name__)` :

```python
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

# nginx transmet X-Forwarded-Proto (voir deploy/nginx-colibre.conf) ; sans ce
# middleware Flask croit servir en http et le canonical pointerait vers une URL
# qui redirige.
server.wsgi_app = ProxyFix(server.wsgi_app, x_proto=1, x_host=1)
```

- [ ] **Step 7: Rendre les descriptions dynamiques**

Dans `src/pages/acheteur.py`, ajouter après `get_title` :

```python
def get_description(acheteur_id: str | None = None) -> str:
    row = DF_ACHETEURS.filter(pl.col("acheteur_id") == acheteur_id)
    if row.height == 0:
        return "Consultez les marchés publics attribués par cet acheteur."
    nom = row.select("acheteur_nom").item(0, 0)
    return (
        f"Les marchés publics attribués par {nom} : objets, montants, "
        "titulaires, dates de notification."
    )
```

et remplacer dans `register_page` :

```python
    description=get_description,
```

Dans `src/pages/titulaire.py`, ajouter après `get_title` :

```python
def get_description(titulaire_id: str | None = None) -> str:
    row = DF_TITULAIRES.filter(pl.col("titulaire_id") == titulaire_id)
    if row.height == 0:
        return "Consultez les marchés publics remportés par ce titulaire."
    nom = row.select("titulaire_nom").item(0, 0)
    return (
        f"Les marchés publics remportés par {nom} : objets, montants, "
        "acheteurs, dates de notification."
    )
```

et remplacer dans son `register_page` :

```python
    description=get_description,
```

Dans `src/pages/marche.py`, `get_title` vaut `f"Marché {uid} | colibre"` et n'interroge pas les données. Ajouter après lui :

```python
def get_description(uid: str = None) -> str:
    return (
        f"Détail du marché public {uid} : montant, acheteur, titulaires, "
        "durée, modifications."
    )
```

et remplacer dans son `register_page` :

```python
    description=get_description,
```

L'objet du marché serait plus parlant que son identifiant, mais l'obtenir demanderait une requête DuckDB à chaque rendu, y compris pour chaque hit de crawler sur les 1,5 M de fiches. L'identifiant suffit à rendre les descriptions distinctes, ce qui est l'objectif.

Aucune de ces fonctions ne fait de `COUNT` ni de requête : elles sont appelées à chaque requête HTTP.

- [ ] **Step 8: Lancer les tests**

Run: `uv run pytest tests/test_seo.py -v`
Expected: PASS

- [ ] **Step 9: Vérifier le rendu réel**

Run:

```bash
uv run python -c "
from src.app import app
import re
h = app.server.test_client().get('/acheteurs/123').get_data(as_text=True)
print(re.findall(r'<title>(.*?)</title>', h))
print(re.findall(r'<link rel=\"canonical\"[^>]*>', h))
"
```

Expected: le titre contient `ACHETEUR 1`, et la balise canonical porte un `href` rempli.

- [ ] **Step 10: Commit**

```bash
pre-commit run --files src/utils/page_meta.py src/app.py src/not_found.py src/pages/acheteur.py src/pages/titulaire.py src/pages/marche.py tests/test_seo.py
git add src/utils/page_meta.py src/app.py src/not_found.py src/pages/acheteur.py src/pages/titulaire.py src/pages/marche.py tests/test_seo.py
git commit -m "Sert title, description et canonical dans le HTML des pages Dash (#128)"
```

---

### Task 8: JSON-LD organisme minimal servi côté serveur

**Files:**

- Modify: `src/utils/seo.py`, `src/app.py`
- Test: `tests/test_seo.py`

**Interfaces:**

- Consumes: Task 7 (`src.utils.page_meta.page_for_path`)
- Produces: `src.utils.seo.make_org_jsonld_minimal(org_id: str, org_type: str, org_name: str) -> dict` — sans appel réseau

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_seo.py` :

```python
def test_jsonld_organisme_servi_dans_le_html(client):
    import json
    import re

    body = client.get("/acheteurs/123").get_data(as_text=True)
    blocs = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', body, re.S
    )
    donnees = [json.loads(b) for b in blocs if b.strip()]
    assert any(d.get("name") == "ACHETEUR 1" for d in donnees)


def test_jsonld_minimal_sans_appel_reseau(monkeypatch):
    """La version servie ne doit jamais appeler l'Annuaire des entreprises."""
    from src.utils import data, seo

    def interdit(*_a, **_k):
        raise AssertionError("appel réseau interdit dans le rendu serveur")

    monkeypatch.setattr(data, "get_annuaire_data", interdit)
    resultat = seo.make_org_jsonld_minimal("123", "acheteur", "ACHETEUR 1")
    assert resultat["name"] == "ACHETEUR 1"
    assert "address" not in resultat


def test_jsonld_minimal_pas_pour_une_page_non_organisme(client):
    body = client.get("/tableau").get_data(as_text=True)
    assert "GovernmentOrganization" not in body
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_seo.py -v -k jsonld`
Expected: FAIL — `make_org_jsonld_minimal` n'existe pas et aucun bloc JSON-LD n'est servi.

- [ ] **Step 3: Ajouter la version minimale**

Ajouter à `src/utils/seo.py` :

```python
def make_org_jsonld_minimal(org_id: str, org_type: str, org_name: str) -> dict:
    """JSON-LD organisme servi dans le HTML, sans appel réseau.

    Le callback de la page enrichit ensuite avec l'adresse, qui dépend de
    l'Annuaire des entreprises et ne peut pas être obtenue sans un appel HTTP
    bloquant pendant le rendu.
    """
    org_types = {"acheteur": "GovernmentOrganization", "titulaire": "Organization"}
    return {
        "@context": "https://schema.org",
        "@type": org_types[org_type],
        "name": org_name,
        "url": f"https://{DOMAIN_NAME}/{org_type}s/{org_id}",
        "sameAs": (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{org_id}"
        ),
        "identifier": {
            "@type": "PropertyValue",
            "propertyID": "siret",
            "value": org_id,
        },
    }
```

- [ ] **Step 4: Injecter dans le HTML servi**

Dans `_interpolate_index_per_request` de `src/app.py`, après l'injection du canonical :

```python
    jsonld_tag = _org_jsonld_tag(_request.path)
    if jsonld_tag:
        kwargs["metas"] = f"{kwargs.get('metas', '')}\n      {jsonld_tag}"
```

et définir au-dessus de `_interpolate_index_per_request` :

```python
def _org_jsonld_tag(path: str) -> str:
    """Balise JSON-LD servie pour les fiches acheteur et titulaire.

    Chaîne vide pour tout autre chemin : le JSON-LD Organization n'a de sens
    que sur une fiche d'organisme.
    """
    import json

    import polars as pl

    from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
    from src.utils.seo import make_org_jsonld_minimal

    segments = path.strip("/").split("/")
    if len(segments) != 2:
        return ""
    segment, org_id = segments
    org_type = {"acheteurs": "acheteur", "titulaires": "titulaire"}.get(segment)
    if not org_type:
        return ""

    df = DF_ACHETEURS if org_type == "acheteur" else DF_TITULAIRES
    row = df.filter(pl.col(f"{org_type}_id") == org_id)
    if row.height == 0:
        return ""
    nom = row.select(f"{org_type}_nom").item(0, 0)

    # NE PAS échapper en HTML : markupsafe.escape transformerait les guillemets
    # du JSON en &quot; et rendrait le bloc illisible pour un parseur. Le seul
    # risque réel dans un <script> est une séquence `</script>` dans une valeur ;
    # neutraliser `<` en < suffit, et reste du JSON valide.
    payload = json.dumps(
        make_org_jsonld_minimal(org_id, org_type, nom), ensure_ascii=False
    ).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'
```

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/test_seo.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/utils/seo.py src/app.py tests/test_seo.py
git add src/utils/seo.py src/app.py tests/test_seo.py
git commit -m "Sert un JSON-LD organisme minimal dans le HTML (#128)"
```

---

### Task 9: Cache de l'Annuaire des entreprises et relèvement du seuil

**Files:**

- Modify: `src/utils/data.py:16`, `src/app.py:84`
- Test: `tests/seo/test_cache_annuaire.py`

**Interfaces:**

- Consumes: rien.
- Produces: `get_annuaire_data` mémoïsée ; `CACHE_THRESHOLD` piloté par la variable d'environnement `CACHE_THRESHOLD`, défaut 300000.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/seo/test_cache_annuaire.py` :

```python
"""Le cache de l'Annuaire protège une API publique à quota par IP.

Sans lui, faire crawler les 242 005 fiches organisme enverrait autant
d'appels à recherche-entreprises.api.gouv.fr : Googlebot exécute le JS, donc
déclenche le callback qui interroge l'Annuaire.
"""


def test_appels_repetes_ne_declenchent_qu_une_requete(monkeypatch):
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils import data

    appels = []

    class _Reponse:
        def raise_for_status(self):
            return self

        def json(self):
            return {"results": [{"siret": "12345678901234"}]}

    def _get(url, **kwargs):
        appels.append(url)
        return _Reponse()

    monkeypatch.setattr(data, "get", _get)
    data.get_annuaire_data.uncached("12345678901234")  # amorce hors cache
    appels.clear()

    data.get_annuaire_data("99999999999999")
    data.get_annuaire_data("99999999999999")
    assert len(appels) == 1


def test_seuil_de_cache_permet_de_tenir_les_organismes():
    """300 entrées ne suffisent pas pour 242 005 SIRET."""
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils.cache import cache

    assert cache.app.config["CACHE_THRESHOLD"] >= 300_000
```

`@cache.memoize` expose `uncached` sur la fonction décorée : c'est ce qui permet de vérifier que la décoration a bien eu lieu.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/seo/test_cache_annuaire.py -v`
Expected: FAIL — `get_annuaire_data` n'a pas d'attribut `uncached`, et le seuil vaut 300.

- [ ] **Step 3: Mémoïser la fonction**

Dans `src/utils/data.py`, ajouter l'import et le décorateur :

```python
from src.utils.cache import cache


@cache.memoize(timeout=3600 * 24 * 30)
def get_annuaire_data(siret: str) -> dict | None:
    ...
```

Le délai de 30 jours reflète la nature des données : des informations d'établissement qui ne bougent quasiment jamais, et dont la fraîcheur n'a aucun enjeu pour un JSON-LD.

Vérifier qu'aucun import circulaire n'apparaît : `src/utils/cache.py` ne dépend de rien d'autre que `flask_caching`, précisément pour ce cas.

- [ ] **Step 4: Relever le seuil**

Dans `src/app.py`, remplacer :

```python
        "CACHE_THRESHOLD": 300,
```

par :

```python
        # 300 par défaut dans flask-caching : `set()` appelle `_prune()` à chaque
        # écriture, qui évince les entrées les plus anciennes dès le seuil
        # franchi. Insuffisant pour les 242 005 SIRET de l'Annuaire, dont la mise
        # en cache protège une API publique à quota. Mesure d'attente : le
        # backend Redis arrive par #123 puis #62, et la bascule se fera par
        # CACHE_TYPE sans toucher aux décorateurs @cache.memoize.
        "CACHE_THRESHOLD": int(os.getenv("CACHE_THRESHOLD", 300_000)),
```

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/seo/test_cache_annuaire.py -v`
Expected: PASS

- [ ] **Step 6: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
pre-commit run --files src/utils/data.py src/app.py tests/seo/test_cache_annuaire.py
git add src/utils/data.py src/app.py tests/seo/test_cache_annuaire.py
git commit -m "Mémoïse les appels à l'Annuaire et relève le seuil de cache (#128)"
```

---

## Vérification finale

- [ ] **Suite complète**

Run: `uv run pytest`
Expected: PASS

- [ ] **Chaîne d'exploration sans JavaScript**

Run:

```bash
uv run python -c "
from src.app import app
c = app.server.test_client()
for url in ('/departements', '/departements/75/acheteurs', '/acheteurs/123/marches'):
    h = c.get(url).get_data(as_text=True)
    print(url, '| taille:', len(h), '| <ul> present:', '<ul>' in h)
"
```

Expected: les trois pages dépassent nettement les 10,6 Ko de la coquille Dash et contiennent un `<ul>`. C'est la mesure qui a servi à diagnostiquer le problème, elle sert ici à confirmer qu'il est résolu.

- [ ] **Points à vérifier au déploiement** (à reporter dans le commentaire de l'issue, pas à traiter ici)

  - Si `/tmp` est un tmpfs sur le serveur cible, les ~242 000 fichiers de cache vivraient en RAM : positionner `CACHE_DIR` ailleurs.
  - `rmtree(cache_dir)` dans `app.py` vide le cache à chaque démarrage : après chaque déploiement, Googlebot rappellera l'Annuaire jusqu'à ce que Redis arrive (#123, #62).
  - Soumettre `/sitemap-arbre.xml` dans la Search Console et surveiller la couverture des index départementaux.
