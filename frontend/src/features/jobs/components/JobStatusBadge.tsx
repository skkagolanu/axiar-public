import { Badge } from '@/components/ui/badge';
import type { JobStatus } from '../types';

interface JobStatusBadgeProps {
  status: JobStatus;
}

const statusStyles: Record<JobStatus, string> = {
  pending: 'bg-amber-100 text-amber-700 hover:bg-amber-100/80',
  scheduled: 'bg-blue-100 text-blue-700 hover:bg-blue-100/80',
  in_progress: 'bg-violet-100 text-violet-700 hover:bg-violet-100/80',
  completed: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100/80',
  cancelled: 'bg-slate-100 text-slate-700 hover:bg-slate-100/80',
};

const statusLabels: Record<JobStatus, string> = {
  pending: 'Pending',
  scheduled: 'Scheduled',
  in_progress: 'In Progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

export function JobStatusBadge({ status }: JobStatusBadgeProps) {
  return (
    <Badge variant="outline" className={`font-medium border-none ${statusStyles[status]}`}>
      {statusLabels[status]}
    </Badge>
  );
}
