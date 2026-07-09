from datetime import datetime

from src.utils.data import DATA_SCHEMA

DROPDOWN_LABELS_FR = {
    "select_all": "Tout sélectionner",
    "deselect_all": "Tout désélectionner",
    "selected_count": "{num_selected} sélectionné(s)",
    "search": "Rechercher...",
    "clear_search": "Effacer la recherche",
    "clear_selection": "Effacer la sélection",
    "no_options_found": "Aucun résultat",
}


def format_date_french(date_input) -> str:
    """Format a date as 'jour mois' (e.g., '1er janvier', '15 décembre')."""
    if isinstance(date_input, str):
        try:
            date_obj = datetime.fromisoformat(date_input)
        except (ValueError, TypeError):
            return str(date_input)
    elif isinstance(date_input, datetime):
        date_obj = date_input
    else:
        return str(date_input)

    day = date_obj.day
    month_names = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    month = month_names[date_obj.month - 1]

    if day == 1:
        return f"1er {month}"
    else:
        return f"{day} {month}"


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
