from flask_smorest import Api

from src.api import routes


def init_api(server) -> None:
    """Enregistre le blueprint d'API privée sur le serveur Flask."""
    server.config.setdefault("API_TITLE", "decp.info API")
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

    import os

    from src.api import tracking

    tracking.start_worker(os.environ["USERS_DB_PATH"])
