from src.utils.data import DATA_SCHEMA


def get_button_properties(height):
    if height > 65000:
        download_disabled = True
        download_text = "Téléchargement désactivé au-delà de 65 000 lignes"
        download_title = " Ajoutez des filtres pour réduire le nombre de lignes, Excel ne supporte pas d'avoir plus de 65 000 URLs dans une même feuille de calcul."
    elif height == 0:
        download_disabled = True
        download_text = "Pas de données à télécharger"
        download_title = ""
    else:
        download_disabled = False
        download_text = "Télécharger au format Excel"
        download_title = "Télécharger les données telles qu'affichées au format Excel"
    return download_disabled, download_text, download_title


def get_enum_values_as_dict(column_name):
    try:
        options = {}
        for value in DATA_SCHEMA[column_name]["enum"]:
            options[value] = value
        return options
    except KeyError:
        return {"not_found": "not found"}
