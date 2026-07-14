# Refonte du système de votes de la roadmap

**Date :** 2026-07-14
**Statut :** proposé (en attente de validation)

## 1. Contexte et objectifs

Les abonné·es votent pour les fonctionnalités à développer en priorité, sur la
page `/compte/roadmap`. La liste des features « au vote » vient des issues GitHub
portant le label `mis au vote` ; elle s'allonge quand une idée est validée et se
raccourcit quand une feature entre en développement (label `en cours`).

Objectifs du responsable projet pour le mécanisme de vote :

1. **Favoriser les utilisateurs fréquents** (qui utilisent l'appli) plutôt que
   les visiteurs ponctuels.
2. **Donner une impression d'impact réel** : pouvoir exprimer qu'une feature est
   essentielle et une autre secondaire.
3. **Empêcher qu'un seul utilisateur fasse basculer le destin d'une feature** en y
   concentrant tous ses votes.
4. **Rester lisible** — une bonne signalétique peut porter un système un peu
   subtil, mais le principe doit s'expliquer en une phrase.

**Inconnue structurante :** le nombre de votants. Le problème est bien plus simple
à 50 votants qu'à 5. Cette inconnue est traitée par une précondition de
déploiement (§5), pas par le mécanisme lui-même.

## 2. Système actuel

- **Solde** : chaque abonné actif a un solde plafonné à `VOTES_PER_WEEK = 3`,
  rechargé paresseusement de +3 par **semaine glissante de 7 jours propre à chaque
  user** (`credit_pending` dans `src/subscriptions/db.py`), **sans accumulation**
  (cap à 3).
- **Dépense** : voter = `spend_vote` (débit de 1 si solde > 0) + `record_vote`
  (insertion d'une ligne dans `feature_votes`). **Aucune limite par feature** : les
  3 votes peuvent aller sur la même.
- **Classement** : `vote_counts` = `COUNT(*)` par `issue_number`, **sur toute
  l'histoire**, sans fenêtre temporelle.

Deux problèmes :

- **Comptage cumulatif à vie.** Une feature présente depuis 10 semaines a accumulé
  des votes qu'une feature ajoutée cette semaine ne rattrapera jamais. Le classement
  mesure autant l'ancienneté dans la liste que la popularité — ce qui mine le
  « consensus fidèle » recherché. C'est le problème principal.
- **Objectifs 2 et 3 en tension.** Exprimer l'intensité = pouvoir concentrer ;
  empêcher un seul de basculer = empêcher la concentration. Aucun mécanisme ne
  satisfait les deux à 100 % ; il s'agit de choisir où placer le curseur.

## 3. Décisions de conception

### 3.1 Saison mensuelle (« championnat »)

Le vote fonctionne par **saisons = mois calendaires**. Le classement d'une feature
n'agrège que **ses votes du mois courant**. Au changement de mois, les compteurs
repartent de zéro et le ballot est renouvelé.

- Résout le comptage cumulatif : dans une saison, N est figé et toutes les features
  ont couru la même distance ; on ne compare pas les totaux d'un mois à l'autre
  (chaque mois est son propre championnat, on en tire le·s vainqueur·s).
- **Le ballot ne change qu'au 1er** : une idée validée le 3 attend le 1er suivant
  (délai ≤ ~4 semaines, acceptable pour un rythme de roadmap). Convention opérateur
  sur les labels GitHub (voir §4.3).

### 3.2 Recharge hebdomadaire, lundi, sans report

Le solde reste de **3 votes**, rechargé **chaque lundi à 00h00 (Europe/Paris),
sans report** (cap à 3, use-it-or-lose-it). Cadence **globale calendaire** — « chaque
lundi, tout le monde retrouve ses votes » — remplaçant le timer glissant par-user.

- C'est le rechargement **hebdomadaire** (et non un budget mensuel donné d'un coup)
  qui porte l'**objectif 1** : un visiteur ponctuel du 28 ne peut pas rattraper un
  habitué qui revient chaque semaine.
- 4 ou 5 lundis par mois → 12 ou 15 votes/mois selon les mois. Non problématique :
  tous les votants d'un mois ont les mêmes lundis, et on ne compare pas d'un mois à
  l'autre.

### 3.3 Aucun cap par feature (option A)

Un utilisateur peut concentrer tout son budget mensuel (~12 votes) sur une seule
feature.

**Justification vis-à-vis de l'objectif 3 :** à faible nombre de votants, _aucune_
valeur de cap ne règle vraiment le risque qu'un seul fasse basculer une feature —
ce qui le règle, c'est le **nombre de votants** (la part d'un individu se dilue quand
V augmente, pas quand N change). Plutôt qu'un demi-garde-fou peu lisible, on neutralise
le risque à la source via la précondition de déploiement (§5). Le cap par feature
(plafonner à ~3 votes/feature/saison) reste une **option de durcissement future** si
le whale redevient un problème à l'échelle.

### 3.4 Horloges découplées

Le passage de saison (1er) **ne touche pas le solde** ; seul le lundi le recharge.
Conséquence assumée : quand le 1er ne tombe pas un lundi, un user qui a gardé ses
votes les reporte (≤ 3) sur la nouvelle saison, et un user qui a vidé son solde attend
le lundi suivant. Cohérent avec le use-it-or-lose-it hebdo.

## 4. Conception technique

