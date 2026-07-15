# Widget de chat Chatwoot (essai) — issue #120

## Contexte

On teste Chatwoot (solution managée, offre d'essai) comme canal de support par
chat. Pas de mail/voix pour l'instant, juste le widget de chat embarqué.

## Design

Suivre le pattern déjà utilisé pour Matomo dans `src/app.py` : injecter le
script d'intégration directement dans `app.index_string`, juste avant
`</body>`.

- Nouvelle variable d'env `CHATWOOT_WEBSITE_TOKEN` (ajoutée à `.template.env`,
  vide/commentée par défaut).
- Dans `src/app.py`, lire `chatwoot_token = os.getenv("CHATWOOT_WEBSITE_TOKEN")`
  avant la construction de `index_string`.
- Construire le bloc `<script>` Chatwoot conditionnellement : si le token est
  absent/vide, le bloc est omis — le widget ne se charge pas. Ça sert à la
  fois d'interrupteur (désactivable sans déploiement le temps de l'essai) et
  garantit que les tests/CI (qui ne définissent pas cette variable) ne
  chargent jamais le widget.
- Interpoler ce bloc dans `index_string` via f-string, à côté du script
  Matomo existant.
- `baseUrl` reste codé en dur sur `https://app.chatwoot.com` (offre managée,
  comme spécifié dans l'issue) — pas besoin d'une variable pour une URL
  self-hosted à ce stade.

## Hors scope

- Auto-hébergement Chatwoot
- Support par mail/voix
- Personnalisation du widget (langue, position, couleurs)
- Affichage conditionnel par page ou par statut de connexion
