// EPI site nav — burger + scroll (mobile-safe)
(function () {
  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(function () {
    var nav = document.getElementById("nav");
    var btn = document.getElementById("mobBtn");
    var menu = document.getElementById("mobMenu");

    if (nav) {
      var onScroll = function () {
        nav.classList.toggle("scrolled", window.scrollY > 24);
      };
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    if (!btn || !menu) return;

    // Prevent duplicate listeners if script loaded twice
    if (btn.dataset.epiNavBound === "1") return;
    btn.dataset.epiNavBound = "1";

    function isOpen() {
      return menu.classList.contains("is-open") || menu.classList.contains("open");
    }

    function setOpen(open) {
      menu.classList.toggle("is-open", open);
      menu.classList.toggle("open", open);
      menu.removeAttribute("hidden");
      menu.style.display = open ? "flex" : "none";
      btn.classList.toggle("is-open", open);
      btn.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      document.body.style.overflow = open ? "hidden" : "";
      document.documentElement.style.overflow = open ? "hidden" : "";
    }

    setOpen(false);

    function toggle(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      setOpen(!isOpen());
    }

    btn.addEventListener("click", toggle);
    // iOS sometimes prefers touchend; use click only to avoid double-fire

    menu.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        setOpen(false);
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) setOpen(false);
    });

    // Close when rotating / resizing to desktop
    window.addEventListener(
      "resize",
      function () {
        if (window.innerWidth > 1100 && isOpen()) setOpen(false);
      },
      { passive: true }
    );
  });
})();
