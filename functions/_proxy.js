/**
 * Shared reverse-proxy helper for Cloudflare Pages Functions.
 * Forwards /api/*, /scitt/*, /.well-known/* to the Render verify portal.
 */
const BACKEND = "https://epi-verify-portal.onrender.com";

export async function proxyToRender(context) {
  const incoming = new URL(context.request.url);
  const target = new URL(incoming.pathname + incoming.search, BACKEND);

  // Clone headers; drop hop-by-hop that confuse origin
  const headers = new Headers(context.request.headers);
  headers.delete("host");
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));

  const method = context.request.method;
  const init = {
    method,
    headers,
    redirect: "manual",
  };

  if (method !== "GET" && method !== "HEAD") {
    init.body = context.request.body;
    // @ts-ignore — required for streaming bodies in CF workers
    init.duplex = "half";
  }

  let response;
  try {
    response = await fetch(target.toString(), init);
  } catch (err) {
    return new Response(
      JSON.stringify({
        ok: false,
        detail: "Upstream API unreachable (Render may be cold-starting). Retry in a few seconds.",
        error: String(err && err.message ? err.message : err),
      }),
      {
        status: 502,
        headers: {
          "content-type": "application/json",
          "access-control-allow-origin": incoming.origin || "*",
          "access-control-allow-credentials": "true",
        },
      },
    );
  }

  // Rebuild response so we can adjust CORS for browser clients
  const outHeaders = new Headers(response.headers);
  const origin = context.request.headers.get("Origin");
  if (origin && (origin.endsWith("epilabs.org") || origin.includes("pages.dev"))) {
    outHeaders.set("access-control-allow-origin", origin);
    outHeaders.set("access-control-allow-credentials", "true");
    outHeaders.append("vary", "Origin");
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outHeaders,
  });
}

/** CORS preflight for proxied API routes */
export function corsPreflight(context) {
  const origin = context.request.headers.get("Origin") || "*";
  return new Response(null, {
    status: 204,
    headers: {
      "access-control-allow-origin": origin,
      "access-control-allow-credentials": "true",
      "access-control-allow-methods": "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
      "access-control-allow-headers":
        context.request.headers.get("Access-Control-Request-Headers") ||
        "authorization, content-type, x-api-key, x-admin-key",
      "access-control-max-age": "600",
      vary: "Origin",
    },
  });
}
