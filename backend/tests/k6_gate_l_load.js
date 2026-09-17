/**
 * Gate L — k6 Load Test
 *
 * Requirements (TZ §9.4):
 *   p95 latency <= 200ms @ 100 VUs
 *   Error rate < 1%
 *   Throughput >= 200 RPS steady-state
 *
 * Run:
 *   k6 run --env BASE_URL=http://localhost:3000 \
 *          --env SKIP_AUTH=true \
 *          backend/tests/k6_gate_l_load.js
 *
 * SOTA: k6 v0.55 (2026) — scenarios, threshold expressions, custom metrics
 */

import http    from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// --- Custom metrics ---
const errorRate   = new Rate('gate_l_errors');
const analyzeTime = new Trend('gate_l_analyze_ms', true);
const catalogTime = new Trend('gate_l_catalog_ms', true);
const reportTime  = new Trend('gate_l_report_ms',  true);
const auditTime   = new Trend('gate_l_audit_ms',   true);
const healthOk    = new Counter('gate_l_health_ok');

// --- Config ---
const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
const AUTH     = __ENV.SKIP_AUTH === 'true' ? '' : 'Bearer dev-token-stub';
const HEADERS  = {
  'Content-Type': 'application/json',
  'Accept':       'application/json',
  ...(AUTH ? { 'Authorization': AUTH } : {}),
};

// --- Scenarios + Thresholds ---
export const options = {
  scenarios: {
    full_load: {
      executor:  'ramping-vus',
      startVUs:  0,
      stages: [
        { duration: '30s', target: 100 },
        { duration: '2m',  target: 100 },
        { duration: '30s', target:   0 },
      ],
      gracefulRampDown: '10s',
      tags: { scenario: 'full_load' },
    },
    spike: {
      executor:  'ramping-vus',
      startVUs:  0,
      startTime: '3m30s',
      stages: [
        { duration: '10s', target: 150 },
        { duration: '30s', target: 150 },
        { duration: '10s', target:   0 },
      ],
      tags: { scenario: 'spike' },
    },
    health_smoke: {
      executor: 'constant-vus',
      vus:      1,
      duration: '5m',
      tags:     { scenario: 'health_smoke' },
    },
  },
  thresholds: {
    'http_req_duration{scenario:full_load}': ['p(95)<200'],
    'http_req_duration{scenario:spike}':     ['p(95)<400'],
    'gate_l_analyze_ms':  ['p(95)<200'],
    'gate_l_catalog_ms':  ['p(95)<50'],
    'gate_l_report_ms':   ['p(95)<100'],
    'gate_l_audit_ms':    ['p(95)<100'],
    'gate_l_errors':      ['rate<0.01'],
    'http_req_failed':    ['rate<0.01'],
  },
};

// --- Helpers ---
function makeDocId() {
  return `doc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function ok(res, expected, label) {
  const passed = check(res, {
    [`${label} status=${expected}`]: r => r.status === expected,
    [`${label} has body`]:           r => r.body && r.body.length > 0,
  });
  errorRate.add(!passed);
  return passed;
}

function isJson(res, label) {
  return check(res, {
    [`${label} is JSON`]: r => {
      try { JSON.parse(r.body); return true; } catch { return false; }
    },
  });
}

// --- Default function ---
export default function () {
  const scenario = __ENV.K6_SCENARIO_NAME || 'full_load';
  if (scenario === 'health_smoke') { runHealthSmoke(); return; }
  runFullFlow();
}

// --- Full protocol flow ---
function runFullFlow() {
  const docId = makeDocId();

  group('GET /api/v1/catalog', () => {
    const t0  = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/catalog`, { headers: HEADERS });
    catalogTime.add(Date.now() - t0);
    ok(res, 200, 'catalog');
    isJson(res, 'catalog');
    const body = JSON.parse(res.body || '{}');
    check(body, {
      'catalog total_count=132': b => b.total_count === 132,
      'catalog 16 groups':       b => Array.isArray(b.groups) && b.groups.length === 16,
    });
  });

  sleep(0.05);

  group('POST /api/v1/protocol/analyze', () => {
    const t0  = Date.now();
    const res = http.post(
      `${BASE_URL}/api/v1/protocol/analyze`,
      JSON.stringify({ docId, pull_from_iais: false }),
      { headers: HEADERS },
    );
    analyzeTime.add(Date.now() - t0);
    ok(res, 202, 'analyze');
    if (res.status === 202) {
      const body = JSON.parse(res.body);
      check(body, {
        'analyze docId matches':    b => b.docId === docId,
        'analyze status=accepted':  b => b.status === 'accepted',
      });
    }
  });

  sleep(0.05);

  group('GET /api/v1/protocol/:docId', () => {
    const t0  = Date.now();
    const res = http.get(
      `${BASE_URL}/api/v1/protocol/${encodeURIComponent(docId)}`,
      { headers: HEADERS },
    );
    reportTime.add(Date.now() - t0);
    ok(res, 200, 'report');
    if (res.status === 200) {
      const body = JSON.parse(res.body || '{}');
      check(res.headers, { 'report X-Gate-K-Passes header': h => h['X-Gate-K-Passes'] !== undefined });
      check(body, {
        'report overall_passed bool': b => typeof b.overall_passed === 'boolean',
        'report total_penalty num':   b => typeof b.total_penalty  === 'number',
      });
    }
  });

  sleep(0.05);

  group('GET /api/v1/audit/:docId', () => {
    const t0  = Date.now();
    const res = http.get(
      `${BASE_URL}/api/v1/audit/${encodeURIComponent(docId)}`,
      { headers: HEADERS },
    );
    auditTime.add(Date.now() - t0);
    ok(res, 200, 'audit');
    if (res.status === 200) {
      const body = JSON.parse(res.body || '{}');
      check(body, {
        'audit events array': b => Array.isArray(b.events),
        'audit docId match':  b => b.docId === docId,
      });
    }
  });

  sleep(0.1);
}

// --- Health smoke ---
function runHealthSmoke() {
  const res = http.get(`${BASE_URL}/health`, { headers: { Accept: 'application/json' } });
  if (ok(res, 200, 'health')) {
    healthOk.add(1);
    const body = JSON.parse(res.body || '{}');
    check(body, {
      'health status=ok':           b => b.status === 'ok',
      'health circuit_breaker ok':  b => ['closed','open','half_open'].includes(b.circuit_breaker),
    });
  }
  sleep(5);
}

// --- Setup / Teardown ---
export function setup() {
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) throw new Error(`Server not ready: ${res.status}`);
  console.log(`[k6 setup] Gate L BFF ready at ${BASE_URL}`);
  return { baseUrl: BASE_URL };
}

export function teardown(data) {
  console.log(`[k6 teardown] Done. Base URL: ${data.baseUrl}`);
}
