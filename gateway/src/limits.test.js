import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";

import {
  MAX_BATCH_BYTES,
  MAX_FILE_BYTES,
  createUploadLimiter,
  exceedsBatchLimit,
  exceedsFileLimit,
  multipartFileState,
} from "./limits.js";
import { createApp } from "./server.js";

test("defaults match the 50 MB file and 200 MB batch limits", () => {
  assert.equal(MAX_FILE_BYTES, 50 * 1024 * 1024);
  assert.equal(MAX_BATCH_BYTES, 200 * 1024 * 1024);
  assert.equal(exceedsFileLimit(MAX_FILE_BYTES), false);
  assert.equal(exceedsFileLimit(MAX_FILE_BYTES + 1), true);
  assert.equal(exceedsBatchLimit(MAX_BATCH_BYTES + 1), true);
});

test("an open file part is counted before the closing boundary", () => {
  const boundary = "kontur";
  const header = Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="big.pdf"\r\n\r\n`,
  );
  const body = Buffer.concat([header, Buffer.alloc(9, 1)]);
  const state = multipartFileState(body, boundary);
  assert.deepEqual(state.complete, []);
  assert.equal(state.open, 9);
});

test("a finished file part reports its byte length", () => {
  const boundary = "kontur";
  const body = Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="a.pdf"\r\n\r\n` +
      `abc\r\n--${boundary}--\r\n`,
  );
  const state = multipartFileState(body, boundary);
  assert.deepEqual(state.complete, [3]);
  assert.equal(state.open, 0);
});

test("upload limiter refuses the next call inside the window", () => {
  let now = 1_000;
  const allow = createUploadLimiter(2, 60_000, () => now);
  assert.equal(allow("10.0.0.8"), true);
  assert.equal(allow("10.0.0.8"), true);
  assert.equal(allow("10.0.0.8"), false);
  assert.equal(allow("10.0.0.9"), true);
  now += 60_001;
  assert.equal(allow("10.0.0.8"), true);
});

test("gateway rejects one oversized file with FILE_TOO_LARGE", async () => {
  const app = createApp({ maxFileBytes: 8, maxBatchBytes: 200 });
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const boundary = "kontur";
  const body = Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="big.pdf"\r\n\r\n` +
      `${"x".repeat(9)}\r\n--${boundary}--\r\n`,
  );
  try {
    const response = await fetch(`http://127.0.0.1:${address.port}/api/v1/documents/upload`, {
      method: "POST",
      headers: {
        "content-type": `multipart/form-data; boundary=${boundary}`,
        "content-length": String(body.length),
      },
      body,
    });
    const payload = await response.json();
    assert.equal(response.status, 413);
    assert.equal(payload.reason_code, "FILE_TOO_LARGE");
  } finally {
    server.close();
  }
});

test("gateway rejects an empty-of-quota burst with RATE_LIMITED", async () => {
  const app = createApp({ maxFileBytes: 0, uploadLimit: 1, uploadWindowMs: 60_000 });
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const boundary = "kontur";
  const body = Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="a.pdf"\r\n\r\n` +
      `a\r\n--${boundary}--\r\n`,
  );
  const send = () =>
    fetch(`http://127.0.0.1:${address.port}/api/v1/documents/upload`, {
      method: "POST",
      headers: {
        "content-type": `multipart/form-data; boundary=${boundary}`,
        "content-length": String(body.length),
      },
      body,
    });
  try {
    const first = await send();
    await first.arrayBuffer();
    const second = await send();
    const payload = await second.json();
    assert.equal(second.status, 429);
    assert.equal(payload.reason_code, "RATE_LIMITED");
  } finally {
    server.close();
  }
});
