import type { ScheduleEvent } from '../types';
import { cn } from '@/lib/utils';
import { useDraggable } from '@dnd-kit/core';

interface JobEventCardProps {
  event: ScheduleEvent;
  style?: React.CSSProperties;
}

export function JobEventCard({ event, style }: JobEventCardProps) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: event.id,
    data: { ...event, type: 'event' },
  });

  const appliedStyle = transform ? {
    transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
    ...style,
  } : style;

  return (
    <div
      ref={setNodeRef}
      style={appliedStyle}
      {...listeners}
      {...attributes}
      className={cn(
        "absolute rounded-md p-2 text-xs text-white shadow-sm cursor-grab active:cursor-grabbing overflow-hidden",
        "bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500",
        "border border-white/10"
      )}
    >
      <div className="font-bold truncate">{event.title}</div>
      <div className="opacity-80 truncate text-[10px]">
        {new Date(event.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - 
        {new Date(event.endTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
}
