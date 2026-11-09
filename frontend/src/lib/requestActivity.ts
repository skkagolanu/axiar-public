import { useSyncExternalStore } from 'react';

let activeRequests = 0;
const listeners = new Set<() => void>();

function emitChange() {
  listeners.forEach((listener) => listener());
}

export function beginRequest() {
  activeRequests += 1;
  emitChange();
}

export function endRequest() {
  activeRequests = Math.max(0, activeRequests - 1);
  emitChange();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return activeRequests > 0;
}

export function useRequestActivity() {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
