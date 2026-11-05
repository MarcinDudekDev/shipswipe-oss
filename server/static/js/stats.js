/* Homepage community counters: animate up on load, then poll to stay live. */
(function () {
  "use strict";

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var DURATION = 900;
  var POLL_MS = 20000;
  var shown = {}; // key -> currently displayed value

  /** Return the stat elements carrying a data-stat key. */
  function nodes() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-stat]"));
  }

  /** Count an element's number up (or down) to a new value. */
  function animate(el, from, to) {
    var key = el.dataset.stat;
    if (reduce || from === to) {
      el.textContent = String(to);
      shown[key] = to;
      return;
    }
    var start = performance.now();
    /** Render one eased frame of the count animation. */
    function step(now) {
      var t = Math.min(1, (now - start) / DURATION);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(from + (to - from) * eased));
      if (t < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = String(to);
        shown[key] = to;
      }
    }
    requestAnimationFrame(step);
  }

  /** Animate every stat from zero to its rendered value. */
  function start() {
    nodes().forEach(function (el) {
      var target = parseInt(el.textContent.trim(), 10) || 0;
      shown[el.dataset.stat] = 0;
      animate(el, 0, target);
    });
  }

  /** Fetch /api/stats and re-animate any counter that changed. */
  function poll() {
    fetch("/api/stats", { headers: { accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        nodes().forEach(function (el) {
          var key = el.dataset.stat;
          if (!(key in data)) return;
          var to = data[key];
          var from = key in shown ? shown[key] : (parseInt(el.textContent, 10) || 0);
          if (to !== from) animate(el, from, to);
        });
      })
      .catch(function () { /* ignore transient errors */ });
  }

  /** Run the first animation and start the refresh interval. */
  function init() {
    start();
    setInterval(poll, POLL_MS);
  }

  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
