export type JobStatus = 'pending' | 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
export type JobPriority = 'low' | 'medium' | 'high';

export interface Job {
  id: string;
  customerName: string;
  customerPhone: string;
  address: string;
  serviceType: string; // e.g., "Plumbing", "HVAC"
  description: string;
  status: JobStatus;
  priority: JobPriority;
  scheduledDate: string; // ISO Date
  scheduledTime: string; // HH:MM
  assignedTech?: {
    id: string;
    name: string;
    avatar?: string;
  };
  price?: number;
}
