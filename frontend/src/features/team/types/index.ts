export type TechStatus = 'available' | 'busy' | 'delayed' | 'offline';

export interface TeamMember {
  id: string;
  userId?: string; // links this FieldAgent entry back to its User.id (see backend team.py)
  fullName: string;
  avatar: string;
  role: 'technician' | 'manager';
  status: 'active' | 'inactive'; // active/inactive employment status
  // Real-time telemetry
  liveStatus: {
    status: TechStatus;
    currentJobId?: string;
    lastPing: string;       // ISO Date
    lat: number;
    lng: number;
    heading: number;        // 0-360 degrees (for car rotation)
    speed: number;          // mph
  };
}

// 📍 The Route Shape (GeoJSON)
export interface ActiveRoute {
  id?: string; // Optional ID
  techId: string;
  jobId: string;
  geometry: {
    type: 'LineString';
    coordinates: number[][]; // [[lng, lat], [lng, lat], ...]
  };
  duration: number; // estimated seconds remaining
  status: 'normal' | 'delayed'; // New field for route health
  distance: number;        // Meters remaining
}
