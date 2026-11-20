// Snapshot mode: `?snapshot=1` on any dashboard URL gives a clean, fixed-width render (no navigation,
// no filter panel) for slide decks. `rbc-bi snapshot <id>` uses this headlessly.
(function () {
  try {
    if (new URLSearchParams(window.location.search).get("snapshot") === "1") {
      document.documentElement.classList.add("rbc-snapshot");
    }
  } catch (e) {
    /* ignore */
  }
})();
