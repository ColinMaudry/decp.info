import os
import sqlite3
from datetime import datetime, timedelta, timezone

from src.auth.db import get_conn
from src.utils import tracking

SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                      INTEGER NOT NULL,
    frisbii_customer_handle      TEXT,
    frisbii_subscription_handle  TEXT,
    plan                         TEXT,
    prix_ht                      REAL,
    status                       TEXT,
    current_period_end           TEXT,
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_handle
    ON subscriptions(frisbii_subscription_handle);

CREATE TABLE IF NOT EXISTS subscriber_state (
    user_id                 INTEGER PRIMARY KEY,
    -- Plus lue ni écrite depuis le passage à l'essai applicatif : l'essai est
    -- désormais porté par trial_ends_at ci-dessous. Conservée pour ne pas
    -- casser les bases existantes ; retrait prévu dans un nettoyage ultérieur.
    trial_used              INTEGER NOT NULL DEFAULT 0,
    trial_ends_at           TEXT,
    votes_balance           INTEGER NOT NULL DEFAULT 0,
    votes_last_credited_at  TEXT,
    updated_at              TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# "trial" ne devrait plus jamais être écrit dans subscriptions.status : l'essai
# est désormais géré par subscriber_state.trial_ends_at, sans ligne
# subscriptions. Gardé quand même pour deux raisons certaines : l'admin
# (src/admin/tables.py) expose "status" en colonne éditable avec "trial" dans
# son menu déroulant (SUBSCRIPTION_STATUSES), donc un·e admin peut l'écrire à
# la main aujourd'hui ; et une base déployée avant ce chantier peut encore
# porter des lignes historiques à ce statut. Accessoirement, ça couvre aussi
# le cas où un plan Frisbii resterait configuré avec un essai malgré le
# no_trial=True envoyé à la création (routes.subscribe) : webhooks.
# map_subscription pourrait alors encore renvoyer "trial", et il ne faut pas
# couper l'accès d'un abonné dans ce cas.
_ACCESS_STATUSES = ("trial", "active")

INITIAL_VOTES = 3
TRIAL_DAYS = 3
VOTES_PER_WEEK = int(os.getenv("VOTES_PER_WEEK", "5"))
WEEK_SECONDS = 7 * 24 * 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(value: str | None) -> datetime | None:
    """Parse un horodatage ISO stocké, en garantissant un datetime aware.

    Une valeur naïve (saisie à la main en base ou via l'admin) ferait lever un
    TypeError à la comparaison avec `datetime.now(timezone.utc)`. Comme cette
    comparaison est dans `has_access`, l'incident se traduirait par une erreur
    500 sur tout l'espace abonné, le connecteur MCP et l'écran de consentement
    OAuth. On normalise donc en UTC plutôt que de supposer le stockage propre.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(SUBSCRIPTIONS_SCHEMA)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(subscriptions)")}
    if "id" not in cols:
        _rebuild_subscriptions_history(conn)


def _rebuild_subscriptions_history(conn: sqlite3.Connection) -> None:
    # L'ancien schéma avait user_id en PRIMARY KEY (1 ligne par utilisateur) et
    # portait aussi l'état cumulatif (votes, essai). SQLite ne peut ni retirer
    # une PRIMARY KEY ni répartir des colonnes vers une autre table via ALTER :
    # on reconstruit la table. foreign_keys OFF pour éviter le cascade-delete
    # pendant le DROP.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE subscriptions_new (
                id                           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                      INTEGER NOT NULL,
                frisbii_customer_handle      TEXT,
                frisbii_subscription_handle  TEXT,
                plan                         TEXT,
                prix_ht                      REAL,
                status                       TEXT,
                current_period_end           TEXT,
                created_at                   TEXT NOT NULL,
                updated_at                   TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "INSERT INTO subscriptions_new (user_id, frisbii_customer_handle, "
            "frisbii_subscription_handle, plan, prix_ht, status, "
            "current_period_end, created_at, updated_at) "
            "SELECT user_id, frisbii_customer_handle, frisbii_subscription_handle, "
            "plan, prix_ht, status, current_period_end, created_at, updated_at "
            "FROM subscriptions"
        )
        conn.execute(
            "INSERT INTO subscriber_state (user_id, trial_used, votes_balance, "
            "votes_last_credited_at, updated_at) "
            "SELECT user_id, trial_used, votes_balance, votes_last_credited_at, "
            "updated_at FROM subscriptions"
        )
        conn.execute("DROP TABLE subscriptions")
        conn.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_user "
            "ON subscriptions(user_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_handle "
            "ON subscriptions(frisbii_subscription_handle)"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def get_current(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        .fetchone()
    )


# Référence pour le menu déroulant admin (src/admin/tables.py) : doit rester
# synchronisée avec les valeurs que map_subscription peut produire, "trial"
# inclus (cf. _ACCESS_STATUSES ci-dessus).
SUBSCRIPTION_STATUSES = ("active", "trial", "cancelled", "expired", "pending")


def list_by_user(user_id: int) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        .fetchall()
    )


def set_status(subscription_id: int, status: str) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), subscription_id),
    )


def get_by_handle(subscription_handle: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE frisbii_subscription_handle = ?",
            (subscription_handle,),
        )
        .fetchone()
    )


def customer_known(customer_handle: str) -> bool:
    row = (
        get_conn()
        .execute(
            "SELECT 1 FROM subscriptions WHERE frisbii_customer_handle = ? LIMIT 1",
            (customer_handle,),
        )
        .fetchone()
    )
    return row is not None


def _next_handle(user_id: int, customer_handle: str) -> str:
    """Prochain handle d'abonnement libre pour cet utilisateur.

    Dérivé du handle customer, donc préfixé par l'environnement (#126) : un
    `colibre-4-1` de production ne peut plus entrer en collision avec le
    `colibre_test-4-1` de test.colibre.fr dans le compte Frisbii partagé.
    """
    prefix = f"{customer_handle}-"
    rows = (
        get_conn()
        .execute(
            "SELECT frisbii_subscription_handle FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        .fetchall()
    )
    # Filtrage en Python plutôt qu'en SQL : le préfixe contient un `_`, qui est
    # un joker LIKE en SQLite.
    n = 0
    for row in rows:
        handle = row["frisbii_subscription_handle"] or ""
        if not handle.startswith(prefix):
            continue
        suffix = handle[len(prefix) :]
        if suffix.isdigit():
            n = max(n, int(suffix))
    return f"{prefix}{n + 1}"


def create_pending(
    user_id: int, customer_handle: str, plan: str, prix_ht: float | None = None
) -> tuple[str, int]:
    """Crée une nouvelle ligne d'historique en statut 'pending'.

    Renvoie (handle, subscription_id). Le handle est choisi et enregistré ici,
    avant tout appel à l'API Frisbii.
    """
    now = _now()
    handle = _next_handle(user_id, customer_handle)
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO subscriber_state (user_id, updated_at) VALUES (?, ?)",
        (user_id, now),
    )
    cur = conn.execute(
        "INSERT INTO subscriptions "
        "(user_id, frisbii_customer_handle, frisbii_subscription_handle, plan, "
        "prix_ht, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
        (user_id, customer_handle, handle, plan, prix_ht, now, now),
    )
    return handle, cur.lastrowid


def mark_failed(subscription_id: int) -> None:
    """Marque une ligne comme échouée (échec de l'appel Frisbii après create_pending).

    Le handle reste enregistré (pas de suppression de la ligne) pour ne
    jamais être réutilisé par _next_handle.
    """
    get_conn().execute(
        "UPDATE subscriptions SET status = 'failed', updated_at = ? WHERE id = ?",
        (_now(), subscription_id),
    )


def _get_state(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM subscriber_state WHERE user_id = ?", (user_id,))
        .fetchone()
    )


def get_subscriber_state(user_id: int) -> sqlite3.Row | None:
    return _get_state(user_id)


def freeze_votes_cursor(user_id: int) -> None:
    """Réactivation après une période sans abonnement : repart de maintenant.

    Ne fait rien si le curseur est NULL (première activation jamais atteinte) :
    les +2 initiaux restent gérés par credit_pending. Ne re-crédite jamais.
    """
    row = _get_state(user_id)
    if row is None or row["votes_last_credited_at"] is None:
        return
    now = _now()
    get_conn().execute(
        "UPDATE subscriber_state SET votes_last_credited_at = ?, updated_at = ? "
        "WHERE user_id = ?",
        (now, now, user_id),
    )


def update_from_webhook(
    subscription_handle: str,
    status: str,
    current_period_end: str | None,
) -> None:
    prev = get_by_handle(subscription_handle)
    if prev is None:
        return
    if prev["status"] == "active" and status != "active":
        credit_pending(prev["user_id"])  # banque les semaines acquises avant gel
    get_conn().execute(
        "UPDATE subscriptions SET status = ?, current_period_end = ?, "
        "updated_at = ? WHERE id = ?",
        (status, current_period_end, _now(), prev["id"]),
    )
    if prev["status"] != "active" and status == "active":
        freeze_votes_cursor(prev["user_id"])
        # Couvre trial → active (transformation d'un essai), pending → active
        # (souscription directe d'un utilisateur ayant déjà consommé son essai)
        # et aussi cancelled/expired → active (réabonnement après résiliation
        # ou expiration) : c'est voulu, un réabonnement est un nouvel abonné
        # payant à comptabiliser au même titre. La condition rend l'émission
        # idempotente : un webhook redélivré trouve prev["status"] déjà à
        # "active" et ne repasse pas ici.
        tracking.track_subscription_goal(
            "subscription_active", prev["plan"], prev["prix_ht"]
        )


def set_cancelled(subscription_id: int, current_period_end: str | None) -> None:
    row = (
        get_conn()
        .execute("SELECT user_id FROM subscriptions WHERE id = ?", (subscription_id,))
        .fetchone()
    )
    if row is None:
        return
    credit_pending(row["user_id"])  # banque les semaines pleines acquises
    get_conn().execute(
        "UPDATE subscriptions SET status = 'cancelled', current_period_end = ?, "
        "updated_at = ? WHERE id = ?",
        (current_period_end, _now(), subscription_id),
    )


def set_reactivated(subscription_id: int, current_period_end: str | None) -> None:
    """Annule une résiliation avant l'échéance (bouton "Je me réabonne").

    Pas de freeze_votes_cursor ici, à la différence de `update_from_webhook` :
    l'accès (`has_access`) n'a jamais été interrompu pendant la fenêtre
    "résilié mais encore actif" (`has_active_subscription` reste vrai tant que
    `current_period_end` n'est pas dépassé), donc les votes continuent de
    s'accumuler normalement et il n'y a aucune coupure à combler.
    """
    get_conn().execute(
        "UPDATE subscriptions SET status = 'active', current_period_end = ?, "
        "updated_at = ? WHERE id = ?",
        (current_period_end, _now(), subscription_id),
    )


def period_end_in_future(current_period_end: str | None) -> bool:
    end = _parse_iso_utc(current_period_end)
    return end is not None and end > datetime.now(timezone.utc)


def has_active_subscription(user_id: int) -> bool:
    row = get_current(user_id)
    if row is None:
        return False
    if row["status"] in _ACCESS_STATUSES:
        return True
    if row["status"] == "cancelled":
        return period_end_in_future(row["current_period_end"])
    return False


def start_trial_if_new(user_id: int) -> None:
    """Ouvre la fenêtre d'essai si ce compte n'en a jamais eu.

    Idempotent : la clause `trial_ends_at IS NULL` garantit qu'un second appel
    ne prolonge jamais l'essai. C'est la seule protection contre une
    re-vérification d'email ou une reconnexion LinkedIn qui rouvriraient
    autrement un essai déjà consommé.
    """
    now = _now()
    conn = get_conn()
    # Le SELECT ... FROM users garantit qu'aucune ligne n'est insérée pour un
    # user_id inconnu : OR IGNORE n'avale PAS les violations de clé étrangère
    # (seulement UNIQUE/NOT NULL/CHECK), on aurait donc une IntegrityError.
    conn.execute(
        "INSERT OR IGNORE INTO subscriber_state (user_id, updated_at) "
        "SELECT id, ? FROM users WHERE id = ?",
        (now, user_id),
    )
    ends = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    conn.execute(
        "UPDATE subscriber_state SET trial_ends_at = ?, updated_at = ? "
        "WHERE user_id = ? AND trial_ends_at IS NULL",
        (ends.isoformat(), now, user_id),
    )


def trial_ends_at(user_id: int) -> datetime | None:
    row = _get_state(user_id)
    if row is None:
        return None
    return _parse_iso_utc(row["trial_ends_at"])


def trial_active(user_id: int) -> bool:
    end = trial_ends_at(user_id)
    return end is not None and end > datetime.now(timezone.utc)


def has_access(user_id: int) -> bool:
    """Accès aux fonctionnalités réservées : essai en cours OU abonnement.

    À ne PAS confondre avec `has_active_subscription`, qui ne parle que
    d'abonnements. Les appelants qui décident d'orienter vers la souscription
    (garde de `subscribe()`, `_post_login_url`, page /a-propos/abonnement)
    doivent rester sur cette dernière : s'ils comptaient l'essai, un
    utilisateur en essai ne pourrait plus s'abonner du tout.
    """
    return trial_active(user_id) or has_active_subscription(user_id)


def _set_votes(user_id: int, balance: int, cursor_iso: str) -> None:
    get_conn().execute(
        "UPDATE subscriber_state SET votes_balance = ?, votes_last_credited_at = ?, "
        "updated_at = ? WHERE user_id = ?",
        (balance, cursor_iso, _now(), user_id),
    )


def _accrues_votes(user_id: int) -> bool:
    """Vrai si l'utilisateur gagne encore des votes chaque semaine.

    L'accumulation suit l'accès (`has_access`) : l'essai vote comme un
    abonnement, et un désabonnement en cours de période reste payé jusqu'à
    `current_period_end`, donc continue d'accumuler.

    `credit_pending` et `next_recharge_at` DOIVENT partager cette définition :
    dès qu'elles divergent, la page roadmap annonce à un utilisateur qui
    n'accumule pas une date calculée sur un curseur gelé, donc dans le passé.
    """
    from src.utils import TOUS_ABONNES

    return TOUS_ABONNES or has_access(user_id)


def credit_pending(user_id: int) -> int:
    """Crédite paresseusement les votes acquis et renvoie le solde courant.

    +VOTES_PER_WEEK à la première activation, puis +VOTES_PER_WEEK par semaine
    pleine. Le solde est cappé à VOTES_PER_WEEK (pas d'accumulation).
    Idempotent : ne crédite que des semaines pleines.

    Sous TOUS_ABONNES, les accès gratuits n'ont pas de ligne `subscriptions` :
    on crée `subscriber_state` à la volée et on lève le garde-fou sur le statut,
    pour que solde et recharge hebdomadaire fonctionnent comme pour un abonné.
    """
    from src.utils import TOUS_ABONNES

    if TOUS_ABONNES:
        # Le SELECT ... FROM users garantit qu'aucune ligne n'est insérée pour un
        # user_id inconnu : OR IGNORE n'avale PAS les violations de clé étrangère
        # (seulement UNIQUE/NOT NULL/CHECK), on aurait donc une IntegrityError.
        get_conn().execute(
            "INSERT OR IGNORE INTO subscriber_state (user_id, updated_at) "
            "SELECT id, ? FROM users WHERE id = ?",
            (_now(), user_id),
        )
    state = _get_state(user_id)
    if state is None:
        return 0
    balance = state["votes_balance"] or 0
    if not _accrues_votes(user_id):
        return balance
    now = datetime.now(timezone.utc)
    cursor = state["votes_last_credited_at"]
    if cursor is None:
        balance = min(balance + INITIAL_VOTES, VOTES_PER_WEEK)
        _set_votes(user_id, balance, now.isoformat())
        return balance
    cur = datetime.fromisoformat(cursor)
    weeks = int((now - cur).total_seconds() // WEEK_SECONDS)
    if weeks > 0:
        balance = min(balance + weeks * VOTES_PER_WEEK, VOTES_PER_WEEK)
        new_cursor = cur + timedelta(seconds=weeks * WEEK_SECONDS)
        _set_votes(user_id, balance, new_cursor.isoformat())
    return balance


def spend_vote(user_id: int) -> bool:
    """Débite 1 vote si le solde le permet. Renvoie True si un vote a été débité."""
    cur = get_conn().execute(
        "UPDATE subscriber_state SET votes_balance = votes_balance - 1, "
        "updated_at = ? WHERE user_id = ? AND votes_balance > 0",
        (_now(), user_id),
    )
    return cur.rowcount > 0


def next_recharge_at(user_id: int) -> datetime | None:
    """Retourne la date du prochain rechargement de votes, ou None si non applicable.

    None dès qu'aucun rechargement n'aura lieu : soit l'utilisateur n'accumule
    plus (curseur gelé, la date qu'on en déduirait serait dans le passé), soit
    son abonnement ou son essai se termine avant l'échéance.
    """
    from src.utils import TOUS_ABONNES

    row = _get_state(user_id)
    if not row or not row["votes_last_credited_at"]:
        return None
    if not _accrues_votes(user_id):
        return None
    cursor = datetime.fromisoformat(row["votes_last_credited_at"])
    nxt = cursor + timedelta(seconds=WEEK_SECONDS)
    if not TOUS_ABONNES and not has_active_subscription(user_id):
        # L'accumulation ne tient qu'à l'essai : pas de rechargement à
        # annoncer au-delà de sa fin.
        end = trial_ends_at(user_id)
        if end is not None and nxt > end:
            return None
    current = get_current(user_id)
    if current and current["status"] == "cancelled" and current["current_period_end"]:
        try:
            end = datetime.fromisoformat(
                current["current_period_end"].replace("Z", "+00:00")
            )
        except ValueError:
            return nxt
        if nxt > end:
            return None
    return nxt
