/** §13 п.4–5: Prometheus /metrics для gateway (CPU/RAM процесса, RPS, latency, 5xx). */

import crypto from "node:crypto";

import client from "prom-client";

const register = new client.Registry();
client.collectDefaultMetrics({ register, prefix: "kontur_gateway_" });

const httpRequestsTotal = new client.Counter({
  name: "http_requests_total",
  help: "HTTP requests handled by the gateway",
  labelNames: ["method", "route", "status"],
  registers: [register],
});

const httpRequestDurationSeconds = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "route", "status"],
  // 0.2 = Gate L / §11; 0.5 = §13 п.7 alert example
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2.5, 5, 10],
  registers: [register],
});

/** Шаблоны маршрутов ядра, доступные через gateway (:p — любой один сегмент). */
export const KNOWN_ROUTES = [
  "/api/v1/demo/kit",
  "/api/v1/documents/upload",
  "/api/v1/evaluation/score",
  "/api/v1/findings/:p/review",
  "/api/v1/healthz",
  "/api/v1/inspection/:p",
  "/api/v1/processes/:p/audit",
  "/api/v1/processes/:p/audit/ui",
  "/api/v1/processes/:p/complete",
  "/api/v1/processes/:p/documents",
  "/api/v1/processes/:p/finalize",
  "/api/v1/processes/:p/findings",
  "/api/v1/processes/:p/findings/confirm",
  "/api/v1/processes/:p/protocol",
  "/api/v1/processes/:p/protocol.docx",
  "/api/v1/processes/:p/protocol.pdf",
  "/api/v1/processes/:p/protocol.xml",
  "/api/v1/processes/:p/revisions/:p/select",
  "/api/v1/processes/:p/status",
  "/api/v1/processes/:p/unfinalize",
  "/api/v1/processes/:p/verify",
  "/api/v1/system/capabilities",
];
const STATIC_ROUTES = new Set(["/", "/healthz", "/metrics"]);
const TEMPLATES = KNOWN_ROUTES.map((t) => t.split("/"));

/**
 * Label `route` с ограниченной кардинальностью: только известные шаблоны
 * `/api/v1/*` (id -> :id) и несколько статических путей; всё остальное
 * (404-сканы, имена файлов, SPA-assets) -> "unmatched".
 */
export function normalizeRoute(path) {
  const clean = (path ?? "").split("?")[0] || "/";
  if (STATIC_ROUTES.has(clean)) return clean;
  if (!clean.startsWith("/api/v1/")) return "unmatched";
  const parts = clean.replace(/\/+$/, "").split("/");
  for (const tpl of TEMPLATES) {
    if (tpl.length !== parts.length) continue;
    let ok = true;
    for (let i = 0; i < tpl.length; i += 1) {
      if (tpl[i] === ":p") {
        if (!parts[i]) ok = false;
      } else if (tpl[i] !== parts[i]) {
        ok = false;
      }
      if (!ok) break;
    }
    if (ok) return tpl.map((seg) => (seg === ":p" ? ":id" : seg)).join("/");
  }
  return "unmatched";
}

/**
 * Доступ к /metrics: Bearer KONTUR_METRICS_TOKEN; без токена — 403, если не
 * задан KONTUR_METRICS_ALLOW_ANON=1 (осознанный анонимный режим, напр. loopback).
 */
function digest(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest();
}

/** Constant-time Bearer check; an empty configured token never matches. */
export function tokenMatches(header, token) {
  if (typeof token !== "string" || token.length === 0) return false;
  const presented = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : "";
  return crypto.timingSafeEqual(digest(presented), digest(token)) && presented.length > 0;
}

export function metricsAuth({ token = process.env.KONTUR_METRICS_TOKEN ?? "", allowAnon = process.env.KONTUR_METRICS_ALLOW_ANON === "1" } = {}) {
  const configured = typeof token === "string" ? token.trim() : "";
  return (req, res, next) => {
    if (configured) {
      if (tokenMatches(req.header("authorization") ?? "", configured)) return next();
      res.status(401).json({ error: "METRICS_UNAUTHORIZED" });
      return undefined;
    }
    if (allowAnon) return next();
    res.status(403).json({ error: "METRICS_DISABLED" });
    return undefined;
  };
}

export function metricsMiddleware(req, res, next) {
  const started = process.hrtime.bigint();
  res.on("finish", () => {
    const elapsedNs = Number(process.hrtime.bigint() - started);
    const durationSec = elapsedNs / 1e9;
    const route = normalizeRoute(req.originalUrl ?? req.path);
    const labels = {
      method: req.method,
      route,
      status: String(res.statusCode),
    };
    httpRequestsTotal.inc(labels);
    httpRequestDurationSeconds.observe(labels, durationSec);
  });
  next();
}

export async function metricsHandler(_req, res) {
  res.setHeader("Content-Type", register.contentType);
  res.end(await register.metrics());
}

export { register, httpRequestsTotal, httpRequestDurationSeconds };
