/* PADDLE LIVE CONFIG */

window.EPI_PADDLE_CONFIG = {
  clientToken: "live_5ce743d200af5fd36c81c5fe8e2",
  environment: "production",

  /* Paddle redirects here after a successful checkout.
     account.html reads ?checkout=success and shows the live activation banner. */
  successUrl: "/account?checkout=success",

  sprintPriceId: "pri_01m0y5tp4geerk93exrs4fkpgp",
  emailStorageKey: "epi-user-email",

  tiers: [
    // WP-PRICING-0 (EPI Cloud v2): Hosted ($199/mo) and Team ($799/mo)
    // "hosted verification" tiers retired from the site. Paddle products are
    // archived in the Paddle dashboard (not deleted). EPI Cloud is in private
    // beta; Design Partner places are invoiced by hand until M7 billing lands.
  ]
};

/* Inject logged-in user identity into every Paddle checkout call.
   Reads epi_user from localStorage (written by account.html after GitHub OAuth).
   Sets _customData so the subscribe() function on the plans page can pass it
   to Paddle. The webhook in billing.py reads customData.user_id to match the
   subscription to the right GitHub account - not just email. */
(function injectUserCustomData() {
  try {
    var raw = localStorage.getItem("epi_user");
    if (!raw) return;
    var u = JSON.parse(raw);
    if (!u || !u.id) return;
    window.EPI_PADDLE_CONFIG._customData = {
      user_id:     String(u.id),
      epi_user_id: String(u.id),
      email:       String(u.email || ""),
      login:       String(u.login || "")
    };
    if (u.email) {
      try { localStorage.setItem("epi-user-email", u.email); } catch (_) {}
    }
  } catch (_) {}
})();
