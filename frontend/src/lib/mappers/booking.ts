import type { Job, JobStatus } from '@/features/jobs/types';

// Wire shape of GET /api/v1/bookings (BookingReadEnriched) — snake_case, cents, ISO UTC.
export interface BookingEnriched {
  id: string;
  customer_id: string;
  provider_id: string;
  service_id: string;
  field_agent_id: string | null;
  scheduled_time: string;
  duration_minutes: number;
  description: string | null;
  status:
    | 'pending'
    | 'confirmed'
    | 'assigned'
    | 'on_my_way'
    | 'arrived'
    | 'delayed'
    | 'in_progress'
    | 'completed'
    | 'cancelled'
    | 'no_show';
  location_postcode: string;
  location_address: string | null;
  base_price_cents: number;
  deposit_paid_cents: number;
  total_paid_cents: number;
  payment_timing: string;
  deposit_percentage: number;
  promo_code: string | null;
  discount_cents: number;
  created_at: string;
  customer_name: string | null;
  customer_phone: string | null;
  service_name: string | null;
  service_type: string | null;
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
}

// The backend lifecycle folds onto the UI's smaller status set: everything before
// actual on-site work (confirmed/assigned/on_my_way/arrived/delayed) reads as
// "scheduled"; no_show is a terminal non-completion, closest to "cancelled".
// Record<...> here is deliberate: adding a backend status without updating this map
// is a compile error, not a silent `undefined` at runtime.
const STATUS_MAP: Record<BookingEnriched['status'], JobStatus> = {
  pending: 'pending',
  confirmed: 'scheduled',
  assigned: 'scheduled',
  on_my_way: 'scheduled',
  arrived: 'scheduled',
  delayed: 'scheduled',
  in_progress: 'in_progress',
  completed: 'completed',
  cancelled: 'cancelled',
  no_show: 'cancelled',
};

// Pure, O(1): the single boundary that knows both the API dialect and the UI Job type.
export function mapBookingToJob(b: BookingEnriched): Job {
  const dt = new Date(b.scheduled_time);
  const isValidDate = !Number.isNaN(dt.getTime());
  return {
    id: b.id,
    customerName: b.customer_name ?? 'Unknown',
    customerPhone: b.customer_phone ?? '',
    address: b.location_address ?? b.location_postcode,
    serviceType: b.service_type ?? b.service_name ?? 'Service',
    description: b.description ?? '',
    status: STATUS_MAP[b.status] ?? 'pending',
    priority: 'medium', // backend has no priority concept yet; sensible default
    scheduledDate: isValidDate ? dt.toISOString() : '',
    scheduledTime: isValidDate
      ? dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : '',
    price: b.base_price_cents / 100,
    assignedTech: b.assigned_agent_id
      ? { id: b.assigned_agent_id, name: b.assigned_agent_name ?? 'Agent' }
      : undefined,
  };
}
