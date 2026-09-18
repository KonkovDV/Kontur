// Нагрузочный harness GET /status. CI k6 не запускает.
// Порог p95 ≤200 мс — цель ТЗ, не измеренный результат этого скрипта.
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 1,
  duration: '5s',
};

const BASE = __ENV.KONTUR_BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = __ENV.KONTUR_TOKEN || 'insp-7/INSPECTOR';
const PDF = '%PDF-1.7\n1 0 obj\n<<>>\nendobj\n';

export function setup() {
  const response = http.post(
    `${BASE}/api/v1/documents/upload`,
    {
      object_id: 'obj-load',
      doc_stage: 'PD',
      files: http.file(PDF, 'pz.pdf', 'application/pdf'),
    },
    { headers: { Authorization: `Bearer ${TOKEN}` } },
  );
  check(response, { 'upload 202': (res) => res.status === 202 });
  return { process_id: response.json('process_id') };
}

export default function (data) {
  const response = http.get(`${BASE}/api/v1/processes/${data.process_id}/status`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  check(response, { 'status 200': (res) => res.status === 200 });
}
