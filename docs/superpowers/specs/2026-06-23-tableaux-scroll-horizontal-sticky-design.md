# Défilement horizontal ergonomique des tableaux (#82)

## Problème

Les tableaux de données (`DataTable` Dash) sont souvent plus larges que l'écran et
**débordent vers la droite**. Aujourd'hui aucun `overflowX` n'est défini sur leur
conteneur : le tableau étire la page entière, et le seul moyen de faire défiler
horizontalement est la **barre de défilement de la fenêtre du navigateur**, tout en
bas du viewport. Cette barre :

- est discrète et fait défiler **toute la page** (pas seulement le tableau) ;
- n'est pas comprise comme « le moyen de voir le reste du tableau ».

De plus, les tableaux dépassent souvent du bas de l'écran : une barre placée en bas
du tableau serait invisible sans scroller.

## Objectif

Rendre le défilement horizontal **évident et toujours accessible**, et garder les
**en-têtes de colonnes visibles** pendant le défilement vertical, sans introduire de
zone scrollable imbriquée gênante.

## Approche retenue (option B — sticky au niveau page)

Le tableau **reste dans le flux de la page** (pas de conteneur à hauteur fixe, pas de
scroll imbriqué). On combine deux mécanismes :

1. **En-têtes collants** — `position: sticky; top: 0` sur la ligne d'en-tête du
   tableau. Quand l'utilisateur descend dans la page, les en-têtes se figent en haut
   de la fenêtre au lieu d'être « avalés ».

2. **Barre de défilement horizontale miroir en haut** — un petit élément placé
   juste au-dessus du tableau, lui aussi `sticky` en haut, dont le défilement
   horizontal est **synchronisé** avec celui du tableau. Elle est donc toujours
   visible dès qu'on voit le haut du tableau, et pilote le défilement horizontal sans
   devoir descendre en bas du tableau.

La barre miroir et les en-têtes collants se figent ensemble en haut de la fenêtre :
l'utilisateur garde en permanence le repère des colonnes **et** le contrôle du
défilement horizontal.

### Pourquoi pas l'option A (tableau « fenêtré » à hauteur fixe)

Écartée volontairement : un conteneur à hauteur fixe avec scroll interne crée un
**scroll imbriqué** (la molette agit d'abord sur le tableau, pas sur la page), source
de confusion. L'option B garde un comportement de défilement vertical unique (celui
de la page) ; seul le défilement horizontal est « custom ».

## Contrainte technique CSS à gérer

Un conteneur en `overflow-x: auto` devient automatiquement un conteneur de
défilement **vertical** (règle CSS : `overflow-y: visible` recalculé en `auto` dès
que l'autre axe n'est pas `visible`), ce qui **casse** le `position: sticky; top: 0`
des en-têtes par rapport à la page.

Conséquences pour l'implémentation :

- Le **défilement horizontal réel** doit se faire dans un conteneur dédié en
  `overflow-x: auto` ; mais ce conteneur ne peut pas, en même temps, héberger des
  en-têtes sticky « page ». La barre miroir du haut résout ce conflit : c'est **elle**
  qui porte le `overflow-x: auto`, séparée du tableau, et synchronisée par JS.
- Il faudra **vérifier et neutraliser au besoin l'`overflow` interne** que Dash
  DataTable applique à ses propres conteneurs (`.dash-spreadsheet-container`,
  `.dash-spreadsheet-inner`) pour que le sticky des en-têtes fonctionne.
- Le rendu réel de Dash DataTable doit être inspecté avant de figer le CSS : la
  structure DOM exacte (où poser `sticky`, quel élément porte la largeur totale)
  conditionne la solution. **À valider en testant dans le navigateur.**

## Composants

| Élément               | Rôle                                                                                                                        | Emplacement probable                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| CSS en-têtes sticky   | `position: sticky; top: 0` sur la ligne d'en-tête, z-index, fond opaque                                                     | `src/assets/css/style.css` (cible `.marches_table`)                        |
| Barre miroir (markup) | `<div>` scrollable au-dessus du tableau, avec un enfant à la largeur du tableau                                             | composant partagé `DataTable` / wrapper dans `src/figures.py`              |
| Synchronisation JS    | lier scrollLeft barre ↔ tableau ; recopier la largeur du tableau dans la barre ; recalcul au resize / changement de données | nouveau fichier `src/assets/js/*.js` (assets Dash, chargé automatiquement) |
| CSS barre miroir      | hauteur, sticky `top: 0`, masquage si pas de débordement                                                                    | `src/assets/css/style.css`                                                 |

