# Plan: Ajouter des cartes de localisation aux pages acheteur et titulaire

## Date: 2026-04-28

## Statut: Approuvé

## Objectif: Ajouter des cartes interactives montrant la localisation des organisations sur les pages acheteur et titulaire

## Contexte

- Les pages acheteur et titulaire ont déjà des placeholders pour les cartes (`acheteur_map` et `titulaire_map`)
- La fonction `point_on_map()` existe déjà dans `src/figures.py` mais utilise un centrage fixe sur la France
- Les données de localisation proviennent de l'API Annuaire des Entreprises
- Les codes départementaux sont disponibles et plus fiables que les coordonnées pour la détection de région

## Exigences

### 1. Carte interactive

- **Localisation**: Colonne de droite dans la section d'informations sur l'organisation
- **Taille**: 400px de largeur × 300px de hauteur (fixe)
- **Contenu**: Carte centrée sur la France ou le département d'outre-mer approprié avec un point rouge à l'emplacement de l'organisation
- **Niveau de zoom**: Approprié pour montrer l'Hexagone ou le département d'outre-mer spécifique
- **Style**: Fond de carte clair avec point rouge visible
- **Interactivité**: Carte zoomable et déplaçable (pas de configuration statique)

### 2. Sources de données

- Utiliser les colonnes `acheteur_latitude` et `acheteur_longitude` pour les pages acheteur
- Utiliser les colonnes `titulaire_latitude` et `titulaire_longitude` pour les pages titulaire
- Utiliser les codes départementaux (`acheteur_departement_code`, `titulaire_departement_code`) pour la détection de région
- Solution de repli: Si les coordonnées ou codes départementaux sont manquants ou invalides, afficher une div vide

### 3. Détection de région

- **Départements métropolitains**: Codes à 2 caractères (ex: "75" pour Paris) → Carte Hexagone
- **Départements d'outre-mer**:
  - "971" → Guadeloupe
  - "972" → Martinique
  - "973" → Guyane
  - "974" → La Réunion
  - "976" → Mayotte
- **Code département manquant**: Retourner une div vide (pas de détection basée sur les coordonnées)

### 4. Gestion des erreurs

- Coordonnées invalides → div vide
- Code département manquant → div vide
- Échec de l'API Annuaire → div vide (comportement existant)
- Format de code département invalide → div vide

## Implémentation

### Fichiers à modifier

#### 1. `src/figures.py` - Améliorer la fonction `point_on_map()`

**Ligne 178-209**: Remplacer la fonction existante par une version améliorée avec:

- Détection de région basée sur les codes départementaux
- Configuration de carte interactive (zoomable)
- Point plus grand (size=15)
- Commentaires en français

#### 2. `src/pages/acheteur.py` - Mettre à jour le callback

**Ligne 249-297**: Modifier `update_acheteur_infos()` pour:

- Extraire le code département du code postal
- Passer le code département à `point_on_map()`
- Ajouter des commentaires en français

#### 3. `src/pages/titulaire.py` - Mettre à jour le callback

**Ligne 259-297**: Modifier `update_titulaire_infos()` pour:

- Extraire le code département du code postal
- Passer le code département à `point_on_map()`
- Ajouter des commentaires en français

## Plan de Test

### Cas de test prioritaires

1. **Organisation métropolitaine**: Code département "75" (Paris) → Carte Hexagone
2. **Organisation à La Réunion**: Code département "974" → Carte centrée sur La Réunion
3. **Code département manquant**: Retourne une div vide
4. **Coordonnées invalides**: Retourne une div vide
5. **Interactivité**: Vérifier zoom et déplacement

### Critères d'acceptation

- [ ] Cartes fonctionnelles avec codes départementaux valides
- [ ] Div vide pour codes manquants/invalides
- [ ] Cartes correctement centrées et zoomées
- [ ] Interactivité (zoom et déplacement)
- [ ] Point de localisation visible (size=15)

## Approbation

Plan approuvé avec spécifications:

- Réutiliser et améliorer `point_on_map`
- Retourner div vide sans code département
- Point légèrement plus grand
- Cartes zoomables
- Utiliser codes départementaux pour détection de région
- Commentaires en français
