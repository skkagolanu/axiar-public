import type { TeamMember } from '../features/team/types';

// 1. Initial State (The "Seed" Data)
export const MOCK_DB = {
  team: [
    {
      id: 't1',
      userId: '1',
      fullName: 'Mario',
      avatar: 'https://ui-avatars.com/api/?name=Mario&background=ef4444&color=fff', 
      role: 'technician',
      status: 'active',
      liveStatus: {
          status: 'busy',
          currentJobId: 'JOB-101',
          lastPing: new Date().toISOString(),
          lat: 51.5010,
          lng: -0.1416,
          heading: 45,
          speed: 25
      }
    },
    { 
      id: 't2', 
      fullName: 'Luigi', 
      avatar: 'https://ui-avatars.com/api/?name=Luigi&background=22c55e&color=fff', 
      role: 'technician',
      skills: ['HVAC'], 
      status: 'active',
      liveStatus: {
          status: 'available',
          lastPing: new Date().toISOString(),
          lat: 51.5034,
          lng: -0.1276,
          heading: 180,
          speed: 0
      }
    },
    { 
      id: 't3', 
      fullName: 'Wario', 
      avatar: 'https://ui-avatars.com/api/?name=Wario&background=eab308&color=fff', 
      role: 'technician',
      skills: ['Electrical'], 
      status: 'busy',
      liveStatus: {
          status: 'delayed', // <--- ALERT STATE
          currentJobId: 'JOB-103',
          lastPing: new Date(Date.now() - 1000 * 60 * 10).toISOString(), // 10m ago
          lat: 51.5202,
          lng: -0.0977,
          heading: 90,
          speed: 5
      }
    },
    { 
      id: 't4', 
      fullName: 'Peach', 
      avatar: 'https://ui-avatars.com/api/?name=Peach&background=ec4899&color=fff', 
      role: 'manager',
      skills: ['Management'], 
      status: 'offline',
      liveStatus: {
          status: 'offline',
          lastPing: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
          lat: 51.5136,
          lng: -0.0889,
          heading: 0,
          speed: 0
      }
    },
  ] as TeamMember[]
};

// 2. Helper to update the DB (Simulates a Database Write)
export const updateTechLocation = (id: string, updates: Partial<TeamMember['liveStatus']>) => {
  const tech = MOCK_DB.team.find(t => t.id === id);
  if (tech) {
    // Merge nested liveStatus object
    tech.liveStatus = { 
        ...tech.liveStatus, 
        ...updates, 
        lastPing: new Date().toISOString() 
    };
  }
};
