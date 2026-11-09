import { test, expect, request as playwrightRequest, type APIRequestContext } from '@playwright/test';
import { Client } from 'pg';
import jwt from 'jsonwebtoken';
import { installStripeMock } from './support/mock-stripe';

/**
 * Guest booking, payment and review integration flow.
 * The UI uses a Stripe mock. Fixture setup marks the booking completed in the
 * database before the review API call, authenticated with a test-signed JWT.
 * Provider and service fixtures are created through the public API.
 */

const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';
const DATABASE_URL =
  process.env.E2E_DATABASE_URL || 'postgresql://axiar:password@localhost:5432/axiar_test';
const JWT_SECRET = process.env.E2E_JWT_SECRET || 'e2e-test-secret-key-minimum-32-characters-long';
const DEMO_E2E = process.env.E2E_DEMO_MODE === 'true';
const demoTenantHeaders = DEMO_E2E ? { 'X-Tenant-Slug': 'demo' } : {};

function uniqueSuffix(): string {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

async function seedProviderAndService(api: APIRequestContext) {
  const suffix = uniqueSuffix();
  const providerEmail = `e2e_provider_${suffix}@example.com`;
  const password = 'E2ETestPass123';

  const registerRes = await api.post(`${API_BASE}/api/v1/auth/register`, {
    headers: demoTenantHeaders,
    data: {
      email: providerEmail,
      password,
      first_name: 'E2E',
      last_name: 'Provider',
      role: 'provider',
    },
  });
  expect(registerRes.ok(), await registerRes.text()).toBeTruthy();

  const loginRes = await api.post(`${API_BASE}/api/v1/auth/login`, {
    headers: demoTenantHeaders,
    form: { username: providerEmail, password },
  });
  expect(loginRes.ok(), await loginRes.text()).toBeTruthy();
  const { access_token: providerToken } = await loginRes.json();
  const authHeaders = { Authorization: `Bearer ${providerToken}`, ...demoTenantHeaders };

  const providerRes = await api.post(`${API_BASE}/api/v1/providers/`, {
    headers: authHeaders,
    data: { business_name: `E2E Test Co ${suffix}` },
  });
  expect(providerRes.ok(), await providerRes.text()).toBeTruthy();
  const provider = await providerRes.json();

  const serviceRes = await api.post(`${API_BASE}/api/v1/providers/${provider.id}/services`, {
    headers: authHeaders,
    data: {
      name: `E2E Cleaning ${suffix}`,
      service_type: 'cleaning',
      base_price_cents: 5000,
      duration_minutes: 60,
    },
  });
  expect(serviceRes.ok(), await serviceRes.text()).toBeTruthy();
  const service = await serviceRes.json();

  return { provider, service, guestEmail: `e2e_guest_${suffix}@example.com` };
}

test.describe('Guest booking happy path', () => {
  test('guest can book, pay (mocked Stripe), and the booking becomes reviewable', async ({ page }) => {
    const api = await playwrightRequest.newContext();
    const { provider, service, guestEmail } = await seedProviderAndService(api);

    // Diagnostic: surface real browser console/page errors directly in the CI log --
    // the first two CI runs failed on "element was detached from the DOM, retrying"
    // for 30s straight with no indication of *why* the page kept re-rendering.
    page.on('console', (msg) => console.log(`[browser:${msg.type()}] ${msg.text()}`));
    page.on('pageerror', (err) => console.log(`[browser:pageerror] ${err.message}`));

    if (!DEMO_E2E) await installStripeMock(page);

    await page.goto('/book');

    // Step 0 -- provider & service
    await page.getByRole('combobox').first().click();
    await page.getByRole('option', { name: new RegExp(provider.business_name) }).click();
    // Selecting the provider triggers a service fetch; the service dropdown becomes
    // enabled once that resolves.
    await expect(page.getByRole('combobox').nth(1)).toBeEnabled();
    await page.getByRole('combobox').nth(1).click();
    await page.getByRole('option', { name: new RegExp(service.name) }).click();
    await page.getByRole('button', { name: 'Next', exact: true }).click();

    // Step 1 -- contact details
    await page.getByLabel(/first name/i).fill('Ada');
    await page.getByLabel(/last name/i).fill('Guest');
    await page.getByLabel(/^email$/i).fill(guestEmail);
    await page.getByRole('button', { name: 'Next', exact: true }).click();

    // Step 2 -- location & time
    await page.getByLabel(/postcode/i).fill('SW1A 1AA');
    await page.getByLabel(/^address$/i).fill('10 Downing St');
    // The date-picker trigger is targeted by test-id, not accessible name: shadcn's
    // FormLabel sets htmlFor={formItemId} and FormControl puts that id on this button,
    // so its accessible name is the field label "Date", not its visible "Pick a date"
    // content (accname: an explicit label wins over content). Advance to next month so
    // any day chosen is strictly in the future -- BookingCreate rejects a scheduled_time
    // that isn't > now, and "today at 14:00" would 422 whenever CI runs past 14:00 UTC.
    await page.getByTestId('book-date-trigger').click();
    await page.getByRole('button', { name: /go to the next month/i }).click();
    // react-day-picker v9 day buttons are accessible-named by full date (PPPP), e.g.
    // "Wednesday, August 15th, 2026" -- the "15th" ordinal is unique within a month.
    await page.getByRole('button', { name: /15th/i }).click();
    // The Popover isn't wired to auto-close on select; dismiss it so the calendar
    // overlay can't intercept clicks on the Time field / Next button below it.
    await page.keyboard.press('Escape');
    await page.getByLabel(/^time$/i).fill('14:00');
    await page.getByRole('button', { name: 'Next', exact: true }).click();

    // Step 3 -- payment (fake CardElement from the Stripe mock)
    if (DEMO_E2E) {
      await expect(page.getByText(/no real payment is taken/i)).toBeVisible();
    } else {
      await expect(page.getByTestId('fake-card-element')).toBeVisible();
    }
    const payButton = page.getByRole('button', { name: /confirm & pay/i });
    await expect(payButton).toBeEnabled();
    await payButton.dispatchEvent('click');

    await expect(page).toHaveURL(/\/book\/success/);

    // Status transitions + review: no customer-facing UI for either yet, so verify
    // through the real API. Jump the booking straight to COMPLETED (documented
    // shortcut above) rather than walking every intermediate provider/field-agent
    // transition, which is already covered by backend tests.
    const db = new Client({ connectionString: DATABASE_URL });
    await db.connect();
    let bookingId: string;
    let customerId: string;
    try {
      const result = await db.query(
        `SELECT b.id, b.customer_id FROM bookings b
         JOIN users u ON u.id = b.customer_id
         WHERE u.email = $1 ORDER BY b.created_at DESC LIMIT 1`,
        [guestEmail]
      );
      expect(result.rows.length, 'booking row for the guest email').toBe(1);
      bookingId = result.rows[0].id;
      customerId = result.rows[0].customer_id;
      await db.query(`UPDATE bookings SET status = 'COMPLETED' WHERE id = $1`, [bookingId]);
    } finally {
      await db.end();
    }

    const guestJwt = jwt.sign(
      { sub: customerId, type: 'access' },
      JWT_SECRET,
      { algorithm: 'HS256', expiresIn: '10m' }
    );

    const reviewRes = await api.post(`${API_BASE}/api/v1/reviews/`, {
      headers: { Authorization: `Bearer ${guestJwt}`, ...demoTenantHeaders },
      data: { booking_id: bookingId, rating: 5, comment: 'Great service, would book again (E2E test).' },
    });
    expect(reviewRes.ok(), await reviewRes.text()).toBeTruthy();
    const review = await reviewRes.json();
    expect(review.rating).toBe(5);
    expect(review.booking_id).toBe(bookingId);

    await api.dispose();
  });
});
