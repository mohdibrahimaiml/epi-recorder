/**
 * EPI theme — light / dark with localStorage + system default.
 * Sets data-theme on <html> and <body>. Exposes window.EPITheme.
 */
(function () {
  var KEY = "epi-theme";

  function systemPrefersDark() {
    try {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch (e) {
      return true;
    }
  }

  function resolve(theme) {
    if (theme === "light" || theme === "dark") return theme;
    return systemPrefersDark() ? "dark" : "light";
  }

  function apply(theme) {
    var t = resolve(theme);
    document.documentElement.setAttribute("data-theme", t);
    if (document.body) document.body.setAttribute("data-theme", t);
    // Keep instrument pages themed; do not force dark class removal
    document.querySelectorAll(".theme-toggle-nav, #themeToggleNav, [data-theme-toggle]").forEach(function (btn) {
      var dark = t === "dark";
      btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      btn.setAttribute("title", dark ? "Light mode" : "Dark mode");
      // Mobile drawer buttons need a label; icon-only on compact nav
      if (btn.classList.contains("mob-theme-btn") || (btn.closest && btn.closest(".mob-menu"))) {
        btn.innerHTML = dark ? "&#9788; Light mode" : "&#9789; Dark mode";
      } else {
        btn.innerHTML = dark ? "&#9788;" : "&#9789;"; // sun / moon
      }
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
    });
    return t;
  }

  function get() {
    try {
      return localStorage.getItem(KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function set(theme) {
    var t = theme === "light" || theme === "dark" ? theme : resolve(theme);
    try {
      localStorage.setItem(KEY, t);
    } catch (e) {}
    return apply(t);
  }

  function toggle() {
    var cur = document.documentElement.getAttribute("data-theme") || resolve(get());
    return set(cur === "dark" ? "light" : "dark");
  }

  function init() {
    var stored = get();
    apply(stored || (systemPrefersDark() ? "dark" : "light"));
    document.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest && e.target.closest("[data-theme-toggle], .theme-toggle-nav, #themeToggleNav");
      if (btn) {
        e.preventDefault();
        toggle();
      }
    });
    try {
      if (window.matchMedia) {
        window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (ev) {
          if (!get()) apply(ev.matches ? "dark" : "light");
        });
      }
    } catch (e) {}
  }

  // NOTE: burger + scroll behavior is owned SOLELY by each page's inline
  // script (getElementById('burger')). A duplicate handler here used to
  // toggle the menu a second time per click, cancelling the first and
  // making the hamburger appear dead. Do not re-add nav handling here.

  window.EPITheme = { init: init, set: set, get: get, toggle: toggle, apply: apply };

  // Run ASAP if body exists; else on DOMContentLoaded
  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);
})();

/**
 * Inject the vendored Lucide icon sprite into the DOM so that
 * `<svg><use href="#lucide-NAME"></use></svg>` resolves even when the
 * page is served as a static file without external-sprite fetching.
 * Sprite source: /assets/icons.svg (MIT-licensed Lucide paths).
 */
window.injectIcons = function () {
  if (document.getElementById("epi-icons")) return;
  var SVG =
    '<svg id="epi-icons" xmlns="http://www.w3.org/2000/svg" style="display:none">' +
    '<defs>' +
    '<symbol id="lucide-shield-check" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M9 12l2 2 4-4"/></symbol>' +
    '<symbol id="lucide-shield-alert" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></symbol>' +
    '<symbol id="lucide-gavel" viewBox="0 0 24 24"><path d="M12 20l-8-8a2 2 0 0 0 0-2l9-9h3a2 2 0 0 1 2 2v3a.5.5 0 0 1-.5.5H15l-6 6h2l1.5-1.5a.5.5 0 0 1 .85.35v4a.5.5 0 0 1-.5.5h-3L9 20a2 2 0 0 1-2 0z"/><path d="M15 7l.5-.5a.5.5 0 0 1 .7.7l-.5.5"/></symbol>' +
    '<symbol id="lucide-list-checks" viewBox="0 0 24 24"><path d="M3 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7.83a2 2 0 0 0-1.42.58l-2.68 2.68a1 1 0 0 1-1.41-.25A1 1 0 0 1 3 19.7V5z"/><path d="M8 4v16"/><path d="M13.5 9l2 2 5-5"/></symbol>' +
    '<symbol id="lucide-users" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-3.87-4H7.88a4 4 0 0 0-3.87 4V21"/><path d="M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/><path d="M16 14h.01"/><path d="M20 14h.01"/><path d="M4 14h.01"/></symbol>' +
    '<symbol id="lucide-user-search" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-3.87-4H7.88a4 4 0 0 0-3.87 4V21"/><path d="M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/><circle cx="18" cy="8" r="2"/><path d="M20 2l-2 2"/></symbol>' +
    '<symbol id="lucide-trending-up" viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8"/><path d="M21 12h-7"/></symbol>' +
    '<symbol id="lucide-code" viewBox="0 0 24 24"><path d="M10 12.5l2 2 5-5"/><path d="m18 16-6-6-6 6"/></symbol>' +
    '<symbol id="lucide-terminal" viewBox="0 0 24 24"><path d="M12 19h7"/><path d="M5.5 2 2 6l3.5 4 3.5-4L5.5 2z"/><path d="m9 10-2 2 2 2"/></symbol>' +
    '<symbol id="lucide-layers" viewBox="0 0 24 24"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="M22 13.47l-8.58 3.91a2 2 0 0 1-1.66 0L4.6 10.39"/></symbol>' +
    '<symbol id="lucide-file-text" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M10 13h2v2"/><path d="M10 9h4"/></symbol>' +
    '<symbol id="lucide-hash" viewBox="0 0 24 24"><path d="M4 9h16"/><path d="M4 15h16"/><path d="M10 3l-2 18"/><path d="M16 3l-2 18"/></symbol>' +
    '<symbol id="lucide-eye" viewBox="0 0 24 24"><path d="M1 12s8-8 11-8 11 8 11 8-8 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></symbol>' +
    '<symbol id="lucide-key-round" viewBox="0 0 24 24"><path d="M2 12c.5-3.5 2.4-6.4 5.5-8 2.9 1.2 5.1 3.4 6.2 6.3A1 1 0 0 1 12 12H5a2 2 0 0 0 0 4h12a2 2 0 0 0 2-2v-2a.5.5 0 0 1 .5-.5h.5"/></symbol>' +
    '<symbol id="lucide-file-clock" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18a6 6 0 1 1 0-12 6 6 0 0 1 0 12z"/><path d="M12 14l1-1-2-1V9"/></symbol>' +
    '<symbol id="lucide-arrow-right" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m12 19 7-7-7-7"/></symbol>' +
    '<symbol id="lucide-chevron-right" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></symbol>' +
    '</defs></svg>';
  var d = document.documentElement;
  // Prepend to body so symbols are available before <use> rendering
  d.insertAdjacentHTML("afterbegin", SVG);
  try { window.EPITheme && window.EPITheme.apply(window.EPITheme.get()); } catch (e) {}
};
// Fallback if onload hasn't fired but DOM is ready
if (document.readyState !== "loading") window.injectIcons();
else document.addEventListener("DOMContentLoaded", window.injectIcons);
