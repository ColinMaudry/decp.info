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
