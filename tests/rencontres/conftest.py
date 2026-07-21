# Importer l'app complète à la collecte : sa découverte use_pages enregistre
# chaque page (et ses @callback) exactement une fois. Voir tests/roadmap/conftest.py.
from src.app import app  # noqa: F401
