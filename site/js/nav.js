// EPI site nav — burger + scroll (single source for all marketing pages)
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
        nav.classList.toggle("scrolled", window.scrollY > 40);
      };
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    if (!btn || !menu) return;

    // support both [hidden] and .open patterns
    function isOpen() {
      return menu.classList.contains("open");
    }

    function setOpen(open) {
      menu.classList.toggle("open", open);
      if (open) menu.removeAttribute("hidden");
      else menu.setAttribute("hidden", "");
      btn.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      document.body.style.overflow = open ? "hidden" : "";
    }

    setOpen(false);

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      setOpen(!isOpen());
    });

    menu.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        setOpen(false);
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) setOpen(false);
    });
  });
})();
