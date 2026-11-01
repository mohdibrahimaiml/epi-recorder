/* Example decision switcher on the homepage.
   One monolith, three real sealed records: denied, approved, escalated.

   The card advances on its own every three seconds so a visitor who never
   touches it still sees all three outcomes. It stops when the visitor takes
   over (clicking a tab), and while the pointer or keyboard focus is on it.
   A Pause/Play control and prefers-reduced-motion both stop the rotation, so
   the moving content always has an off switch (WCAG 2.2.2).

   External file, not inline: the site's CSP lists script hashes and this keeps
   the page free of a new one. */
(function () {
  "use strict";

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".z-decision-tab"));
  var card = document.getElementById("decisionCard");
  if (!tabs.length || !card) return;

  var panels = Array.prototype.slice.call(document.querySelectorAll(".z-hero-monolith__panel"));
  var pauseBtn = document.getElementById("decisionPause");
  var AUTO_MS = 3000;
  var reduceMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var timer = null;
  var paused = false;
  var hovering = false;
  var focused = false;

  function selectedIndex() {
    for (var i = 0; i < tabs.length; i += 1) {
      if (tabs[i].getAttribute("aria-selected") === "true") return i;
    }
    return 0;
  }

  function select(tab, focus) {
    var id = tab.getAttribute("data-panel");
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.setAttribute("tabindex", on ? "0" : "-1");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== id;
    });
    if (focus) tab.focus();
  }

  function advance() {
    select(tabs[(selectedIndex() + 1) % tabs.length]);
  }

  function stop() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function sync() {
    var shouldRun = !paused && !hovering && !focused && !reduceMotion && !document.hidden;
    if (shouldRun && timer === null) {
      timer = window.setInterval(advance, AUTO_MS);
    } else if (!shouldRun) {
      stop();
    }
  }

  function setPaused(value) {
    paused = value;
    if (pauseBtn) {
      pauseBtn.setAttribute("aria-pressed", value ? "true" : "false");
      pauseBtn.textContent = value ? "Play" : "Pause";
      pauseBtn.setAttribute(
        "aria-label",
        value ? "Play the example rotation" : "Pause the example rotation"
      );
    }
    sync();
  }

  tabs.forEach(function (tab, index) {
    tab.setAttribute("tabindex", tab.getAttribute("aria-selected") === "true" ? "0" : "-1");
    tab.addEventListener("click", function () {
      select(tab);
      setPaused(true);
    });
    tab.addEventListener("keydown", function (event) {
      var next = null;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        event.preventDefault();
        select(next, true);
        setPaused(true);
      }
    });
  });

  if (pauseBtn) {
    pauseBtn.addEventListener("click", function () {
      setPaused(!paused);
    });
  }

  card.addEventListener("mouseenter", function () {
    hovering = true;
    sync();
  });
  card.addEventListener("mouseleave", function () {
    hovering = false;
    sync();
  });
  card.addEventListener("focusin", function () {
    focused = true;
    sync();
  });
  card.addEventListener("focusout", function () {
    if (!card.contains(document.activeElement)) {
      focused = false;
      sync();
    }
  });
  document.addEventListener("visibilitychange", sync);

  sync();
})();
