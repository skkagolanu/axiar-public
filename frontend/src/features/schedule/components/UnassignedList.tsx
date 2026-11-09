import type { Job } from '@/features/jobs/types';
import { useDraggable } from '@dnd-kit/core';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

interface UnassignedListProps {
  jobs: Job[];
}

function DraggableJobCard({ job }: { job: Job }) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: `job-${job.id}`,
    data: { ...job, type: 'job' },
  });

  const style = transform ? {
    transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
  } : undefined;

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className="mb-3 cursor-grab hover:shadow-md transition-shadow active:cursor-grabbing bg-slate-800 border-slate-700"
    >
      <CardContent className="p-3">
        <div className="flex justify-between items-start mb-2">
            <span className="font-heading font-medium text-slate-100 text-sm truncate">{job.serviceType}</span>
            <Badge variant="outline" className="text-[10px] border-slate-600 text-slate-400">{job.priority}</Badge>
        </div>
        <div className="text-xs text-slate-400 truncate">{job.customerName}</div>
        <div className="text-xs text-slate-500 mt-1">{job.id}</div>
      </CardContent>
    </Card>
  );
}

import { useDroppable } from '@dnd-kit/core';
import { cn } from '@/lib/utils';

// ... (DraggableJobCard remains same)

export function UnassignedList({ jobs }: UnassignedListProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: 'unassigned-zone',
  });

  return (
    <div 
        ref={setNodeRef}
        className={cn(
            "h-full flex flex-col border-l border-slate-800 transition-colors",
            isOver ? "bg-slate-800/80 ring-2 ring-inset ring-violet-500/20" : "bg-slate-900"
        )}
    >
      <div className="p-4 border-b border-slate-800">
        <h3 className="font-heading text-lg font-semibold text-white">Unassigned Jobs</h3>
        <p className="text-xs text-slate-400">{jobs.length} jobs pending dispatch</p>
      </div>
      <ScrollArea className="flex-1 p-4">
        {jobs.map((job) => (
          <DraggableJobCard key={job.id} job={job} />
        ))}
      </ScrollArea>
    </div>
  );
}
