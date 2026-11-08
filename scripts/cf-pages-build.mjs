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
import { spawnSync } from "node:child_process";

const SRC = "website";
const DESTINATIONS = ["site", "dist"];
const BLOG_BUILDER = "scripts/build_blog.py";

// Regenerate website/blog/ before the copy. The generator is standard-library
// Python only, so it runs on the Cloudflare build image without extra packages.
// If Python is unavailable, the committed output is still valid; refuse only
// when there is no output at all.
function buildBlog() {
  const candidates = process.env.PYTHON
    ? [process.env.PYTHON]
    : process.platform === "win32"
      ? ["python", "py"]
      : ["python3", "python"];
  for (const exe of candidates) {
    const result = spawnSync(exe, [BLOG_BUILDER], { stdio: "inherit" });
    if (result.error) continue;
    if (result.status !== 0) {
      console.error(`ERROR: ${BLOG_BUILDER} failed with exit code ${result.status}`);
      return false;
    }
    return true;
  }
  return false;
}

if (!buildBlog()) {
  if (!existsSync(join(SRC, "blog", "index.html"))) {
    console.error(
      `ERROR: could not run Python and ${SRC}/blog/index.html is missing. ` +
        "Generate it with: python scripts/build_blog.py",
    );
    process.exit(1);
  }
  console.warn(
    `WARNING: Python not available; using the committed ${SRC}/blog output. ` +
      "Regenerate before committing post changes.",
  );
}

// Internal Markdown (sales templates such as outreach.md, etc.) must never
// ship to public output. Only README.md is allowed through — mirrors the
// exclusion in scripts/sync_website.py.
const PUBLIC_MD_ALLOWLIST = new Set(["README.md"]);

// The site sells exactly one paid offer. These are the strings plans.html must
// carry (one offer, one price), and the ones that must never come back
// (retired tiers). tests/test_website_offer.py checks this list against the
// real page, so the guard cannot drift away from the page again.
const PLANS_PAGE_REQUIRED = ["AI vendor review", "4,500", "9,500", "15,000", "first 3 customers"];
const PLANS_PAGE_RETIRED = ["Decision File pilot", "Design Partner", "Agent Evidence Sprint", "Pick your evidence plan"];
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

  const blogIndex = join(DEST, "blog", "index.html");
  if (!existsSync(blogIndex)) {
    console.error(`ERROR: ${blogIndex} is missing after the build.`);
    process.exit(1);
  }

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
