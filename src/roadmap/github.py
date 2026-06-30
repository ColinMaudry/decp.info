import httpx

from src.utils.cache import cache

GITHUB_REPO = "ColinMaudry/decp.info"
_LABEL_KEYS = {"en cours": "en_cours", "mis au vote": "au_vote"}


@cache.memoize(timeout=3600)
def fetch_roadmap_issues() -> dict[str, list[dict]]:
    """Issues ouvertes du dépôt portant un label de roadmap, regroupées par label.

    Appel anonyme à l'API GitHub publique. Mis en cache 1 h.
    """
    resp = httpx.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        params={"state": "open", "per_page": 100},
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    resp.raise_for_status()
    result: dict[str, list[dict]] = {"en_cours": [], "au_vote": []}
    for issue in resp.json():
        if "pull_request" in issue:
            continue  # l'endpoint /issues inclut les PR
        labels = {lbl["name"] for lbl in issue.get("labels", [])}
        for label, key in _LABEL_KEYS.items():
            if label in labels:
                result[key].append(
                    {
                        "number": issue["number"],
                        "title": issue["title"],
                        "html_url": issue["html_url"],
                    }
                )
    return result
