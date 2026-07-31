// Émission des deux événements de conversion attribuables à une campagne.
//
// Le serveur pose un paramètre sur l'URL de redirection (src/auth/routes.py
// pour l'inscription, src/subscriptions/routes.py pour le retour de checkout) ;
// ce script le consomme et le retire. Les événements alimentent deux objectifs
// Matomo configurés sur « Send an event » avec correspondance exacte sur
// l'Event Action.
//
// L'événement `subscription_active` n'est PAS émis ici : il vient du webhook
// Frisbii (src/subscriptions/db.py), sans navigateur, donc sans attribution.
//
// Chargé automatiquement par Dash sur ses pages (tout .js de src/assets/).
// /connexion et /compte/abonnement sont des pages Dash, donc aucune référence
// explicite n'est nécessaire dans le gabarit SEO SSR.
(function () {
  var METHODES = ["email", "linkedin"];
  var PLANS = ["simple", "soutien"];

  function retirerParams(cles) {
    var url = new URL(window.location.href);
    var modifie = false;
    cles.forEach(function (cle) {
      if (url.searchParams.has(cle)) {
        url.searchParams.delete(cle);
        modifie = true;
      }
    });
    // Sans ce nettoyage, un rechargement (F5) recompterait la conversion.
    if (modifie) window.history.replaceState({}, "", url.toString());
  }

  function emettre() {
    // `_paq` est absent quand le traqueur est désactivé (tracking_enabled()
    // dans src/utils/matomo.py) : il n'y a alors rien à faire.
    if (!window._paq) return;

    var params = new URLSearchParams(window.location.search);

    var methode = params.get("compte_cree");
    if (methode && METHODES.indexOf(methode) !== -1) {
      window._paq.push(["trackEvent", "Compte", "account_created", methode]);
      retirerParams(["compte_cree"]);
    }

    var plan = params.get("plan");
    if (params.get("souscription") === "trial" && PLANS.indexOf(plan) !== -1) {
      window._paq.push([
        "trackEvent",
        "Abonnement",
        "subscription_trial",
        plan,
      ]);
      retirerParams(["souscription", "plan"]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", emettre);
  } else {
    emettre();
  }
})();
