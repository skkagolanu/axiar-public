import { describe, expect, it, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

// jsdom doesn't implement real WebSocket networking; stub the constructor so we
// can assert what useWebSocket actually passes it (the auth
// token must travel as a subprotocol, never in the URL).
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState = FakeWebSocket.CONNECTING;
  url: string;
  protocols?: string | string[];
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {}
}

describe('useWebSocket', () => {
  afterEach(() => {
    FakeWebSocket.instances = [];
    vi.unstubAllGlobals();
  });

  it('constructs WebSocket with the given subprotocols (token kept out of the URL)', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() => useWebSocket('ws://localhost/api/v1/chat/ws', ['access_token', 'jwt-abc']));

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toBe('ws://localhost/api/v1/chat/ws');
    expect(FakeWebSocket.instances[0].url).not.toContain('token=');
    expect(FakeWebSocket.instances[0].protocols).toEqual(['access_token', 'jwt-abc']);
  });

  it('does not construct a WebSocket when the url is empty (e.g. logged out)', () => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() => useWebSocket('', undefined));

    expect(FakeWebSocket.instances).toHaveLength(0);

    // Also confirm it doesn't spin up a reconnect loop against no URL.
    vi.advanceTimersByTime(10000);
    expect(FakeWebSocket.instances).toHaveLength(0);

    vi.useRealTimers();
  });

  it('constructs WebSocket with no protocols argument when none are given', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() => useWebSocket('ws://localhost/api/v1/chat/ws', undefined));

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].protocols).toBeUndefined();
  });

  it('sends a heartbeat ping on the configured interval once connected', () => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() =>
      useWebSocket('ws://localhost/api/v1/chat/ws', undefined, { heartbeatInterval: 1000, heartbeatTimeout: 500 })
    );

    const socket = FakeWebSocket.instances[0];
    socket.readyState = FakeWebSocket.OPEN;
    socket.onopen?.();

    vi.advanceTimersByTime(1000);

    expect(socket.sent).toEqual([JSON.stringify({ type: 'ping' })]);

    vi.useRealTimers();
  });

  it('forces a reconnect if no pong arrives within the heartbeat timeout', () => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() =>
      useWebSocket('ws://localhost/api/v1/chat/ws', undefined, { heartbeatInterval: 1000, heartbeatTimeout: 500 })
    );

    const socket = FakeWebSocket.instances[0];
    socket.readyState = FakeWebSocket.OPEN;
    socket.onopen?.();
    const closeSpy = vi.spyOn(socket, 'close');

    vi.advanceTimersByTime(1000); // ping sent
    vi.advanceTimersByTime(500); // no pong arrives before the timeout

    expect(closeSpy).toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('clears the heartbeat timeout when a pong is received', () => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);

    renderHook(() =>
      useWebSocket('ws://localhost/api/v1/chat/ws', undefined, { heartbeatInterval: 1000, heartbeatTimeout: 500 })
    );

    const socket = FakeWebSocket.instances[0];
    socket.readyState = FakeWebSocket.OPEN;
    socket.onopen?.();
    const closeSpy = vi.spyOn(socket, 'close');

    vi.advanceTimersByTime(1000); // ping sent
    socket.onmessage?.({ data: JSON.stringify({ type: 'pong' }) } as MessageEvent);
    vi.advanceTimersByTime(500); // timeout would have fired here if not cleared

    expect(closeSpy).not.toHaveBeenCalled();

    vi.useRealTimers();
  });
});
