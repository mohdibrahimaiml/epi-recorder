/**
 * EPI Labs — Dynamic Enterprise Theme Engine powered by DarkReader
 * (https://github.com/darkreader/darkreader)
 */
(function () {
  if (typeof DarkReader === "undefined") {
    return;
  }

  // Dark Reader Enterprise Theme Config
  var darkThemeConfig = {
    brightness: 100,
    contrast: 105,
    sepia: 0,
    darkSchemeBackgroundColor: "#07090E",
    darkSchemeTextColor: "#F8FAFC",
    selectionColor: "#10B981"
  };

  var darkThemeFixes = {
    invert: [".nav-logo img", ".footer-logo", ".ent-dropzone-icon"],
    css: ""
  };

  function applyTheme(theme) {
    if (theme === "dark") {
      DarkReader.enable(darkThemeConfig, darkThemeFixes);
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      DarkReader.disable();
      document.documentElement.setAttribute("data-theme", "light");
    }
  }

  // Initialize theme
  var savedTheme = localStorage.getItem("epi-theme") || "dark";
  applyTheme(savedTheme);

  // Hook toggle button
  document.addEventListener("DOMContentLoaded", function () {
    var toggles = document.querySelectorAll("[data-theme-toggle], #themeToggleNav");
    toggles.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var current = document.documentElement.getAttribute("data-theme") || "dark";
        var next = current === "dark" ? "light" : "dark";
        try {
          localStorage.setItem("epi-theme", next);
        } catch (e) {}
        applyTheme(next);
      });
    });
  });
})();
