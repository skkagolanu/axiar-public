import { useState, useEffect } from 'react';
import type { TeamMember, ActiveRoute } from '../types';
import api from '@/lib/axios';

export function useTeamLocation() {
  const [technicians, setTechnicians] = useState<TeamMember[]>([]);
  const [routes, setRoutes] = useState<ActiveRoute[]>([]);

  useEffect(() => {
    const fetchTeamData = async () => {
       try {
           const teamRes = await api.get('/api/v1/team');
           setTechnicians(teamRes.data);
       } catch (err) {
           console.error("Failed to poll team data", err);
       }
    };

    const interval = setInterval(fetchTeamData, 15000);
    fetchTeamData();

    return () => clearInterval(interval);
  }, []);

  // Fetch routes once on mount
  useEffect(() => {
      const fetchRoutes = async () => {
          try {
            const teamRes = await api.get('/api/v1/team');
            const activeTechs = teamRes.data.filter((t: any) =>
               t.liveStatus?.status === 'busy' || t.liveStatus?.status === 'available'
            );
            const routePromises = activeTechs.map((t: any) =>
               api.get(`/api/v1/routes/${t.id}`).then((r: any) => r.data).catch(() => null)
            );
            const routesRes = await Promise.all(routePromises);
            setRoutes(routesRes.filter(Boolean));
          } catch (e) { console.error(e); }
      };
      fetchRoutes();
  }, []);

  return { technicians, routes };
}
