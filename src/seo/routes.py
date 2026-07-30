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
