// Node.js BFF. Границы ответственности зафиксированы намеренно:
// шлюз отвечает за внешний контракт, аутентификацию, RBAC, лимиты и логи;
// доменные решения и статусы находок остаются в Python-ядре.
// Шлюз не имеет права изменять finding_status (ADR-0001).

import express from "express";
import pino from "pino";
import { createProxyMiddleware } from "http-proxy-middleware";

const log = pino({ base: { service: "gateway" } });
const app = express();

const CORE_URL = process.env.KONTUR_CORE_URL ?? "http://localhost:8000";
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_BATCH_BYTES = 200 * 1024 * 1024;

// Структурированный лог по ТЗ п. 13: timestamp, level, service, message,
// request_id, user_id.
app.use((req, res, next) => {
  req.requestId = req.header("x-request-id") ?? crypto.randomUUID();
  res.setHeader("x-request-id", req.requestId);
  log.info({ request_id: req.requestId, method: req.method, path: req.path });
  next();
});

app.get("/healthz", (_req, res) => res.json({ status: "ok" }));

// TODO(L0): антивирусная проверка и лимиты до передачи в ядро.
// TODO(security): аутентификация и RBAC (инспектор / администратор / ML-инженер).
app.use(
  "/api/v1",
  createProxyMiddleware({
    target: CORE_URL,
    changeOrigin: true,
    limit: MAX_BATCH_BYTES,
  }),
);

app.listen(process.env.PORT ?? 3000, () => {
  log.info({ core: CORE_URL, MAX_FILE_BYTES, MAX_BATCH_BYTES }, "gateway started");
});
