import http from 'k6/http';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';
import exec from 'k6/execution';

// Each arrival makes exactly ONE request. Per-VU state carries the authenticated
// customer/provider workflow across arrivals, so iterations/sec means HTTP RPS.
const identities = new SharedArray('synthetic identities', () => JSON.parse(open(__ENV.FIXTURE_PATH)));
const offered = Number(__ENV.OFFERED_RPS);
const errorRate = new Rate('unexpected_errors');
const reads = new Trend('read_latency_ms', true);
const writes = new Trend('booking_write_latency_ms', true);
const workflowLatency = new Trend('workflow_latency_ms', true);
const completed = new Counter('completed_workflows');
const aborted = new Counter('aborted_workflows');
let phase = 0;
let bookingId = null;
let cycle = 0;
let workflowStarted = 0;

export const options = {
  scenarios: {
    mixed_workflow: {
      executor: 'constant-arrival-rate', rate: offered, timeUnit: '1s',
      duration: __ENV.DURATION || '10m', preAllocatedVUs: offered >= 500 ? 500 : 32,
      maxVUs: offered >= 500 ? 500 : 32, gracefulStop: '15s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(50)', 'p(95)', 'p(99)'],
  thresholds: {
    unexpected_errors: ['rate<0.01'],
    read_latency_ms: ['p(95)<300'],
    booking_write_latency_ms: ['p(95)<750', 'p(99)<1500'],
    dropped_iterations: ['count==0'],
  },
  systemTags: ['status', 'method', 'name', 'scenario', 'expected_response', 'error_code'],
};

export default function () {
  const who = identities[(exec.vu.idInTest - 1) % identities.length];
  const base = __ENV.API_URL;
  let response;
  let expected = 200;
  let name;
  let headers = who.customer_headers;
  if (phase === 0) {
    workflowStarted = Date.now();
    name = 'schedule_read';
    response = http.get(`${base}/api/v1/bookings/?limit=50`, {
      headers: who.provider_headers, tags: { name }, timeout: '10s',
    });
  } else if (phase === 1) {
    cycle += 1;
    name = 'booking_create';
    expected = 201;
    // Every VU owns one provider at these profiles. Cycle spacing is two hours;
    // the VU term also keeps slots distinct if the configured VU limit grows.
    const slot = new Date(Date.UTC(2032, 0, 1) + ((exec.vu.idInTest - 1) * 5000 + cycle * 2) * 3600000);
    response = http.post(`${base}/api/v1/bookings/`, JSON.stringify({
      provider_id: who.provider_id, service_id: who.service_id, scheduled_time: slot.toISOString(),
      duration_minutes: 60, base_price_cents: 5000, location_postcode: 'NG7 2RD',
      description: 'benchmark-extremes',
    }), { headers: { ...headers, 'Content-Type': 'application/json' }, tags: { name }, timeout: '10s' });
    if (response.status === 201) bookingId = response.json('id');
  } else if (phase === 2 || phase === 4) {
    name = phase === 2 ? 'booking_confirm' : 'booking_cancel';
    headers = phase === 2 ? who.provider_headers : who.customer_headers;
    response = http.patch(`${base}/api/v1/bookings/${bookingId}/status`,
      JSON.stringify({ status: phase === 2 ? 'confirmed' : 'cancelled' }),
      { headers: { ...headers, 'Content-Type': 'application/json' }, tags: { name }, timeout: '10s' });
  } else {
    name = 'booking_read';
    response = http.get(`${base}/api/v1/bookings/${bookingId}`, { headers, tags: { name }, timeout: '10s' });
  }
  let success = response.status === expected;
  if (success && phase === 3) success = response.json('status') === 'confirmed';
  errorRate.add(!success, { operation: name });
  if (phase === 0 || phase === 3) reads.add(response.timings.duration, { operation: name });
  else writes.add(response.timings.duration, { operation: name });
  if (!success) {
    aborted.add(1);
    phase = 0;
    bookingId = null;
    return;
  }
  phase += 1;
  if (phase === 5) {
    completed.add(1);
    workflowLatency.add(Date.now() - workflowStarted);
    phase = 0;
    bookingId = null;
  }
}

export function handleSummary(data) {
  return { [__ENV.SUMMARY_PATH]: JSON.stringify(data, null, 2) };
}
