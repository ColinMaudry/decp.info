"""Utilitaires partagés par les tests."""


def walk_components(component):
    """Parcourt récursivement l'arbre de composants Dash.

    Le `repr` d'un composant Dash tronque les longs sous-arbres : chercher une
    chaîne dans `str(layout)` donne des faux négatifs. On inspecte donc l'arbre.
    """
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, str):
            yield child
        else:
            yield from walk_components(child)
