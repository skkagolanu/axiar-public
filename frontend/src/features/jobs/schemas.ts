import { z } from 'zod';

export const createJobSchema = z.object({
  providerId: z.string().uuid('Please select a provider'),
  serviceId: z.string().uuid('Please select a service'),
  locationPostcode: z.string().min(5, 'Postcode is required').max(10),
  locationAddress: z.string().min(5, 'Address is required'),
  description: z.string().optional(),
  scheduledDate: z.date({ message: 'Date is required' }),
  scheduledTime: z.string().min(1, 'Time is required'),
  // Derived from the selected service — stored in form state, not entered by user
  basePriceCents: z.number().int().min(100),
  durationMinutes: z.number().int().min(15),
});

export type CreateJobFormData = z.infer<typeof createJobSchema>;
