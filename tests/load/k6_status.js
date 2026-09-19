// Gate L: live GET /status load after a real upload/pipeline setup.
// 100 concurrent inspectors poll once per second for 60 seconds.
// A runner-issued JWT is required; plaintext and legacy credentials are forbidden.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const statusRequests = new Counter('kontur_status_requests');

export const options = {
  vus: 100,
  duration: '60s',
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    'http_req_duration{name:status}': ['p(95)<200'],
    'http_req_failed{name:status}': ['rate<0.01'],
    kontur_status_requests: ['count>0'],
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
    { headers: HEADERS, tags: { name: 'setup-upload' } },
  );
  check(response, { 'upload 202': (res) => res.status === 202 });
  if (response.status !== 202) {
    throw new Error(`setup: status=${response.status}`);
  }
  return { process_id: response.json('process_id') };
}

export default function (data) {
  const response = http.get(`${BASE}/api/v1/processes/${data.process_id}/status`, {
    headers: HEADERS,
    tags: { name: 'status' },
  });
  statusRequests.add(1);
  check(response, { 'status 200': (res) => res.status === 200 });
  sleep(1);
}

export function handleSummary(data) {
  const path = __ENV.KONTUR_SUMMARY_PATH || '/work/out/k6-summary.json';
  return { [path]: `${JSON.stringify(data)}\n` };
}
