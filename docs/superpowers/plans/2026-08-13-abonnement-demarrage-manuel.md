# Démarrage manuel de l'abonnement — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** sortir la période d'essai de Frisbii pour qu'aucun débit ne puisse
survenir sans une action explicite de l'utilisateur après la fin de l'essai.

**Architecture:** l'essai devient une fenêtre de dates dans `subscriber_state`
(`trial_ends_at`), posée à l'activation du compte. Aucun abonnement Frisbii
n'existe pendant l'essai. L'abonnement payant n'est créé qu'au moment de la
décision d'achat, via le parcours de souscription existant avec
`no_trial=True`.

**Tech Stack:** Python 3, Flask + Dash 4.4, SQLite (`users.sqlite`), API
Frisbii/Reepay, pytest.

Spec : `docs/superpowers/specs/2026-08-13-abonnement-demarrage-manuel-design.md`
Issue : [#132](https://github.com/ColinMaudry/colibre/issues/132)

## Global Constraints

- Imports internes toujours préfixés `src.` (`from src.subscriptions import db`),
  jamais `from subscriptions import db`.
- Interface utilisateur en français.
- Durée d'essai : **2 jours**, constante `TRIAL_DAYS` dans
  `src/subscriptions/db.py`. Ne pas la rendre configurable par variable
  d'environnement.
- `has_active_subscription()` ne doit **jamais** être modifiée pour inclure
  l'essai. Le nouvel accès passe par `has_access()`.
- Horodatages stockés en ISO 8601 UTC (`datetime.now(timezone.utc).isoformat()`),
  comme le reste de `src/subscriptions/db.py`.
- Prix : formule `simple` 20 € HT (24 € TTC), formule `soutien` 50 € HT
  (60 € TTC). TVA 20 %. Ne jamais coder un prix en dur dans une vue : le lire
  via `plans.plan_meta(key)["prix_ht"]`.
- Avant tout `git add`, exécuter `pre-commit` (formatage ruff/prettier) — cf.
  `CLAUDE.md`.
- Lancer les tests avec `uv run pytest`, jamais `pytest` seul.
- **Chaque tâche ne lance que les fichiers de test qu'elle touche.** La suite
  complète (`uv run pytest` sans chemin) n'est lancée qu'à la tâche 10.
- **Le corps des tests est à écrire par l'implémenteur.** Chaque tâche liste ce
  que les tests doivent _prouver_, pas leur code. Toute assertion d'absence
  (`assert "x" not in ...`) doit être adossée à une assertion positive prouvant
  que l'action a bien eu lieu — sans quoi elle reste vraie sur une page vide ou
  une erreur 500.

---

## Structure des fichiers

| Fichier                                    | Responsabilité après le chantier                                                                               |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `src/migrations.py`                        | migration `0014` ajoutant `subscriber_state.trial_ends_at`                                                     |
| `src/subscriptions/db.py`                  | fenêtre d'essai (`start_trial_if_new`, `trial_active`) et verrou d'accès (`has_access`), en plus de l'existant |
| `src/auth/routes.py`                       | ouvre l'essai à l'activation du compte, redirige vers `/compte/abonnement`                                     |
| `src/subscriptions/plans.py`               | plans sans notion d'essai                                                                                      |
| `src/subscriptions/routes.py`              | souscription toujours `no_trial=True`                                                                          |
| `src/pages/compte/abonnement.py`           | états essai en cours / essai terminé / abonné                                                                  |
| `src/pages/compte/abonnement_mes_infos.py` | écran de confirmation d'achat (formule, récapitulatif, bouton nommant le montant)                              |
| `src/pages/a_propos/abonnement.py`         | mention d'essai globale, plus par formule                                                                      |
| `src/pages/inscription.py`                 | annonce que la validation de l'email démarre l'essai                                                           |
| `src/assets/goals.js`                      | objectif Matomo `subscription_trial` ré-ancré sur le démarrage de l'essai                                      |

---

### Task 1: Fenêtre d'essai en base

**Files:**

- Modify: `src/migrations.py` (ajouter un tuple à la fin de `_MIGRATIONS`)
- Modify: `src/subscriptions/db.py` (`SUBSCRIPTIONS_SCHEMA` ligne 26-33, puis nouvelles fonctions)
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes: `_now()`, `_get_state()`, `has_active_subscription()` (existants dans `src/subscriptions/db.py`)
- Produces:

  - `TRIAL_DAYS: int` (= 2)
  - `start_trial_if_new(user_id: int) -> None`
  - `trial_ends_at(user_id: int) -> datetime | None`
  - `trial_active(user_id: int) -> bool`
  - `has_access(user_id: int) -> bool`

- [ ] **Step 1: Écrire les tests en échec**

Dans `tests/subscriptions/test_db.py`, en suivant le montage déjà utilisé dans
ce fichier (fixture `users_db_path`, helper `_make_user()`, `db.init_schema()`).

Ce que les tests doivent prouver :

1. `start_trial_if_new` crée la ligne `subscriber_state` quand elle n'existe
   pas, et y écrit un `trial_ends_at` situé environ 2 jours dans le futur
   (assertion sur l'écart, tolérance de quelques secondes — pas seulement
   « non nul »).
2. Un second appel à `start_trial_if_new` **ne modifie pas** la valeur : lire
   `trial_ends_at` avant et après, et prouver l'égalité stricte. Ne pas se
   contenter de vérifier que l'essai est toujours actif.
3. `start_trial_if_new` sur un `user_id` inexistant n'insère aucune ligne et ne
   lève pas.
4. `trial_active` est vrai pour une échéance future, faux pour une échéance
   passée, faux quand `trial_ends_at` est `NULL`, faux quand la ligne
   `subscriber_state` est absente.
5. `trial_active` tolère un horodatage suffixé `Z` (comme
   `has_active_subscription` le fait déjà) et renvoie `False` — sans lever —
   sur une valeur non parsable.
6. `has_access` est vrai pendant l'essai **sans aucune ligne `subscriptions`**,
   vrai pour un abonné `active` dont l'essai est expiré, et faux quand ni l'un
   ni l'autre.
7. `has_active_subscription` reste **fausse** pendant l'essai seul : c'est la
   propriété dont dépendent la garde de `subscribe()` et `_post_login_url`.
   Ce test est le garde-fou du chantier.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_db.py -v -k "trial or has_access"`
Expected: FAIL — `AttributeError: module 'src.subscriptions.db' has no attribute 'start_trial_if_new'`

- [ ] **Step 3: Ajouter la colonne au schéma et la migration**

Dans `src/subscriptions/db.py`, la table `subscriber_state` de
`SUBSCRIPTIONS_SCHEMA` gagne une colonne (les bases fraîches la reçoivent
directement) :

```sql
CREATE TABLE IF NOT EXISTS subscriber_state (
    user_id                 INTEGER PRIMARY KEY,
    trial_used              INTEGER NOT NULL DEFAULT 0,
    trial_ends_at           TEXT,
    votes_balance           INTEGER NOT NULL DEFAULT 0,
    votes_last_credited_at  TEXT,
    updated_at              TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

Dans `src/migrations.py`, à la fin de `_MIGRATIONS` :

```python
    (
        "0014_add_trial_ends_at_to_subscriber_state",
        "ALTER TABLE subscriber_state ADD COLUMN trial_ends_at TEXT",
    ),
```

- [ ] **Step 4: Écrire les fonctions**

Dans `src/subscriptions/db.py`, après `INITIAL_VOTES` :

```python
TRIAL_DAYS = 2
```

Puis, après `has_used_trial` :

```python
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
    if row is None or row["trial_ends_at"] is None:
        return None
    try:
        return datetime.fromisoformat(row["trial_ends_at"].replace("Z", "+00:00"))
    except ValueError:
        return None


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
```

`timedelta` est déjà importé en tête de fichier (ligne 3).

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: PASS (y compris les tests préexistants du fichier)

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/migrations.py src/subscriptions/db.py tests/subscriptions/test_db.py
git add src/migrations.py src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "Fenêtre d'essai en base : trial_ends_at, trial_active, has_access (#132)"
```

---

### Task 2: Démarrage de l'essai à l'activation du compte

**Files:**

- Modify: `src/auth/routes.py` (`verify_email()` lignes 115-130, `linkedin_callback()` lignes 303-340)
- Test: `tests/auth/test_verify_email.py`, `tests/auth/test_auth.py`

**Interfaces:**

- Consumes: `db.start_trial_if_new(user_id)` (Task 1)
- Produces: paramètre d'URL `essai=demarre` posé sur la redirection qui suit
  l'ouverture de l'essai (consommé par `src/assets/goals.js` en Task 4)

- [ ] **Step 1: Écrire les tests en échec**

Ce que les tests doivent prouver :

1. `GET /auth/verify-email?token=…` valide ouvre l'essai : après l'appel,
   `src.subscriptions.db.trial_active(uid)` est vrai. Le test doit lire l'état
   en base, pas se contenter du code de redirection.
2. La redirection pointe vers `/compte/abonnement` et porte `essai=demarre`.
3. La même chose **sous `TOUS_ABONNES`** : la destination reste
   `/compte/abonnement` (le test existant
   `test_verify_email_tous_abonnes_redirects_to_abonnement` couvre déjà la
   destination ; vérifier qu'il passe toujours).
4. Le test existant
   `test_verify_email_valid_token_logs_in_and_redirects_to_mes_infos` attend
   `/compte/abonnement/mes-infos` : **le mettre à jour** (nouvelle destination
   `/compte/abonnement`) et le renommer en conséquence. Ne pas le supprimer :
   il prouve aussi la connexion et `email_verified == 1`.
5. Retour LinkedIn créant un compte : l'essai est ouvert et la destination
   porte `essai=demarre` **et** `compte_cree=linkedin`.
6. Retour LinkedIn d'un compte **existant** (identité déjà liée, donc
   `compte_cree` faux) : aucun essai n'est ouvert — prouvé en vérifiant que
   `trial_ends_at(uid)` vaut toujours `None` sur un compte préexistant sans
   essai, et non simplement que l'URL n'a pas le paramètre.

`tests/auth/test_auth.py` contient déjà de quoi simuler un retour LinkedIn ;
s'en inspirer plutôt que de remonter un montage.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/auth/test_verify_email.py tests/auth/test_auth.py -v`
Expected: FAIL — la redirection vaut encore `/compte/abonnement/mes-infos` et aucun essai n'est ouvert

- [ ] **Step 3: Implémenter**

Dans `src/auth/routes.py`, remplacer le corps de `verify_email()` à partir de
`db.set_email_verified(user_id)` :

```python
    db.set_email_verified(user_id)
    login_user(User(db.get_user_by_id(user_id)), remember=True)
    from src.subscriptions import db as sub_db

    # L'essai démarre ici et pas à la création du compte : tant que l'email
    # n'est pas vérifié, `login()` refuse la session (voir plus bas), donc le
    # compte est strictement inutilisable et l'horloge tournerait dans le vide.
    sub_db.start_trial_if_new(user_id)
    # `essai=demarre` déclenche l'événement `subscription_trial` côté navigateur
    # (src/assets/goals.js).
    return redirect("/compte/abonnement?essai=demarre")
```

Le `from src.utils import TOUS_ABONNES` et la variable `dest` de cette fonction
disparaissent : la destination ne dépend plus du drapeau.

Dans `linkedin_callback()`, après `login_user(user, remember=True)` :

```python
    login_user(user, remember=True)
    dest = safe_next(oauth_next, fallback=_post_login_url(user.id))
    if compte_cree:
        from src.subscriptions import db as sub_db

        sub_db.start_trial_if_new(user.id)
        # Déclenche `account_created` et `subscription_trial` côté navigateur
        # (src/assets/goals.js).
        dest = _avec_param(dest, "compte_cree", "linkedin")
        dest = _avec_param(dest, "essai", "demarre")
    return redirect(dest)
```

L'ouverture de l'essai est conditionnée à `compte_cree` : un compte créé avant
ce déploiement, qui se connecterait pour la première fois via LinkedIn, ne doit
pas obtenir un essai rétroactif.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/auth/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/auth/routes.py tests/auth/test_verify_email.py tests/auth/test_auth.py
git add src/auth/routes.py tests/auth/
git commit -m "L'essai démarre à l'activation du compte (#132)"
```

---

### Task 3: L'essai ouvre les fonctionnalités réservées

**Files:**

- Modify: `src/pages/_compte_shell.py:41-49`
- Modify: `src/mcp/auth.py:9` (import) et son appelant interne
- Modify: `src/mcp/oauth/consent.py:5,10`
- Test: `tests/test_compte_shell.py`, `tests/mcp/test_oauth_consent.py`, `tests/mcp/test_auth.py`

**Interfaces:**

- Consumes: `has_access(user_id)` (Task 1)
- Produces: rien de nouveau

- [ ] **Step 1: Écrire les tests en échec**

Ce que les tests doivent prouver :

1. `current_user_has_subscription()` est vrai pour un utilisateur dont l'essai
   est en cours et qui n'a **aucune** ligne `subscriptions`.
2. Elle est fausse une fois l'essai expiré, toujours sans ligne
   `subscriptions`.
3. `subscription_ok(user_id)` (MCP OAuth) suit la même règle : vrai pendant
   l'essai, faux après.
4. La garde du transport MCP (`src/mcp/auth.py`) accepte un jeton pendant
   l'essai et le refuse après — en vérifiant le code HTTP réel de la réponse,
   pas seulement une valeur booléenne interne.
5. `TOUS_ABONNES` continue de tout ouvrir.
6. Les votes de la roadmap restent **fermés** pendant l'essai :
   `db.credit_pending(uid)` renvoie 0 pour un utilisateur en essai sans ligne
   `subscriptions`. C'est une propriété que rien dans le code n'impose
   explicitement — elle découle de `_accrues_votes`, qui exige une ligne
   `subscriptions` — donc elle mérite un test qui la verrouille.

Repérer d'abord, dans `src/mcp/auth.py`, l'endroit exact où
`has_active_subscription` est appelée (l'import est ligne 9) : il n'y a qu'un
site d'appel.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_compte_shell.py tests/mcp/test_oauth_consent.py tests/mcp/test_auth.py -v`
Expected: FAIL — l'essai seul ne donne pas encore accès

- [ ] **Step 3: Implémenter**

`src/pages/_compte_shell.py` :

```python
def current_user_has_subscription() -> bool:
    from src.subscriptions import db
    from src.utils import TOUS_ABONNES

    if not current_user.is_authenticated:
        return False
    if TOUS_ABONNES:
        return True
    # has_access, pas has_active_subscription : la période d'essai ouvre les
    # mêmes fonctionnalités qu'un abonnement.
    return db.has_access(current_user.id)
```

`src/mcp/oauth/consent.py` :

```python
from src.subscriptions.db import has_access


def subscription_ok(user_id: int) -> bool:
    return bool(TOUS_ABONNES or has_access(user_id))
```

`src/mcp/auth.py` : remplacer l'import ligne 9 par
`from src.subscriptions.db import has_access` et le site d'appel par
`has_access(...)`.

`src/mcp/account.py` n'est pas modifié : il délègue déjà à
`current_user_has_subscription()`.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/test_compte_shell.py tests/mcp/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/_compte_shell.py src/mcp/auth.py src/mcp/oauth/consent.py
git add src/pages/_compte_shell.py src/mcp/auth.py src/mcp/oauth/consent.py tests/
git commit -m "L'essai ouvre les fonctionnalités réservées (#132)"
```

---

### Task 4: Objectif Matomo `subscription_trial` ré-ancré

**Files:**

- Modify: `src/assets/goals.js`
- Test: `tests/test_goals_asset.py`

**Interfaces:**

- Consumes: paramètre `essai=demarre` posé en Task 2
- Produces: rien

- [ ] **Step 1: Écrire les tests en échec**

`tests/test_goals_asset.py` lit le source dépouillé de ses commentaires
(`_code_sans_commentaires()`). Ce que les tests doivent prouver :

1. Le script réagit au paramètre `essai` et non plus à `souscription`/`plan`.
2. L'événement `subscription_trial` est toujours poussé (l'Action Matomo ne
   change pas, l'objectif configuré côté Matomo reste valide).
3. Le paramètre `essai` est retiré de l'URL après émission — la garde
   anti-recomptage au rechargement.
4. La liste `PLANS`, devenue inutile, a disparu ; adosser cette assertion
   d'absence à une assertion positive prouvant que le bloc `subscription_trial`
   existe toujours.
5. Mettre à jour les tests existants du fichier qui référencent
   `souscription`/`plan`.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_goals_asset.py -v`
Expected: FAIL — `souscription` encore présent

- [ ] **Step 3: Implémenter**

Dans `src/assets/goals.js`, supprimer `var PLANS = ["simple", "soutien"];` et
remplacer le second bloc de `emettre()` par :

```javascript
if (params.get("essai") === "demarre") {
  window._paq.push(["trackEvent", "Abonnement", "subscription_trial"]);
  retirerParams(["essai"]);
}
```

Mettre à jour le commentaire d'en-tête du fichier : le paramètre est désormais
posé par `src/auth/routes.py` au démarrage de l'essai, plus par
`src/subscriptions/routes.py` au retour du checkout.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/test_goals_asset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/assets/goals.js tests/test_goals_asset.py
git add src/assets/goals.js tests/test_goals_asset.py
git commit -m "subscription_trial émis au démarrage de l'essai (#132)"
```

---

### Task 5: Page /compte/abonnement — essai en cours et essai terminé

**Files:**

- Modify: `src/pages/compte/abonnement.py`
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes: `db.trial_active(user_id)`, `db.trial_ends_at(user_id)` (Task 1),
  `format_datetime_french` (déjà importé dans la page)
- Produces: `_trial_view(end)`, `_trial_ended_view()`

- [ ] **Step 1: Écrire les tests en échec**

Les tests de ce fichier appellent directement les fonctions de vue et
inspectent `str(...)` — suivre ce style. Ce que les tests doivent prouver :

1. `_trial_view(end)` affiche la date **et l'heure** de fin (l'essai dure
   2 jours, il se joue à l'heure près) et rappelle les fonctionnalités
   débloquées.
2. `_trial_view(end)` propose un lien de souscription anticipée vers
   `/compte/abonnement/mes-infos`, et annonce que le débit est immédiat et que
   les jours d'essai restants ne sont pas reportés.
3. `_trial_ended_view()` contient le libellé exact
   « Commencer mon abonnement » et un lien vers
   `/compte/abonnement/mes-infos`.
4. `_trial_ended_view()` n'affiche **pas** de montant (la formule n'est pas
   encore choisie) — adosser cette absence à la présence du libellé du bouton.
5. `_active_view` sur un abonnement `pending` ne parle plus de période d'essai
   et propose de reprendre le paiement.
6. Les tests existants `test_active_view_trial_banner*` portent sur une branche
   supprimée : les **retirer**, et vérifier qu'aucun autre test du fichier ne
   dépend d'un `status == "trial"`.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: FAIL — `_trial_view` n'existe pas

- [ ] **Step 3: Implémenter**

Dans `src/pages/compte/abonnement.py`, ajouter après `_free_access_view()` :

```python
def _trial_view(end_raw):
    from src.pages.a_propos.abonnement import abonnement_features

    end = format_datetime_french(end_raw) if end_raw else None
    titre = (
        f"Essai gratuit jusqu'au {end}" if end else "Essai gratuit en cours"
    )
    return html.Div(
        [
            html.H5(titre, className="mb-3"),
            html.P("Votre essai débloque :"),
            abonnement_features,
            dcc.Markdown(
                "À la fin de l'essai, rien n'est prélevé : c'est à vous de "
                "démarrer votre abonnement depuis cette page.",
                className="text-muted mt-3",
            ),
            html.A(
                "M'abonner dès maintenant",
                href="/compte/abonnement/mes-infos",
                className="btn btn-outline-secondary mt-2",
            ),
            # Le débit est immédiat, y compris pendant l'essai : le différer
            # jusqu'à la fin de l'essai reviendrait au prélèvement automatique
            # que ce chantier supprime. Les jours restants sont donc perdus, et
            # il faut le dire avant le clic.
            html.P(
                "Le premier prélèvement a lieu immédiatement ; les jours "
                "d'essai restants ne sont pas reportés.",
                className="text-muted small mt-2",
            ),
        ],
        className="mb-4",
    )


def _trial_ended_view():
    return html.Div(
        [
            html.H5("Votre essai gratuit est terminé", className="mb-3"),
            html.P(
                "Les fonctionnalités réservées aux abonné·es ne sont plus "
                "accessibles. Vous pouvez démarrer votre abonnement à tout "
                "moment."
            ),
            html.A(
                "Commencer mon abonnement",
                href="/compte/abonnement/mes-infos",
                className="btn btn-secondary mt-2",
            ),
        ],
        className="mb-4",
    )
```

Remplacer la branche `elif row["status"] == "trial":` de `_active_view` (lignes
114-120) — plus aucun abonnement Frisbii n'atteint ce statut — et reformuler la
branche `pending` :

```python
    if row["status"] == "pending":
        blocks.extend(
            [
                dbc.Alert(
                    "Votre abonnement n'est pas finalisé : aucune méthode de "
                    "paiement n'a été enregistrée.",
                    color="warning",
                    className="mb-3",
                ),
                html.Form(
                    method="POST",
                    action="/subscriptions/add-payment",
                    children=[
                        _csrf_input(),
                        html.Button(
                            "Ajouter une méthode de paiement",
                            type="submit",
                            className="btn btn-secondary mb-3",
                        ),
                    ],
                ),
            ]
        )
    elif row["status"] == "cancelled":
```

Dans `layout()`, brancher les nouvelles vues avant `_no_sub_view` :

```python
    if _show_active_view(row):
        body.append(_active_view(row))
        body.append(_resiliation_modal(row["current_period_end"]))
    else:
        from src.utils import TOUS_ABONNES

        if TOUS_ABONNES:
            body.append(_no_sub_view(True, row))
        elif db.trial_active(current_user.id):
            end = db.trial_ends_at(current_user.id)
            body.append(_trial_view(end.isoformat() if end else None))
        elif db.trial_ends_at(current_user.id) is not None:
            body.append(_trial_ended_view())
        else:
            body.append(_no_sub_view(False, row))
```

`format_datetime_french` attend une chaîne ISO, d'où le `.isoformat()`.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git add src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "Page abonnement : essai en cours et essai terminé (#132)"
```

---

### Task 6: Page mes-infos — écran de confirmation d'achat

**Files:**

- Modify: `src/pages/compte/abonnement_mes_infos.py`
- Test: `tests/subscriptions/test_mes_infos_plan.py`

**Interfaces:**

- Consumes: `plans.plan_meta(key)["prix_ht"]`
- Produces: `_submit_label(mode, plan_key) -> str`

- [ ] **Step 1: Écrire les tests en échec**

Ce que les tests doivent prouver :

1. `_recap_lines("simple", date(...))` (sans paramètre `trial`) ne contient
   plus de ligne « Période d'essai gratuite », et son « Début de l'abonnement
   payant » vaut la date du jour passée en argument. Adosser l'absence à la
   présence des cinq autres champs exigés au checkout (Vendeur, Prestation,
   Début, Durée, Prix).
2. `_submit_label("subscribe", "simple")` contient « Commencer mon abonnement »
   et « 24 € TTC » ; pour `"soutien"`, « 60 € TTC ». Le montant doit être
   dérivé de `plan_meta`, pas écrit en dur dans le test attendu comme dans le
   code.
3. `_submit_label("configure", …)` renvoie toujours
   « Mettre à jour mon abonnement ».
4. `_select_plan` renvoie le libellé du bouton correspondant à la formule
   cliquée, en plus de ses sorties existantes — vérifier l'arité du tuple
   retourné, qui passe de 6 à 7.
5. Les tests existants qui passent un paramètre `trial`/`trials` sont mis à
   jour.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: FAIL — `_submit_label` n'existe pas, `_recap_lines` attend encore `trial`

- [ ] **Step 3: Implémenter**

Supprimer `_trial_for` — c'est le dernier appelant de
`sub_db.has_used_trial()`, que la Task 8 supprimera ensuite.

`_recap_lines` perd son paramètre `trial` :

```python
def _recap_lines(plan_key: str, today: date) -> list[tuple[str, str]]:
    """Récapitulatif de commande affiché avant la saisie de la carte bancaire.

    Reprend les informations exigées « in the checkout process » par l'organisme
    de validation des paiements : raison sociale complète, description de la
    prestation, date de début et durée de l'abonnement, prix et devise. Le
    panneau équivalent côté Frisbii est replié derrière « Aperçu des détails »,
    d'où ce doublon volontaire.

    Plus de ligne d'essai : l'essai est antérieur et sans lien avec cette
    commande, qui démarre et se facture le jour même.
    """
    meta = plans.plan_meta(plan_key)
    if meta is None:
        return []
    ttc = round(meta["prix_ht"] * 1.2, 2)
    return [
        ("Vendeur", _VENDEUR),
        ("Prestation", f"{meta['label']}. {meta['description']}"),
        ("Début de l'abonnement payant", _jj_mm_aaaa(today)),
        (
            "Durée",
            "1 mois, reconduit automatiquement chaque mois jusqu'à résiliation",
        ),
        (
            "Prix",
            f"{meta['prix_ht']:g} € HT par mois, soit {ttc:g} € TTC par mois "
            "(TVA 20 %), en euros (EUR)",
        ),
    ]


def _recap(plan_key: str | None, today: date | None = None):
    lines = _recap_lines(plan_key, today or date.today()) if plan_key else []
    ...  # inchangé à partir d'ici
```

`timedelta` n'est plus utilisé dans ce fichier : retirer l'import s'il devient
inutile (ruff le signalera).

Nouveau libellé de bouton :

```python
def _submit_label(mode: str, plan_key: str | None) -> str:
    if mode == "configure":
        return "Mettre à jour mon abonnement"
    meta = plans.plan_meta(plan_key) if plan_key else None
    if meta is None:
        return "Commencer mon abonnement"
    ttc = round(meta["prix_ht"] * 1.2, 2)
    return f"Commencer mon abonnement ({ttc:g} € TTC / mois)"


def _submit_button(mode: str, plan_key: str | None):
    return html.Button(
        _submit_label(mode, plan_key),
        id="inf-submit",
        type="submit",
        className="btn btn-secondary",
        disabled=(mode == "subscribe"),
    )
```

`_selectable_cards` perd son paramètre `trial_for` et appelle
`_plan_card(meta, None)` — le badge d'essai par formule disparaît. La signature
de `_plan_card` elle-même est nettoyée en Task 7, qui met à jour cet appel.

`_select_plan` gagne une sortie :

```python
@callback(
    Output("inf-plan-hidden", "value"),
    Output("plan-card-simple", "className"),
    Output("plan-card-soutien", "className"),
    Output("inf-change-hint", "className"),
    Output("inf-change-hint", "children"),
    Output("inf-recap", "children"),
    Output("inf-submit", "children"),
    Input("plan-card-simple", "n_clicks"),
    Input("plan-card-soutien", "n_clicks"),
    State("inf-sub-info", "data"),
    prevent_initial_call=True,
)
def _select_plan(_n_simple, _n_soutien, sub_info):
    selected = "simple" if ctx.triggered_id == "plan-card-simple" else "soutien"
    value, cls_simple, cls_soutien = _selection_state(selected)
    hint_cls, hint_txt = _change_hint(selected, sub_info)
    sub_info = sub_info or {}
    mode = sub_info.get("mode")
    recap = _recap(selected) if mode == "subscribe" else None
    return (
        value,
        cls_simple,
        cls_soutien,
        hint_cls,
        hint_txt,
        recap,
        _submit_label(mode, selected),
    )
```

`inf-submit.children` et `inf-submit.disabled` sont deux propriétés
distinctes : `_toggle_submit`, qui pilote `disabled`, n'entre pas en conflit.

Dans `layout()`, supprimer `trial_for` et `trials`, réduire `sub_info` à
`{"mode": mode}` (plus les clés du mode `configure`), et adapter les appels :
`_selectable_cards(selected=selected)`, `_recap(selected) if mode == "subscribe" else None`,
`_submit_button(mode, selected)`.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git add src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git commit -m "mes-infos : écran de confirmation d'achat, sans essai (#132)"
```

---

### Task 7: Mentions d'essai — inscription et page publique

**Files:**

- Modify: `src/pages/inscription.py`
- Modify: `src/pages/a_propos/abonnement.py`
- Test: `tests/test_abonnement_public.py`, `tests/test_linkedin_button.py`

**Interfaces:**

- Consumes: rien
- Produces: `_plan_card(meta)` (le paramètre `trial` disparaît)

- [ ] **Step 1: Écrire les tests en échec**

Ce que les tests doivent prouver :

1. La page `/inscription` annonce que la validation de l'adresse email démarre
   l'essai de 2 jours, et qu'aucune carte bancaire n'est demandée.
2. `linkedin_next` vaut `/compte/abonnement` que `TOUS_ABONNES` soit vrai ou
   faux (plus de branche).
3. `/a-propos/abonnement` affiche une mention d'essai **unique**, au-dessus des
   formules, et plus un badge par carte — adosser l'absence du badge à la
   présence des deux cartes de formule.
4. `_subscribe_button` continue d'afficher « Je m'abonne » vers
   `/compte/abonnement/mes-infos` pour un utilisateur authentifié **sans
   abonnement**, y compris pendant son essai. C'est la page de conversion :
   elle ne doit pas basculer sur « Gérer mon abonnement » pendant l'essai.

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_abonnement_public.py tests/test_linkedin_button.py -v`
Expected: FAIL — la mention d'essai est absente

- [ ] **Step 3: Implémenter**

Dans `src/pages/inscription.py`, supprimer le calcul conditionnel de
`linkedin_next` (et l'import `TOUS_ABONNES` s'il devient inutile) :

```python
    linkedin_next = "/compte/abonnement"
```

et insérer, juste avant le `dbc.Button("Créer le compte", …)` :

```python
                    html.P(
                        "Votre essai gratuit de 2 jours démarre dès la "
                        "validation de votre adresse email. Aucune carte "
                        "bancaire n'est demandée.",
                        className="text-muted small mb-3",
                    ),
```

Dans `src/pages/a_propos/abonnement.py`, `_plan_card` perd son paramètre et son
badge :

```python
def _plan_card(meta: dict):
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"], className="mb-1"),
                html.P(
                    f"{meta['prix_ht']} € HT / mois "
                    f"({round(meta['prix_ht'] * 1.2, 2):g} € TTC)",
                    className="text-muted mb-3",
                ),
                html.P(meta["description"], className="mb-3"),
            ],
            className="p-4",
        ),
        className="h-100",
    )


def _plan_cards():
    # L'essai n'est plus adossé à une formule : il est ouvert à la création du
    # compte, quelle que soit la formule choisie ensuite. D'où une mention
    # unique au-dessus des cartes plutôt qu'un badge par carte.
    cards = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta))
    return html.Div(
        [
            html.P(
                "2 jours d'essai gratuit à la création de votre compte, sans "
                "carte bancaire.",
                className="text-muted mb-3",
            ),
            dbc.Row([dbc.Col(c, md=6) for c in cards], className="g-4 mb-4"),
        ]
    )
```

`_subscribe_button` et `layout()` ne changent pas : ils restent sur
`sub_db.has_active_subscription`.

Vérifier que `_plan_card` n'est plus appelé avec deux arguments :

```bash
grep -rn "_plan_card(" src/ tests/
```

(l'appel de `src/pages/compte/abonnement_mes_infos.py:156` doit devenir
`_plan_card(meta)`).

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/test_abonnement_public.py tests/test_linkedin_button.py tests/subscriptions/test_mes_infos_plan.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/inscription.py src/pages/a_propos/abonnement.py src/pages/compte/abonnement_mes_infos.py
git add src/pages/ tests/
git commit -m "Mentions d'essai : inscription et page abonnement publique (#132)"
```

---

### Task 8: Plus aucun essai côté Frisbii

**Files:**

- Modify: `src/subscriptions/plans.py` (retirer `trial_days()` et la clé `trial_days`)
- Modify: `src/subscriptions/routes.py:30-42` (`subscribe()`)
- Modify: `src/subscriptions/db.py` (retirer `has_used_trial()`, et l'écriture de `trial_used` dans `update_from_webhook`)
- Test: `tests/subscriptions/test_plans.py`, `tests/subscriptions/test_routes.py`, `tests/subscriptions/test_routes_accept_url.py`, `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes: rien de Task 1-3
- Produces: `client.create_subscription_session(..., no_trial=True)` systématique

- [ ] **Step 1: Écrire les tests en échec**

Ce que les tests doivent prouver :

1. `POST /subscriptions/subscribe` envoie `no_trial: True` dans le corps JSON
   du `POST /v1/subscription` — y compris pour un utilisateur qui n'a **jamais**
   souscrit. Utiliser la fixture `fake_httpx` et inspecter le corps capturé,
   pas seulement le code de retour.
2. L'`accept_url` transmis à la session de checkout ne contient plus
   `souscription=trial` **et** contient bien `paiement=succes` — l'assertion
   d'absence doit être adossée à cette assertion positive, sinon elle passerait
   sur une URL vide.
3. `src.subscriptions.plans` n'expose plus `trial_days` : les tests existants
   `test_trial_days_returns_configured_value` et
   `test_trial_days_none_when_plan_handle_unset` sont **supprimés**.
4. Le test existant `test_trial_used_is_sticky_across_resubscribe`
   (`tests/subscriptions/test_db.py`) porte sur une colonne qu'on cesse
   d'écrire : le **supprimer**. La propriété qu'il protégeait — un essai n'est
   pas rejouable — est désormais couverte par l'idempotence de
   `start_trial_if_new` (Task 1, test 2).
5. Un webhook Frisbii passant un abonnement à `active` met bien à jour le
   statut et `current_period_end` (le reste de `update_from_webhook` est
   intact).

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_routes.py tests/subscriptions/test_routes_accept_url.py -v`
Expected: FAIL — `no_trial` absent du corps pour un premier abonnement

- [ ] **Step 3: Implémenter**

Dans `src/subscriptions/plans.py`, retirer la clé `"trial_days": 2` des deux
entrées de `PLANS` et supprimer la fonction `trial_days()`.

Dans `src/subscriptions/routes.py`, `subscribe()` : remplacer le bloc qui
calcule `no_trial` et enrichit `accept_url` (lignes 31-42) par :

```python
        # L'essai n'existe plus côté Frisbii : il est tenu par colibre
        # (subscriber_state.trial_ends_at) et se termine sans débit. Toute
        # souscription est donc immédiatement payante.
        accept_url = f"{base}/compte/abonnement?paiement=succes"
        cancel_url = f"{base}/compte/abonnement?paiement=annule"
```

et, aux deux appels à `client.create_subscription_session(...)`, remplacer
`no_trial=no_trial` par `no_trial=True`. L'import local
`from src.utils import TOUS_ABONNES` et la variable `no_trial` disparaissent de
cette fonction.

Dans `src/subscriptions/db.py`, supprimer `has_used_trial()` et, dans
`update_from_webhook`, le bloc qui écrit `trial_used` :

```python
    if status in _ACCESS_STATUSES:
        get_conn().execute(
            "UPDATE subscriber_state SET trial_used = 1, updated_at = ? "
            "WHERE user_id = ?",
            (_now(), prev["user_id"]),
        )
```

La colonne `trial_used` reste dans le schéma, inutilisée (retrait dans un
nettoyage ultérieur, hors périmètre).

Vérifier qu'aucun appelant de `has_used_trial` ou `plans.trial_days` ne
subsiste :

```bash
grep -rn "has_used_trial\|trial_days" src/ tests/
```

Expected: aucun résultat. Les tâches 6 et 7 ont déjà retiré les deux seuls
appelants (`_trial_for` dans `abonnement_mes_infos.py`, `_plan_cards` dans
`a_propos/abonnement.py`). Si le grep remonte encore quelque chose, c'est
qu'une tâche précédente est incomplète : la traiter avant de continuer, ne pas
laisser une définition orpheline.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest tests/subscriptions/ tests/test_abonnement_public.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/subscriptions/plans.py src/subscriptions/routes.py src/subscriptions/db.py
git add src/subscriptions/ tests/subscriptions/
git commit -m "Souscription toujours sans essai côté Frisbii (#132)"
```

---

### Task 9: Conditions d'abonnement

**Files:**

- Modify: `src/pages/a_propos/abonnement.py` (bloc `subscription_terms`)
- Modify: `docs/cgv-abonnement-api.md`
- Test: `tests/test_abonnement_public.py`

**Interfaces:**

- Consumes: rien
- Produces: rien

Ces deux textes décrivent aujourd'hui un essai adossé à un abonnement, qui se
transforme en abonnement payant à son échéance. C'est devenu faux.

- [ ] **Step 1: Relever les phrases devenues fausses**

```bash
grep -n "essai\|reconduc\|prélèv\|rétractation" src/pages/a_propos/abonnement.py docs/cgv-abonnement-api.md
```

Produire la liste des phrases concernées **avant** de modifier quoi que ce soit.

- [ ] **Step 2: Écrire le test en échec**

Ce que le test doit prouver : les conditions d'abonnement affichées sur
`/a-propos/abonnement` ne décrivent plus de transformation automatique de
l'essai en abonnement payant, et énoncent que l'abonnement démarre au moment de
la souscription. Adosser l'absence de l'ancienne formulation à la présence de
la nouvelle.

- [ ] **Step 3: Corriger les phrases**

Réécrire **uniquement** les phrases relevées à l'étape 1, au plus près de
l'existant. Ne pas ajouter de nouvelle clause, ne pas allonger les textes : la
règle de fond ne change pas (abonnement mensuel reconduit jusqu'à résiliation),
seul son point de départ change — la souscription explicite, et non plus la fin
d'un essai.

- [ ] **Step 4: Lancer le test**

Run: `uv run pytest tests/test_abonnement_public.py -v`
Expected: PASS

- [ ] **Step 5: Soumettre la formulation avant de commiter**

Afficher le diff des deux fichiers et **attendre la validation de Colin** :
c'est du texte contractuel, il ne se relit pas dans un commit.

```bash
git diff src/pages/a_propos/abonnement.py docs/cgv-abonnement-api.md
```

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/pages/a_propos/abonnement.py docs/cgv-abonnement-api.md
git add src/pages/a_propos/abonnement.py docs/cgv-abonnement-api.md
git commit -m "Conditions d'abonnement : l'essai ne se transforme plus en abonnement (#132)"
```

---

### Task 10: Vérification de bout en bout

**Files:** aucun (sauf correctifs révélés par la suite complète)

- [ ] **Step 1: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS. Certains tests sont Selenium et exigent un Chrome/Chromium
disponible.

- [ ] **Step 2: Traiter les échecs résiduels**

Les échecs attendus à ce stade viennent de tests non listés dans les tâches
précédentes qui référencent l'ancien parcours (redirection vers
`mes-infos` après vérification d'email, badge d'essai, `souscription=trial`).
Les corriger un par un, sans relâcher une assertion pour la faire passer : si
un test devient faux, c'est son intention qu'il faut réécrire.

- [ ] **Step 3: Vérifier qu'aucune trace de l'ancien mécanisme ne subsiste**

```bash
grep -rn "has_used_trial\|trial_days\|souscription=trial" src/ tests/
```

Expected: aucun résultat.

- [ ] **Step 4: Vérification manuelle du parcours**

Avec `uv run run.py` et `TOUS_ABONNES=False` :

1. créer un compte, valider l'email → atterrissage sur `/compte/abonnement`,
   mention « Essai gratuit jusqu'au … », `/compte/mcp` accessible ;
2. avancer artificiellement la fin d'essai
   (`UPDATE subscriber_state SET trial_ends_at = '2020-01-01T00:00:00+00:00'`)
   → `/compte/mcp` renvoie vers `/compte/abonnement`, qui affiche « Votre essai
   gratuit est terminé » et le bouton ;
3. cliquer le bouton → `mes-infos`, choisir une formule → le bouton affiche
   « Commencer mon abonnement (24 € TTC / mois) », le récapitulatif ne
   mentionne aucun essai et démarre le jour même.

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "Ajustements de la suite de tests pour le démarrage manuel d'abonnement (#132)"
```

---

## Après le déploiement (hors code)

- Retirer la période d'essai de la configuration des plans
  `FRISBII_PLAN_SIMPLE` et `FRISBII_PLAN_SOUTIEN` dans Frisbii. Sans cela, un
  oubli de `no_trial` réintroduirait la conversion automatique.
- Vérifier dans Matomo que l'objectif `subscription_trial` reçoit toujours des
  événements après le changement d'ancrage.
