import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import type { TechPerformance } from "../types";

export function TechPerformanceChart({ data }: { data: TechPerformance[] }) {
  return (
    <div className="h-[350px] w-full">
        <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis 
                    dataKey="name" 
                    stroke="#64748b" 
                    fontSize={12} 
                    tickLine={false} 
                    axisLine={false}
                />
                <YAxis 
                    stroke="#64748b" 
                    fontSize={12} 
                    tickLine={false} 
                    axisLine={false}
                />
                <Tooltip 
                    cursor={{ fill: '#f1f5f9' }}
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                />
                <Legend iconType="circle" />
                <Bar 
                    dataKey="completed" 
                    name="Jobs Completed" 
                    fill="#10b981" 
                    radius={[4, 4, 0, 0]} 
                />
                <Bar 
                    dataKey="delayed" 
                    name="Delayed / Late" 
                    fill="#f59e0b" 
                    radius={[4, 4, 0, 0]} 
                />
            </BarChart>
        </ResponsiveContainer>
    </div>
  );
}
