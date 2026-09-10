// EPI Labs — Privacy notice bar (PECR / ePrivacy Directive compliance)
// Plausible is cookieless and GDPR-exempt by design,
// but this minimal disclosure bar is best practice under PECR.
// Fires once per browser, stored in localStorage. WCAG 2.1 AA accessible.
(function () {
  var KEY = "epi-privacy-ack";
  try { if (localStorage.getItem(KEY)) return; } catch (e) { return; }
  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }
  ready(function () {
    var bar = document.createElement("div");
    bar.id = "epi-privacy-bar";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Privacy notice");
    bar.setAttribute("aria-live", "polite");
    bar.innerHTML =
      "<p>We use <a href=\"/privacy\">privacy-first, cookieless analytics</a> (Plausible). No tracking cookies. No personal data collected or sold.</p>" +
      "<button type=\"button\" id=\"epi-privacy-ack-btn\" aria-label=\"Dismiss privacy notice\">Got it</button>";
    document.body.appendChild(bar);
    document.getElementById("epi-privacy-ack-btn").addEventListener("click", function () {
      try { localStorage.setItem(KEY, "1"); } catch (e) {}
      bar.style.transition = "opacity 0.25s";
      bar.style.opacity = "0";
      setTimeout(function () { if (bar.parentNode) bar.parentNode.removeChild(bar); }, 260);
    });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape" && document.getElementById("epi-privacy-bar")) {
        document.getElementById("epi-privacy-ack-btn").click();
        document.removeEventListener("keydown", esc);
      }
    });
  });
})();
