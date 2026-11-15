/**
 * CSP violation report sink.
 *
 * The site ships `Content-Security-Policy-Report-Only` for script-src,
 * style-src and connect-src. That is only useful if the reports land somewhere,
 * otherwise "enforce it after a week of clean reports" is unmeasurable. This
 * accepts them and logs a bounded one-line summary to the Pages function log,
 * which is enough to see whether the policy is ready to enforce.
 *
 * Deliberately stores nothing and logs no query strings: a document URL can
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
