/* Défilement vers les ancres de la page (#136).
 *
 * Deux raisons pour lesquelles le navigateur ne s'en charge pas seul :
 *  - le contenu est rendu par Dash APRÈS le chargement du document, donc à
 *    l'instant où le navigateur cherche l'ancre du hash elle n'existe pas
 *    encore, et le saut échoue silencieusement ;
 *  - les liens internes (nav latérale) passent par dcc.Link, qui intercepte le
 *    clic côté client : le saut natif n'a jamais lieu.
 *
 * Une ancre pointant sur une ligne du tableau des champs
 * (/projet/donnees#nom_du_champ) est en plus surlignée brièvement.
 */
(function () {
  "use strict";

  var HIGHLIGHT_MS = 2500;
  var TIMEOUT_MS = 15000; // au-delà, la grille ne viendra pas : on abandonne
  var SETTLE_MS = 5000; // durée de recalage après le premier défilement
  var SETTLE_STEP_MS = 150;
  var TOLERANCE_PX = 4;

  function highlight(cell) {
    var row = cell.closest(".ag-row") || cell;
    row.classList.add("champ-cible");
    window.setTimeout(function () {
      row.classList.remove("champ-cible");
    }, HIGHLIGHT_MS);
  }

  /* Les lignes en "autoHeight" sont mesurées après coup : leur hauteur change
   * sous la cible et la décale de plusieurs milliers de pixels. On recale donc
   * tant que la position bouge, au lieu de faire confiance au premier
   * scrollIntoView. */
  function scrollUntilSettled(cell, onSettled) {
    var deadline = Date.now() + SETTLE_MS;
    var previousTop = null;
    var stable = 0;

    function step() {
      var top = cell.getBoundingClientRect().top;
      var wanted = window.innerHeight / 2;
      // La grille mesure ses lignes par lots : deux relevés identiques ne
      // signifient pas que la page a fini de bouger. On exige donc plusieurs
      // relevés stables avant de renoncer à centrer la cible.
      stable = top === previousTop ? stable + 1 : 0;
      var settled = Math.abs(top - wanted) <= TOLERANCE_PX || stable >= 3;
      if (!settled) {
        cell.scrollIntoView({ block: "center" });
      }
      previousTop = top;
      if (settled || Date.now() >= deadline) {
        onSettled();
      } else {
        window.setTimeout(step, SETTLE_STEP_MS);
      }
    }

    cell.scrollIntoView({ block: "center" });
    window.setTimeout(step, SETTLE_STEP_MS);
  }

  /* Renvoie true si l'ancre a été atteinte (ou s'il n'y a rien à faire). */
  function reveal(wanted) {
    var hash = (wanted || window.location.hash).replace(/^#/, "");
    if (!hash) {
      return true;
    }
    var cell = document.getElementById(decodeURIComponent(hash));
    if (!cell) {
      return false;
    }
    // Ancre de titre (#sources, #qualite...) : simple défilement, sans
    // recalage ni surlignage — sa position ne bouge plus une fois rendue.
    if (!cell.closest(".ag-row")) {
      cell.scrollIntoView({ block: "start" });
      return true;
    }
    // Surlignage seulement une fois le défilement stabilisé : sinon il
    // s'éteint pendant que la grille se recale encore.
    scrollUntilSettled(cell, function () {
      highlight(cell);
    });
    return true;
  }

  function watch(wanted) {
    if (reveal(wanted)) {
      return;
    }
    var observer = new MutationObserver(function () {
      if (reveal(wanted)) {
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.setTimeout(function () {
      observer.disconnect();
    }, TIMEOUT_MS);
  }

  window.addEventListener("hashchange", function () {
    watch();
  });

  /* Les liens internes de Dash (dcc.Link, dont dbc.NavLink) changent l'URL par
   * history.pushState, qui n'émet PAS de hashchange : sans cet écouteur, un
   * clic sur une sous-section de la nav latérale met le hash à jour sans rien
   * faire défiler. On lit le hash sur le lien plutôt que sur location, dont la
   * mise à jour par Dash n'a pas forcément eu lieu à cet instant. */
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest('a[href*="#"]');
    if (!link) {
      return;
    }
    var hash = link.getAttribute("href").split("#")[1];
    if (hash) {
      window.setTimeout(function () {
        watch("#" + hash);
      }, 0);
    }
  });
  if (document.readyState === "loading") {
    // Enveloppé : l'écouteur reçoit un Event, que watch() prendrait pour un
    // hash.
    document.addEventListener("DOMContentLoaded", function () {
      watch();
    });
  } else {
    watch();
  }
})();
