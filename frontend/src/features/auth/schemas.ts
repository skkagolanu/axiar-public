import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1, "Password is required"),
  rememberMe: z.boolean().optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  fullName: z.string().min(2, "Name is required"),
  companyName: z.string().min(2, "Company name is required"),
  email: z.string().email(),
  password: z.string().min(8, "Password must be at least 8 characters")
    .regex(/[0-9]/, "Must contain at least one number")
    .regex(/[^a-zA-Z0-9]/, "Must contain at least one special character"),
});

export type RegisterFormData = z.infer<typeof registerSchema>;
