# Design : amélioration du style des exports Excel (#83)

**Date :** 2026-06-23
**Issue :** #83

## Contexte

Les 6 fonctions d'export Excel du projet produisent des fichiers basiques : toutes les colonnes ont la même largeur par défaut et les en-têtes ne sont pas mis en valeur. L'objectif est d'améliorer la lisibilité en imitant les largeurs de colonnes du `DataTable` commun et en stylisant les en-têtes.

## Périmètre

Toutes les fonctions d'export Excel :

| Fichier                     | Fonction                           | Page            |
| --------------------------- | ---------------------------------- | --------------- |
| `src/pages/tableau.py`      | `download_data`                    | `/tableau`      |
| `src/pages/acheteur.py`     | `download_acheteur_data`           | `/acheteur`     |
| `src/pages/acheteur.py`     | `download_filtered_acheteur_data`  | `/acheteur`     |
| `src/pages/titulaire.py`    | `download_titulaire_data`          | `/titulaire`    |
| `src/pages/titulaire.py`    | `download_filtered_titulaire_data` | `/titulaire`    |
| `src/pages/observatoire.py` | `download_observatoire`            | `/observatoire` |

## Solution retenue : wrapper `write_styled_excel` (approche C)

Le besoin de `text_wrap` impose de créer le workbook manuellement (`xlsxwriter.Workbook` avec `default_format_properties`). Répéter ce boilerplate 6 fois est peu maintenable, donc on centralise dans une fonction utilitaire dans `src/utils/table.py`.

## Détail du design

### Constantes et wrapper — `src/utils/table.py`

```python
import xlsxwriter

_EXCEL_MIN_COLUMN_WIDTH = 132          # ≈ 3.5 cm à 96 DPI
_EXCEL_HEADER_FORMAT = {
    "bold": True,
    "bg_color": "#b33821",             # couleur primaire de l'app
    "font_color": "white",
}
_EXCEL_COLUMN_WIDTHS = {               # tirés des minWidth du DataTable commun (src/figures.py:269)
    "objet": 350,
    "acheteur_nom": 250,
    "titulaire_nom": 250,
    "acheteur_id": 160,
}

def write_styled_excel(df: pl.DataFrame, buffer, worksheet: str = "DECP") -> None:
    col_widths = {
        col: max(_EXCEL_MIN_COLUMN_WIDTH, _EXCEL_COLUMN_WIDTHS.get(col, 0))
        for col in df.columns
    }
    wb = xlsxwriter.Workbook(buffer, {"default_format_properties": {"text_wrap": True}})
    ws = wb.add_worksheet(worksheet)
    df.write_excel(
        workbook=wb,
        worksheet=ws,
        header_format=_EXCEL_HEADER_FORMAT,
        column_widths=col_widths,
    )
    wb.close()
```

**Comportement :**

- `text_wrap=True` via `default_format_properties` s'applique à toutes les cellules de données.
- Chaque colonne reçoit au minimum 132 px (≈ 3.5 cm) ; les colonnes avec largeur explicite utilisent leur valeur si elle est supérieure.
- En-têtes : fond rouge (`#b33821`), texte blanc, gras.
- Le wrapper accepte un `pl.DataFrame` ; les callbacks qui travaillent avec une `LazyFrame` appellent `.collect()` (éventuellement `engine="streaming"`) avant d'appeler le wrapper.

### Mise à jour des 6 callbacks

Chaque bloc `def to_bytes(buffer):` est remplacé par un appel au wrapper.

**Exemples :**

```python
# tableau.py — download_data
def to_bytes(buffer):
    write_styled_excel(lff.collect(engine="streaming"), buffer)

# acheteur.py — download_acheteur_data (worksheet dynamique selon l'année)
def to_bytes(buffer):
    write_styled_excel(
        df_to_download, buffer,
        worksheet="DECP" if annee in ["Toutes les années", None] else annee,
    )

# acheteur.py — download_filtered_acheteur_data
def to_bytes(buffer):
    write_styled_excel(lff.collect(engine="streaming"), buffer)
```

Titulaire et observatoire : même pattern.

## Décisions clés

- **`autofit=False`** (pas d'autofit Polars) : les largeurs sont entièrement contrôlées par `col_widths`.
- **`text_wrap` via workbook** : seule façon d'appliquer le wrapping à toutes les cellules via `write_excel` (les paramètres `column_formats`/`dtype_formats` de Polars n'exposent pas les propriétés xlsxwriter de format cellule).
- **Constantes privées** (`_EXCEL_*`) : non exportées, consommées uniquement par `write_styled_excel`.
- **Worksheet dynamique** : `download_acheteur_data` et `download_titulaire_data` utilisent l'année comme nom de feuille quand elle est définie — conservé via le paramètre `worksheet`.