## Portée

Les **quatre pages** utilisant `className="marches_table"` :
`/tableau`, `/acheteur`, `/titulaire`, `/observatoire`. La solution passe par le
composant `DataTable` partagé et la classe CSS `marches_table`, donc l'effort est
quasi identique pour une ou quatre pages.

## Flux de données / interactions

1. Au rendu (et à chaque changement de données / largeur de fenêtre), le JS mesure la
   largeur totale du tableau et la reporte dans l'élément interne de la barre miroir →
   la barre miroir affiche une glissière proportionnelle.
2. Événement `scroll` sur la barre miroir → on applique `scrollLeft` au conteneur du
   tableau ; et inversement (scroll du tableau → barre miroir), avec garde anti-boucle.
3. Si le tableau ne déborde pas, la barre miroir est masquée.

## Cas limites

- **Pas de débordement** : barre miroir masquée, en-têtes sticky inoffensifs.
- **Pagination / re-render** (pages en `page_action="custom"`) : la largeur peut
  changer → la synchro doit se recalculer après mise à jour des données.
- **Resize de la fenêtre** : recalcul de la largeur miroir.
- **Plusieurs tableaux sur une page** (`/observatoire`, `/titulaire`, `/acheteur` ont
  plusieurs `marches_table`) : le JS doit gérer chaque tableau indépendamment.
- **Persistance / tri / filtre** : ne doit pas casser la synchro (réattacher les
  écouteurs si le DOM est recréé).

## Tests / validation

- Vérification **manuelle dans le navigateur** (point critique vu l'incertitude sur le
  DOM de DataTable) : débordement horizontal sur `/tableau`, sticky des en-têtes en
  scrollant, synchro des deux barres, comportement sur les pages à tableaux multiples.
- S'assurer que les tests Selenium existants ne régressent pas
  (`pytest tests/test_main.py`).

## Hors périmètre (YAGNI)

- Colonnes figées (1re colonne sticky horizontalement).
- Réduction du nombre de colonnes par défaut / refonte du sélecteur de colonnes.
- `overscroll-behavior` et zones scrollables imbriquées (option A écartée).

## Verdict du spike

Le spike (Steps 1–3 exécutés par l'utilisateur en DevTools) doit valider les points suivants. En cas de déviation, le reste du plan reste applicable ; seule l'implémentation du sticky (Task 2) ajustera sa stratégie.

### Éléments attendus du DOM

- **Conteneur scrollable** : `.dash-spreadsheet-container` (enfant direct de `.marches_table`)
- **Conteneur interne** : `.dash-spreadsheet-inner` (enfant de `.dash-spreadsheet-container`) — peut aussi porter un `overflow` interne
- **En-têtes** : sélecteur exact `th.dash-header` (dans un `tr` au sein du tableau)
- **Table complète** : `.cell-table` avec ses dimensions (`scrollWidth` >> `clientWidth` du parent → débordement confirmé)

### Hypothèse sticky

L'astuce CSS consiste à :

1. Neutraliser l'`overflow` sur `.dash-spreadsheet-container` et `.dash-spreadsheet-inner` en les ramenant à `overflow: visible` (ou en supprimant le style si possible)
2. Appliquer `position: sticky; top: 0; z-index: 10; background: #fff` aux en-têtes `th.dash-header`

**Verdict attendu :** ✅ Oui — les en-têtes restent collés au haut de la fenêtre quand on scroll verticalement la page, sans recours à du JS supplémentaire (hormis la synchro scrollLeft pour le miroir).

**Si verdict = ❌ Non :** les en-têtes seront pilotés entièrement en JS (repositionnement au scroll), avec synchronisation du scroll vertical. Le reste du plan (barre miroir, synchro horizontale) reste valable.

### Références (à noter lors du spike)

- `scrollWidth` et `clientWidth` de la table vs. ses parents
- Styles `overflow` en _Computed_ sur `.dash-spreadsheet-container`, `.dash-spreadsheet-inner` et `.cell-table`
- Résultat du test d'hypothèse JS (sticky page fonctionne-t-il ?)
