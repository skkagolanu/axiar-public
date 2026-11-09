import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// `globals: true` is intentionally off (see vite.config.ts), so React Testing Library's
// auto-cleanup — which hooks into a global `afterEach` — never registers on its own.
// Unmount after every test or renders from prior tests leak into the next one's DOM.
afterEach(() => {
  cleanup();
});

// jsdom doesn't implement ResizeObserver; several Radix UI primitives (e.g. Checkbox,
// Select) call it during layout effects and throw a ReferenceError without this stub.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver);
