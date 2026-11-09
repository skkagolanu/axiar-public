import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { ScheduleBoard } from '../components/ScheduleBoard';
import type { TeamMember, ScheduleEvent } from '../types';
import type { Job } from '@/features/jobs/types';
import { Skeleton } from '@/components/ui/skeleton';

export default function SchedulePage() {
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [events, setEvents] = useState<ScheduleEvent[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const [date, setDate] = useState<Date | undefined>(new Date());

  useEffect(() => {
    // Load schedule events for the selected date.
    // const fetchEvents = async () => ...
    const fetchData = async () => {
        try {
            const [teamRes, eventsRes, jobsRes] = await Promise.all([
                api.get('/api/v1/team'),
                api.get('/api/v1/schedule'),
                api.get('/api/v1/jobs')
            ]);
            setTeam(teamRes.data);
            setEvents(eventsRes.data);
            // Filter only pending jobs for the sidebar
            setJobs(jobsRes.data.filter((j: Job) => j.status === 'pending'));
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };
    fetchData();
  }, [date]);

  if (loading) return <div className="p-6"><Skeleton className="w-full h-96" /></div>;

  return (
    <div className="h-full flex flex-col overflow-hidden p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h2 className="text-3xl font-bold tracking-tight font-heading text-slate-900">Dispatch Board</h2>
        <div className="flex items-center space-x-2">
            <CalendarDatePicker date={date} setDate={setDate} />
        </div>
      </div>
      
      {/* Board takes remaining height */}
      <div className="flex-1 overflow-hidden">
        <ScheduleBoard 
            initialTeam={team} 
            initialEvents={events} 
            initialJobs={jobs} 
            currentDate={date || new Date()}
        />
      </div>
    </div>
  );
}

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { CalendarIcon } from "lucide-react"
import { format } from "date-fns"

function CalendarDatePicker({ date, setDate }: { date: Date | undefined, setDate: (date: Date | undefined) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={"outline"}
          className={cn(
            "w-[240px] justify-start text-left font-normal",
            !date && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {date ? format(date, "PPP") : <span>Pick a date</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="end">
        <Calendar
          mode="single"
          selected={date}
          onSelect={setDate}
          initialFocus
        />
        <div className="p-3 border-t border-slate-100 flex justify-end">
            <Button size="sm" onClick={() => setOpen(false)}>
                Done
            </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
