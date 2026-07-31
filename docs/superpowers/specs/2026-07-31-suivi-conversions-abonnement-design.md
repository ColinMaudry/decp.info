# Suivi des conversions d'abonnement et consolidation Matomo

Date : 2026-07-31

## Objectif

Mesurer dans Matomo trois moments du parcours utilisateur — la création de
compte, le démarrage d'un essai, le passage en abonnement payant — en rattachant
les deux premiers à la campagne d'acquisition d'origine.

Cette mesure n'est pas déployable en l'état : la configuration Matomo du projet
est éclatée en trois conventions divergentes, dont une est muette en production.
La consolidation est donc un prérequis, traité dans le même document.

## Contexte : l'état réel de la configuration Matomo

Inventaire au 2026-07-31, croisé entre le dépôt et le `.env` de production.

| Chemin de suivi                                    | Variables lues                                                  | État en production |
| -------------------------------------------------- | --------------------------------------------------------------- | ------------------ |
| Traqueur navigateur (`src/utils/matomo.py`)        | `MATOMO_TRACKING_ENABLED` + domaine et site ID **codés en dur** | fonctionne         |
| Recherches et outils MCP (`src/utils/tracking.py`) | `MATOMO_DOMAIN`, `MATOMO_ID_SITE`, `MATOMO_TOKEN`               | fonctionne         |
| Suivi de l'API (`src/api/tracking.py`)             | `MATOMO_URL`, `MATOMO_SITE_ID`                                  | **muet**           |

Le `.env` de production porte `MATOMO_ID_SITE`, `MATOMO_DOMAIN`, `MATOMO_TOKEN`
et `MATOMO_TRACKING_ENABLED`. Il ne porte ni `MATOMO_URL` ni `MATOMO_SITE_ID`.
Or `enqueue_matomo_event` (`src/api/tracking.py:64-67`) retourne sans rien
émettre si l'une des deux manque : le suivi Matomo de l'API n'a donc jamais rien
remonté en production, sans qu'aucun signal ne le révèle.

`MATOMO_BASE_URL`, présente dans `.env` et `.template.env`, n'est lue nulle part
dans le code.

## Périmètre

1. Consolidation de la configuration Matomo sur une convention unique.
2. Suivi des trois conversions du parcours, et leur neutralisation sous
   `TOUS_ABONNES`.

Le second dépend du premier : le nouvel émetteur se pose sur la convention
consolidée plutôt que d'en inaugurer une quatrième.

## Partie 1 — Consolidation Matomo

### Convention retenue

`MATOMO_URL` / `MATOMO_SITE_ID` / `MATOMO_TRACKING_ENABLED`.

Motifs : c'est la convention documentée dans `.template.env`, celle qu'emploient
les tests existants, et son drapeau d'activation est déjà présent en production
et déjà partagé par les trois chemins. `MATOMO_URL` porte une URL complète, plus
explicite qu'un domaine nu auquel le code recolle `https://` et `/matomo.php` à
deux endroits.

Variables supprimées : `MATOMO_DOMAIN`, `MATOMO_ID_SITE`, `MATOMO_TOKEN`,
`MATOMO_BASE_URL`.

### 1.1 — Une garde unique : `tracking_enabled()`

Les quatre points d'émission — `build_tracker_script` (`src/utils/matomo.py`),
`track_search` et `track_mcp_tool` (`src/utils/tracking.py`),
`enqueue_matomo_event` (`src/api/tracking.py:62`) et le nouveau
`track_subscription_goal` — partagent un seul helper, dans
`src/utils/matomo.py` :

```python
def tracking_enabled() -> bool:
    if os.getenv("DEVELOPMENT", "False").lower() == "true":
        return False
    return os.getenv("MATOMO_TRACKING_ENABLED", "false").lower() == "true"
```

Deux effets.

**`DEVELOPMENT` neutralise tout le suivi.** C'est ce qui protège le Matomo de
production des instances non-prod. Aujourd'hui, si test.colibre.fr porte
`MATOMO_TRACKING_ENABLED=true`, ses pages vues alimentent déjà le site 14 ; la
garde corrige donc une pollution existante, pas seulement le risque introduit
par les futures conversions. Un garde-fou dans le dépôt survit à un `.env`
recopié de travers ou à une nouvelle instance de test, contrairement à une
consigne de déploiement.

