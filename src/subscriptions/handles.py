"""Génération des handles Frisbii (customer et abonnement).

Les handles sont uniques à l'échelle du compte Frisbii, partagé par tous les
déploiements de colibre (production, test, dev). Sans discriminant, l'utilisateur
n°4 de test.colibre.fr et celui de colibre.fr réclameraient le même handle, et le
second ne pourrait pas activer son abonnement (#126).

Le préfixe est déduit de `APP_BASE_URL` :

- ``https://colibre.fr``      → ``colibre``
- ``https://test.colibre.fr`` → ``colibre_test``
- tout le reste (non défini, localhost, …) → ``colibre_dev``
"""

import os
from urllib.parse import urlparse

_PREFIX_BY_HOST = {
    "colibre.fr": "colibre",
    "www.colibre.fr": "colibre",
    "test.colibre.fr": "colibre_test",
}
_DEFAULT_PREFIX = "colibre_dev"


def env_prefix() -> str:
    """Préfixe de handle propre à l'environnement de déploiement."""
    base = (os.getenv("APP_BASE_URL") or "").strip()
    # urlparse a besoin d'un schéma pour peupler hostname ; APP_BASE_URL peut
    # être renseigné sans (ex. « test.colibre.fr »).
    if base and "//" not in base:
        base = f"//{base}"
    host = (urlparse(base).hostname or "").lower()
    return _PREFIX_BY_HOST.get(host, _DEFAULT_PREFIX)


def customer_handle(user_id: int) -> str:
    """Handle Frisbii du customer correspondant à l'utilisateur ``user_id``.

    Les handles d'abonnement en dérivent : voir ``db._next_handle``.
    """
    return f"{env_prefix()}-{user_id}"
