/**
 * Harness нагрузки: GET /api/v1/processes/:id/status.
 *
 * Цель ТЗ п. 14.4: p(95) ≤ 200 мс при 100 VU / 60 с.
 * CI k6 не запускает (нет сервера); скрипт запускается вручную:
 *   KONTUR_BASE_URL=http://localhost:8000 k6 run tests/load/k6_status.js
 *
 * thresholds: команда k6 выходит 1 если p(95) > 200 мс — единственный артефакт измерения.
 */
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 100,
  duration: '60s',
  thresholds: {
    // Порог ТЗ п. 14.4: 95-й перцентиль ответа не превышает 200 мс.
    'http_req_duration{name:status}': ['p(95)<200'],
    // Не больше 1 % HTTP-ошибок (4xx/5xx).
    'http_req_failed{name:status}': ['rate<0.01'],
  },
};

const BASE  = __ENV.KONTUR_BASE_URL || 'http://127.0.0.1:8000';
// INSPECTOR имеет getProcessStatus; формат токена — "subject/ROLE" (см. auth.py).
const TOKEN = __ENV.KONTUR_TOKEN || 'insp-7/INSPECTOR';
const HEADERS = { Authorization: `Bearer ${TOKEN}` };

const MIN_PDF = '%PDF-1.7\n1 0 obj\n<<>>\nendobj\n';

/** setup() вызывается один раз до разогрева; возвращает context для default(). */
export function setup() {
  const fd = new FormData();
  fd.append('object_id', 'load-obj-1');
  fd.append('doc_stage', 'PD');
  fd.append('files', http.file(MIN_PDF, 'pz.pdf', 'application/pdf'));

  const res = http.post(
    `${BASE}/api/v1/documents/upload`,
    fd.body(),
    { headers: { ...HEADERS, 'Content-Type': fd.contentType() } },
  );
  check(res, { 'setup upload 202': (r) => r.status === 202 });
  if (res.status !== 202) {
    throw new Error(`setup failed: status=${res.status} body=${res.body}`);
  }
  return { process_id: res.json('process_id') };
}

/** Главная функция: 100 VU делают GET /status в течение 60 с. */
export default function (data) {
  const res = http.get(
    `${BASE}/api/v1/processes/${data.process_id}/status`,
    // Метка 'status' попадает в thresholds['http_req_duration{name:status}'].
    { headers: HEADERS, tags: { name: 'status' } },
  );
  check(res, { 'status 200': (r) => r.status === 200 });
}