**La lecture est faite à l'appel, pas à l'import.** Le helper lit
`os.getenv("DEVELOPMENT")` plutôt que la constante `DEVELOPMENT` de
`src/utils/__init__.py:33`, figée au premier import. C'est délibéré :
`pyproject.toml:56` pinne `DEVELOPMENT=true` pour toute la suite de tests, donc
une garde reposant sur la constante rendrait intestable le chemin « traqueur
émis quand il est activé ». Or ce chemin est précisément celui que l'incident
#128 avait laissé passer, et que `tests/test_matomo.py` couvre depuis. Avec une
lecture à l'appel, ces tests lèvent la garde par `monkeypatch.setenv`.

Le corollaire : la garde est contournable en modifiant l'environnement à chaud.
Sans importance en production, où l'environnement est figé au démarrage.

`enqueue_matomo_event` remplace donc son test inline de
`MATOMO_TRACKING_ENABLED` par un appel au helper. Le long commentaire qui le
précède (`src/api/tracking.py:56-61`), qui décrit la variable comme partagée
entre deux chemins, devient obsolète et est réécrit : la garde est désormais
commune aux quatre.

### 1.2 — `src/utils/tracking.py` migre sur la convention unique

`track_search` et `track_mcp_tool` lisent désormais `MATOMO_URL` et
`MATOMO_SITE_ID`.

Deux changements de comportement associés :

- **Garde unifiée.** La condition passe de la constante `DEVELOPMENT` à
  `tracking_enabled()`, comme les trois autres chemins. Un seul interrupteur
  pour toute l'analytique.
- **`token_auth` supprimé.** L'endpoint `matomo.php` est public par construction —
  c'est celui qu'appelle le `matomo.js` de chaque visiteur. `token_auth` n'est
  requis que pour les paramètres privilégiés (`cip`, `cdt` au-delà de ~24 h,
  `country`/`region`/`city`/`lat`/`long`), qu'aucune de ces fonctions n'utilise.
  Les paramètres `h`/`m`/`s` de `track_search` sont de simples indications
  d'heure locale, non privilégiées. Surtout, `src/utils/tracking.py` envoie
  aujourd'hui ce secret via `params=`, donc **dans la query string**, où il
  atterrit dans les journaux d'accès de Matomo. L'envoi passe en `data=`,
  aligné sur `src/api/tracking.py`.

### 1.3 — `src/utils/matomo.py` cesse de coder le serveur en dur

`build_tracker_script` dérive aujourd'hui son endpoint de deux constantes
littérales (`src/utils/matomo.py:34` et `:36`). Elles sont remplacées par des
valeurs dérivées de `MATOMO_URL` et `MATOMO_SITE_ID`.

L'URL de base du tracker s'obtient en retirant le suffixe `matomo.php` de
`MATOMO_URL`. Les deux valeurs sont injectées dans le JavaScript via
`json.dumps`, de sorte qu'une apostrophe ou un guillemet dans la variable
produise un littéral valide au lieu de casser le script.

`build_tracker_script` s'appuie sur `tracking_enabled()` et retourne en outre la
chaîne vide si `MATOMO_URL` ou `MATOMO_SITE_ID` manque, même quand la garde
passe — comportement cohérent avec l'avertissement ci-dessous.

`src/app.py` et `src/seo/routes.py` ne changent pas : tous deux appellent déjà
`build_tracker_script()` et ne portent aucune valeur en dur.

### 1.4 — Avertissement au démarrage sur configuration incomplète

Si `tracking_enabled()` est vrai mais que `MATOMO_URL` ou `MATOMO_SITE_ID`
manque, l'application journalise un avertissement au démarrage, nommant la ou
les variables absentes.

C'est ce qui manquait pour que la panne du suivi de l'API se voie. Une
configuration incomplète cesse d'être une panne silencieuse.

