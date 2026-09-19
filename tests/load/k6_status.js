// Нагрузочный harness GET /status. CI k6 не запускает и p95 не публикует.
// Обязателен реально выданный JWT через KONTUR_BEARER_TOKEN; plaintext credential запрещён.
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 100,
  duration: '60s',
  thresholds: {
    'http_req_duration{name:status}': ['p(95)<200'],
    'http_req_failed{name:status}': ['rate<0.01'],
  },
};

const BASE = __ENV.KONTUR_BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = __ENV.KONTUR_BEARER_TOKEN;
if (!TOKEN) {
  throw new Error('KONTUR_BEARER_TOKEN is required');
}
const HEADERS = { Authorization: `Bearer ${TOKEN}` };
const PDF = '%PDF-1.7\n1 0 obj\n<<>>\nendobj\n';

export function setup() {
  const response = http.post(
    `${BASE}/api/v1/documents/upload`,
    {
      object_id: 'obj-load',
      doc_stage: 'PD',
      files: http.file(PDF, 'pz.pdf', 'application/pdf'),
    },
    { headers: HEADERS },
  );
  check(response, { 'upload 202': (res) => res.status === 202 });
  if (response.status !== 202) {
    throw new Error(`setup: status=${response.status} body=${response.body}`);
  }
  return { process_id: response.json('process_id') };
}

export default function (data) {
  const response = http.get(`${BASE}/api/v1/processes/${data.process_id}/status`, {
    headers: HEADERS,
    tags: { name: 'status' },
  });
  check(response, { 'status 200': (res) => res.status === 200 });
}
