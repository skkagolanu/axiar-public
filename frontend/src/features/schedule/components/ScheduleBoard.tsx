import { useState } from 'react';
import api from '@/lib/axios';
import { 
  DndContext, 
  DragOverlay, 
  useSensor, 
  useSensors, 
  PointerSensor, 
  type DragStartEvent, 
  type DragEndEvent 
} from '@dnd-kit/core';
import type { Job } from '@/features/jobs/types';
import type { TeamMember, ScheduleEvent } from '../types';
import { UnassignedList } from './UnassignedList';
import { JobEventCard } from './JobEventCard';
import { useDroppable } from '@dnd-kit/core';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { toast } from '@/hooks/use-toast';

interface ScheduleBoardProps {
  initialTeam: TeamMember[];
  initialEvents: ScheduleEvent[];
  initialJobs: Job[];
  currentDate: Date;
}

const HOUR_WIDTH = 80;
const START_HOUR = 0;
const HOURS_COUNT = 24;
const ROW_HEIGHT = 80;

// Inline TeamRow that doesn't try to do sticky positioning
function TimelineRow({ 
  member, 
  events, 
  hourWidth, 
  startHour 
}: { 
  member: TeamMember; 
  events: ScheduleEvent[]; 
  hourWidth: number; 
  startHour: number;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: member.id,
    data: { member },
  });

  return (
    <div 
      ref={setNodeRef}
      className={cn(
        "relative border-b border-slate-200",
        isOver && "bg-violet-50/50"
      )}
      style={{ height: `${ROW_HEIGHT}px`, width: `${hourWidth * HOURS_COUNT}px` }}
    >
      {/* Grid Lines */}
      {Array.from({ length: HOURS_COUNT }).map((_, i) => (
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
              height: '60px',
              top: '10px'
            }}
          />
        );
      })}
    </div>
  );
}

// Team member info panel (left column)
function TeamMemberCell({ member }: { member: TeamMember }) {
  return (
    <div 
      className="flex items-center space-x-3 p-3 border-b border-r border-slate-200 bg-white"
      style={{ height: `${ROW_HEIGHT}px` }}
    >
      <Avatar className="h-10 w-10">
        <AvatarImage src={member.avatar} />
        <AvatarFallback>{member.fullName?.substring(0, 2).toUpperCase() || '?'}</AvatarFallback>
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
  );
}

