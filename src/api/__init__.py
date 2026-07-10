from flask_smorest import Api

from src.api import routes


def init_api(server) -> None:
    """Enregistre le blueprint d'API privée sur le serveur Flask."""
    import os

    from src.api import tokens_db, tracking

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
