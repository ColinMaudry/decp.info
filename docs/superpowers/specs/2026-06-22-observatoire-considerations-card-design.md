# Tuile « Considérations sociales et environnementales » — Observatoire

## Objectif

Ajouter dans `/observatoire` une tuile (card) qui visualise, à l'aide de barres
de progression « plus ou moins remplies », la part des marchés publics filtrés
qui comportent **au moins une considération sociale** et la part qui comportent
**au moins une considération environnementale**.

La tuile s'insère juste **après la tuile « Type d'achat »**, avec le même style
que les autres cards.

## Données

Colonnes concernées (type `String`, valeurs libres potentiellement composées) :

- `considerationsSociales`
- `considerationsEnvironnementales`

Exemples de valeurs : `Sans objet`, `Clause sociale`, `Critère social`,
`Marché réservé`, `Clause environnementale`, `Critère environnemental`,
`Pas de considération sociale`, `null`, ou des combinaisons
(`Critère social, Clause sociale`).

### Définition « au moins une considération »

Un marché compte comme ayant une considération si la valeur de la colonne
**contient** l'un des mots-clés (insensible à la casse) :

- `Clause`
- `Critère`
- `Marché réservé`

Regex utilisée : `(?i)Clause|Critère|Marché réservé`.

Conséquence (validée avec l'utilisateur) : **`Marché réservé` compte comme
considération sociale**. Les valeurs `Sans objet`, `Pas de considération…` et
`null` ne contiennent aucun de ces mots-clés et ne comptent donc pas.

### Calcul du pourcentage

- **Dédoublonnage par `uid`** : un marché est compté une seule fois même s'il
  apparaît sur plusieurs lignes (plusieurs titulaires). On prend la première
  valeur de chaque colonne par `uid`.
- **Dénominateur** : **tous** les marchés filtrés (y compris `Sans objet` et
  non renseignés) — validé avec l'utilisateur.
- **Numérateur** : nombre de marchés (uid distincts) dont la valeur de colonne
  satisfait la regex.
- `pourcentage = round(100 * numérateur / dénominateur)` ; si dénominateur = 0,
  pourcentage = 0.

## Composant visuel

Nouvelle fonction `get_considerations_card_content(lff: pl.LazyFrame)` dans
`src/figures.py`, renvoyant un `html.Div` contenant deux barres `dbc.Progress`
empilées :

| Considération     | Couleur (px.colors.qualitative.Safe) | Valeur RGB           |
| ----------------- | ------------------------------------ | -------------------- |
| Sociales          | index 1 (rouge)                      | `rgb(204, 102, 119)` |
| Environnementales | index 3 (vert)                       | `rgb(17, 119, 51)`   |

Chaque barre :

- `dbc.Progress(value=pourcentage, label=f"{pourcentage} %", style={"backgroundColor": <couleur>})`
- précédée d'un libellé (`Sociales` / `Environnementales`) et suivie du nombre
  de marchés concernés (`N marchés`), formaté avec `format_number`.

### Robustesse (colonne absente)

`tests/test.parquet` peut ne pas contenir ces colonnes. La fonction vérifie la
présence de chaque colonne via `lff.collect_schema().names()` ; si une colonne
manque, son pourcentage et son compte valent 0 (pas d'exception), à l'image de
`get_distance_histogram`.

## Intégration

Dans `src/pages/observatoire.py`, fonction `_compute_dashboard_children` :

```python
donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?")
cards.append(make_card(title="Type d'achat", ...))

# NOUVEAU
considerations = get_considerations_card_content(lff)
cards.append(
    make_card(
        title="Considérations sociales et environnementales",
        subtitle="part des marchés concernés",
        fig=considerations,
    )
)
```

`make_card` utilise ses dimensions par défaut (`lg=6, xl=4`), comme la tuile
« Type d'achat ».

Import à ajouter : `get_considerations_card_content` depuis `src.figures`.

## Tests

- Test unitaire de `get_considerations_card_content` sur un petit `LazyFrame`
  construit en mémoire couvrant : valeur avec considération, `Sans objet`,
  `null`, `Marché réservé`, doublon de `uid`. Vérifier les pourcentages
  attendus.
- Cas colonne absente → 0 % sans exception.

## Hors périmètre (YAGNI)

- Pas de tooltip détaillé sur les types de considérations.
- Pas de graphe de répartition par type (clause vs critère).
- Pas de nouveau filtre (les filtres existants `social`/`env` restent inchangés).