L'avertissement est émis **au niveau module de `src/utils/matomo.py`**, donc une
seule fois lors du premier import. Ce placement est délibéré : le loger dans
`build_tracker_script` le répéterait à chaque requête, puisque
`src/seo/routes.py:65` appelle cette fonction par requête via son
`context_processor`. Il évite aussi de toucher `src/app.py`, qui reste inchangé.

### 1.5 — Nettoyage des fichiers d'environnement

`.template.env` perd `MATOMO_DOMAIN`, `MATOMO_ID_SITE`, `MATOMO_TOKEN` et
`MATOMO_BASE_URL`, et conserve le triplet retenu.

### 1.6 — Étape de déploiement

**Le `.env` de production doit recevoir `MATOMO_URL` et `MATOMO_SITE_ID` avant
ou pendant la mise en ligne.** À défaut, les recherches et les appels d'outils
MCP — qui fonctionnent aujourd'hui — s'éteignent à leur tour.

```
MATOMO_URL=https://analytics.maudry.com/matomo.php
MATOMO_SITE_ID=14
```

Les anciennes clés peuvent être retirées dans la foulée.

**Vérification après mise en ligne.** La garde de §1.1 interdisant toute
émission depuis test.colibre.fr, rien n'est validable en pré-production : le
contrôle se fait donc en production, une fois déployé. Trois points, dans
l'ordre :

1. Le journal de démarrage ne contient pas l'avertissement de §1.4.
2. Le rapport _Visiteurs_ continue de recevoir des pages vues, et le rapport
   _Recherches_ de nouvelles requêtes — c'est ce qui prouve que la migration
   n'a pas éteint ce qui fonctionnait.
3. Le suivi de l'API, muet jusqu'ici, produit enfin des hits.

Hors code : `MATOMO_TOKEN` a été exposé en clair pendant la conception. Comme il
n'est plus utilisé par le code, il est simplement supprimé du `.env` ; il donne
accès à l'API de reporting du Matomo, donc il est à révoquer côté Matomo.

## Partie 2 — Suivi des conversions

### Mécanique retenue

Trois événements Matomo, chacun adossé à son propre objectif (goal) déclenché
par correspondance exacte sur l'_Event Action_.

|                   | Event Category | Event Action          | Event Name            | Event Value |
| ----------------- | -------------- | --------------------- | --------------------- | ----------- |
| Compte créé       | `Compte`       | `account_created`     | `email` ou `linkedin` | —           |
| Essai démarré     | `Abonnement`   | `subscription_trial`  | plan                  | —           |
| Abonnement payant | `Abonnement`   | `subscription_active` | plan                  | `prix_ht`   |

Un objectif par événement plutôt qu'un motif unique `subscription_` : un objectif commun
fusionnerait les deux moments dans le rapport Objectifs et ferait disparaître le
taux de transformation entre essai et abonnement payé, qui est la métrique
recherchée.

Les trois événements dessinent l'entonnoir complet — compte créé, essai démarré,
abonnement payé — et les deux premiers, émis côté navigateur, portent
l'attribution de campagne.

L'essai ne porte pas de montant : il génère 0 €. Cela évite aussi de faire
transiter le prix par l'URL de retour du checkout. Seul l'objectif « abonnement
payant » active l'option « utiliser la valeur de l'événement comme revenu », ce
qui donne un chiffre d'affaires par campagne sans figer les prix dans la
configuration Matomo.

### 2.1 — `account_created` : côté navigateur

Deux chemins de création de compte, tous deux avec navigateur présent, donc tous
deux attribuables. L'_Event Name_ porte la méthode, ce qui permet de comparer le
rendement des deux parcours par campagne.

`src/mcp/account.py:30` crée un **jeton MCP**, pas un compte : hors périmètre.

**Formulaire** (`src/auth/routes.py:80`). L'événement ne se pose pas sur
`create_user` : si l'envoi du mail de vérification échoue, `routes.py:87` fait
`db.delete_user(user_id)` et le compte disparaît trois lignes plus bas. Il se
pose sur la redirection finale (`routes.py:89`), atteinte uniquement en cas de
succès :

```
/connexion?pending_verification=1&compte_cree=email
```

