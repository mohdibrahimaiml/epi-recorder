import { corsPreflight, proxyToRender } from "../_proxy.js";

// Trust anchors are committed under this site (website/.well-known/*, mirrored
// into site/). Serve the static file first, so did:web:epilabs.org, the trust
// registry and security.txt keep resolving after the legacy Render portal is
// retired.
//
// Anything not present locally may only proxy if it is a name the portal is
// known to answer for. This path is same-origin, so proxying an arbitrary
// /.well-known/<anything> would turn the backend into same-origin content if
// it ever reflected input. Everything else is a plain 404.
const PORTAL_WELL_KNOWN = new Set([
  "jwks.json",
  "oauth-authorization-server",
  "openid-configuration",
  "webfinger",
  "apple-app-site-association",
  "assetlinks.json",
]);

// Names nothing in either repo calls any more. Answer 410 instead of waking
// the retiring Render portal. A committed static file still wins because the
// function serves context.next() before this check.
const RETIRED_WELL_KNOWN = new Set([
  "webfinger",
  "apple-app-site-association",
  "assetlinks.json",
]);

const GONE_BODY = JSON.stringify({
  error: {
    code: "gone",
    message: "This endpoint was served by the retired EPI portal. Use https://cloud.epilabs.org.",
  },
});

export async function onRequest(context) {
  if (context.request.method === "OPTIONS") {
    return corsPreflight(context);
  }
  const asset = await context.next();
  if (asset.status !== 404) {
    return asset;
  }
  const name = new URL(context.request.url).pathname
    .replace(/^\/\.well-known\//i, "")
    .replace(/\/$/, "");
  if (RETIRED_WELL_KNOWN.has(name)) {
    return new Response(GONE_BODY, {
      status: 410,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  }
  if (!PORTAL_WELL_KNOWN.has(name)) {
    return new Response("Not found", {
      status: 404,
      headers: { "content-type": "text/plain", "cache-control": "no-store" },
    });
  }
  return proxyToRender(context);
}
