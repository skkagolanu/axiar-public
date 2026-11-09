export interface DashboardStats {
  revenue: {
    total: number;
    trend: number; // Percentage (e.g., +12.5)
    trendDirection: 'up' | 'down';
  };
  jobs: {
    today: number;
    inProgress: number;
    pending: number;
  };
  team: {
    active: number;
    total: number;
  };
}

export interface ActivityLog {
  id: string;
  type: 'job_created' | 'job_completed' | 'alert' | 'payment';
  message: string;
  timestamp: string; // ISO Date
  priority: 'low' | 'medium' | 'high';
}
