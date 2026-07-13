from src.mcp.oauth import metadata

BASE = "https://colibre.fr"


def test_protected_resource_metadata():
    m = metadata.protected_resource_metadata(BASE)
    assert m["resource"] == "https://colibre.fr/_mcp"
    assert m["authorization_servers"] == ["https://colibre.fr"]
    assert "offline_access" in m["scopes_supported"]


def test_authorization_server_metadata():
    m = metadata.authorization_server_metadata(BASE)
    assert m["issuer"] == "https://colibre.fr"
    assert m["authorization_endpoint"] == "https://colibre.fr/oauth/authorize"
    assert m["token_endpoint"] == "https://colibre.fr/oauth/token"
    assert m["registration_endpoint"] == "https://colibre.fr/oauth/register"
    assert m["code_challenge_methods_supported"] == ["S256"]
    assert m["token_endpoint_auth_methods_supported"] == ["none"]
    assert set(m["grant_types_supported"]) == {"authorization_code", "refresh_token"}
    assert "offline_access" in m["scopes_supported"]
