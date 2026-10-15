import assert from "node:assert/strict";
import { once } from "node:events";
import http from "node:http";
import test from "node:test";

import { createApp } from "./server.js";
import { normalizeRoute } from "./metrics.js";

test("normalizeRoute collapses UUID and numeric ids", () => {
  assert.equal(
    normalizeRoute("/api/v1/processes/550e8400-e29b-41d4-a716-446655440000/status"),
    "/api/v1/processes/:id/status",
  );
  assert.equal(normalizeRoute("/api/v1/processes/42/status"), "/api/v1/processes/:id/status");
});

test("GET /metrics is Prometheus text with gateway process + http counters", async () => {
  const app = createApp({ coreUrl: "http://127.0.0.1:9" });
  const server = http.createServer(app);
  await once(server.listen(0), "listening");
  const { port } = server.address();
  const base = `http://127.0.0.1:${port}`;

  assert.equal((await fetch(`${base}/healthz`)).status, 200);
  // three different process ids → one route label
  for (const id of ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"]) {
    await fetch(`${base}/api/v1/processes/${id}/status`);
  }
  // core down → 502 from proxy path (may be 502 or error)
  await fetch(`${base}/api/v1/healthz`).catch(() => {});

  const res = await fetch(`${base}/metrics`);
  assert.equal(res.status, 200);
  const ct = res.headers.get("content-type") ?? "";
  assert.match(ct, /text\/plain/);
  const body = await res.text();
  assert.match(body, /kontur_gateway_process_cpu/);
  assert.match(body, /http_requests_total/);
  assert.match(body, /http_request_duration_seconds/);
  assert.match(body, /route="\/api\/v1\/processes\/:id\/status"/);
  // /metrics itself must not be proxied under /api/v1
  const leaked = await fetch(`${base}/api/v1/metrics`);
  assert.notEqual(leaked.status, 200);
  const leakedBody = await leaked.text();
  assert.doesNotMatch(leakedBody, /kontur_gateway_process_cpu/);

  server.close();
});
