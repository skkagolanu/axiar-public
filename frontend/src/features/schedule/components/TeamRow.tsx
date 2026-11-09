import { useDroppable } from '@dnd-kit/core';
import type { TeamMember, ScheduleEvent } from '../types';
import { JobEventCard } from './JobEventCard';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';

interface TeamRowProps {
  member: TeamMember;
  events: ScheduleEvent[];
  hourWidth: number; // Pixels per hour, e.g., 100px
  startHour: number; // e.g., 8 (8 AM)
}

export function TeamRow({ member, events, hourWidth, startHour }: TeamRowProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: member.id,
    data: { member },
  });

  return (
    <div className="flex border-b border-slate-200 h-24 relative min-w-max">
      {/* Resource Header - Sticky Left */}
      <div className="w-[20vw] flex-shrink-0 bg-white border-r border-slate-200 p-3 flex items-center space-x-3 sticky left-0 z-10 shadow-[4px_0_24px_-12px_rgba(0,0,0,0.1)] left-0 absolute" style={{ left: 0 }}>
        <Avatar>
          <AvatarImage src={member.avatar} />
          <AvatarFallback>{member.fullName?.substring(0, 2) || '?'}</AvatarFallback>
        </Avatar>
        <div>
          <div className="text-sm font-medium text-slate-900">{member.fullName}</div>
          <div className="flex items-center space-x-1">
            <div className={cn("w-2 h-2 rounded-full", 
                member.status === 'active' ? "bg-emerald-500" : 
                member.status === 'busy' ? "bg-amber-500" : "bg-slate-300"
            )} />
            <span className="text-xs text-slate-500 capitalize">{member.status}</span>
          </div>
        </div>
      </div>

      {/* Timeline Drop Zone */}
      <div 
        ref={setNodeRef}
        className={cn(
            "flex-1 relative bg-slate-50/50 min-w-[1000px]",
            isOver && "bg-violet-50/50 ring-2 ring-inset ring-violet-500/20"
        )}
      >
        {/* Grid Lines */}
        {Array.from({ length: 24 }).map((_, i) => (
             <div 
                key={i} 
                className="absolute top-0 bottom-0 border-r border-slate-100" 
                style={{ left: `${(i + 1) * hourWidth}px` }} 
            />
        ))}

        {/* Events */}
        {events.map((event) => {
             const start = new Date(event.startTime);
             const end = new Date(event.endTime);
             
             // Simple calculation: (Hours from 8AM) * Width
             const startOffset = (start.getHours() + start.getMinutes() / 60 - startHour) * hourWidth;
             const duration = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
             const width = duration * hourWidth;

             return (
                 <JobEventCard 
                    key={event.id} 
                    event={event} 
                    style={{
                        left: `${startOffset}px`,
                        width: `${width}px`,
                        height: '70%',
                        top: '15%'
                    }}
                 />
             );
        })}
      </div>
    </div>
  );
}
