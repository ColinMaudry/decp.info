# Charte graphique des boutons — design

Date : 2026-06-30
Statut : validé (charte), à implémenter

## Problème

Le thème Bootstrap **Simplex** dérive ses couleurs contextuelles à partir de la
couleur primaire. La primaire de decp.info étant un terracotta chaud
(`rgb(179, 56, 33)` = `#b33821`), Simplex calcule un **`danger` mauve** (`#9b479f`)
et un **`secondary` gris très clair**. Résultat constaté sur `/compte/vues` :

- bouton **Renommer** (`color="secondary", outline=True`) : gris clair sur fond
  blanc, quasi illisible ;
- bouton **Supprimer** (`color="danger", outline=True`) : mauve, sans rapport
  sémantique avec une action destructive.

Les couleurs Simplex ne servent donc pas la lisibilité ni la sémantique. Il faut
**redéfinir les styles `primary`, `secondary` et `danger`** des boutons et établir
une charte claire où **chaque style a une fonction**.

## Principe directeur

**La couleur encode la fonction (sémantique) ; le remplissage encode l'emphase.**

Trois rôles seulement. Le code applicatif continue d'écrire
`color="primary|secondary|danger"` + `outline=True|False` exactement comme avant —
le CSS ne fait que restyler ces classes. Aucun changement d'API, aucun helper.

## La charte

| Style (dbc)             | Fonction                                                                                                                 | Apparence                                                                                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `primary` plein         | **L'**action principale validante d'un contexte — idéalement une par écran (Rechercher, Enregistrer, S'abonner, Envoyer) | terracotta plein `#b33821`, texte blanc (dégradé existant conservé)                              |
| `primary` + `outline`   | action affirmative de moindre emphase (quand le plein serait trop lourd)                                                 | bord + texte terracotta, fond transparent ; survol = plein terracotta texte blanc                |
| `secondary` + `outline` | action **neutre / alternative** (Renommer, Annuler, navigation)                                                          | gris ardoise — bord `#5a6570`, texte `#344054`, fond transparent ; survol = fond gris très clair |
| `danger` + `outline`    | action **destructive** dans une liste ou le flux courant (Supprimer, Se désabonner)                                      | rouge `#c0392b` — bord + texte, fond transparent ; survol = plein rouge texte blanc              |
| `danger` plein          | **confirmation finale** destructive (dans une modale)                                                                    | rouge plein `#c0392b`, texte blanc                                                               |

### Règles d'usage

1. **Une seule action `primary` pleine par contexte.** Tout le reste est `outline`
   ou `secondary`.
2. **Le destructif est `outline` par défaut** ; seul le bouton de confirmation
   finale (modale) est plein rouge.
3. **`secondary` est le défaut neutre** — remplace les boutons gris clair
   illisibles sur fond blanc.

## Palette

Quatre valeurs ajoutées/confirmées ; le reste hérité de Simplex.

```
terracotta  #b33821                    primary    (chaud, marque)  — existant
ardoise     texte #344054 / bord #5a6570  secondary  (froid, neutre)
rouge       #c0392b                    danger     (chaud saturé, distinct du terracotta)
disabled    bord #ccc / texte #666     état désactivé — existant, conservé
```

Le rouge `#c0392b` est volontairement plus saturé et légèrement plus froid que le
terracotta `#b33821`, pour rester distinguable à côté d'un bouton primaire.

## Périmètre

### Dans le périmètre

- Override CSS des classes **boutons uniquement** dans `src/assets/css/style.css` :
  - `.btn-primary` (harmonisation du dégradé déjà présent)
  - `.btn-outline-primary`
  - `.btn-secondary` et `.btn-outline-secondary`
  - `.btn-danger` et `.btn-outline-danger`
  - états `:hover`, `:focus-visible`, `:disabled` correspondants
- Audit des boutons existants (~46 occurrences `color=…`, dont 8 `outline=True`)
  pour corriger les cas qui ne respectent pas la charte, en particulier :
  - `src/saved_views/ui.py` : Renommer (`secondary`+outline), Supprimer
    (`danger`+outline) — déjà conformes en intention, à revalider visuellement ;
  - vérifier qu'aucun écran n'a deux `primary` pleins concurrents ;
  - vérifier que les confirmations destructives en modale sont en `danger` plein
    et les déclencheurs en liste en `danger` outline.

### Hors périmètre (inchangé)

- Les variables racine `--bs-primary`, `--bs-danger`, `--bs-secondary`, etc. **ne
  sont pas modifiées.** L'override cible exclusivement les sélecteurs `.btn-*`.
  Conséquence : `dbc.Alert`, badges, `text-danger`, etc. conservent la sémantique
  Simplex.
- `info` / `success` / `warning` : utilisés quasi exclusivement par des
  `dbc.Alert` (bleu / vert / ambre). On garde la sémantique Simplex pour les
  alertes. Aucun bouton `info`/`success`/`warning` n'est restylé.
- `light` (1 bouton, navbar `src/app.py`) et `link` (1 bouton,
  `src/saved_views/ui.py`) : laissés tels quels, hors charte des trois rôles.

## Approche d'implémentation

**Retenue : CSS-only + audit.**

Override des classes `.btn-*` dans `style.css`, puis passe de revue des boutons
existants. Minimal, sans churn d'API, respecte le fonctionnement de
`dash-bootstrap-components`.

**Écartée : helper Python encapsulant `dbc.Button`.** Plus invasif (toucher tous
les appels), aucun bénéfice ici puisque la charte se mappe exactement sur les
`color`/`outline` natifs.

## Détails CSS à respecter

- Scoper aux sélecteurs `.btn-*` pour ne pas toucher alertes/badges.
- Gérer explicitement `:hover`, `:focus-visible` (anneau de focus visible —
  accessibilité clavier) et `[disabled]`.
- Conserver le `border-radius: 3px` et la typographie (`Inter`, poids 400) déjà en
  place pour `.btn-primary`.
- Attention à la spécificité : le `.btn-primary` actuel est ciblé via
  `button.btn.btn-primary`. Aligner la spécificité des nouvelles règles pour
  éviter qu'elles s'annulent avec celles de `bootstrap.simplex.css`.
- Respecter `prefers-reduced-motion` si des transitions de survol sont ajoutées.

## Critères de réussite

- Sur `/compte/vues` : « Renommer » lisible (gris ardoise) et « Supprimer »
  clairement rouge, plus aucun mauve ni gris clair illisible.
- Les trois rôles sont visuellement distincts (terracotta / ardoise / rouge) et
  cohérents sur toutes les pages.
- Les `dbc.Alert` (info/success/warning) sont inchangées.
- Focus clavier visible sur tous les boutons.
