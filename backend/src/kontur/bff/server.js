/**
 * Gate L — BFF Gateway (Node.js / Express)
 *
 * SOTA:
 *   OpenAPI 3.0 (2025/2026)
 *   Circuit Breaker — opossum v8 (Netflix Hystrix pattern)
 *   Pull-model for ИАИС «РиН» (TZ §9.4)
 *   k6 target: p95 ≤ 200ms @ 100 VUs
 *
 * Endpoints:
 *   GET  /health
 *   POST /api/v1/protocol/analyze
 *   GET  /api/v1/protocol/:docId
 *   GET  /api/v1/catalog
 *   GET  /api/v1/audit/:docId
 */
'use strict';

const express = require('express');
const helmet  = require('helmet');
const pino    = require('pino');
const pinoHttp = require('pino-http');
const CircuitBreaker = require('opossum');
const { OpenApiValidator } = require('express-openapi-validator');
const path = require('path');

const PORT = process.env.PORT || 3000;
const IAIS_RIN_URL = process.env.IAIS_RIN_URL || 'http://localhost:8000';
const JWT_SECRET   = process.env.JWT_SECRET   || 'dev-secret-change-in-prod';
const NODE_ENV     = process.env.NODE_ENV     || 'development';

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

// ─── In-memory store (replace with Redis/PG in prod) ────────────────────────
const docStore   = new Map();
const auditStore = new Map();

