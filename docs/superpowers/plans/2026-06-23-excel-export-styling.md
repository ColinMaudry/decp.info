# Excel Export Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Améliorer les exports Excel de toutes les vues tableau : en-têtes stylisés (fond rouge `#b33821`, texte blanc, gras), largeurs de colonnes issues du `DataTable` commun, largeur minimale de 3.5 cm, et retour à la ligne automatique dans toutes les cellules.

**Architecture:** Une fonction utilitaire `write_styled_excel(df, buffer, worksheet)` centralisée dans `src/utils/table.py` crée le workbook xlsxwriter avec `default_format_properties: {text_wrap: True}`, puis délègue à `polars.DataFrame.write_excel` avec le `header_format` et les `column_widths` calculés. Les 6 callbacks de téléchargement appellent cette fonction à la place de `.write_excel()` direct.

**Tech Stack:** Python, Polars, xlsxwriter (déjà en dep), openpyxl (disponible, utilisé en test uniquement)

## Global Constraints

- Imports de modules internes toujours via `src.` (ex. `from src.utils.table import …`)
- `xlsxwriter` est en dep de prod — pas besoin de l'ajouter
- `openpyxl` est disponible (dep transitive) — pas besoin de l'ajouter à `pyproject.toml`
- Run tests : `uv run pytest` (pas `pytest` direct)
- Couleur primaire de l'app : `#b33821`
- Largeur minimale : 132 pixels (≈ 3.5 cm à 96 DPI)

---

## File Map

| Fichier                     | Action   | Rôle                                                                                                           |
| --------------------------- | -------- | -------------------------------------------------------------------------------------------------------------- |
| `src/utils/table.py`        | Modifier | Ajouter `import xlsxwriter`, constantes `_EXCEL_*`, fonction `write_styled_excel`                              |
| `tests/test_excel.py`       | Créer    | Tests unitaires de `write_styled_excel`                                                                        |
| `src/pages/tableau.py`      | Modifier | Importer et utiliser `write_styled_excel` dans `download_data`                                                 |
| `src/pages/acheteur.py`     | Modifier | Importer et utiliser `write_styled_excel` dans `download_acheteur_data` et `download_filtered_acheteur_data`   |
| `src/pages/titulaire.py`    | Modifier | Importer et utiliser `write_styled_excel` dans `download_titulaire_data` et `download_filtered_titulaire_data` |
| `src/pages/observatoire.py` | Modifier | Importer et utiliser `write_styled_excel` dans `download_observatoire`                                         |

---

### Task 1 : `write_styled_excel` dans `src/utils/table.py`

**Files:**

- Modify: `src/utils/table.py:1` (ajouter import), `src/utils/table.py:559` (fin de fichier)
- Create: `tests/test_excel.py`

**Interfaces:**

- Produces: `write_styled_excel(df: pl.DataFrame, buffer, worksheet: str = "DECP") -> None` — exporté publiquement depuis `src.utils.table`

- [ ] **Step 1 : Créer `tests/test_excel.py` avec les tests en échec**

```python
import io

import openpyxl
import polars as pl
import pytest

from src.utils.table import write_styled_excel


def test_write_styled_excel_header_bold_and_color():
    df = pl.DataFrame({"objet": ["marché A"], "montant": [1000.0]})
    buf = io.BytesIO()
    write_styled_excel(df, buf)
    buf.seek(0)
    wb = openpyxl.load_workbook(buf)
    ws = wb.active
    cell = ws.cell(row=1, column=1)
    assert cell.font.bold is True
    assert cell.fill.fgColor.rgb == "FFB33821"
    assert cell.font.color.rgb == "FFFFFFFF"


def test_write_styled_excel_data_cell_text_wrap():
    df = pl.DataFrame({"objet": ["marché A"]})
    buf = io.BytesIO()
    write_styled_excel(df, buf)
    buf.seek(0)
    wb = openpyxl.load_workbook(buf)
    ws = wb.active
    cell = ws.cell(row=2, column=1)
    assert cell.alignment.wrap_text is True


def test_write_styled_excel_known_column_wider_than_minimum():
    # "objet" a une largeur explicite (350px) > minimum (132px)
    # "autre" n'a pas de largeur explicite → reçoit le minimum
    df = pl.DataFrame({"autre": ["x"], "objet": ["y"]})
    buf = io.BytesIO()
    write_styled_excel(df, buf)
    buf.seek(0)
    wb = openpyxl.load_workbook(buf)
    ws = wb.active
    width_autre = ws.column_dimensions["A"].width  # colonne 1 = "autre"
    width_objet = ws.column_dimensions["B"].width  # colonne 2 = "objet"
    assert width_autre > 0
    assert width_objet > width_autre


def test_write_styled_excel_custom_worksheet_name():
    df = pl.DataFrame({"col": ["val"]})
    buf = io.BytesIO()
    write_styled_excel(df, buf, worksheet="2025")
    buf.seek(0)
    wb = openpyxl.load_workbook(buf)
    assert "2025" in wb.sheetnames
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```bash
uv run pytest tests/test_excel.py -v
```

Attendu : `ImportError` ou `AttributeError: module 'src.utils.table' has no attribute 'write_styled_excel'`

- [ ] **Step 3 : Ajouter `import xlsxwriter` dans `src/utils/table.py`**

Ligne 1 du fichier, après les imports existants. Le bloc imports actuel (lignes 1–14) devient :

```python
import os
import uuid

