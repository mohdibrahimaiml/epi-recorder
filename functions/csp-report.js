/**
 * CSP violation report sink.
 *
 * The site ships an enforcing `Content-Security-Policy` whose `report-uri`
 * points here. Enforcement makes reports matter more, not less: a blocked
 * resource is still lost to the visitor, so the only way to notice is for the
 * browser to say so. This accepts them and logs a bounded one-line summary to
 * the Pages function log, which Cloudflare exposes through real-time logs /
 * Logpush. A durable sink would need a storage binding (KV/D1/Analytics
 * Engine) on the Pages project; the log line is the shape such a sink wants.
 *
 * Stores nothing and logs no query strings: a document URL can
 * carry a token (`/t/<id>#k=` pages), and the point of the report is the
 * directive, not the visitor.
 */
const MAX_BYTES = 8192;

const noContent = () => new Response(null, { status: 204 });

export async function onRequest(context) {
  const { request } = context;
  if (request.method !== "POST") {
    return new Response("Method not allowed", {
      status: 405,
      headers: { allow: "POST" },
    });
  }

  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_BYTES) {
    // Refuse to read it at all rather than buffer an oversized body.
    return noContent();
  }

  let raw = "";
  try {
    raw = await request.text();
  } catch {
    return noContent();
  }
  if (raw.length > MAX_BYTES) {
    return noContent();
  }

  try {
    const parsed = JSON.parse(raw);
    // Legacy `report-uri` shape is {"csp-report": {...}}; the Reporting API
    // posts an array of {type, body}.
    const report =
      parsed["csp-report"] ||
      (Array.isArray(parsed) ? parsed[0] && parsed[0].body : null) ||
      {};
    console.log(
      JSON.stringify({
        kind: "csp-report",
        directive:
          report["violated-directive"] ||
          report["effective-directive"] ||
          "",
        blocked: String(report["blocked-uri"] || "").slice(0, 200),
        document: String(report["document-uri"] || "").split("?")[0].slice(0, 200),
      }),
    );
  } catch {
    // A malformed report still tells us the browser tried to send one.
    console.log(JSON.stringify({ kind: "csp-report", malformed: true }));
  }
  return noContent();
}
