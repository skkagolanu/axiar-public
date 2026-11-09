import { useCallback, useEffect, useMemo } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useWebSocketStore } from '../store/websocket';
import { useAuthStore } from '@/store/useAuthStore';
import { toast } from '@/hooks/use-toast';

// "in_progress" -> "In progress" -- underscore-separated backend status values
function formatStatusLabel(status: string): string {
  const spaced = status.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { setConnected, addMessage } = useWebSocketStore();
  // Read the JWT from the persisted auth store (not raw localStorage['token'],
  // which is never set — the store persists under the 'auth-storage' key).
  const token = useAuthStore((state) => state.token);

  // Derive the ws:// origin from the API origin (VITE_API_URL), defaulting to local backend.
  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const wsBase = apiBase.replace(/^http/, 'ws');

  const wsUrl = token ? `${wsBase}/api/v1/chat/ws` : null;

  // The token travels as a WebSocket subprotocol, not a URL query param — browsers can't
  // set custom headers on a WS handshake, and Sec-WebSocket-Protocol is the standard
  // workaround (keeps the bearer token out of server access logs / browser history).
  // Memoized so an unchanged token doesn't hand useWebSocket a new array every render
  // (which would tear down and reconnect the socket for no reason).
  const protocols = useMemo(() => (token ? ['access_token', token] : undefined), [token]);

  // Stable callbacks prevent useWebSocket's effect from tearing down and opening
  // a new socket on every provider render while a handshake is still in flight.
  const handleConnect = useCallback(() => setConnected(true), [setConnected]);
  const handleDisconnect = useCallback(() => setConnected(false), [setConnected]);
  const handleMessage = useCallback((message: { type: string; [key: string]: any }) => {
    console.log('WebSocket message:', message);
    addMessage(message);

    if (message.type === 'booking_status_update') {
      toast({
        title: 'Booking status updated',
        description: `Now ${formatStatusLabel(message.new_status)} (was ${formatStatusLabel(message.old_status)})`,
      });
    }
  }, [addMessage]);

  const { send } = useWebSocket(wsUrl || '', protocols, {
    onConnect: handleConnect,
    onDisconnect: handleDisconnect,
    onMessage: handleMessage,
  });

  useEffect(() => {
    // Expose send function globally for easy access
    (window as any).wsSend = send;
  }, [send]);

  return <>{children}</>;
}
