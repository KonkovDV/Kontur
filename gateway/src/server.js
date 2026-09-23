// Node.js BFF. Границы ответственности зафиксированы намеренно:
// шлюз отвечает за внешний контракт, лимиты тела и логи;
// аутентификация, RBAC и статусы находок остаются в Python-ядре.
// Шлюз не имеет права изменять finding_status (ADR-0001).

import express from "express";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import pino from "pino";
import { createProxyMiddleware } from "http-proxy-middleware";

const log = pino({ base: { service: "gateway" } });
const app = express();

const CORE_URL = process.env.KONTUR_CORE_URL ?? "http://localhost:8000";
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_BATCH_BYTES = 200 * 1024 * 1024;
const PROXY_TIMEOUT_MS = Number(process.env.KONTUR_PROXY_TIMEOUT_MS ?? 600_000);
const webRoot =
  process.env.KONTUR_WEB_ROOT ??
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "web");

// Структурированный лог по ТЗ п. 13: timestamp, level, service, message,
// request_id, user_id.
app.use((req, res, next) => {
  req.requestId = req.header("x-request-id") ?? crypto.randomUUID();
  res.setHeader("x-request-id", req.requestId);
  log.info({ request_id: req.requestId, method: req.method, path: req.path });
  next();
});

app.get("/healthz", (_req, res) => res.json({ status: "ok" }));

app.use((req, res, next) => {
  const length = Number(req.headers["content-length"] || 0);
  if (Number.isFinite(length) && length > MAX_BATCH_BYTES) {
    res.status(413).json({
      reason_code: "BATCH_LIMIT_EXCEEDED",
      message: `Content-Length ${length} больше лимита ${MAX_BATCH_BYTES} Б`,
    });
    return;
  }
  next();
});

// RBAC — в Python-ядре (presentation/rbac.py); шлюз не пишет finding_status.
app.use(
  "/api/v1",
  createProxyMiddleware({
    target: CORE_URL,
    changeOrigin: true,
    proxyTimeout: PROXY_TIMEOUT_MS,
    timeout: PROXY_TIMEOUT_MS,
  }),
);

if (fs.existsSync(webRoot)) {
  app.use(express.static(webRoot));
}

app.listen(process.env.PORT ?? 3000, () => {
  log.info(
    { core: CORE_URL, MAX_FILE_BYTES, MAX_BATCH_BYTES, webRoot },
    "gateway started",
  );
});
