def _data_params(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    return resp.get_json()["paths"]["/api/v1/data"]["get"]["parameters"]


def test_openapi_no_placeholder_parameter_name(api_client):
    """Un nom de paramètre littéral `<colonne>__<opérateur>` est ingérable par
    Swagger UI : le champ « Try it out » envoie le placeholder comme nom réel
    (`?%3Ccolonne%3E__%3Cop%C3%A9rateur%3E=montant__greater%3D1000000`) → 400."""
    noms = [p["name"] for p in _data_params(api_client)]
    assert not [n for n in noms if "<" in n], noms


def test_openapi_declares_free_form_filter_parameter(api_client):
    """Les filtres dynamiques doivent être déclarés en objet free-form
    (`style: form`, `explode: true`) : Swagger UI rend alors un champ JSON
    clé/valeur et sérialise `?colonne__op=valeur`."""
    libres = [
        p
        for p in _data_params(api_client)
        if p.get("schema", {}).get("type") == "object"
    ]
    assert len(libres) == 1, [p["name"] for p in _data_params(api_client)]
    param = libres[0]
    assert param["in"] == "query"
    assert param["style"] == "form"
    assert param["explode"] is True


def test_openapi_documents_new_keywords(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    raw = resp.get_data(as_text=True)
    for keyword in [
        "count_results",
        "differs",
        "groupby",
        "__sum",
        "__avg",
        "__min",
        "__max",
    ]:
        assert keyword in raw, f"{keyword} absent de la doc OpenAPI"
