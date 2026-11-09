import { describe, expect, it } from 'vitest';
import { mapBookingToJob, type BookingEnriched } from './booking';

// Contract with the backend's `BookingStatus` (str, Enum) in
// backend/app/domain/booking/models.py -- keep this list in sync with the enum.
// Cover every backend booking status in the UI mapping.
const ALL_BACKEND_STATUSES: BookingEnriched['status'][] = [
  'pending',
  'confirmed',
  'assigned',
  'on_my_way',
  'arrived',
  'delayed',
  'in_progress',
  'completed',
  'cancelled',
  'no_show',
];

function makeBooking(overrides: Partial<BookingEnriched> = {}): BookingEnriched {
  return {
    id: 'b-1',
    customer_id: 'c-1',
    provider_id: 'p-1',
    service_id: 's-1',
    field_agent_id: null,
    scheduled_time: '2026-08-01T09:30:00.000Z',
    duration_minutes: 60,
    description: 'Leaky tap',
    status: 'pending',
    location_postcode: 'M1 1AD',
    location_address: '123 Maple Ave',
    base_price_cents: 15000,
    deposit_paid_cents: 0,
    total_paid_cents: 0,
    payment_timing: 'before_service',
    deposit_percentage: 0,
    promo_code: null,
    discount_cents: 0,
    created_at: '2026-07-01T00:00:00.000Z',
    customer_name: 'Alice Springs',
    customer_phone: '555-0101',
    service_name: 'Plumbing',
    service_type: 'Plumbing',
    assigned_agent_id: null,
    assigned_agent_name: null,
    ...overrides,
  };
}

describe('mapBookingToJob', () => {
  it('converts cents to pounds', () => {
    const job = mapBookingToJob(makeBooking({ base_price_cents: 15000 }));
    expect(job.price).toBe(150);
  });

  it('falls back to postcode when address is missing', () => {
    const job = mapBookingToJob(makeBooking({ location_address: null }));
    expect(job.address).toBe('M1 1AD');
  });

  it('falls back to "Unknown" customer name when null', () => {
    const job = mapBookingToJob(makeBooking({ customer_name: null }));
    expect(job.customerName).toBe('Unknown');
  });

  it.each([
    ['pending', 'pending'],
    ['confirmed', 'scheduled'],
    ['assigned', 'scheduled'],
    ['on_my_way', 'scheduled'],
    ['arrived', 'scheduled'],
    ['delayed', 'scheduled'],
    ['in_progress', 'in_progress'],
    ['completed', 'completed'],
    ['cancelled', 'cancelled'],
    ['no_show', 'cancelled'],
  ] as const)('folds backend status "%s" to UI status "%s"', (backendStatus, uiStatus) => {
    const job = mapBookingToJob(makeBooking({ status: backendStatus }));
    expect(job.status).toBe(uiStatus);
  });

  it('maps every known backend status to a defined, non-empty UI status', () => {
    for (const status of ALL_BACKEND_STATUSES) {
      const job = mapBookingToJob(makeBooking({ status }));
      expect(job.status, `status "${status}" mapped to an empty/undefined UI status`).toBeTruthy();
    }
  });

  it('leaves assignedTech undefined when no agent is assigned', () => {
    const job = mapBookingToJob(makeBooking({ assigned_agent_id: null }));
    expect(job.assignedTech).toBeUndefined();
  });

  it('maps the assigned agent id and name', () => {
    const job = mapBookingToJob(
      makeBooking({ assigned_agent_id: 'agent-9', assigned_agent_name: 'Mario' })
    );
    expect(job.assignedTech).toEqual({ id: 'agent-9', name: 'Mario' });
  });

  it('defaults the assigned agent name to "Agent" when missing', () => {
    const job = mapBookingToJob(
      makeBooking({ assigned_agent_id: 'agent-9', assigned_agent_name: null })
    );
    expect(job.assignedTech).toEqual({ id: 'agent-9', name: 'Agent' });
  });

  it('prefers service_type over service_name', () => {
    const job = mapBookingToJob(makeBooking({ service_type: 'HVAC', service_name: 'HVAC Service' }));
    expect(job.serviceType).toBe('HVAC');
  });

  it('falls back to service_name then a default when service_type is missing', () => {
    const job = mapBookingToJob(makeBooking({ service_type: null, service_name: 'HVAC Service' }));
    expect(job.serviceType).toBe('HVAC Service');

    const jobNoService = mapBookingToJob(makeBooking({ service_type: null, service_name: null }));
    expect(jobNoService.serviceType).toBe('Service');
  });

  it('produces empty scheduledDate/scheduledTime for an invalid date rather than throwing', () => {
    const job = mapBookingToJob(makeBooking({ scheduled_time: 'not-a-date' }));
    expect(job.scheduledDate).toBe('');
    expect(job.scheduledTime).toBe('');
  });
});
