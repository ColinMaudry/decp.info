"""Accord singulier/pluriel pour les libellés générés dynamiquement.

Utilisé par `src/seo/routes.py` : les pages d'index (~2 500 pages) affichent
un total variable (0, 1 ou N organismes/marchés), et le français distingue le
singulier ("1 marché public") du pluriel ("5 marchés publics"). Centraliser
l'accord ici évite de disperser des `if n > 1 else ...` dans chaque gabarit de
phrase.
"""


def accorder(n: int, singulier: str, pluriel: str | None = None) -> str:
    """Forme adaptée à `n` : `singulier` si `n <= 1`, sinon la forme plurielle.

    `pluriel` par défaut à `singulier` suffixé d'un "s" (cas régulier
    français) ; à fournir explicitement pour les formes irrégulières.
    """
    if n <= 1:
        return singulier
    return pluriel if pluriel is not None else f"{singulier}s"
