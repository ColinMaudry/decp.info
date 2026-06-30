from src.roadmap import github


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_ISSUES = [
    {
        "number": 10,
        "title": "Feature en cours",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/10",
        "labels": [{"name": "en cours"}],
    },
    {
        "number": 20,
        "title": "Feature au vote",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/20",
        "labels": [{"name": "mis au vote"}],
    },
    {
        "number": 30,
        "title": "Issue sans label pertinent",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/30",
        "labels": [{"name": "bug"}],
    },
    {
        "number": 40,
        "title": "Une PR déguisée en issue",
        "html_url": "https://github.com/ColinMaudry/decp.info/pull/40",
        "labels": [{"name": "mis au vote"}],
        "pull_request": {"url": "..."},
    },
]


def test_fetch_roadmap_issues_filters_by_label(monkeypatch):
    monkeypatch.setattr(github.httpx, "get", lambda *a, **k: _FakeResp(_ISSUES))
    result = github.fetch_roadmap_issues.uncached()
    assert [i["number"] for i in result["en_cours"]] == [10]
    assert [i["number"] for i in result["au_vote"]] == [20]  # PR #40 exclue
    assert result["en_cours"][0] == {
        "number": 10,
        "title": "Feature en cours",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/10",
    }
