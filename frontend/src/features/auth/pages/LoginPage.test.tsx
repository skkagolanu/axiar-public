import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from './LoginPage';

// Smoke test: proves the Vitest + jsdom + React Testing Library pipeline actually
// renders a real page (form fields, validation) — not just pure-function assertions.
describe('LoginPage', () => {
  it('renders the email and password fields', () => {
    render(<LoginPage />, { wrapper: MemoryRouter });

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in|log in/i })).toBeInTheDocument();
  });

  it('shows a validation error when submitting an invalid email', async () => {
    const user = userEvent.setup();
    render(<LoginPage />, { wrapper: MemoryRouter });

    await user.type(screen.getByLabelText(/email/i), 'not-an-email');
    await user.type(screen.getByLabelText(/password/i), 'x');
    await user.click(screen.getByRole('button', { name: /sign in|log in/i }));

    expect(await screen.findByText(/invalid email/i)).toBeInTheDocument();
  });
});
