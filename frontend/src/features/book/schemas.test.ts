import { describe, expect, it } from 'vitest';
import { guestBookingSchema } from './schemas';

const validBooking = {
  email: 'jane@example.com',
  firstName: 'Jane',
  lastName: 'Smith',
  phone: '+44 7700 900000',
  providerId: '11111111-1111-4111-8111-111111111111',
  serviceId: '22222222-2222-4222-8222-222222222222',
  locationPostcode: 'SW1A 1AA',
  locationAddress: '10 Downing St',
  scheduledDate: new Date('2026-08-01'),
  scheduledTime: '09:00',
  description: '',
  basePriceCents: 8500,
  durationMinutes: 60,
};

describe('guestBookingSchema', () => {
  it('accepts a fully valid guest booking', () => {
    const result = guestBookingSchema.safeParse(validBooking);
    expect(result.success).toBe(true);
  });

  it('treats phone and description as optional', () => {
    const withoutOptional = {
      email: validBooking.email,
      firstName: validBooking.firstName,
      lastName: validBooking.lastName,
      providerId: validBooking.providerId,
      serviceId: validBooking.serviceId,
      locationPostcode: validBooking.locationPostcode,
      locationAddress: validBooking.locationAddress,
      scheduledDate: validBooking.scheduledDate,
      scheduledTime: validBooking.scheduledTime,
      basePriceCents: validBooking.basePriceCents,
      durationMinutes: validBooking.durationMinutes,
    };
    const result = guestBookingSchema.safeParse(withoutOptional);
    expect(result.success).toBe(true);
  });

  it('rejects a non-UUID providerId', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, providerId: 'not-a-uuid' });
    expect(result.success).toBe(false);
  });

  it('rejects a non-UUID serviceId', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, serviceId: 'not-a-uuid' });
    expect(result.success).toBe(false);
  });

  it('rejects an invalid email', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, email: 'nope' });
    expect(result.success).toBe(false);
  });

  it('rejects a postcode shorter than 5 characters', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, locationPostcode: 'SW1' });
    expect(result.success).toBe(false);
  });

  it('rejects a missing scheduledTime', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, scheduledTime: '' });
    expect(result.success).toBe(false);
  });

  it('rejects a basePriceCents below the 100-cent minimum', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, basePriceCents: 50 });
    expect(result.success).toBe(false);
  });

  it('rejects a non-integer durationMinutes', () => {
    const result = guestBookingSchema.safeParse({ ...validBooking, durationMinutes: 60.5 });
    expect(result.success).toBe(false);
  });

  it('rejects a missing scheduledDate', () => {
    const withoutDate = { ...validBooking, scheduledDate: undefined };
    const result = guestBookingSchema.safeParse(withoutDate);
    expect(result.success).toBe(false);
  });
});
