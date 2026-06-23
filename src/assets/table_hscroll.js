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
    const thumb = document.createElement("div");
    thumb.className = "dt-hscroll-thumb";
    bar.appendChild(thumb);
    wrapper.insertBefore(bar, wrapper.firstChild);

    // Étend la barre à toute la largeur du viewport, hors du container Bootstrap.
    // wrapper.getBoundingClientRect().left donne le décalage horizontal du conteneur.
    const adjustBarWidth = () => {
      const left = wrapper.getBoundingClientRect().left;
      bar.style.marginLeft = -left + "px";
      bar.style.width = window.innerWidth + "px";
    };

    // Métriques basées sur window.innerWidth (la barre occupe exactement la largeur du viewport).
    const metrics = () => {
      const total = document.documentElement.scrollWidth;
      const visible = window.innerWidth;
      const thumbW = Math.max(40, (visible / total) * visible);
      const scrollRange = total - visible;
      const thumbRange = visible - thumbW;
      return { total, visible, thumbW, scrollRange, thumbRange };
    };

    // --- Mise à jour de la position du thumb ---
    const syncThumb = () => {
      const { total, visible, thumbW, scrollRange, thumbRange } = metrics();
      if (total <= visible + 1 || thumbRange <= 0) return;
      thumb.style.width = thumbW + "px";
      const fraction = scrollRange > 0 ? window.scrollX / scrollRange : 0;
      thumb.style.left = Math.round(fraction * thumbRange) + "px";
    };

    // --- Drag souris + tactile ---
    let dragStartX = null;
    let dragScrollStart = null;

    const startDrag = (clientX) => {
      dragStartX = clientX;
      dragScrollStart = window.scrollX;
    };
    const moveDrag = (clientX) => {
      if (dragStartX === null) return;
      const dx = clientX - dragStartX;
      const { scrollRange, thumbRange } = metrics();
      if (thumbRange <= 0) return;
      window.scrollTo(
        dragScrollStart + (dx / thumbRange) * scrollRange,
        window.scrollY
      );
    };
    const endDrag = () => {
      dragStartX = null;
    };

    thumb.addEventListener("mousedown", (e) => {
      startDrag(e.clientX);
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => moveDrag(e.clientX));
    document.addEventListener("mouseup", endDrag);

    thumb.addEventListener(
      "touchstart",
      (e) => {
        startDrag(e.touches[0].clientX);
        e.preventDefault();
      },
      { passive: false }
    );
    document.addEventListener(
      "touchmove",
      (e) => {
        if (dragStartX !== null) {
          moveDrag(e.touches[0].clientX);
          e.preventDefault();
        }
      },
      { passive: false }
    );
    document.addEventListener("touchend", endDrag);

    // Clic sur le track (hors thumb) : saute à la position cliquée.
    bar.addEventListener("click", (e) => {
      if (e.target === thumb) return;
      const { scrollRange, thumbW, thumbRange } = metrics();
      const fraction = Math.max(
        0,
        Math.min(
          1,
          (e.clientX - bar.getBoundingClientRect().left - thumbW / 2) /
            thumbRange
        )
      );
      window.scrollTo(fraction * scrollRange, window.scrollY);
    });

    // Synchronise le thumb quand la page défile (clavier, molette, barre native, etc.).
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    window.addEventListener("scroll", syncThumb);

    const refresh = () => {
      adjustBarWidth();
      // Mesure la largeur réelle de CETTE table (pas de la page entière) pour
      // ne pas afficher la barre sur les petits tableaux d'une page qui a aussi
      // un grand tableau (ex. top10 sur /acheteur, /titulaire, /observatoire).
      const tableEl =
        dashContainer.querySelector(".cell-table") || dashContainer;
      const tableWidth = tableEl.getBoundingClientRect().width;
      const hasOverflow = tableWidth > window.innerWidth + 1;
      bar.classList.toggle("is-hidden", !hasOverflow);
      if (hasOverflow) syncThumb();
    };

    // Recalcule quand le tableau change (pagination, tri, filtre, données).
    const obs = new MutationObserver(() => refresh());
    obs.observe(dashContainer, {
      childList: true,
      subtree: true,
      attributes: true,
    });
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    window.addEventListener("resize", () => {
      adjustBarWidth();
      refresh();
    });

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
