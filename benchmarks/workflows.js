import http from 'k6/http';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const identities = new SharedArray('workflow identities', () => JSON.parse(open(__ENV.FIXTURE_PATH)));
const offered = Number(__ENV.WORKFLOWS_PER_SECOND);
const attempts = new Counter('workflow_attempts');
const completed = new Counter('completed_workflows');
const errors = new Rate('workflow_errors');
const allLatency = new Trend('workflow_duration_ms', true);
const successLatency = new Trend('successful_workflow_duration_ms', true);
const writes = new Counter('acknowledged_booking_writes');
const operationLatency = new Trend('operation_duration_ms', true);

export const options = {
  scenarios: { booking: {
    executor: 'constant-arrival-rate', rate: offered, timeUnit: '1s',
    duration: __ENV.DURATION || '30s', preAllocatedVUs: Number(__ENV.VUS || 500),
    maxVUs: Number(__ENV.VUS || 500), gracefulStop: '60s',
  } },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(50)', 'p(95)', 'p(99)'],
  thresholds: {
    workflow_errors: ['rate<0.01'], dropped_iterations: ['count==0'],
    workflow_duration_ms: ['p(99)<10'],
  },
  systemTags: ['status', 'method', 'name', 'scenario', 'expected_response', 'error_code'],
};

export default function () {
  const iteration = exec.scenario.iterationInTest;
  const who = identities[iteration % identities.length];
  const base = __ENV.API_URL;
  const start = Date.now();
  let success = false;
  attempts.add(1);
  // Cover every tenant/provider independently of the VU cap. Each provider gets
  // distinct two-hour slots, independent of how requests are distributed to VUs.
  const slot = new Date(Date.UTC(2032, 0, 1) + Math.floor(iteration / identities.length) * 2 * 3600000);
  function call(method, path, name, expected, headers, data) {
    const response = http.request(method, `${base}${path}`, data ? JSON.stringify(data) : null, {
      headers: { ...headers, 'Content-Type': 'application/json' },
      tags: { name }, timeout: '10s',
    });
    operationLatency.add(response.timings.duration, { operation: name });
    return response.status === expected ? response : null;
  }
  try {
    const listing = call('GET', '/api/v1/bookings/?limit=50', 'schedule_read', 200, who.provider_headers);
    if (!listing || listing.json().length !== 50) return;
    const created = call('POST', '/api/v1/bookings/', 'booking_create', 201, who.customer_headers, {
      provider_id: who.provider_id, service_id: who.service_id, scheduled_time: slot.toISOString(),
      duration_minutes: 60, base_price_cents: 5000, location_postcode: 'NG7 2RD',
      description: 'benchmark-extremes',
    });
    if (!created) return;
    writes.add(1);
    const bid = created.json('id');
    if (!call('PATCH', `/api/v1/bookings/${bid}/status`, 'booking_confirm', 200,
      who.provider_headers, { status: 'confirmed' })) return;
    writes.add(1);
    const found = call('GET', `/api/v1/bookings/${bid}`, 'booking_read', 200, who.customer_headers);
    if (!found || found.json('status') !== 'confirmed') return;
    if (!call('PATCH', `/api/v1/bookings/${bid}/status`, 'booking_cancel', 200,
      who.customer_headers, { status: 'cancelled' })) return;
    writes.add(1);
    success = true;
    exec.vu.metrics.metadata['booking_id'] = bid;
    exec.vu.metrics.metadata['tenant_id'] = who.tenant_id;
    exec.vu.metrics.metadata['provider_id'] = who.provider_id;
    completed.add(1);
    delete exec.vu.metrics.metadata['booking_id'];
    delete exec.vu.metrics.metadata['tenant_id'];
    delete exec.vu.metrics.metadata['provider_id'];
    successLatency.add(Date.now() - start);
  } finally {
    errors.add(!success);
    allLatency.add(Date.now() - start);
  }
}

export function handleSummary(data) {
  return { [__ENV.SUMMARY_PATH]: JSON.stringify(data, null, 2) };
}
