import { useEffect, useRef, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  data?: any;
  // Server messages carry different shapes per type (e.g. booking_status_update's
  // old_status/new_status/booking_id vs chat's sender_id/content) -- an index
  // signature avoids a cast at every call site instead of pretending every
  // message fits the same fixed shape.
  [key: string]: any;
}

interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  // fire for a "zombie" connection (TCP silently dead after client suspension or a
  // NAT/proxy timeout, but no close frame ever arrives) -- an application-level
  // ping/pong is the standard way to detect that and force a reconnect.
  heartbeatInterval?: number;
  heartbeatTimeout?: number;
}

export function useWebSocket(url: string, protocols: string | string[] | undefined, options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 3000,
    heartbeatInterval = 25000,
    heartbeatTimeout = 10000,
  } = options;

  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<number>(0);
  const heartbeatIntervalId = useRef<number>(0);
  const heartbeatTimeoutId = useRef<number>(0);
  const connectRef = useRef<() => void>(() => {});

  const stopHeartbeat = useCallback(() => {
    clearInterval(heartbeatIntervalId.current);
    clearTimeout(heartbeatTimeoutId.current);
  }, []);

  const startHeartbeat = useCallback(() => {
    stopHeartbeat();
    heartbeatIntervalId.current = window.setInterval(() => {
      if (ws.current?.readyState !== WebSocket.OPEN) return;
      ws.current.send(JSON.stringify({ type: 'ping' }));
      // No pong within heartbeatTimeout => treat the connection as dead and force
      // a reconnect; the existing onclose handler's reconnect logic takes it from there.
      heartbeatTimeoutId.current = window.setTimeout(() => {
        console.warn('WebSocket heartbeat timed out — forcing reconnect');
        ws.current?.close();
      }, heartbeatTimeout);
    }, heartbeatInterval);
  }, [heartbeatInterval, heartbeatTimeout, stopHeartbeat]);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;
    // No URL yet (e.g. logged out, waiting on an auth token) -- `new WebSocket('')`
    // throws immediately, which onerror/onclose would otherwise turn into an
    // infinite reconnect-every-3s loop. Skip connecting until a real url shows up;
    // the effect below re-runs connect() when the url dependency changes.
    if (!url) return;

    ws.current = protocols ? new WebSocket(url, protocols) : new WebSocket(url);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      onConnect?.();
      startHeartbeat();
    };

    ws.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'pong') {
          clearTimeout(heartbeatTimeoutId.current);
          return;
        }
        onMessage?.(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      stopHeartbeat();
      onDisconnect?.();

      // Reconnect after interval
      reconnectTimeout.current = window.setTimeout(() => {
        connectRef.current();
      }, reconnectInterval);
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }, [url, protocols, onMessage, onConnect, onDisconnect, reconnectInterval, startHeartbeat, stopHeartbeat]);

  // Keep connectRef in sync so onclose always calls the latest connect function
  useEffect(() => { connectRef.current = connect; }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }
    stopHeartbeat();
    ws.current?.close();
  }, [stopHeartbeat]);

  const send = useCallback((message: WebSocketMessage) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { send, disconnect, reconnect: connect };
}
