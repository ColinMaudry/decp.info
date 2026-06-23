// Barre de défilement horizontale pour les tableaux (.marches_table) — #82
(function () {
  "use strict";

  function setup(wrapper) {
    if (wrapper.dataset.hscrollReady === "1") return;

    const dashContainer = wrapper.querySelector(".dash-spreadsheet-container");
    if (!dashContainer) return;

    // Garde posée après la vérification de dashContainer, avant toute manipulation DOM
    // qui déclencherait rootObs et provoquerait une re-entrée dans setup().
    wrapper.dataset.hscrollReady = "1";

    const bar = document.createElement("div");
    bar.className = "dt-hscroll is-hidden";
    const inner = document.createElement("div");
    inner.className = "dt-hscroll-inner";
    bar.appendChild(inner);
    wrapper.insertBefore(bar, wrapper.firstChild);

    // La barre synchronise le scroll horizontal de la page (overflow: visible sur les
    // conteneurs Dash laisse le scroll se faire au niveau de la page, ce qui permet
    // aux en-têtes position:sticky de rester calés sur la fenêtre).
    // syncing évite les boucles dans la même pile d'exécution.
    let syncing = false;
    const onBar = () => {
      if (syncing) return;
      syncing = true;
      window.scrollTo(bar.scrollLeft, window.scrollY);
      syncing = false;
    };
    const onPage = () => {
      if (syncing) return;
      syncing = true;
      bar.scrollLeft = window.scrollX;
      syncing = false;
    };
    bar.addEventListener("scroll", onBar);
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    window.addEventListener("scroll", onPage);

    const refresh = () => {
      const total = document.documentElement.scrollWidth;
      const visible = window.innerWidth;
      inner.style.width = total + "px";
      // +1 absorbe les erreurs d'arrondi sous-pixel
      bar.classList.toggle("is-hidden", total <= visible + 1);
      bar.scrollLeft = window.scrollX;
    };

    // Recalcule quand le tableau change (pagination, tri, filtre, données).
    const obs = new MutationObserver(() => refresh());
    obs.observe(dashContainer, {
      childList: true,
      subtree: true,
      attributes: true,
    });
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    window.addEventListener("resize", refresh);

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
