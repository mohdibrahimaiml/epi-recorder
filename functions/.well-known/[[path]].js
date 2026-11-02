import { corsPreflight, proxyToRender } from "../_proxy.js";

// Trust anchors are committed under this site (website/.well-known/*, mirrored
// into site/). Serve the static file first, so did:web:epilabs.org, the trust
// registry and security.txt keep resolving after the legacy Render portal is
// retired. Anything not present locally still proxies, as before.
export async function onRequest(context) {
  if (context.request.method === "OPTIONS") {
    return corsPreflight(context);
  }
  const asset = await context.next();
  if (asset.status !== 404) {
    return asset;
  }
  return proxyToRender(context);
}