Conformément au cadrage, l'événement est émis à l'inscription et non à la
vérification de l'email : c'est le seul moment où le visiteur est encore dans la
visite issue de son clic sur l'annonce. Le lien de vérification est souvent
ouvert depuis une autre application ou un autre appareil, donc depuis un
visiteur Matomo distinct et sans campagne. Le corollaire assumé : les
inscriptions jamais vérifiées sont comptées. Ce taux se lit dans SQLite via la
colonne `users.email_verified`.

**LinkedIn** (`src/auth/routes.py:48`). `resolve_oauth_user` a trois branches et
**une seule est une création** :

| Branche        | Cas                                    | Événement                 |
| -------------- | -------------------------------------- | ------------------------- |
| `routes.py:38` | identité OAuth connue                  | non — c'est une connexion |
| `routes.py:42` | email déjà inscrit, identité rattachée | non — le compte existait  |
| `routes.py:48` | `create_oauth_user`                    | **oui**                   |

Sans cette distinction, chaque connexion LinkedIn compterait comme une
inscription.

`resolve_oauth_user` retourne donc `tuple[User, bool]`, le booléen signalant la
création. Son unique appelant applicatif (`routes.py:309`) propage l'information
jusqu'à la redirection.

Cette redirection est le point délicat : contrairement au retour de checkout,
sa cible est variable — `safe_next(oauth_next, fallback=_post_login_url(user.id))`
(`routes.py:313`) — et peut déjà porter une query string. Le paramètre est donc
ajouté par un helper qui recompose l'URL via `urllib.parse`
(`urlsplit` / `parse_qsl` / `urlencode` / `urlunsplit`) plutôt que par
concaténation.

### 2.2 — `subscription_trial` : côté navigateur

Émis depuis le navigateur, au retour du checkout Frisbii. Le visiteur est
présent, donc l'événement s'inscrit dans sa visite en cours et hérite
naturellement de sa campagne d'acquisition.

`src/subscriptions/routes.py` connaît déjà `no_trial` (ligne 31) dans la portée
même où il construit l'`accept_url` (lignes 62 et 74). Cette URL reçoit un
discriminant :

```
/compte/abonnement?paiement=succes&souscription=trial&plan=<plan_key>
```

Le discriminant n'est ajouté que lorsque `no_trial` est faux. Aucune lecture en
base n'est nécessaire, donc aucune course avec le webhook Frisbii — qui peut
très bien ne pas être encore arrivé quand le navigateur atterrit.

Le callback d'ajout de moyen de paiement (`routes.py:111`, `:120`, `:125`)
conserve son `?paiement=succes` nu et ne déclenche donc rien, ce qui lève
l'ambiguïté du paramètre partagé.

### 2.3 — L'asset navigateur commun

Un seul asset `src/assets/goals.js` sert les deux événements navigateur, sur le
modèle de `src/assets/consent_pub.js` :

- ne fait rien si `window._paq` est absent (traqueur désactivé, §1.1) ;
- lit la query string et, selon le paramètre trouvé, pousse :
  - `compte_cree=<méthode>` →
    `['trackEvent', 'Compte', 'account_created', méthode]`
  - `souscription=trial` + `plan=<clé>` →
    `['trackEvent', 'Abonnement', 'subscription_trial', plan]`
- retire les paramètres consommés de l'URL via `history.replaceState`, pour
  qu'un rechargement (F5) ne recompte pas la conversion ;
- valide la méthode contre la liste `["email", "linkedin"]` et le plan contre
  les clés connues avant de les transmettre, plutôt que de relayer une valeur
  arbitraire de la query string dans un rapport Matomo.

L'asset est chargé automatiquement par Dash sur ses pages. `/connexion` et
`/compte/abonnement` étant toutes deux des pages Dash, aucune référence
explicite n'est nécessaire dans le gabarit SEO SSR — contrairement à
`consent_pub.js`.

### 2.4 — `subscription_active` : côté serveur

Émis depuis `update_from_webhook` (`src/subscriptions/db.py:265`), qui est le
point de passage unique des changements de statut et lit déjà `prev["status"]`
avant d'écrire le nouveau.

La condition nécessaire existe déjà textuellement à la ligne 286 :

```python
if prev["status"] != "active" and status == "active":
    freeze_votes_cursor(prev["user_id"])
```

