/* FLIP animation for #roadmap-vote-list — only animates items that move */

(function () {
  var firstPositions = {};
  var debounceTimer = null;
  var listObserver = null;
  var observedList = null;

  function getKey(el) {
    var a = el.querySelector("a");
    return a ? a.getAttribute("href") : el.textContent.trim().slice(0, 40);
  }

  function capturePositions() {
    var list = document.getElementById("roadmap-vote-list");
    if (!list) return;
    firstPositions = {};
    list.querySelectorAll(".list-group-item").forEach(function (el) {
      firstPositions[getKey(el)] = el.getBoundingClientRect().top;
    });
  }

  function applyFlip() {
    var list = document.getElementById("roadmap-vote-list");
    if (!list || Object.keys(firstPositions).length === 0) return;
    list.querySelectorAll(".list-group-item").forEach(function (el) {
      var key = getKey(el);
      var first = firstPositions[key];
      if (first === undefined) return;
      var dy = first - el.getBoundingClientRect().top;
      if (Math.abs(dy) < 2) return;
      el.style.transition = "none";
      el.style.transform = "translateY(" + dy + "px)";
      void el.offsetWidth;
      el.style.transition = "transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)";
      el.style.transform = "";
    });
    firstPositions = {};
  }

  function attachObserver() {
    var list = document.getElementById("roadmap-vote-list");
    if (!list || list === observedList) return;
    if (listObserver) listObserver.disconnect();
    observedList = list;
    listObserver = new MutationObserver(function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(applyFlip, 50);
    });
    listObserver.observe(list, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  document.addEventListener(
    "click",
    function (e) {
      if (e.target.closest('[id*="roadmap-vote"]')) capturePositions();
    },
    true
  );

  setInterval(attachObserver, 1000);
  attachObserver();
})();
