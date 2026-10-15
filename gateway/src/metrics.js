/** §13 п.4–5: Prometheus /metrics для gateway (CPU/RAM процесса, RPS, latency, 5xx). */

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

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi;
const HEX64_RE = /\/[0-9a-f]{64}(?=\/|$)/gi;

/** Снижает кардинальность: UUID и длинные hex → :id. */
export function normalizeRoute(path) {
  if (!path || path === "/") return "/";
  let route = path.split("?")[0];
  route = route.replace(UUID_RE, ":id");
  route = route.replace(HEX64_RE, "/:id");
  // числовые id сегменты
  route = route.replace(/\/\d+(?=\/|$)/g, "/:id");
  return route || "/";
}

export function metricsMiddleware(req, res, next) {
  const started = process.hrtime.bigint();
  res.on("finish", () => {
    const elapsedNs = Number(process.hrtime.bigint() - started);
    const durationSec = elapsedNs / 1e9;
    const route = normalizeRoute(req.route?.path ? req.baseUrl + req.route.path : req.path);
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
