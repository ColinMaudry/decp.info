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

    // Métriques basées sur le conteneur scrollable (pas la page).
    // dashContainer a overflow-x:hidden → scrollLeft est contrôlable par JS.
    const metrics = () => {
      const total = dashContainer.scrollWidth;
      const visible = dashContainer.clientWidth;
      const thumbW = Math.max(40, (visible / total) * visible);
      const scrollRange = total - visible;
      const thumbRange = visible - thumbW;
      return { total, visible, thumbW, scrollRange, thumbRange };
    };

    // Mise à jour de la position du thumb selon dashContainer.scrollLeft.
    const syncThumb = () => {
      const { total, visible, thumbW, scrollRange, thumbRange } = metrics();
      if (total <= visible + 1 || thumbRange <= 0) return;
      thumb.style.width = thumbW + "px";
      const fraction =
        scrollRange > 0 ? dashContainer.scrollLeft / scrollRange : 0;
      thumb.style.left = Math.round(fraction * thumbRange) + "px";
    };

    // --- Drag souris + tactile ---
    let dragStartX = null;
    let dragScrollStart = null;

    const startDrag = (clientX) => {
      dragStartX = clientX;
      dragScrollStart = dashContainer.scrollLeft;
    };
    const moveDrag = (clientX) => {
      if (dragStartX === null) return;
      const dx = clientX - dragStartX;
      const { scrollRange, thumbRange } = metrics();
      if (thumbRange <= 0) return;
      dashContainer.scrollLeft = Math.max(
        0,
        Math.min(scrollRange, dragScrollStart + (dx / thumbRange) * scrollRange)
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
      const rect = bar.getBoundingClientRect();
      const { scrollRange, thumbW, thumbRange } = metrics();
      const fraction = Math.max(
        0,
        Math.min(1, (e.clientX - rect.left - thumbW / 2) / thumbRange)
      );
      dashContainer.scrollLeft = fraction * scrollRange;
    });

    // Scroll molette/trackpad horizontal → redirigé vers le conteneur.
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    wrapper.addEventListener(
      "wheel",
      (e) => {
        if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
        e.preventDefault();
        dashContainer.scrollLeft = Math.max(
          0,
          Math.min(
            dashContainer.scrollWidth - dashContainer.clientWidth,
            dashContainer.scrollLeft + e.deltaX
          )
        );
      },
      { passive: false }
    );

    // Synchronise le thumb quand le conteneur défile (drag, wheel, ou autre).
    // SPA : ce listener est intentionnellement conservé pour toute la durée de vie de la page.
    dashContainer.addEventListener("scroll", syncThumb);

    const refresh = () => {
      const hasOverflow =
        dashContainer.scrollWidth > dashContainer.clientWidth + 1;
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
