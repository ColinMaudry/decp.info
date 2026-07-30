"""Constantes partagées entre les routes SEO SSR et le sitemap.

`SEGMENT_SANS_DEPARTEMENT` doit avoir un sens unique et partagé : voir
`src/seo/routes.py` et `src/utils/sitemap.py`, qui l'utilisent tous les deux
pour décider quels organismes relèvent du segment "non-renseigne".
"""

SEGMENT_SANS_DEPARTEMENT = "non-renseigne"
