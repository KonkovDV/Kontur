/**
 * Gate L нагрузочный тест: GET /api/v1/processes/{id}/status
 *
 * Цель: 100 VU, p95 ≤ 200ms, ошибки < 1%.
 *
 * Запуск:
 *   k6 run tests/load/k6_status.js
 *   BASE_URL=http://prod:8000 k6 run tests/load/k6_status.js
 *
 * Требования в среде:
 *   - API-сервер доступен по BASE_URL
 *   - токен инспектора с ролью INSPECTOR авторизует загрузку и запрос статуса
 */
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    status_load: {
      executor: 'constant-vus',
      vus: 100,
      duration: '60s',
    },
  },
  thresholds: {
    // Gate L: p95 ≤ 200ms
    http_req_duration: ['p(95)<200'],
    // Жёсткая планка: менее 1% ошибок
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH = { Authorization: 'Bearer insp-7/INSPECTOR' };

// Минимальный ASCII-PDF для загрузки на этапе setup.
// open() вызывается в init-контексте (module level), не внутри функций.
const PDF_CONTENT = open('./fixtures/minimal.pdf', 'b');

/**
 * setup() выполняется один раз перед налью: создаёт один процесс,
 * чтобы все VU пользовались одним и тем же process_id через data.
 */
export function setup() {
  const res = http.post(
    `${BASE_URL}/api/v1/documents/upload`,
    {
      object_id: 'k6-gate-l-status-probe',
      doc_stage: 'PD',
      files: http.file(PDF_CONTENT, 'probe.pdf', 'application/pdf'),
    },
    { headers: AUTH },
  );

  if (res.status !== 202) {
    throw new Error(`setup: upload failed ${res.status}: ${res.body}`);
  }

  const body = res.json();
  if (!body.process_id) {
    throw new Error(`setup: no process_id in response: ${res.body}`);
  }
  return { process_id: body.process_id };
}

/**
 * Главная функция выполняется каждым VU непрерывно втечение duration.
 * data.process_id — результат setup().
 */
export default function (data) {
  const res = http.get(
    `${BASE_URL}/api/v1/processes/${data.process_id}/status`,
    { headers: AUTH },
  );

  check(res, {
    '200 OK': (r) => r.status === 200,
    'has process_state': (r) => r.json('process_state') !== null,
    'has counters': (r) => r.json('counters') !== null,
  });
}

// teardown не нужен: процесс остаётся в PARSING и будет собран сорщиком при следующем запуске.