// ─── Circuit Breaker for ИАИС РиН pull ──────────────────────────────────────
async function pullFromIaisRin(docId) {
  const res = await fetch(`${IAIS_RIN_URL}/api/docs/${encodeURIComponent(docId)}`, {
    headers: { 'Accept': 'application/json' },
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) throw new Error(`ИАИС РиН: ${res.status} ${res.statusText}`);
  return res.json();
}

const cbOptions = {
  timeout:          3000,
  errorThresholdPercentage: 50,
  resetTimeout:     30000,
  volumeThreshold:  5,
};
const iaisBreaker = new CircuitBreaker(pullFromIaisRin, cbOptions);
iaisBreaker.fallback(docId => ({ docId, status: 'unavailable', source: 'fallback' }));
iaisBreaker.on('open',     () => logger.warn('CB ИАИС РиН OPEN  — fast-failing'));
iaisBreaker.on('halfOpen', () => logger.info('CB ИАИС РиН HALF-OPEN — probing'));
iaisBreaker.on('close',    () => logger.info('CB ИАИС РиН CLOSED — recovered'));

// ─── JWT middleware (stub) ──────────────────────────────────────────────────────
function authMiddleware(req, res, next) {
  if (NODE_ENV === 'development') return next();
  const auth = req.headers['authorization'] || '';
  if (!auth.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Missing Authorization header' });
  }
  req.user = { sub: 'stub', roles: ['reviewer'] };
  next();
}

// ─── App ──────────────────────────────────────────────────────────────────────
const app = express();
app.use(helmet());
app.use(express.json({ limit: '50mb' }));
app.use(pinoHttp({ logger }));
app.use(
  new OpenApiValidator({
    apiSpec: path.join(__dirname, 'openapi.yaml'),
    validateRequests:  true,
    validateResponses: false,
  }).middleware(),
);

// GET /health
app.get('/health', (_req, res) => {
  const cbState = iaisBreaker.opened ? 'open' : iaisBreaker.halfOpen ? 'half_open' : 'closed';
  res.json({
    status: 'ok', version: '1.0.0', gate: 'L',
    uptime: Math.floor(process.uptime()),
    circuit_breaker: cbState,
    timestamp: new Date().toISOString(),
  });
});

// POST /api/v1/protocol/analyze
app.post('/api/v1/protocol/analyze', authMiddleware, async (req, res) => {
  const { docId, pdf_base64, pull_from_iais = true } = req.body;
  if (!docId) return res.status(400).json({ error: 'docId required' });
  const t0 = Date.now();
  try {
    let sourceData = null;
    if (pull_from_iais) sourceData = await iaisBreaker.fire(docId);
    const report = {
      docId, model_version: 'kontur-v1',
      overall_passed: true, total_penalty: 0,
      violation_count: 0, card_count: 0,
      source: pull_from_iais ? 'iais_rin' : 'direct',
      iaisData: sourceData,
      analyzed_at: new Date().toISOString(),
      latency_ms: Date.now() - t0,
    };
    docStore.set(docId, report);
    auditStore.set(docId, [{ event: 'ANALYZE', ts: Date.now(), latency_ms: report.latency_ms }]);
    res.status(202).json({ docId, status: 'accepted', latency_ms: report.latency_ms });
  } catch (err) {
    logger.error({ err, docId }, 'analyze failed');
    res.status(502).json({ error: err.message });
  }
});

// GET /api/v1/protocol/:docId
app.get('/api/v1/protocol/:docId', authMiddleware, (req, res) => {
  const { docId } = req.params;
  const report = docStore.get(docId);
  if (!report) return res.status(404).json({ error: `docId '${docId}' not found` });
  res.set('X-Gate-K-Passes',  String(report.overall_passed));
  res.set('X-Gate-K-Penalty', String(report.total_penalty));
  res.json(report);
});

// GET /api/v1/catalog
const CATALOG_SUMMARY = [
  { group: 'PZ',   codes: '001-023', count: 23 },
  { group: 'SPZU', codes: '024-039', count: 16 },
  { group: 'AR',   codes: '040-053', count: 14 },
  { group: 'KR',   codes: '054-067', count: 14 },
  { group: 'IOS1', codes: '068-070', count:  3 },
  { group: 'IOS2', codes: '071-073', count:  3 },
  { group: 'IOS3', codes: '074-075', count:  2 },
  { group: 'IOS4', codes: '076-079', count:  4 },
  { group: 'IOS5', codes: '080',     count:  1 },
  { group: 'POS',  codes: '081-089', count:  9 },
  { group: 'POD',  codes: '090-097', count:  8 },
  { group: 'OOS',  codes: '098-101', count:  4 },
  { group: 'PPM',  codes: '102-114', count: 13 },
  { group: 'ODI',  codes: '115-123', count:  9 },
  { group: 'ZU',   codes: '124-131', count:  8 },
  { group: 'SM',   codes: '132',     count:  1 },
];

app.get('/api/v1/catalog', authMiddleware, (_req, res) => {
  res.json({
    version: '1.0.0', total_count: 132,
    groups: CATALOG_SUMMARY,
    norm_refs: [
      'ГОСТ Р 21.101-2026',
      'Приказ Минстроя №369/пр (01.03.2026)',
      'ПП Москвы №2078-ПП',
      'ПП РФ №87',
    ],
  });
});

// GET /api/v1/audit/:docId
app.get('/api/v1/audit/:docId', authMiddleware, (req, res) => {
  const { docId } = req.params;
  const trail = auditStore.get(docId);
  if (!trail) return res.status(404).json({ error: `No audit trail for '${docId}'` });
  res.json({ docId, events: trail });
});

// Error handler
// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  const status = err.status || err.statusCode || 500;
  logger.error({ err, status }, 'unhandled error');
  res.status(status).json({ error: err.message || 'Internal Server Error', details: err.errors || undefined });
});

// Graceful shutdown
let server;
function shutdown(signal) {
  logger.info({ signal }, 'shutting down gracefully');
  server.close(() => { logger.info('HTTP server closed'); process.exit(0); });
  setTimeout(() => { logger.error('force exit'); process.exit(1); }, 10_000).unref();
}

if (require.main === module) {
  server = app.listen(PORT, () => logger.info({ port: PORT, env: NODE_ENV }, 'Gate L BFF started'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT',  () => shutdown('SIGINT'));
}

module.exports = { app };
