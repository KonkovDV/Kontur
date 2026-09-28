// Node.js BFF. Границы ответственности зафиксированы намеренно:
// шлюз отвечает за внешний контракт, лимиты тела и логи;
// аутентификация, RBAC и статусы находок остаются в Python-ядре.
// Шлюз не имеет права изменять finding_status (ADR-0001).

import express from "express";
import fs from "fs";
import http from "node:http";
import path from "path";
import { fileURLToPath } from "url";
import pino from "pino";
import { createProxyMiddleware } from "http-proxy-middleware";

import {
  MAX_BATCH_BYTES,
  MAX_FILE_BYTES,
  UPLOAD_LIMIT,
  UPLOAD_WINDOW_MS,
  createUploadLimiter,
  exceedsBatchLimit,
  exceedsFileLimit,
  multipartFileState,
} from "./limits.js";

const log = pino({ base: { service: "gateway" } });

const CORE_URL = process.env.KONTUR_CORE_URL ?? "http://localhost:8000";
const PROXY_TIMEOUT_MS = Number(process.env.KONTUR_PROXY_TIMEOUT_MS ?? 600_000);
const webRoot =
  process.env.KONTUR_WEB_ROOT ??
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "web");

function reject(res, status, reason, message) {
  res.status(status).json({ reason_code: reason, message });
}

function boundaryOf(contentType) {
  const matched = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType ?? "");
  if (!matched) return null;
  return (matched[1] ?? matched[2]).trim();
}

function isUpload(req) {
  return req.method === "POST" && req.originalUrl.startsWith("/api/v1/documents/upload");
}

function clientKey(req) {
  return req.socket?.remoteAddress ?? "unknown";
}

function readBody(req, maxBatchBytes) {
  return new Promise((resolve, rejectRead) => {
    const chunks = [];
    let total = 0;
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    req.on("data", (chunk) => {
      if (settled) return;
      total += chunk.length;
      if (exceedsBatchLimit(total, maxBatchBytes)) {
        req.destroy();
        finish({ kind: "batch", total });
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => finish({ kind: "ok", body: Buffer.concat(chunks), total }));
    req.on("error", (error) => {
      if (!settled) {
        settled = true;
        rejectRead(error);
      }
    });
  });
}

function forwardBuffered(req, res, body, coreUrl) {
  const target = new URL(req.originalUrl, coreUrl);
  const headers = { ...req.headers, host: target.host };
  headers["content-length"] = String(body.length);
  const upstream = http.request(
    target,
    { method: req.method, headers, timeout: PROXY_TIMEOUT_MS },
    (response) => {
      res.writeHead(response.statusCode ?? 502, response.headers);
      response.pipe(res);
    },
  );
  upstream.on("error", () => {
    if (!res.headersSent) {
      reject(res, 502, "UPSTREAM_UNAVAILABLE", "ядро недоступно");
    }
  });
  upstream.end(body);
}

export function createApp({
  maxFileBytes = MAX_FILE_BYTES,
  maxBatchBytes = MAX_BATCH_BYTES,
  uploadLimit = UPLOAD_LIMIT,
  uploadWindowMs = UPLOAD_WINDOW_MS,
  coreUrl = CORE_URL,
} = {}) {
  const app = express();
  const allowUpload = createUploadLimiter(uploadLimit, uploadWindowMs);

  app.use((req, res, next) => {
    req.requestId = req.header("x-request-id") ?? crypto.randomUUID();
    res.setHeader("x-request-id", req.requestId);
    log.info({ request_id: req.requestId, method: req.method, path: req.path });
    next();
  });

  app.get("/healthz", (_req, res) => res.json({ status: "ok" }));

  app.use((req, res, next) => {
    const length = Number(req.headers["content-length"] || 0);
    if (Number.isFinite(length) && exceedsBatchLimit(length, maxBatchBytes)) {
      reject(
        res,
        413,
        "BATCH_LIMIT_EXCEEDED",
        `Content-Length ${length} больше лимита ${maxBatchBytes} Б`,
      );
      return;
    }
    next();
  });

  app.use((req, res, next) => {
    if (!isUpload(req)) {
      next();
      return;
    }
    if (!allowUpload(clientKey(req))) {
      reject(res, 429, "RATE_LIMITED", "слишком много загрузок, повторите позже");
      return;
    }
    const length = Number(req.headers["content-length"] || 0);
    if (!Number.isFinite(length) || length <= maxFileBytes) {
      next();
      return;
    }
    const boundary = boundaryOf(req.header("content-type"));
    if (!boundary) {
      reject(
        res,
        413,
        "FILE_TOO_LARGE",
        `тело ${length} Б больше лимита файла ${maxFileBytes} Б`,
      );
      return;
    }
    readBody(req, maxBatchBytes)
      .then((result) => {
        if (res.headersSent) return;
        if (result.kind === "batch") {
          reject(
            res,
            413,
            "BATCH_LIMIT_EXCEEDED",
            `пакет ${result.total} Б больше лимита ${maxBatchBytes} Б`,
          );
          return;
        }
        const state = multipartFileState(result.body, boundary);
        const oversized = [...state.complete, state.open].find((size) =>
          exceedsFileLimit(size, maxFileBytes),
        );
        if (oversized !== undefined) {
          reject(
            res,
            413,
            "FILE_TOO_LARGE",
            `${oversized} Б больше лимита ${maxFileBytes} Б`,
          );
          return;
        }
        forwardBuffered(req, res, result.body, coreUrl);
      })
      .catch(() => {
        if (!res.headersSent) {
          reject(res, 400, "CORRUPTED_FILE", "тело загрузки не прочитано");
        }
      });
  });

  app.use(
    "/api/v1",
    createProxyMiddleware({
      target: coreUrl,
      changeOrigin: true,
      proxyTimeout: PROXY_TIMEOUT_MS,
      timeout: PROXY_TIMEOUT_MS,
      pathRewrite: (requestPath) =>
        requestPath.startsWith("/api/v1") ? requestPath : `/api/v1${requestPath}`,
    }),
  );

  if (fs.existsSync(webRoot)) {
    app.use(express.static(webRoot));
  }
  return app;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const app = createApp();
  app.listen(process.env.PORT ?? 3000, () => {
    log.info(
      { core: CORE_URL, MAX_FILE_BYTES, MAX_BATCH_BYTES, webRoot },
      "gateway started",
    );
  });
}
