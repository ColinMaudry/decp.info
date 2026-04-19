from src.utils import DOMAIN_NAME
from src.utils.data import get_annuaire_data


def make_org_jsonld(org_id, org_type, org_name=None, type_org_id="SIRET") -> dict:
    org_types = {"acheteur": "GovernmentOrganization", "titulaire": "Organization"}
    address = None
    if type_org_id.lower() == "siret" and len(org_id) == 14:
        annuaire_data = get_annuaire_data(org_id)
        annuaire_address = annuaire_data["matching_etablissements"][0]
        code_postal = annuaire_address["code_postal"]
        commune = annuaire_address["libelle_commune"]

        address = (
            {
                "@type": "PostalAddress",
                "streetAddress": annuaire_address.get("adresse", "")
                .replace(code_postal, "")
                .replace(commune, "")
                .strip(),
                "addressLocality": commune,
                "postalCode": code_postal,
                "addressCountry": "FR",
            },
        )

    jsonld = {
        "@type": org_types[org_type],
        "name": org_name,
        "url": f"https://decp.info/{org_type}s/{org_id}",
        "sameAs": f"https://annuaire-entreprises.data.gouv.fr/etablissement/{org_id}",
        "identifier": {
            "@type": "PropertyValue",
            "propertyID": type_org_id.lower(),
            "value": org_id,
        },
    }

    if address:
        jsonld["address"] = address

    return jsonld


META_CONTENT = {
    "image_url": f"https://{DOMAIN_NAME}/assets/decp.info.png",
    "title": "decp.info - exploration des marchés publics français",
    "description": (
        "Explorez et analysez les données des marchés publics français avec cet outil libre et gratuit. "
        "Pour une commande publique accessible à toutes et tous."
    ),
}
