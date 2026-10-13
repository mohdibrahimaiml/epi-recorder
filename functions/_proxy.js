/**
 * Shared reverse-proxy helper for Cloudflare Pages Functions.
 * Forwards /api/*, /scitt/*, /.well-known/* to the Render verify portal.
 */

// WP-SEC-2: exact origin allowlist. Never substring-match: endsWith("epilabs.org")
// also matches evilepilabs.org, and includes("pages.dev") matches any project.
const ALLOWED = new Set(["https://epilabs.org", "https://www.epilabs.org"]);
// This project's Cloudflare Pages previews only (project name: epi-recorder).
const PREVIEW = /^https:\/\/[a-z0-9-]+\.epi-recorder\.pages\.dev$/;
function allowedOrigin(o){ if(typeof o!=="string"||/[\r\n]/.test(o))return null; return (ALLOWED.has(o)||PREVIEW.test(o))?o:null; }

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
    // Even the error path must not reflect an untrusted origin.
    const errHeaders = {
      "content-type": "application/json",
    };
    const allowedErr = allowedOrigin(incoming.origin);
    if (allowedErr) {
      errHeaders["access-control-allow-origin"] = allowedErr;
      errHeaders["access-control-allow-credentials"] = "true";
    }
    return new Response(
      JSON.stringify({
        ok: false,
        detail: "Upstream API unreachable (Render may be cold-starting). Retry in a few seconds.",
        error: String(err && err.message ? err.message : err),
      }),
      {
        status: 502,
        headers: errHeaders,
      },
    );
  }

  // Rebuild response so we can adjust CORS for browser clients
  const outHeaders = new Headers(response.headers);
  const origin = context.request.headers.get("Origin");
  const allowed = allowedOrigin(origin);
  if (allowed) {
    outHeaders.set("access-control-allow-origin", allowed);
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
  const origin = context.request.headers.get("Origin");
  const allowed = allowedOrigin(origin);
  const headers = {
    "access-control-allow-methods": "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
    "access-control-allow-headers":
      context.request.headers.get("Access-Control-Request-Headers") ||
      "authorization, content-type, x-api-key, x-admin-key",
    "access-control-max-age": "600",
    vary: "Origin",
  };
  // Reflect ACAO only for allowlisted origins; otherwise omit it entirely.
  if (allowed) {
    headers["access-control-allow-origin"] = allowed;
    headers["access-control-allow-credentials"] = "true";
  }
  return new Response(null, {
    status: 204,
    headers,
  });
}
