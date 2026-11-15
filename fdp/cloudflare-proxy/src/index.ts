/**
 * Cloudflare Worker reverse proxy for the Modal-hosted FDP API.
 *
 * Responsibilities:
 * - Authenticate incoming requests with a Bearer token (PROXY_TOKEN secret).
 * - Forward allowed requests to the Modal origin (MODAL_URL variable).
 * - Add CORS headers for browser-based MCP clients.
 * - Hide the Modal deployment URL from end clients.
 *
 * Environment:
 *   MODAL_URL       - origin of the Modal app
 *   ALLOWED_ORIGINS - comma-separated CORS origins, or "*"
 * Secrets:
 *   PROXY_TOKEN     - Bearer token required in Authorization header
 */

export interface Env {
  MODAL_URL: string;
  ALLOWED_ORIGINS: string;
  PROXY_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return handleCors(url, env, 204);
    }

    // Authenticate
    const auth = request.headers.get("Authorization") || "";
    const expected = `Bearer ${env.PROXY_TOKEN}`;
    if (!env.PROXY_TOKEN || auth !== expected) {
      return new Response(
        JSON.stringify({ error: "Unauthorized" }),
        {
          status: 401,
          headers: {
            "Content-Type": "application/json",
            ...corsHeaders(url, env),
          },
        },
      );
    }

    if (!env.MODAL_URL) {
      return new Response(
        JSON.stringify({ error: "MODAL_URL not configured" }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
            ...corsHeaders(url, env),
          },
        },
      );
    }

    // Build upstream URL
    const upstream = new URL(url.pathname + url.search, env.MODAL_URL);

    // Forward request, stripping the Authorization header the client sent
    // so it is not leaked to Modal. Modal uses its own token if needed.
    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.delete("Authorization");
    upstreamHeaders.set("Host", new URL(env.MODAL_URL).host);

    const upstreamRequest = new Request(upstream.toString(), {
      method: request.method,
      headers: upstreamHeaders,
      body: request.body,
    });

    try {
      const response = await fetch(upstreamRequest);

      // Add CORS to the upstream response
      const modified = new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: mergeHeaders(response.headers, corsHeaders(url, env)),
      });

      return modified;
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Upstream error", detail: String(err) }),
        {
          status: 502,
          headers: {
            "Content-Type": "application/json",
            ...corsHeaders(url, env),
          },
        },
      );
    }
  },
};

function corsHeaders(requestUrl: URL, env: Env): Record<string, string> {
  const allowed = (env.ALLOWED_ORIGINS || "*")
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);

  const origin = requestUrl.origin;
  const allowOrigin = allowed.includes("*") || allowed.includes(origin)
    ? origin
    : allowed[0] || "*";

  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
    "Access-Control-Allow-Credentials": "true",
  };
}

function handleCors(requestUrl: URL, env: Env, status: number): Response {
  return new Response(null, {
    status,
    headers: corsHeaders(requestUrl, env),
  });
}

function mergeHeaders(
  base: Headers,
  extra: Record<string, string>,
): Headers {
  const result = new Headers(base);
  for (const [key, value] of Object.entries(extra)) {
    result.set(key, value);
  }
  return result;
}