Le nouvel appel s'y greffe. Cette condition couvre d'un seul tenant :

- `trial → active` — la transformation d'un essai ;
- `pending → active` — la souscription directe en payant d'un utilisateur ayant
  déjà consommé son essai (`no_trial=True`).

Les deux déclenchent le même événement, conformément à la décision de cadrage :
c'est le même résultat commercial, un abonné payant de plus, et le total se lit
sans additionner deux métriques.

Cet événement n'est **jamais** émis côté navigateur, y compris pour la
souscription directe. Source unique, donc aucun risque de double comptage et
aucune perte si l'utilisateur ferme son onglet avant le retour. On y renonce à
l'attribution de campagne — assumé : un réabonné qui a déjà consommé son essai a
une campagne d'acquisition ancienne et sans intérêt analytique.

Le plan et le montant sont directement disponibles : `get_by_handle` fait
`SELECT *` (`src/subscriptions/db.py:147-155`) et la table porte les colonnes
`plan` et `prix_ht` (`db.py:73-74`), renseignées par `create_pending`. L'appel
lit donc `prev["plan"]` et `prev["prix_ht"]`.

### 2.5 — Neutralisation sous `TOUS_ABONNES`

Sous `TOUS_ABONNES` (`src/utils/__init__.py:36`), l'accès est offert à tous et
la souscription payante est désactivée : `src/subscriptions/db.py:343` note que
« les accès gratuits n'ont pas de ligne `subscriptions` », et le parcours saute
la page de paiement (`src/pages/inscription.py:32-34`,
`src/auth/routes.py:104-106`). Aucun essai ni abonnement ne devrait donc être
enregistré.

Ce n'est pourtant pas garanti par construction, pour deux raisons :

- la route `POST /subscriptions/subscribe` (`src/subscriptions/routes.py:13`)
  **n'est pas gardée** par `TOUS_ABONNES` — seule l'interface l'est. Une requête
  directe atteindrait donc Frisbii ;
- les abonnements créés **avant** l'activation du drapeau continuent de recevoir
  des webhooks, donc de traverser `update_from_webhook`.

Deux gardes explicites :

1. `track_subscription_goal` retourne sans rien émettre sous `TOUS_ABONNES`.
   C'est le point de passage unique des deux événements d'abonnement, donc la
   garde décisive.
2. `src/subscriptions/routes.py` n'ajoute pas le discriminant `souscription` à
   l'`accept_url` sous `TOUS_ABONNES`, ce qui neutralise aussi le chemin
   navigateur à la source.

`account_created` **n'est pas** concerné : une création de compte reste un fait
réel, quel que soit le mode d'accès.

L'import se fait **dans le corps de la fonction** (`from src.utils import TOUS_ABONNES`), et non au niveau module. C'est le motif déjà employé par
`src/subscriptions/db.py:347` et `src/pages/compte/abonnement.py:274` : la
constante étant figée à l'import de `src.utils`, seul l'import différé rend
effectif le `monkeypatch.setattr("src.utils.TOUS_ABONNES", True)` qu'utilisent
les tests existants (`tests/subscriptions/test_db.py:327`).

### 2.6 — Émetteur partagé

`track_subscription_goal(action: str, plan: str | None, revenue: float | None)`
dans `src/utils/tracking.py`, aux côtés de `track_mcp_tool`.

Muet si `tracking_enabled()` est faux, comme les trois autres émetteurs.

Paramètres envoyés à la Tracking API : `idsite`, `rec=1`,
`url=https://colibre.fr/compte/abonnement`, `e_c=Abonnement`, `e_a=<action>`,
`e_n=<plan>`, `e_v=<revenue>`, `rand`, `apiv=1`. Sans `token_auth`, pour les
raisons exposées en 1.1.

L'envoi part dans un thread daemon. Un `httpx.post` synchrone retarderait de
plusieurs secondes la réponse 200 au webhook Frisbii, qui pourrait alors
considérer la livraison en échec et réessayer.

Sans `cip`, Matomo géolocalise ces événements à l'adresse du serveur. C'est
cohérent avec leur nature anonyme, mais le rapport géographique des
`subscription_active` est à ignorer.

## Gestion des erreurs

