/* EPI Labs contact form.
   Transport is POST-first: the message goes to the EPI Cloud Worker, which
   stores it for the founder. If that request fails for any reason, the form
   falls back to opening the visitor's mail client with every field prefilled,
   so a message is never silently lost and the page never claims a delivery
   that did not happen.

   window.EPI_CONTACT_ENDPOINT is the Worker's public contact route. Do NOT
   point it at /api/contact: that path is proxied to the legacy Render portal
   and is answered by a Cloudflare managed challenge (HTTP 429, "Just a
   moment…"), so the fetch fails for every real visitor. */
(function () {
  "use strict";

  window.EPI_CONTACT_ENDPOINT = "https://cloud.epilabs.org/contact";
  // The waitlist is a different list with a different owner; keep it on email
  // until it has its own route.
  window.EPI_WAITLIST_ENDPOINT = "";

  function $(s, c) { return (c || document).querySelector(s); }

  function initForm(form) {
    if (!form || form.dataset.bound) return;
    form.dataset.bound = "1";

    var status = $(".cf-status", form);
    var btn = $('button[type="submit"]', form);
    var btnLabel = btn ? btn.textContent : "Send";

    function show(kind, msg) {
      if (!status) return;
      status.className = "cf-status " + (kind || "");
      status.innerHTML = msg;
    }

    function validate() {
      var ok = true;
      var req = form.querySelectorAll("[required]");
      req.forEach(function (f) {
        var bad = !f.value || !f.value.trim();
        if (f.type === "email" && f.value && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.value)) bad = true;
        f.classList.toggle("invalid", bad);
        if (bad) ok = false;
      });
      return ok;
    }

    // The Worker's /contact route expects
    // {name, work_email, company, interest, message, website}. `website` is a
    // honeypot: it is visually hidden and must stay empty.
    function fields() {
      var d = {};
      form.querySelectorAll("input,select,textarea").forEach(function (f) {
        if (f.name) d[f.name] = f.value.trim();
      });
      return d;
    }

    function payload(d) {
      var extra = [
        d.role ? "Role: " + d.role : "",
        d.who ? "Who is asking: " + d.who : "",
        d.deadline ? "Deadline: " + d.deadline : ""
      ].filter(Boolean).join("\n");
      return {
        name: d.name || "",
        work_email: d.email || "",
        company: d.company || "",
        interest: d.interest || "",
        message: [d.message || "", extra].filter(Boolean).join("\n\n"),
        website: d.website || ""
      };
    }

    function mailtoFallback(d) {
      var subject = "[epilabs.org] " + (d.interest || "Inquiry") + " — " + (d.name || "website");
      var body = [
        d.name ? "Name: " + d.name : "",
        d.email ? "Email: " + d.email : "",
        d.company ? "Company: " + d.company : "",
        d.role ? "Role: " + d.role : "",
        d.interest ? "Interested in: " + d.interest : "",
        d.message ? "\n" + d.message : ""
      ].filter(Boolean).join("\n");
      window.location.href = "mailto:mohdibrahim@epilabs.org?subject=" +
        encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!validate()) {
        show("err", "Please fill the required fields (valid email included).");
        return;
      }
      var d = fields();

      if (!window.EPI_CONTACT_ENDPOINT) {
        // Honest fallback: open the visitor's mail client, prefilled.
        show("warn", "Opening your email client with the message prefilled&hellip; " +
          "(Or write directly to <a href=\"mailto:mohdibrahim@epilabs.org\">mohdibrahim@epilabs.org</a>.)");
        mailtoFallback(d);
        return;
      }

      btn.disabled = true;
      btn.textContent = "Sending…";
      fetch(window.EPI_CONTACT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload(d))
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        form.reset();
        btn.disabled = false;
        btn.textContent = btnLabel;
        show("ok", "Thanks — message received. You'll hear back within one business day.");
      }).catch(function () {
        // Delivery is not confirmed, so say so and hand over to email.
        show("warn", "We could not send it automatically. Opening your email client " +
          "with the message prefilled&hellip; (Or write directly to " +
          "<a href=\"mailto:mohdibrahim@epilabs.org\">mohdibrahim@epilabs.org</a>.)");
        btn.disabled = false;
        btn.textContent = btnLabel;
        mailtoFallback(d);
      });
    });
  }

  function boot() {
    document.querySelectorAll("form.cform").forEach(initForm);
    initWaitlist();
  }

  /* ── Waitlist (closing band) ─────────────────────────────────── */
  function initWaitlist() {
    var form = document.querySelector("form.wl-form");
    if (!form || form.dataset.bound) return;
    form.dataset.bound = "1";
    var status = document.querySelector(".wl-status");
    var btn = form.querySelector("button");

    function show(msg) {
      if (!status) return;
      status.innerHTML = msg;
      status.classList.add("show");
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = form.querySelector("input[name=email]");
      var v = (email.value || "").trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
        email.classList.add("invalid");
        show("Please enter a valid email address.");
        return;
      }
      email.classList.remove("invalid");

      if (!window.EPI_WAITLIST_ENDPOINT) {
        // Honest fallback: no fake success. Point to direct email.
        show("Join by email — write to <a href=\"mailto:mohdibrahim@epilabs.org?subject=Control%20Plane%20early%20access\">" +
          "mohdibrahim@epilabs.org</a> with \u201Cearly access\u201D and you're on the list.");
        return;
      }

      btn.disabled = true;
      btn.textContent = "…";
      fetch(window.EPI_WAITLIST_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        // Same /api/contact contract; tier marks it as a waitlist lead.
        body: JSON.stringify({
          name: "Waitlist",
          email: v,
          company: "",
          tier: "waitlist",
          use_case: "Control Plane early access"
        })
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        form.reset();
        show("You're on the list. One email when the pilot program opens — that's it.");
      }).catch(function () {
        show("Could not join automatically — email <a href=\"mailto:mohdibrahim@epilabs.org?subject=Control%20Plane%20early%20access\">mohdibrahim@epilabs.org</a>.");
        btn.disabled = false;
        btn.textContent = "Join waitlist";
      });
    });
  }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
