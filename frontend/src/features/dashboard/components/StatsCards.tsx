import { ArrowUpRight, ArrowDownRight, PoundSterling, Briefcase, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DashboardStats } from '../types';

interface StatsCardsProps {
  stats: DashboardStats;
}

export function StatsCards({ stats }: StatsCardsProps) {
  if (!stats || !stats.revenue || !stats.jobs) {
      return null; // or loading state, or error message
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* Revenue Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium font-heading">Total Revenue</CardTitle>
          <PoundSterling className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold font-heading text-primary">£{stats.revenue.total?.toLocaleString() ?? "0"}</div>
          <p className="text-xs text-muted-foreground flex items-center mt-1">
            {stats.revenue.trendDirection === 'up' ? (
              <ArrowUpRight className="mr-1 h-4 w-4 text-green-500" />
            ) : (
              <ArrowDownRight className="mr-1 h-4 w-4 text-red-500" />
            )}
            <span className={stats.revenue.trendDirection === 'up' ? 'text-green-500' : 'text-red-500'}>
              {stats.revenue.trend}%
            </span>
            <span className="ml-1">from last month</span>
          </p>
        </CardContent>
      </Card>

      {/* Jobs Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium font-heading">Jobs Today</CardTitle>
          <Briefcase className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold font-heading">{stats.jobs.today}</div>
          <p className="text-xs text-muted-foreground mt-1">
            {stats.jobs.inProgress} in progress, {stats.jobs.pending} pending
          </p>
        </CardContent>
      </Card>

      {/* Team Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium font-heading">Team</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold font-heading text-slate-900">{stats.team?.active ?? 0}</div>
          <p className="text-xs text-muted-foreground mt-1">
            active of {stats.team?.total ?? 0} total
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
