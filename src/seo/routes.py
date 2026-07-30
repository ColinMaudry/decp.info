"""Pages SEO rendues côté serveur.

Ces pages sont des listes de liens pures : aucune interactivité, aucun
graphique. Les servir en Flask plutôt qu'en pages Dash les rend explorables
par les crawlers qui n'exécutent pas de JavaScript — ce qui est leur unique
raison d'être. `src/not_found.py` documente le fait que les vraies routes
Flask échappent au catch-all de Dash.
"""

from flask import Blueprint, abort, redirect, render_template, request

from src.seo import SEGMENT_SANS_DEPARTEMENT, pagination, queries
from src.utils.data import DEPARTEMENTS
from src.utils.matomo import build_tracker_script
from src.utils.pluriel import accorder
from src.utils.table import format_number


def _nombre(n: int) -> str:
    """Nombre formaté à la française, avec espace insécable comme le reste du site.

    `format_number` renvoie une chaîne vide pour 0 : sans ce repli, un
    département sans organisme afficherait « organismes — Wallis-et-Futuna »
    au lieu de « 0 organismes ».
    """
    return format_number(n) or "0"


seo_bp = Blueprint("seo", __name__)

# `segment` : préfixe d'URL. `verbe_*`/`type_*` : formes singulier/pluriel des
# libellés générés (voir `accorder`). Les noms de département ne sont jamais
# accolés à une préposition contractable ("de"/"du"/"des"/"dans") dans les
# gabarits ci-dessous : aucune règle fiable ne dérive l'article correct du
# seul nom (« du Nord », « des Alpes-Maritimes », « de la Réunion », « de
# Paris »), donc on sépare par un tiret cadratin plutôt que d'en inventer une.
_LIBELLES = {
    "acheteur": {
        "segment": "acheteurs",
        "verbe_singulier": "attribué par",
        "verbe_pluriel": "attribués par",
        "type_singulier": "Acheteur public",
        "type_pluriel": "Acheteurs publics",
        # "Acheteur public" porte déjà le mot "public" : il se suffit à
        # lui-même dans le titre de catégorie, pas besoin du complément.
        "titre_departement": "Acheteurs publics",
    },
    "titulaire": {
        "segment": "titulaires",
        "verbe_singulier": "remporté par",
        "verbe_pluriel": "remportés par",
        "type_singulier": "Titulaire",
        "type_pluriel": "Titulaires",
        # "Titulaire" seul ne porte pas le mot-clé et reste ambigu : il a
        # besoin du complément pour être compréhensible hors contexte.
        "titre_departement": "Titulaires de marchés publics",
    },
}


@seo_bp.context_processor
def _inject_matomo():
    """Rend `matomo_script` disponible dans tous les gabarits de ce blueprint.

    Un seul point d'injection plutôt qu'un argument répété dans chaque
    `render_template` : voir `src/utils/matomo.py` pour le conditionnement
    par `MATOMO_TRACKING_ENABLED`.
    """
    return {"matomo_script": build_tracker_script()}


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

    libelles = _LIBELLES[org_type]
    segment = libelles["segment"]
    verbe = accorder(total, libelles["verbe_singulier"], libelles["verbe_pluriel"])
    marches_libelle = accorder(total, "marché public", "marchés publics")
    article_partitif = accorder(total, "du", "des")
    nombre = "" if total <= 1 else f"{_nombre(total)} "
    base = f"/{segment}/{org_id}/marches"
    rang = f" (page {page} sur {pages})" if pages > 1 else ""

    return render_template(
        "seo_liste.html",
        titre=f"{_nombre(total)} {marches_libelle} {verbe} {nom}{rang} | colibre",
        description=(
            f"Liste complète {article_partitif} {nombre}{marches_libelle} {verbe} {nom}, "
            "publiée par colibre."
        ),
        canonical=request.base_url + (f"?page={page}" if page > 1 else ""),
        titre_h1=f"{marches_libelle.capitalize()} {verbe} {nom}",
        chapeau=f"{_nombre(total)} {marches_libelle} {verbe} {nom}.",
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
            href=f"/departements/{SEGMENT_SANS_DEPARTEMENT}/acheteurs",
            libelle="Département non renseigné — acheteurs",
        )
    )
    entrees.append(
        Entree(
            href=f"/departements/{SEGMENT_SANS_DEPARTEMENT}/titulaires",
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

    if code == SEGMENT_SANS_DEPARTEMENT:
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
    libelles = _LIBELLES[org_type]
    # Libellé de catégorie : une constante par type, indépendante du nombre
    # d'organismes du département (#128 — un libellé accordé sur `total`
    # ferait basculer le titre au singulier pour les départements à 0 ou 1
    # organisme, et il changerait d'une livraison de données à l'autre).
    libelle_type = libelles["titre_departement"]
    # Ici, en revanche, l'accord porte sur un décompte réel affiché en toutes
    # lettres ("1 acheteur public" / "3 acheteurs publics") : légitime, comme
    # pour le chapeau.
    libelle_compte = accorder(
        total, libelles["type_singulier"], libelles["type_pluriel"]
    )
    possessif = accorder(total, "son", "leur")
    organisme_libelle = accorder(total, "organisme", "organismes")
    autre_type_org = "titulaires" if type_org == "acheteurs" else "acheteurs"

    return render_template(
        "seo_liste.html",
        titre=f"{libelle_type} — {nom_dept}{rang} | colibre",
        description=(
            f"{_nombre(total)} {libelle_compte.lower()} — {nom_dept}, "
            f"avec {possessif} nombre de marchés publics."
        ),
        canonical=request.base_url + (f"?page={page}" if page > 1 else ""),
        titre_h1=f"{libelle_type} — {nom_dept}",
        chapeau=f"{_nombre(total)} {organisme_libelle} — {nom_dept}.",
        entrees=[
            Entree(
                href=f"/{type_org}/{org_id}",
                libelle=nom or org_id,
                suffixe=f"{_nombre(nb)} marché{'s' if nb > 1 else ''}",
                lien_secondaire=f"/{type_org}/{org_id}/marches",
            )
            for org_id, nom, nb in rows
        ],
        page=page,
        pages=pages,
        url_page=lambda n: base if n == 1 else f"{base}?page={n}",
        retour_href="/departements",
        retour_libelle="Retour à la liste des départements",
        lien_croise=Entree(
            href=f"/departements/{code}/{autre_type_org}",
            libelle=f"{nom_dept} — {autre_type_org}",
        ),
    )


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
