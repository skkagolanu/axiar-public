import { z } from 'zod';

export const guestBookingSchema = z.object({
  // Contact
  email: z.string().email('Valid email required'),
  firstName: z.string().min(1, 'Required'),
  lastName: z.string().min(1, 'Required'),
  phone: z.string().optional(),
  // Service
  providerId: z.string().uuid('Please select a provider'),
  serviceId: z.string().uuid('Please select a service'),
  // Location
  locationPostcode: z.string().min(5, 'Postcode required').max(10),
  locationAddress: z.string().min(5, 'Address required'),
  // Schedule
  scheduledDate: z.date({ message: 'Date required' }),
  scheduledTime: z.string().min(1, 'Time required'),
  description: z.string().optional(),
  // Derived from service (hidden from user)
  basePriceCents: z.number().int().min(100),
  durationMinutes: z.number().int().min(15),
});

export type GuestBookingFormData = z.infer<typeof guestBookingSchema>;
