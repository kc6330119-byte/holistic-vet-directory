// geo-guard — block scraper/bot traffic from datacenter regions at the edge.
//
// Why: Google Analytics (May–Jun 2026) showed ~75% of all "users" were a single
// Singapore datacenter (~3,200 hits ≈ one per listing page = a content scraper),
// arriving as direct/no-referrer, 99% "new". The real audience is US (+ a little
// Canada) via DuckDuckGo/Bing/Yahoo. Fencing the datacenter region keeps that
// scraped/bot traffic from inflating analytics and (once ads serve) AdSense
// invalid-traffic counts. Runs on every page request via Netlify Edge (all plans
// expose context.geo). Static assets are excluded to keep invocations down.
//
// To tune: add ISO-3166-1 alpha-2 codes to BLOCKED_COUNTRIES as new abuse
// sources appear; remove SG if the scrape stops and you want it fully open again.

import type { Context } from "https://edge.netlify.com";

// Country codes blocked outright. Keep this tight — only regions with no real
// audience and demonstrated abuse. The site's users are US-based.
const BLOCKED_COUNTRIES = new Set<string>(["SG"]);

// Legitimate search-engine crawlers are ALWAYS allowed through, even from a
// blocked region, so indexing/SEO can never be harmed. (User-agents can be
// spoofed, but the downside of accidentally blocking a real crawler outweighs a
// scraper impersonating one — and the scraper would still show in logs.)
const ALLOWED_BOTS =
  /(googlebot|google-inspectiontool|storebot-google|bingbot|applebot|duckduckbot|slurp|baiduspider|yandex(bot)?|petalbot|chrome-lighthouse)/i;

export default async (request: Request, context: Context): Promise<Response | void> => {
  const country = context.geo?.country?.code ?? "";
  if (!BLOCKED_COUNTRIES.has(country)) return; // not a blocked region → pass through

  const ua = request.headers.get("user-agent") ?? "";
  if (ALLOWED_BOTS.test(ua)) return; // real search crawler → pass through

  // Lands in Netlify's edge-function logs so you can confirm it's working.
  console.log(`geo-guard: blocked ${country} ${new URL(request.url).pathname} ua="${ua.slice(0, 80)}"`);

  return new Response("Access denied.", {
    status: 403,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
    },
  });
};

// Run on all routes except static assets (css/js/images), which don't need
// per-request geo checks and would otherwise multiply edge invocations.
export const config = {
  path: "/*",
  excludedPath: ["/static/*", "/favicon.ico", "/robots.txt", "/ads.txt"],
};