L'émetteur ne lève jamais. Une panne Matomo ne doit pas faire répondre 502 au
webhook : Frisbii réessaierait, et l'événement pourrait être émis en double.

L'idempotence est acquise sans code dédié. Si Frisbii redélivre un webhook déjà
traité, `prev["status"]` vaut déjà `active` et la condition est fausse.

Côté navigateur, le retrait des paramètres de l'URL protège du rechargement. Il
reste possible de forger une conversion en visitant l'URL avec le paramètre à la
main — sans conséquence à l'échelle du projet, et de toute façon inévitable
puisque l'endpoint de tracking est public et que le navigateur ne s'authentifie
pas.

## Configuration Matomo (hors code)

Deux objectifs à créer dans l'interface Matomo, tous deux déclenchés par « Send
an event », avec _Event Action_ en correspondance **exacte** :

| Nom               | Motif                 | Revenu                |
| ----------------- | --------------------- | --------------------- |
| Compte créé       | `account_created`     | non                   |
| Essai démarré     | `subscription_trial`  | non                   |
| Abonnement payant | `subscription_active` | valeur de l'événement |

La correspondance exacte est préférée à une expression régulière : plus sûre, et
sans groupe de capture inutile.

Aucune nouvelle variable d'environnement n'est introduite par la partie 2.

**test.colibre.fr est couvert par la garde de §1.1.** Sans elle, les abonnements
de test déclencheraient de vraies conversions dans le Matomo de production —
Colin est le seul abonné de cette instance, donc le volume serait faible, mais
un objectif de conversion se lit en unités et non en tendance : quelques faux
positifs suffisent à fausser un taux. `tracking_enabled()` retournant faux dès
que `DEVELOPMENT=true`, rien n'est émis depuis l'instance de test.

Conséquence assumée : les objectifs ne sont pas validables de bout en bout
ailleurs qu'en production. La vérification après déploiement (§1.6) en tient
lieu.

Le même raisonnement vaut pour le paramètre `url` envoyé par l'émetteur, figé à
`https://colibre.fr/compte/abonnement` — cohérent avec `src/api/tracking.py:68`
et `track_mcp_tool`, qui codent déjà ce domaine en dur, mais qui ne distingue
donc pas l'origine des hits.

## Tests

Partie 1 :

- `tracking_enabled()` : faux quand `DEVELOPMENT=true` **même si**
  `MATOMO_TRACKING_ENABLED=true` ; faux quand le drapeau est absent ou à
  `false` ; vrai seulement quand `DEVELOPMENT` est faux et le drapeau à `true`.
  La première assertion est le cœur de la protection de test.colibre.fr.
- `track_search` et `track_mcp_tool` : muets quand `tracking_enabled()` est
  faux ; émettent vers `MATOMO_URL` avec `MATOMO_SITE_ID` sinon ; aucun
  `token_auth` dans la charge utile.
- `build_tracker_script` : chaîne vide si `MATOMO_URL` ou `MATOMO_SITE_ID`
  manque, même quand la garde passe ; le script produit contient les valeurs
  de l'environnement et non les anciennes constantes.
- Avertissement au démarrage journalisé sur configuration incomplète.

Partie 2 :

- `update_from_webhook` : événement émis sur `trial → active` et
  `pending → active` ; **non** émis sur `active → active`,
  `trial → cancelled`, `pending → trial`. Émetteur mocké.
- `src/subscriptions/routes.py` : l'`accept_url` porte `souscription=trial&plan=…`
  quand `no_trial` est faux, et ne le porte pas sinon.
- `track_subscription_goal` : muet quand `tracking_enabled()` est faux ;
  paramètres corrects sinon ; n'exceptionne pas quand le POST échoue.
- **Création de compte** : la redirection du formulaire porte
  `compte_cree=email` ; elle ne le porte pas quand l'envoi du mail échoue et que
  le compte est supprimé.
- **`resolve_oauth_user`** : retourne `cree=True` seulement sur la branche
  `create_oauth_user` ; `False` sur identité connue et sur rattachement d'un
  email existant. Le helper d'ajout de paramètre préserve une query string
  déjà présente dans l'URL de redirection.
