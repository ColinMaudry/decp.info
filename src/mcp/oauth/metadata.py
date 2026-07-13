SCOPES = ["mcp", "offline_access"]


def mcp_resource(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/_mcp"


def protected_resource_metadata(base_url: str) -> dict:
    base = base_url.rstrip("/")
    return {
        "resource": mcp_resource(base),
        "authorization_servers": [base],
        "scopes_supported": SCOPES,
        "bearer_methods_supported": ["header"],
    }


def authorization_server_metadata(base_url: str) -> dict:
    base = base_url.rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "scopes_supported": SCOPES,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }
