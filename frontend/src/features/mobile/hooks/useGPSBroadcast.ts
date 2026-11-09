import { useEffect, useRef } from 'react';

/**
 * Broadcasts the device's real GPS position to the backend while `isWorking` is true.
 * `agentId` must be the field agent's own FieldAgent.id (not User.id) — see
 * FieldLayout.tsx for how that's resolved from the logged-in user.
 */
export function useGPSBroadcast(agentId: string | null, isWorking: boolean) {
  const watchIdRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!isWorking || !agentId) {
      return;
    }

    if (!('geolocation' in navigator)) {
      console.warn('Geolocation is not available in this browser — GPS broadcast disabled.');
      return;
    }

    const sendPosition = (position: GeolocationPosition) => {
      const payload = {
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        heading: position.coords.heading ?? 0,
        status: 'busy',
      };

      fetch(`/api/v1/team/${agentId}/location`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(console.error);
    };

    const handleError = (error: GeolocationPositionError) => {
      console.error('GPS broadcast: geolocation error', error.message);
    };

    watchIdRef.current = navigator.geolocation.watchPosition(sendPosition, handleError, {
      enableHighAccuracy: true,
      maximumAge: 5000,
      timeout: 10000,
    });

    return () => {
      if (watchIdRef.current !== undefined) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, [agentId, isWorking]);
}
