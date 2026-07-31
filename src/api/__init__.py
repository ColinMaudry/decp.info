from flask_smorest import Api

# `routes` n'est PAS importé ici : il importe `src.db`, qui construit ou ouvre
# la base DuckDB en effet de bord d'import. Au niveau paquet, un simple
# `from src.api import tokens_db` — du SQLite pur — déclencherait donc tout le
# bootstrap des données. C'est ce qui cassait `python -m src.api.tokens_cli` en
# production : runpy importe le paquet parent avant d'exécuter le corps du
# module, donc avant le `load_dotenv()` du CLI ; sans .env, DUCKDB_PATH
# retombait sur un chemin relatif inexistant et la reconstruction échouait.
# L'import vit dans `init_api`, seul endroit qui utilise `routes`.


def init_api(server) -> None:
    """Enregistre le blueprint d'API privée sur le serveur Flask."""
    import os

    from src.api import routes, tokens_db, tracking

    # Garantit que api_tokens existe avant que apply_pending (init_subscriptions,
    # plus tard) ne tente l'ALTER de la migration 0007.
    tokens_db.init_schema(os.environ["USERS_DB_PATH"])

    server.config.setdefault("API_TITLE", "colibre API")
    server.config.setdefault("API_VERSION", "v1")
    server.config.setdefault("OPENAPI_VERSION", "3.0.3")
    server.config.setdefault("OPENAPI_URL_PREFIX", "/api/v1")
    server.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    server.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "swagger")
    server.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )
    server.config.setdefault(
        "API_SPEC_OPTIONS",
        {
            "components": {
                "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}
            }
        },
    )

    api = Api(server)
    api.register_blueprint(routes.bp)

    tracking.start_worker(os.environ["USERS_DB_PATH"])
