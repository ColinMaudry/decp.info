// Barre de défilement horizontale miroir pour les tableaux (.marches_table) — #82
(function () {
  "use strict";

  // Renvoie le conteneur réellement scrollable horizontalement du tableau.
  function getScrollEl(wrapper) {
    return wrapper.querySelector(".dash-spreadsheet-container") || wrapper;
  }

  function setup(wrapper) {
    if (wrapper.dataset.hscrollReady === "1") return;
    const scrollEl = getScrollEl(wrapper);

    const bar = document.createElement("div");
    bar.className = "dt-hscroll is-hidden";
    const inner = document.createElement("div");
    inner.className = "dt-hscroll-inner";
    bar.appendChild(inner);
    wrapper.insertBefore(bar, wrapper.firstChild);

    // syncing évite les boucles dans la même pile d'exécution ; l'affectation de scrollLeft
    // déclenche l'événement scroll de façon synchrone dans Chromium.
    let syncing = false;
    const onBar = () => {
      if (syncing) return;
      syncing = true;
      scrollEl.scrollLeft = bar.scrollLeft;
      syncing = false;
    };
    const onTable = () => {
      if (syncing) return;
      syncing = true;
      bar.scrollLeft = scrollEl.scrollLeft;
      syncing = false;
    };
    bar.addEventListener("scroll", onBar);
    scrollEl.addEventListener("scroll", onTable);

    const refresh = () => {
      const total = scrollEl.scrollWidth;
      const visible = scrollEl.clientWidth;
      inner.style.width = total + "px";
      // +1 absorbe les erreurs d'arrondi sous-pixel
      bar.classList.toggle("is-hidden", total <= visible + 1);
      bar.scrollLeft = scrollEl.scrollLeft;
    };

    // Recalcule quand le tableau change (pagination, tri, filtre, données).
    const obs = new MutationObserver(() => refresh());
    obs.observe(scrollEl, { childList: true, subtree: true, attributes: true });
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    window.addEventListener("resize", refresh);

    wrapper.dataset.hscrollReady = "1";
    refresh();
  }

  function scan() {
    document.querySelectorAll(".marches_table").forEach(setup);
  }

  // Les tableaux apparaissent après le rendu Dash : observer le body.
  const rootObs = new MutationObserver(() => scan());
  rootObs.observe(document.body, { childList: true, subtree: true });
  scan();
})();
