import datetime
from typing import Any

import polars as pl


def to_json_records(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convertit un DataFrame Polars en liste de dicts JSON-sérialisables.

    Les dates/datetimes deviennent des chaînes ISO 8601 ; les valeurs nulles
    restent None. Utilisé par tous les tools MCP pour produire une sortie propre.
    """
    return [
        {key: _jsonify(value) for key, value in row.items()} for row in df.to_dicts()
    ]


def _jsonify(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value