export function ScheduleBoard({ initialTeam, initialEvents, initialJobs, currentDate }: ScheduleBoardProps) {
  const [events, setEvents] = useState<ScheduleEvent[]>(initialEvents);
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draggedItem, setDraggedItem] = useState<any>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
    setDraggedItem(event.active.data.current);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (over && active.data.current?.type === 'job' && over.id !== 'unassigned-zone') {
      const techId = over.id;
      const job = active.data.current as Job;
      
      const start = new Date(currentDate);
      start.setHours(9, 0, 0, 0);
      const end = new Date(start);
      end.setHours(11, 0, 0, 0);

      const newEvent: ScheduleEvent = {
        id: job.id,
        resourceId: techId as string,
        startTime: start.toISOString(),
        endTime: end.toISOString(),
        title: job.serviceType,
        status: 'scheduled',
        type: job.serviceType
      };

      const prevEvents = events;
      const prevJobs = jobs;
      setEvents([...events, newEvent]);
      setJobs(jobs.filter(j => j.id !== job.id));

      // Call API — revert the optimistic move if it fails
      api.post(`/api/v1/dispatch/${job.id}/assign/${techId}`).catch(err => {
        console.error("Failed to assign job", err);
        setEvents(prevEvents);
        setJobs(prevJobs);
        toast({ variant: 'destructive', title: 'Assignment failed', description: 'Could not assign the job — change reverted.' });
      });
    }
    else if (over && over.id === 'unassigned-zone' && active.data.current?.type === 'event') {
      const scheduleEvent = active.data.current as ScheduleEvent;
      setEvents(events.filter(e => e.id !== scheduleEvent.id));
      
      const restoredJob: Job = {
        id: scheduleEvent.id,
        customerName: 'Unassigned Customer',
        customerPhone: '',
        address: '',
        serviceType: scheduleEvent.title,
        description: '',
        status: 'pending',
        priority: 'medium',
        scheduledDate: '',
        scheduledTime: '',
        price: 0
      };
      setJobs([...jobs, restoredJob]);
    }
    else if (over && active.data.current?.type === 'event' && over.id !== 'unassigned-zone') {
      const techId = over.id;
      const scheduleEvent = active.data.current as ScheduleEvent;
      
      const prevEvents = events;
      const updatedEvents = events.map(e =>
        e.id === scheduleEvent.id ? { ...e, resourceId: techId as string } : e
      );
      setEvents(updatedEvents);

      // Call API — revert the optimistic move if it fails
      // Note: the real endpoint only reassigns the agent, not the time — dragging to a new
      // hour slot moves the event locally but the backend has no time-update path yet.
      api.post(`/api/v1/dispatch/${scheduleEvent.id}/assign/${techId}`).catch(err => {
        console.error("Failed to reassign job", err);
        setEvents(prevEvents);
        toast({ variant: 'destructive', title: 'Reassign failed', description: 'Could not move the job — change reverted.' });
      });
    }

    setActiveId(null);
    setDraggedItem(null);
  };

  return (
    <DndContext 
      sensors={sensors} 
      onDragStart={handleDragStart} 
      onDragEnd={handleDragEnd}
    >
      {/* 3-Column Fixed Layout */}
      <div 
        className="h-full rounded-lg overflow-hidden border border-slate-200 bg-white shadow-sm"
        style={{ 
          display: 'grid', 
          gridTemplateColumns: '200px 1fr 280px' 
        }}
      >
        {/* LEFT: Team Members (Fixed) */}
        <div className="overflow-y-auto border-r border-slate-200 bg-white">
          {/* Header spacer */}
          <div className="h-12 border-b border-slate-200 bg-slate-50 flex items-center px-4">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Team</span>
          </div>
          {/* Team list */}
          {initialTeam.map(member => (
            <TeamMemberCell key={member.id} member={member} />
          ))}
        </div>

        {/* CENTER: Timeline (Horizontal Scroll) */}
        <div className="overflow-x-auto overflow-y-auto bg-slate-50">
          {/* Time header */}
          <div 
            className="h-12 border-b border-slate-200 flex bg-slate-50 sticky top-0 z-10"
            style={{ width: `${HOUR_WIDTH * HOURS_COUNT}px` }}
          >
            {Array.from({ length: HOURS_COUNT }).map((_, i) => (
              <div 
                key={i} 
                className="flex-shrink-0 border-l border-slate-200 pl-2 pt-3 text-xs font-medium text-slate-500"
                style={{ width: `${HOUR_WIDTH}px` }}
              >
                {i}:00
              </div>
            ))}
          </div>
          
          {/* Swimlanes */}
          <div style={{ width: `${HOUR_WIDTH * HOURS_COUNT}px` }}>
            {initialTeam.map(member => (
              <TimelineRow 
                key={member.id} 
                member={member} 
                events={events.filter(e => e.resourceId === member.id)}
                hourWidth={HOUR_WIDTH}
                startHour={START_HOUR}
              />
            ))}
          </div>
        </div>

        {/* RIGHT: Unassigned (Fixed) */}
        <div className="overflow-y-auto bg-slate-900">
          <UnassignedList jobs={jobs} />
        </div>
      </div>

      <DragOverlay>
        {activeId && draggedItem ? (
          <div className="opacity-90 pointer-events-none">
            {draggedItem.type === 'job' ? (
              <div className="bg-violet-600 text-white p-3 rounded-lg shadow-lg text-sm font-bold w-40">
                {draggedItem.serviceType}
              </div>
            ) : (
              <div className="bg-violet-600 text-white p-2 rounded shadow text-sm w-32">
                {draggedItem.title}
              </div>
            )}
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
