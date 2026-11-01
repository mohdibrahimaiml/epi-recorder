/**
 * Cloudflare Pages build step.
 *
 * Canonical static site lives in website/. CF Pages needs a build output
 * directory — we copy website/ → site/ with no transform.
 *
 * Build command:        npm run build
 * Build output directory: site (wrangler.toml: pages_build_output_dir = "site")
 * Root directory:       (repo root, leave empty)
 */
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync, readFileSync, statSync } from "node:fs";
import { join, basename } from "node:path";

const SRC = "website";
const DESTINATIONS = ["site", "dist"];

// Internal Markdown (sales templates such as outreach.md, etc.) must never
// ship to public output. Only README.md is allowed through — mirrors the
// exclusion in scripts/sync_website.py.
const PUBLIC_MD_ALLOWLIST = new Set(["README.md"]);

// The site sells exactly one paid offer. These are the strings plans.html must
// carry (one offer, one price), and the ones that must never come back
// (retired tiers). tests/test_website_offer.py checks this list against the
// real page, so the guard cannot drift away from the page again.
const PLANS_PAGE_REQUIRED = ["Decision File pilot", "4,500"];
const PLANS_PAGE_RETIRED = ["Design Partner", "Agent Evidence Sprint", "Pick your evidence plan"];
const skipExcludedPublicMd = (src) => {
  let st;
  try {
    st = statSync(src);
  } catch {
    return true;
  }
  if (!st.isFile()) return true;
  const base = basename(src);
  if (base.toLowerCase().endsWith(".md") && !PUBLIC_MD_ALLOWLIST.has(base)) {
    return false;
  }
  return true;
};

if (!existsSync(SRC)) {
  console.error(`ERROR: ${SRC}/ not found. Cloudflare Pages must build from repo root.`);
  process.exit(1);
}
if (!existsSync(join(SRC, "index.html"))) {
  console.error(`ERROR: ${SRC}/index.html missing.`);
  process.exit(1);
}

for (const DEST of DESTINATIONS) {
  rmSync(DEST, { recursive: true, force: true });
  mkdirSync(DEST, { recursive: true });
  cpSync(SRC, DEST, { recursive: true, filter: skipExcludedPublicMd });

  // Never ship directory-style pricing/ (old Starter/Pro SaaS page).
  // Canonical is flat pricing.html — directory routes can shadow it on CF.
  const stalePricing = join(DEST, "pricing");
  if (existsSync(stalePricing)) {
    rmSync(stalePricing, { recursive: true, force: true });
    console.log(`Removed stale ${DEST}/pricing/ directory`);
  }

  // Ensure CF treats this as a static site (not a Worker-only project)
  const routesPath = join(DEST, "_routes.json");
  writeFileSync(
    routesPath,
    JSON.stringify(
      {
        version: 1,
        include: ["/*"],
        exclude: [],
      },
      null,
      2,
    ),
  );

  const count = (() => {
    try {
      return readFileSync(join(DEST, "index.html"), "utf8").length;
    } catch {
      return 0;
    }
  })();
  const plansContent = (() => {
    try {
      return readFileSync(join(DEST, "plans.html"), "utf8");
    } catch {
      return "";
    }
  })();
  const missing = PLANS_PAGE_REQUIRED.filter((needle) => !plansContent.includes(needle));
  const retired = PLANS_PAGE_RETIRED.filter((needle) => plansContent.includes(needle));
  if (plansContent && (missing.length || retired.length)) {
    const detail = [
      missing.length ? `missing: ${missing.join(", ")}` : "",
      retired.length ? `retired offer back: ${retired.join(", ")}` : "",
    ]
      .filter(Boolean)
      .join("; ");
    console.warn(`WARNING: ${DEST}/plans.html is not the one-offer page (${detail})`);
  }
  console.log(`Cloudflare Pages build OK: copied ${SRC}/ → ${DEST}/ (index.html ${count} bytes)`);
}
