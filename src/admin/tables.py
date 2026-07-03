from dataclasses import dataclass
from typing import Callable

from src.auth.db import get_conn
from src.subscriptions.db import SUBSCRIPTION_STATUSES
from src.subscriptions.plans import PLANS


@dataclass(frozen=True)
class TableConfig:
    columns: list[str]
    editable_columns: frozenset[str]
    pk: str
    column_types: dict[str, type]
    dropdowns: dict[str, list[str]]
    target_user_id: Callable[[dict], int | None]


TABLES: dict[str, TableConfig] = {
    "users": TableConfig(
        columns=[
            "id",
            "email",
            "email_verified",
            "siret",
            "pending_email",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"email", "email_verified", "siret", "pending_email"}
        ),
        pk="id",
        column_types={
            "email": str,
            "email_verified": int,
            "siret": str,
            "pending_email": str,
        },
        dropdowns={"email_verified": ["0", "1"]},
        target_user_id=lambda row: row["id"],
    ),
    "subscriptions": TableConfig(
        columns=[
            "id",
            "user_id",
            "frisbii_customer_handle",
            "frisbii_subscription_handle",
            "plan",
            "prix_ht",
            "status",
            "current_period_end",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset({"plan", "prix_ht", "status", "current_period_end"}),
        pk="id",
        column_types={
            "plan": str,
            "prix_ht": float,
            "status": str,
            "current_period_end": str,
        },
        dropdowns={
            "status": list(SUBSCRIPTION_STATUSES),
            "plan": list(PLANS.keys()),
        },
        target_user_id=lambda row: row["user_id"],
    ),
    "subscriber_state": TableConfig(
        columns=[
            "user_id",
            "trial_used",
            "votes_balance",
            "votes_last_credited_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"trial_used", "votes_balance", "votes_last_credited_at"}
        ),
        pk="user_id",
        column_types={
            "trial_used": int,
            "votes_balance": int,
            "votes_last_credited_at": str,
        },
        dropdowns={"trial_used": ["0", "1"]},
        target_user_id=lambda row: row["user_id"],
    ),
    "admin_actions": TableConfig(
        columns=[
            "id",
            "admin_email",
            "action",
            "target_user_id",
            "details",
            "created_at",
        ],
        editable_columns=frozenset(),
        pk="id",
        column_types={},
        dropdowns={},
        target_user_id=lambda row: None,
    ),
}


def get_rows(table: str) -> list[dict]:
    cfg = TABLES[table]
    cols_sql = ", ".join(cfg.columns)
    rows = get_conn().execute(f"SELECT {cols_sql} FROM {table}").fetchall()
    return [dict(row) for row in rows]


def _coerce_value(table: str, column: str, value):
    cfg = TABLES[table]
    if column not in cfg.editable_columns:
        raise ValueError(f"Colonne non éditable : {column}")
    if column in cfg.dropdowns and str(value) not in cfg.dropdowns[column]:
        raise ValueError(f"Valeur non autorisée pour {column} : {value!r}")
    expected_type = cfg.column_types[column]
    try:
        if expected_type is int:
            return int(value)
        if expected_type is float:
            return float(value)
        return str(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valeur invalide pour {column} : {value!r}") from exc


def set_cell(table: str, pk_value, column: str, value) -> None:
    if table not in TABLES:
        raise ValueError(f"Table inconnue : {table}")
    cfg = TABLES[table]
    coerced = _coerce_value(table, column, value)
    get_conn().execute(
        f"UPDATE {table} SET {column} = ? WHERE {cfg.pk} = ?", (coerced, pk_value)
    )


def find_changed_cell(
    data: list[dict], data_previous: list[dict] | None
) -> tuple[int, str, object, object] | None:
    if data_previous is None or len(data) != len(data_previous):
        return None
    for i, (new_row, old_row) in enumerate(zip(data, data_previous)):
        for col, new_val in new_row.items():
            old_val = old_row.get(col)
            if new_val != old_val:
                return i, col, old_val, new_val
    return None
