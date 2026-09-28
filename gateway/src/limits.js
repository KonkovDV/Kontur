// Лимиты входа. Шлюз не пишет finding_status и не заменяет проверку ядра.

export const MAX_FILE_BYTES = 50 * 1024 * 1024;
export const MAX_BATCH_BYTES = 200 * 1024 * 1024;
export const UPLOAD_LIMIT = 30;
export const UPLOAD_WINDOW_MS = 60_000;

export function exceedsFileLimit(size, maxFileBytes = MAX_FILE_BYTES) {
  return size > maxFileBytes;
}

export function exceedsBatchLimit(size, maxBatchBytes = MAX_BATCH_BYTES) {
  return size > maxBatchBytes;
}

export function multipartFileState(body, boundary) {
  const marker = Buffer.from(`--${boundary}`);
  const indexes = [];
  let from = 0;
  while (from < body.length) {
    const at = body.indexOf(marker, from);
    if (at < 0) break;
    indexes.push(at);
    from = at + marker.length;
  }
  const complete = [];
  for (let i = 0; i < indexes.length - 1; i += 1) {
    const size = partFileSize(body.subarray(indexes[i] + marker.length, indexes[i + 1]), false);
    if (size !== null) complete.push(size);
  }
  let open = 0;
  if (indexes.length > 0) {
    const tail = body.subarray(indexes[indexes.length - 1] + marker.length);
    const size = partFileSize(tail, true);
    if (size !== null) open = size;
  }
  return { complete, open };
}

function partFileSize(slice, unfinished) {
  let data = slice;
  if (data.length >= 2 && data[0] === 45 && data[1] === 45) return null;
  if (data.length >= 2 && data[0] === 13 && data[1] === 10) data = data.subarray(2);
  if (
    !unfinished &&
    data.length >= 2 &&
    data[data.length - 2] === 13 &&
    data[data.length - 1] === 10
  ) {
    data = data.subarray(0, data.length - 2);
  }
  const headerEnd = data.indexOf("\r\n\r\n");
  if (headerEnd < 0) return unfinished ? 0 : null;
  const headers = data.subarray(0, headerEnd).toString("latin1");
  if (!/filename=/i.test(headers)) return null;
  return data.length - headerEnd - 4;
}

export function createUploadLimiter(limit, windowMs, now = Date.now) {
  const hits = new Map();
  return (key) => {
    const time = now();
    const kept = (hits.get(key) ?? []).filter((stamp) => time - stamp < windowMs);
    if (kept.length >= limit) {
      hits.set(key, kept);
      return false;
    }
    kept.push(time);
    hits.set(key, kept);
    return true;
  };
}
