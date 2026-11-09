export interface TeamMember {
  id: string;
  name?: string;        // Legacy, may be undefined
  fullName: string;     // Preferred
  avatar: string;
  skills?: string[];    // e.g., ['Plumbing']
  status: 'active' | 'offline' | 'busy';
}

export interface ScheduleEvent {
  id: string;        // Links to Job ID
  resourceId: string; // Links to TeamMember ID
  startTime: string; // ISO String
  endTime: string;   // ISO String
  title: string;
  status: 'scheduled' | 'in_progress' | 'completed';
  type: string; // Service type for color coding if needed
}