import polars as pl
import xlsxwriter
from dash import no_update
from polars import selectors as cs
from unidecode import unidecode

from src.db import count_marches, count_unique_marches, query_marches, schema
from src.utils import logger
from src.utils.cache import cache
from src.utils.data import DATA_SCHEMA
from src.utils.frontend import get_button_properties
from src.utils.tracking import track_search
```

- [ ] **Step 4 : Ajouter les constantes et `write_styled_excel` à la fin de `src/utils/table.py`**

Après la ligne `COLUMNS = schema.names()` (actuellement dernière ligne, 559) :

```python

_EXCEL_MIN_COLUMN_WIDTH = 132  # ≈ 3.5 cm à 96 DPI
_EXCEL_HEADER_FORMAT = {
    "bold": True,
    "bg_color": "#b33821",
    "font_color": "white",
}
_EXCEL_COLUMN_WIDTHS = {
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

- [ ] **Step 5 : Vérifier que les tests passent**

```bash
uv run pytest tests/test_excel.py -v
```

Attendu : 4 tests PASS

- [ ] **Step 6 : Commit**

```bash
git add src/utils/table.py tests/test_excel.py
git commit -m "feat: add write_styled_excel utility for styled Excel exports #83"
```

---

### Task 2 : Mettre à jour les 6 callbacks de téléchargement

**Files:**

- Modify: `src/pages/tableau.py:26-33,344-345`
- Modify: `src/pages/acheteur.py:30-37,399-402,441-442`
- Modify: `src/pages/titulaire.py:29-36,421-423,462-463`
- Modify: `src/pages/observatoire.py:43,813-814`

**Interfaces:**

- Consumes: `write_styled_excel(df: pl.DataFrame, buffer, worksheet: str = "DECP") -> None` depuis Task 1

- [ ] **Step 1 : Mettre à jour `src/pages/tableau.py`**

Ajouter `write_styled_excel` à l'import existant (lignes 26–33) :

```python
from src.utils.table import (
    COLUMNS,
    filter_table_data,
    get_default_hidden_columns,
    invert_columns,
    prepare_table_data,
    sort_table_data,
    write_styled_excel,
)
```

Remplacer le bloc `def to_bytes` dans `download_data` (lignes 344–345) :

```python
    def to_bytes(buffer):
        write_styled_excel(lff.collect(engine="streaming"), buffer)
```

- [ ] **Step 2 : Mettre à jour `src/pages/acheteur.py`**

Ajouter `write_styled_excel` à l'import existant (lignes 30–37) :

```python
from src.utils.table import (
    COLUMNS,
    filter_table_data,
    format_number,
    get_default_hidden_columns,
    prepare_table_data,
    sort_table_data,
    write_styled_excel,
)
```

Remplacer le bloc `def to_bytes` dans `download_acheteur_data` (lignes 399–402) :

```python
    def to_bytes(buffer):
        write_styled_excel(
            df_to_download,
            buffer,
            worksheet="DECP" if annee in ["Toutes les années", None] else annee,
        )
```

Remplacer le bloc `def to_bytes` dans `download_filtered_acheteur_data` (ligne 441–442) :

```python
    def to_bytes(buffer):
        write_styled_excel(lff.collect(engine="streaming"), buffer)
```

- [ ] **Step 3 : Mettre à jour `src/pages/titulaire.py`**

Ajouter `write_styled_excel` à l'import existant (lignes 29–36) :

```python
from src.utils.table import (
    COLUMNS,
    filter_table_data,
    format_number,
    get_default_hidden_columns,
    prepare_table_data,
    sort_table_data,
    write_styled_excel,
)
```

Remplacer le bloc `def to_bytes` dans `download_titulaire_data` (lignes 421–423) :

```python
    def to_bytes(buffer):
        write_styled_excel(
            df_to_download,
            buffer,
            worksheet="DECP" if annee in ["Toutes les années", None] else annee,
        )
```

Remplacer le bloc `def to_bytes` dans `download_filtered_titulaire_data` (lignes 462–463) :

```python
    def to_bytes(buffer):
        write_styled_excel(lff.collect(engine="streaming"), buffer)
```

- [ ] **Step 4 : Mettre à jour `src/pages/observatoire.py`**

Modifier l'import (ligne 43) :

```python
from src.utils.table import COLUMNS, get_default_hidden_columns, prepare_table_data, write_styled_excel
```

Remplacer le bloc `def to_bytes` dans `download_observatoire` (ligne 813–814) :

```python
    def to_bytes(buffer):
        write_styled_excel(dff, buffer)
```

- [ ] **Step 5 : Vérifier les tests existants et les nouveaux**

```bash
uv run pytest tests/test_excel.py tests/test_main.py::test_003_tableau_download -v
```

Attendu : tous PASS (le test existant vérifie que le contenu base64 est non vide et que le nom de fichier commence par `decp_` — comportement inchangé)

- [ ] **Step 6 : Commit**

```bash
git add src/pages/tableau.py src/pages/acheteur.py src/pages/titulaire.py src/pages/observatoire.py
git commit -m "refactor: use write_styled_excel in all download callbacks #83"
```
