import pytest

from src.subscriptions import handles


@pytest.mark.parametrize(
    "base_url, expected",
    [
        ("https://colibre.fr", "colibre"),
        ("https://colibre.fr/", "colibre"),
        ("https://www.colibre.fr", "colibre"),
        ("colibre.fr", "colibre"),
        ("https://test.colibre.fr", "colibre_test"),
        ("http://test.colibre.fr:8050", "colibre_test"),
        ("test.colibre.fr", "colibre_test"),
        ("http://localhost:8050", "colibre_dev"),
        ("", "colibre_dev"),
        ("https://autre.exemple.fr", "colibre_dev"),
    ],
)
def test_env_prefix(monkeypatch, base_url, expected):
    monkeypatch.setenv("APP_BASE_URL", base_url)
    assert handles.env_prefix() == expected


def test_env_prefix_without_app_base_url(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    assert handles.env_prefix() == "colibre_dev"


def test_customer_handle_differs_between_environments(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    prod = handles.customer_handle(4)
    monkeypatch.setenv("APP_BASE_URL", "https://test.colibre.fr")
    test = handles.customer_handle(4)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    dev = handles.customer_handle(4)
    assert prod == "colibre-4"
    assert test == "colibre_test-4"
    assert dev == "colibre_dev-4"
    assert len({prod, test, dev}) == 3
