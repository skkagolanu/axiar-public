import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { StatsCards } from '../components/StatsCards';
import type { DashboardStats, ActivityLog } from '../types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activity, setActivity] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [statsRes, activityRes] = await Promise.all([
          api.get('/api/v1/dashboard/stats'),
          api.get('/api/v1/dashboard/activity'),
        ]);
        
        // Defensive check: Ensure we have a valid object response
        if (statsRes.data && typeof statsRes.data === 'object') {
             setStats(statsRes.data);
        } else {
             console.error("Invalid stats response:", statsRes.data);
        }

        setActivity(Array.isArray(activityRes.data) ? activityRes.data : []);
      } catch (error) {
        console.error('Failed to fetch dashboard data', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 space-y-4 pt-6">
        <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight font-heading text-slate-900">Dashboard</h2>
      </div>

      {stats && <StatsCards stats={stats} />}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle className="font-heading">Revenue Overview</CardTitle>
          </CardHeader>
          <CardContent className="pl-2">
             <div className="h-[200px] flex items-center justify-center text-slate-400 text-sm">
                Chart Placeholder (Recharts coming soon)
             </div>
          </CardContent>
        </Card>
        
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle className="font-heading">Recent Activity</CardTitle>
            <CardDescription>
              You have {activity.length} new events today.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
                {Array.isArray(activity) && activity.map((item) => (
                    <div key={item.id} className="flex items-center">
                        <div className="ml-4 space-y-1">
                            <p className="text-sm font-medium leading-none text-slate-800">{item.message}</p>
                            <p className="text-xs text-muted-foreground">{new Date(item.timestamp).toLocaleTimeString()}</p>
                        </div>
                         {item.priority === 'high' && (
                            <div className="ml-auto font-medium text-red-500 text-xs">High</div>
                         )}
                    </div>
                ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
