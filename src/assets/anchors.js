/* Deep-link vers un champ du tableau /projet/donnees#nom_du_champ (#136).
 *
 * La grille des champs est rendue par Dash APRÈS le chargement du document :
 * quand le navigateur cherche l'ancre du hash, la ligne n'existe pas encore et
 * le saut natif échoue silencieusement. On attend donc son apparition, on la
 * fait défiler puis on la surligne brièvement.
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
  function reveal() {
    var hash = window.location.hash.slice(1);
    if (!hash) {
      return true;
    }
    var cell = document.getElementById(decodeURIComponent(hash));
    // Une ancre hors grille (#sources, #qualite...) est laissée au navigateur.
    if (!cell || !cell.closest(".ag-row")) {
      return false;
    }
    // Surlignage seulement une fois le défilement stabilisé : sinon il
    // s'éteint pendant que la grille se recale encore.
    scrollUntilSettled(cell, function () {
      highlight(cell);
    });
    return true;
  }

  function watch() {
    if (reveal()) {
      return;
    }
    var observer = new MutationObserver(function () {
      if (reveal()) {
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.setTimeout(function () {
      observer.disconnect();
    }, TIMEOUT_MS);
  }

  window.addEventListener("hashchange", watch);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();
