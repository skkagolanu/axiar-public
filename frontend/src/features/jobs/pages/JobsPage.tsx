import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { mapBookingToJob, type BookingEnriched } from '@/lib/mappers/booking';
import type { Job } from '../types';
import { JobDataTable } from '../components/JobDataTable';
import { JobCard } from '../components/JobCard';
import { CreateJobSheet } from '../components/CreateJobSheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Plus, Search, Filter } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchJobs = async () => {
    try {
      const response = await api.get<BookingEnriched[]>('/api/v1/bookings');
      setJobs(response.data.map(mapBookingToJob));
    } catch (error) {
      console.error('Failed to fetch jobs', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    api.get<BookingEnriched[]>('/api/v1/bookings')
      .then(response => { if (!cancelled) setJobs(response.data.map(mapBookingToJob)); })
      .catch(error => console.error('Failed to fetch jobs', error))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filteredJobs = jobs.filter(job => 
    job.customerName.toLowerCase().includes(searchTerm.toLowerCase()) ||
    job.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
            <h2 className="text-3xl font-bold tracking-tight font-heading text-slate-900">Jobs</h2>
            <p className="text-slate-500">Manage your service interventions.</p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)} className="bg-gradient-to-r from-violet-600 to-indigo-600 shadow-lg shadow-violet-500/20">
            <Plus className="mr-2 h-4 w-4" /> New Job
        </Button>
      </div>

      {/* Filters */}
       <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <Input
                placeholder="Search jobs..."
                className="pl-9 bg-white"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
            />
        </div>
        <Button variant="outline" size="icon">
            <Filter className="h-4 w-4 text-slate-600" />
        </Button>
       </div>

      {/* Content */}
      {loading ? (
         <div className="space-y-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
         </div>
      ) : (
        <>
            {/* Desktop View */}
            <div className="hidden md:block">
                <JobDataTable data={filteredJobs} />
            </div>

            {/* Mobile View */}
            <div className="md:hidden space-y-4">
                {filteredJobs.map((job) => (
                    <JobCard key={job.id} job={job} />
                ))}
                {filteredJobs.length === 0 && (
                    <div className="text-center py-8 text-slate-500">No jobs found.</div>
                )}
            </div>
        </>
      )}

      <CreateJobSheet 
        open={isCreateOpen} 
        onOpenChange={setIsCreateOpen} 
        onJobCreated={fetchJobs} 
      />
    </div>
  );
}
