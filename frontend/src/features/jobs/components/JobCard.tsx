import type { Job } from '../types';
import { JobStatusBadge } from './JobStatusBadge';
import { Card, CardContent } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Calendar, MapPin, User, ChevronRight } from 'lucide-react';

interface JobCardProps {
  job: Job;
}

export function JobCard({ job }: JobCardProps) {
  return (
    <Card className="overflow-hidden hover:bg-slate-50 transition-colors cursor-pointer border-slate-200 shadow-sm">
      <CardContent className="p-4">
        <div className="flex justify-between items-start mb-2">
            <div>
                 <span className="text-xs font-mono text-slate-400 block mb-1">{job.id}</span>
                 <h3 className="font-heading font-semibold text-slate-900">{job.customerName}</h3>
            </div>
            <JobStatusBadge status={job.status} />
        </div>
        
        <div className="space-y-2 mb-3">
            <div className="flex items-center text-sm text-slate-600">
                <MapPin className="h-3.5 w-3.5 mr-2 text-slate-400" />
                <span className="truncate">{job.address}</span>
            </div>
             <div className="flex items-center text-sm text-slate-600">
                <Calendar className="h-3.5 w-3.5 mr-2 text-slate-400" />
                <span>{new Date(job.scheduledDate).toLocaleDateString()} at {job.scheduledTime}</span>
            </div>
        </div>

        <div className="flex items-center justify-between border-t border-slate-100 pt-3 mt-3">
            <div className="flex items-center gap-2">
                 {job.assignedTech ? (
                      <>
                        <Avatar className="h-5 w-5">
                            <AvatarImage src={job.assignedTech.avatar} />
                            <AvatarFallback>{job.assignedTech.name[0]}</AvatarFallback>
                        </Avatar>
                        <span className="text-xs text-slate-500">{job.assignedTech.name}</span>
                      </>
                 ) : (
                     <div className="flex items-center text-xs text-slate-400">
                         <User className="h-3.5 w-3.5 mr-1" />
                         Unassigned
                     </div>
                 )}
            </div>
            <div className="flex items-center text-primary text-xs font-medium">
                Svc: {job.serviceType}
                <ChevronRight className="h-3 w-3 ml-1" />
            </div>
        </div>

      </CardContent>
    </Card>
  );
}
