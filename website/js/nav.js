// EPI site nav — burger + scroll
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

    function isOpen() {
      return menu.classList.contains("is-open");
    }

    function setOpen(open) {
      menu.classList.toggle("is-open", open);
      menu.classList.toggle("open", open);
      menu.removeAttribute("hidden"); // never use [hidden] — UA !important fights open state
      menu.style.display = open ? "flex" : "none";
      btn.classList.toggle("is-open", open);
      btn.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      document.body.style.overflow = open ? "hidden" : "";
    }

    setOpen(false);

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
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