Principe directeur : **tout est dérivé du calendrier, aucun cron.** Ni la remise à
zéro de saison ni le rechargement n'exigent de tâche planifiée. **Aucune migration
de schéma** n'est nécessaire — uniquement de la logique.

### 4.1 Saison = fenêtre sur `created_at`

`feature_votes` porte déjà `created_at`. Le classement se restreint au mois courant :

- Ajouter un helper `season_start(now) -> datetime` = 1er du mois courant à 00h00
  Europe/Paris, converti en UTC.
- `vote_counts()` (`src/roadmap/db.py`) ajoute `WHERE created_at >= :season_start`.
  Les `created_at` sont stockés en ISO UTC (`...+00:00`) ; comparer avec
  `season_start.astimezone(timezone.utc).isoformat()` (comparaison lexicographique ISO
  valide car même format/offset).

Aucun effacement : au changement de mois, la fenêtre glisse et les votes du mois
précédent sortent du décompte (ils restent en base comme historique ; purge
éventuelle plus tard).

### 4.2 Recharge = lundi calendaire, paresseux

Réécrire `credit_pending` et `next_recharge_at` (`src/subscriptions/db.py`) autour du
lundi Europe/Paris au lieu de `WEEK_SECONDS` :

- `last_monday(now) -> datetime` = lundi 00h00 Europe/Paris le plus récent (UTC).
- `next_monday(now) -> datetime` = lundi 00h00 Europe/Paris suivant (UTC) — pour
  l'affichage « rechargement le … ».
- `credit_pending(user_id)` :
  - garde la garde `status == "active"` (les essais ne votent pas).
  - première activation (`votes_last_credited_at is None`) → `balance = INITIAL_VOTES`,
    cursor = `last_monday(now)`.
  - sinon, si `votes_last_credited_at < last_monday(now)` → `balance = VOTES_PER_WEEK`
    (on **fixe** à 3, pas d'ajout : ni report ni accumulation des lundis manqués),
    cursor = `last_monday(now)`. Idempotent : sans effet si déjà crédité pour ce lundi.
- `next_recharge_at(user_id)` → `next_monday(now)` (indépendant du cursor).
- `WEEK_SECONDS` devient inutile (à retirer).

`zoneinfo.ZoneInfo("Europe/Paris")` pour les bornes locales ; cursors stockés en UTC.

### 4.3 Appartenance au ballot

Source de vérité inchangée : les labels GitHub (`fetch_roadmap_issues`). **Convention
opérateur : ne re-labelliser (`mis au vote` / `en cours`) qu'au 1er du mois**, pour que
le ballot reste figé pendant la saison.

_Fragilité connue :_ une re-labellisation en cours de mois ferait apparaître/disparaître
une feature en pleine saison (une nouveauté démarrerait à 0 face à des features déjà
votées). Acceptable en v1 (Colin est seul opérateur). **Durcissement futur possible :**
snapshoter les `issue_number` au vote en début de saison dans une table dédiée.

### 4.4 Déploiement des données existantes

Au déploiement, les lignes `feature_votes` accumulées à vie restent en base mais seules
celles du mois courant comptent → le classement « se réinitialise » de fait sur le mois
en cours. Comportement désiré, aucune action de données requise.

### 4.5 UI

- `src/roadmap/ui.py` : le libellé du solde peut évoquer le rechargement hebdo
  (« rechargement le lundi ») et, si utile, la logique de saison. `_balance_item`
  affiche déjà `next_recharge`.
- Signalétique à prévoir (texte de `roadmap_content`) : expliquer le championnat mensuel
  et les 3 votes/semaine. Détails de rédaction hors périmètre de cette spec.

### 4.6 Ce qui ne change pas

`spend_vote`, `record_vote`, le flux du bouton « + » (`cast_vote`), la source GitHub des
issues, le schéma SQLite.

## 5. Précondition de déploiement

**Ce système n'entre pas en production tant que le nombre d'utilisateurs votant
(système actuel) n'a pas dépassé un seuil** défini par le responsable projet. En
dessous du seuil, on conserve le système actuel.

C'est le levier qui remplace le cap par feature pour l'objectif 3 : on n'ouvre le vote
concentré-libre que lorsqu'il y a assez de votants pour diluer un dumpeur. Le seuil est
un go/no-go opérateur, **pas** un paramètre de code. Pour l'évaluer : nombre de
`user_id` distincts ayant voté sur la dernière saison, ou nombre d'abonnés actifs
pouvant voter.

## 6. Tests

Cibler `tests/subscriptions/test_db.py` et `tests/roadmap/` :

- **Saison** : un vote daté du mois précédent n'est pas compté ; un vote du mois courant
  l'est ; bornes autour du 1er 00h00 Europe/Paris.
- **Recharge** : franchissement d'un lundi → solde fixé à 3 (pas 3+report) ; pas de
  re-crédit le même lundi (idempotence) ; première activation → `INITIAL_VOTES` ;
  `next_recharge_at` = prochain lundi.
- **Fuseau** : un vote/rechargement autour de minuit tombe du bon côté en Europe/Paris
  (vérifier notamment l'heure d'été).
- **Découplage** : un passage de mois ne modifie pas le solde.

## 7. Points différés

- Valeur exacte du seuil de déploiement (§5).
- Snapshot du ballot en début de saison pour figer strictement l'appartenance (§4.3).
- Rédaction de la signalétique utilisateur (§4.5).
- Purge éventuelle des vieilles lignes `feature_votes`.
- Cap par feature comme durcissement si le whale réapparaît à l'échelle.
