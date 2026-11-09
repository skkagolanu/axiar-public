import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { RevenueChart } from '../components/RevenueChart';
import { TechPerformanceChart } from '../components/TechPerformanceChart';
import type { RevenuePoint, TechPerformance } from '../types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { DollarSign, TrendingUp, Users } from 'lucide-react';

export default function ReportsPage() {
  const [revenueData, setRevenueData] = useState<RevenuePoint[]>([]);
  const [techData, setTechData] = useState<TechPerformance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
        try {
            const [revRes, techRes] = await Promise.all([
                api.get('/api/v1/reports/revenue'),
                api.get('/api/v1/reports/tech-performance')
            ]);
            // Format ISO dates to "Jun 1" style for chart labels
            const formatted = revRes.data.map((p: RevenuePoint) => ({
                ...p,
                date: new Date(p.date).toLocaleDateString('en-GB', { month: 'short', day: 'numeric' }),
            }));
            setRevenueData(formatted);
            setTechData(techRes.data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };
    fetchData();
  }, []);

  if (loading) return <div className="p-6 space-y-6"><Skeleton className="h-64 w-full" /></div>;

  // Calculate some summary stats from the mock data
  const totalRevenue = revenueData.reduce((acc, curr) => acc + curr.amount, 0);
  const avgRevenue = Math.floor(totalRevenue / revenueData.length);
  const totalJobs = techData.reduce((acc, curr) => acc + curr.completed, 0);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6 bg-slate-50">
        <div className="flex items-center justify-between">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-heading text-slate-900">Analytics</h1>
                <p className="text-slate-500">Business health and operational efficiency.</p>
            </div>
        </div>

        {/* 1. Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SummaryCard
                title="Total Revenue (30d)"
                value={`£${totalRevenue.toLocaleString()}`}
                icon={DollarSign}
                trend={revenueData.length > 0 ? "Live data" : "No data yet"}
                trendColor="text-emerald-600"
            />
             <SummaryCard
                title="Avg Daily Revenue"
                value={`£${avgRevenue.toLocaleString()}`}
                icon={TrendingUp}
                trend="30-day average"
                 trendColor="text-violet-600"
            />
             <SummaryCard 
                title="Total Jobs Completed" 
                value={totalJobs.toString()} 
                icon={Users}
                trend="94% Efficiency Rate"
                 trendColor="text-emerald-600"
            />
        </div>

        {/* 2. Main Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="shadow-sm border-slate-200">
                <CardHeader>
                    <CardTitle>Revenue Trend</CardTitle>
                    <CardDescription>Income over the last 30 days</CardDescription>
                </CardHeader>
                <CardContent className="pl-0">
                    <RevenueChart data={revenueData} />
                </CardContent>
            </Card>

            <Card className="shadow-sm border-slate-200">
                <CardHeader>
                    <CardTitle>Technician Efficiency</CardTitle>
                    <CardDescription>Completed vs Delayed jobs per tech</CardDescription>
                </CardHeader>
                <CardContent>
                    <TechPerformanceChart data={techData} />
                </CardContent>
            </Card>
        </div>
    </div>
  );
}

function SummaryCard({ title, value, icon: Icon, trend, trendColor }: any) {
    return (
        <Card className="shadow-sm border-slate-200">
            <CardContent className="p-6">
                <div className="flex items-center justify-between space-y-0 pb-2">
                    <p className="text-sm font-medium text-slate-500">{title}</p>
                    <Icon className="h-4 w-4 text-slate-400" />
                </div>
                <div className="text-2xl font-bold font-heading text-slate-900">{value}</div>
                <p className={`text-xs ${trendColor} mt-1 font-medium`}>{trend}</p>
            </CardContent>
        </Card>
    )
}
