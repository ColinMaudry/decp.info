"""Pages SEO rendues côté serveur.

Ces pages sont des listes de liens pures : aucune interactivité, aucun
graphique. Les servir en Flask plutôt qu'en pages Dash les rend explorables
par les crawlers qui n'exécutent pas de JavaScript — ce qui est leur unique
raison d'être. `src/not_found.py` documente le fait que les vraies routes
Flask échappent au catch-all de Dash.
"""

from flask import Blueprint, abort, render_template, request

from src.seo import pagination, queries
from src.utils.data import DEPARTEMENTS

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
