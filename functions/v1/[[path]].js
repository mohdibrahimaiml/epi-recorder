/**
 * Cloudflare Pages Function: same-origin proxy for the reviewer trust page.
 *
 * The trust page (website/t/app.js) calls /v1/trust/* same-origin, but
 * epilabs.org is static — the trust API lives on the EPI Cloud Worker.
 * This function forwards ONLY the reviewer endpoints to the Worker.
 *
 * Strict allow-list (fail closed):
 * - exact path shapes for GET /v1/trust/<slug>,
 *   GET /v1/trust/<slug>/witness-lines, POST /v1/trust/<slug>/events,
 *   GET /v1/orgs/<org>/artifacts/<id>/content (the shared file bytes the
 *   trust page hashes and zips; still authorized by the share token)
 * - only GET/POST; query strings are dropped
 * - only the X-EPI-Share-Token header (+ Content-Type on POST) is
 *   forwarded. Cookies and Authorization are NEVER forwarded, so this
 *   proxy cannot become a credentialed backdoor into org APIs.
 * Responses carry Cache-Control: no-store (a trust doc cached without its
 * token would leak one customer's evidence to the next reviewer) and any
 * upstream Set-Cookie is stripped.
 */

const CLOUD_ORIGIN_DEFAULT = "https://cloud.epilabs.org";

const ROUTES = [
  { method: "GET", pattern: /^\/v1\/trust\/[A-Za-z0-9_-]{1,128}$/ },
  { method: "GET", pattern: /^\/v1\/trust\/[A-Za-z0-9_-]{1,128}\/witness-lines$/ },
  { method: "POST", pattern: /^\/v1\/trust\/[A-Za-z0-9_-]{1,128}\/events$/ },
  { method: "GET", pattern: /^\/v1\/orgs\/[A-Za-z0-9_-]{1,64}\/artifacts\/[A-Za-z0-9_-]{1,64}\/content$/ },
];

export function trustProxyAllowed(method, pathname) {
  return ROUTES.some((r) => r.method === method && r.pattern.test(pathname));
}

export async function proxyTrustToCloud(request, fetchFn, cloudOrigin) {
  const url = new URL(request.url);
  if (!trustProxyAllowed(request.method, url.pathname)) {
    return new Response(
      JSON.stringify({ error: { code: "not_found", message: "Unknown route." } }),
      {
        status: 404,
        headers: { "content-type": "application/json", "cache-control": "no-store" },
      },
    );
  }
  const headers = new Headers();
  const token = request.headers.get("X-EPI-Share-Token");
  if (token) headers.set("X-EPI-Share-Token", token);
  const init = { method: request.method, headers, redirect: "manual" };
  if (request.method === "POST") {
    const ctype = request.headers.get("content-type");
    if (ctype) headers.set("content-type", ctype);
    init.body = request.body;
    // @ts-ignore — required for streaming bodies in CF workers
    init.duplex = "half";
  }
  let upstream;
  try {
    upstream = await fetchFn((cloudOrigin ?? CLOUD_ORIGIN_DEFAULT) + url.pathname, init);
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: { code: "bad_gateway", message: "Evidence service unreachable. Retry in a moment." },
      }),
      {
        status: 502,
        headers: { "content-type": "application/json", "cache-control": "no-store" },
      },
    );
  }
  const out = new Headers(upstream.headers);
  out.delete("set-cookie");
  out.delete("access-control-allow-origin");
  out.delete("access-control-allow-credentials");
  out.set("cache-control", "no-store");
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}

export async function onRequest(context) {
  return proxyTrustToCloud(context.request, fetch, context.env?.CLOUD_ORIGIN);
}
