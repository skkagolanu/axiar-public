export interface RevenuePoint {
  date: string;  // "Mon", "Tue" or ISO date
  amount: number;
}

export interface TechPerformance {
  name: string;
  completed: number;
  delayed: number;
}
