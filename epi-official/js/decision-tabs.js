/* Example decision switcher on the homepage.
   One monolith, three real sealed records: denied, approved, escalated.
   External file, not inline: the site's CSP lists script hashes and this keeps
   the page free of a new one. */
(function () {
  "use strict";

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".z-decision-tab"));
  if (!tabs.length) return;
  var panels = Array.prototype.slice.call(document.querySelectorAll(".z-hero-monolith__panel"));

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

  tabs.forEach(function (tab, index) {
    tab.setAttribute("tabindex", tab.getAttribute("aria-selected") === "true" ? "0" : "-1");
    tab.addEventListener("click", function () {
      select(tab);
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
      }
    });
  });
})();
