import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Button } from './button';
import { RequestActivityIndicator } from './loading-state';
import { beginRequest, endRequest } from '@/lib/requestActivity';

describe('loading feedback', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('disables a pending button and exposes its state', () => {
    render(
      <Button loading loadingText="Saving…">
        Save
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Saving…' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('shows delayed global feedback for an active request', () => {
    vi.useFakeTimers();
    render(<RequestActivityIndicator />);

    act(() => beginRequest());
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(180));
    expect(screen.getByText('Loading…')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(2500));
    expect(screen.getByText(/live demo is waking up/i)).toBeInTheDocument();

    act(() => endRequest());
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
});
