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
    {
      name: "Hosted",
      description: "For teams shipping agents into regulated workflows. 10k hosted verifications, remote SCITT, 10 API keys.",
      features: [
        "10,000 hosted verifications / month",
        "Remote SCITT registration",
        "10 API keys",
        "Offline verify + embedded viewer (always free)",
        "Support via GitHub issues"
      ],
      featured: true,
      priceId: { month: "pri_01m0y54canxd7z63ykf928qs04", year: "pri_01m0y54ckbm8vj32dsms9xfeev" },
      /* USD base shown ONLY when live localized pricing is unreachable
         (see the watchdog in plans.html). Keep in sync with Paddle. */
      fallbackUSD: 199
    },
    {
      name: "Team",
      description: "Hosted custody and SCITT at volume for enterprises.",
      features: [
        "50,000 hosted verifications / month",
        "Remote SCITT registration",
        "50 API keys"
      ],
      featured: false,
      priceId: { month: "pri_01m0y54d6t0q3ehgqmmepg45vj", year: "pri_01m0y54df4smpc7qq4p21j4v9s" },
      /* USD base shown ONLY when live localized pricing is unreachable
         (see the watchdog in plans.html). Keep in sync with Paddle. */
      fallbackUSD: 799
    }
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
