import hashlib
import hmac
import json


def _js(value) -> str:
    """Littéral JS sûr : JSON n'échappe pas `<`, or `</script>` dans une chaîne
    fermerait la balise et permettrait une injection via l'email."""
    return json.dumps(value).replace("<", "\\u003c")


def build_widget_script(website_token: str | None) -> str:
    """Bloc <script> d'intégration du widget de chat Chatwoot (offre managée).

    Renvoie une chaîne vide si aucun token n'est fourni, ce qui désactive le
    widget (utilisé comme interrupteur pendant l'essai, voir issue #120).
    """
    if not website_token:
        return ""
    return f"""<script>
  (function(d,t) {{
    var BASE_URL="https://app.chatwoot.com";
    var g=d.createElement(t),s=d.getElementsByTagName(t)[0];
    g.src=BASE_URL+"/packs/js/sdk.js";
    g.async = true;
    s.parentNode.insertBefore(g,s);
    g.onload=function(){{
      window.chatwootSDK.run({{
        websiteToken: '{website_token}',
        baseUrl: BASE_URL
      }})
    }}
  }})(document,"script");
</script>"""


def subscription_attributes(user_id: int) -> dict[str, str]:
    """Attributs d'abonnement à afficher sur la fiche contact Chatwoot.

    Ce que le support a besoin de savoir d'emblée : abonné ou pas, sur quelle
    offre, et jusqu'à quand. On prend le dernier abonnement (get_current), donc
    un `expired` suivi d'un `active` remonte bien `active`.

    Ces clés doivent être déclarées dans Chatwoot (Settings → Custom Attributes)
    pour apparaître dans la barre latérale ; sinon elles sont stockées sur le
    contact mais pas affichées.
    """
    from src.subscriptions import db as subscriptions_db
    from src.subscriptions.plans import PLANS

    row = subscriptions_db.get_current(user_id)
    if row is None:
        return {"statut_abonnement": "aucun"}

    attributes = {"statut_abonnement": row["status"] or "inconnu"}
    if row["plan"]:
        meta = PLANS.get(row["plan"])
        attributes["offre"] = meta["label"] if meta else row["plan"]
    if row["current_period_end"]:
        attributes["fin_periode"] = row["current_period_end"]
    return attributes


def build_identity_script(
    identifier: int | str | None,
    email: str | None,
    hmac_token: str | None = None,
    custom_attributes: dict[str, str] | None = None,
) -> str:
    """Bloc <script> qui déclare l'utilisateur connecté auprès du widget.

    L'identifiant est l'id interne (stable même si l'utilisateur change d'email) ;
    l'email n'est là que pour l'affichage dans la fiche contact Chatwoot.

    `$chatwoot` n'existe pas encore au moment où ce script s'exécute : le SDK ne
    l'installe qu'après le chargement de son iframe, d'où l'écoute de
    `chatwoot:ready` (émis sur window). Le SDK compare l'identité au cookie
    existant et ignore l'appel si elle est inchangée : rejouer ce bloc à chaque
    page est sans effet de bord.

    Si `hmac_token` est fourni (validation d'identité activée sur l'inbox), on
    joint le HMAC-SHA256 de l'identifiant, sans quoi n'importe qui peut se faire
    passer pour un autre depuis la console.

    `custom_attributes` (cf. subscription_attributes) est posé APRÈS setUser,
    pour atterrir sur le bon contact. Le dict vide est ignoré : le SDK lève
    « Custom attributes should have atleast one key ».
    """
    if not identifier or not email:
        return ""

    identifier = str(identifier)
    user: dict[str, str] = {"email": email}
    if hmac_token:
        user["identifier_hash"] = hmac.new(
            hmac_token.encode(), identifier.encode(), hashlib.sha256
        ).hexdigest()

    calls = [f"window.$chatwoot.setUser({_js(identifier)}, {_js(user)});"]
    if custom_attributes:
        calls.append(f"window.$chatwoot.setCustomAttributes({_js(custom_attributes)});")
    body = "\n    ".join(calls)

    return f"""<script>
  window.addEventListener("chatwoot:ready", function () {{
    {body}
  }});
</script>"""


def build_reset_script() -> str:
    """Bloc <script> qui dissocie le contact Chatwoot du navigateur.

    À n'injecter qu'au retour d'une déconnexion : le SDK garde le contact en
    cookie, donc sans reset le visiteur suivant sur la même machine hériterait
    de la conversation du précédent. Ne pas le poser sur toutes les pages
    anonymes, sinon on efface la conversation en cours d'un visiteur non
    connecté à chaque rechargement.
    """
    return """<script>
  window.addEventListener("chatwoot:ready", function () {
    window.$chatwoot.reset();
  });
</script>"""
