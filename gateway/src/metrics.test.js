import assert from "node:assert/strict";
import { once } from "node:events";
import http from "node:http";
import test from "node:test";

import { createApp } from "./server.js";
import { normalizeRoute } from "./metrics.js";

test("normalizeRoute maps known templates, everything else is unmatched", () => {
  assert.equal(
    normalizeRoute("/api/v1/processes/550e8400-e29b-41d4-a716-446655440000/status"),
    "/api/v1/processes/:id/status",
  );
  assert.equal(normalizeRoute("/api/v1/processes/f-abc/revisions/f-xyz/select?x=1"), "/api/v1/processes/:id/revisions/:id/select");
  assert.equal(normalizeRoute("/api/v1/healthz"), "/api/v1/healthz");
  assert.equal(normalizeRoute("/api/v1/nope/1234"), "unmatched");
  assert.equal(normalizeRoute("/wp-admin/x.php"), "unmatched");
  assert.equal(normalizeRoute("/assets/app-3f2a.js"), "unmatched");
  assert.equal(normalizeRoute("/api/v1/processes/a/b/c/d/e"), "unmatched");
});

test("404 scans do not create new route label values", async () => {
  const app = createApp({ coreUrl: "http://127.0.0.1:9", metricsToken: "t0k" });
  const server = http.createServer(app);
  await once(server.listen(0), "listening");
  const base = `http://127.0.0.1:${server.address().port}`;
  for (const p of ["/scan-1.php", "/api/v1/zzz-1", "/api/v1/zzz-2"]) {
    await fetch(`${base}${p}`).catch(() => {});
  }
  const body = await (await fetch(`${base}/metrics`, { headers: { authorization: "Bearer t0k" } })).text();
  assert.doesNotMatch(body, /scan-1|zzz-/);
  assert.match(body, /route="unmatched"/);
  server.close();
});

test("/metrics requires auth: 403 without token config, 401 bad token, 200 good token, anon opt-in", async () => {
  const run = async (opts, headers) => {
    const server = http.createServer(createApp({ coreUrl: "http://127.0.0.1:9", ...opts }));
    await once(server.listen(0), "listening");
    const res = await fetch(`http://127.0.0.1:${server.address().port}/metrics`, { headers });
    server.close();
    return res.status;
  };
  assert.equal(await run({ metricsToken: "", metricsAllowAnon: false }, {}), 403);
  assert.equal(await run({ metricsToken: "s3", metricsAllowAnon: false }, {}), 401);
  assert.equal(await run({ metricsToken: "s3" }, { authorization: "Bearer wrong" }), 401);
  assert.equal(await run({ metricsToken: "s3" }, { authorization: "Bearer s3" }), 200);
  assert.equal(await run({ metricsToken: "", metricsAllowAnon: true }, {}), 200);
});

test("GET /metrics is Prometheus text with gateway process + http counters", async () => {
  const app = createApp({ coreUrl: "http://127.0.0.1:9", metricsAllowAnon: true });
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