- **`TOUS_ABONNES`** : `track_subscription_goal` est muet et l'`accept_url` ne
  porte pas de discriminant quand le drapeau est vrai ; `account_created` reste
  émis. Les tests patchent `src.utils.TOUS_ABONNES` comme
  `tests/subscriptions/test_db.py:327`.

Le fragment JavaScript n'est pas testé par Selenium — le harnais `dash_duo` a
des angles morts sur les attributs de composants, et le fragment est
volontairement mince pour cette raison.

**Ricochet sur les tests existants**, à traiter dans le plan. La suite tourne
avec `DEVELOPMENT=true` et `MATOMO_TRACKING_ENABLED=false`
(`pyproject.toml:56,67`), donc tout test qui attend une émission doit désormais
lever **les deux** verrous :

- `tests/mcp/test_tracking.py:19,38` pose `MATOMO_DOMAIN` et valide un chemin
  qui change de convention : à migrer sur `MATOMO_URL` / `MATOMO_SITE_ID`, plus
  `monkeypatch.setenv("DEVELOPMENT", "false")`.
- `tests/test_matomo.py:24`, `tests/test_seo.py:134` et
  `tests/test_linkedin_consent.py:178` posent `MATOMO_TRACKING_ENABLED=true` et
  attendent un traqueur non vide : ils devront poser aussi `MATOMO_URL`,
  `MATOMO_SITE_ID` et `DEVELOPMENT=false`.
- `tests/test_matomo.py:38` exerce `src/app.py` dans un sous-processus et
  construit son environnement à la main (`env = {**os.environ, ...}`) : les
  trois variables sont à ajouter à ce dict, pas via `monkeypatch`.
- `tests/auth/test_oauth_resolve.py` appelle `resolve_oauth_user` à six
  endroits (lignes 10, 24, 36, 42, 43) et en lit le retour : la signature
  passant à `tuple[User, bool]`, ces appels sont à dépaqueter. C'est aussi
  l'endroit naturel pour assertionner le booléen de création.

Un test de non-régression est à ajouter en miroir : avec `DEVELOPMENT=true` et
`MATOMO_TRACKING_ENABLED=true`, `build_tracker_script()` retourne la chaîne
vide. C'est l'assertion qui garantit qu'aucune instance de test ne réalimentera
le Matomo de production.

## Ce qui n'est délibérément pas fait

- **Pas d'attribution de campagne sur `subscription_active`.** Cela supposerait
  de stocker l'identifiant de visiteur Matomo (`_pk_id`) sur le compte
  utilisateur pour le rejouer côté serveur — donc de relier explicitement une
  identité à un historique de navigation, ce que les mentions légales déclarent
  aujourd'hui impossible. Le compromis retenu place l'attribution sur l'essai,
  qui est le moment d'acquisition.
- **Pas d'unification des trois modules de suivi.** `src/utils/tracking.py`,
  `src/api/tracking.py` et `src/utils/matomo.py` restent distincts ; seule leur
  configuration converge. Fusionner leurs émetteurs déborderait du sujet.
- **Pas d'événement `account_verified`.** L'entonnoir s'arrêterait sur un
  événement mal attribué (§2.1), pour une information que
  `users.email_verified` contient déjà.
- **Pas de garde `TOUS_ABONNES` sur la route `/subscriptions/subscribe`.** Le
  trou relevé en §2.5 est antérieur à ce travail et déborde du sujet : la spec
  neutralise la _mesure_, pas la souscription elle-même. À traiter séparément si
  le drapeau doit devenir une vraie barrière.
- **Pas de rattrapage des données perdues.** Le suivi de l'API a été muet
  jusqu'ici ; rien n'est reconstruit.
- **Pas de site Matomo dédié à test.colibre.fr.** Ce serait l'autre façon
  d'isoler l'instance de test, et elle aurait permis de valider les objectifs de
  bout en bout avant la production. Écartée : elle repose sur une configuration
  serveur correcte, là où la garde de §1.1 est portée par le dépôt et ne peut
  pas être oubliée. Reste ouverte si le besoin de mesurer réellement
  test.colibre.fr apparaît — il faudrait alors lever la garde `DEVELOPMENT`.
