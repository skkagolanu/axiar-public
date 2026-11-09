import { describe, expect, it } from 'vitest';
import { loginSchema, registerSchema } from './schemas';

describe('loginSchema', () => {
  it('accepts a valid email + non-empty password', () => {
    const result = loginSchema.safeParse({ email: 'jane@example.com', password: 'x' });
    expect(result.success).toBe(true);
  });

  it('rejects an invalid email', () => {
    const result = loginSchema.safeParse({ email: 'not-an-email', password: 'x' });
    expect(result.success).toBe(false);
  });

  it('rejects an empty password', () => {
    const result = loginSchema.safeParse({ email: 'jane@example.com', password: '' });
    expect(result.success).toBe(false);
  });

  it('treats rememberMe as optional', () => {
    const result = loginSchema.safeParse({ email: 'jane@example.com', password: 'x' });
    expect(result.success).toBe(true);
  });
});

describe('registerSchema', () => {
  const validBase = {
    fullName: 'Jane Smith',
    companyName: 'Acme Plumbing',
    email: 'jane@example.com',
  };

  it('accepts a password with a digit and a special character', () => {
    const result = registerSchema.safeParse({ ...validBase, password: 'Secret1!' });
    expect(result.success).toBe(true);
  });

  it('rejects a password shorter than 8 characters', () => {
    const result = registerSchema.safeParse({ ...validBase, password: 'S1!' });
    expect(result.success).toBe(false);
  });

  it('rejects a password with no digit', () => {
    const result = registerSchema.safeParse({ ...validBase, password: 'Secretive!' });
    expect(result.success).toBe(false);
  });

  it('rejects a password with no special character', () => {
    const result = registerSchema.safeParse({ ...validBase, password: 'Secret123' });
    expect(result.success).toBe(false);
  });

  it('rejects a full name shorter than 2 characters', () => {
    const result = registerSchema.safeParse({ ...validBase, fullName: 'J', password: 'Secret1!' });
    expect(result.success).toBe(false);
  });

  it('rejects a company name shorter than 2 characters', () => {
    const result = registerSchema.safeParse({ ...validBase, companyName: 'A', password: 'Secret1!' });
    expect(result.success).toBe(false);
  });
});
