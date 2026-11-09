import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import api from "@/lib/axios";
import { format } from "date-fns";
import { Loader2, MapPin, Navigation } from "lucide-react";
import { RatingModal } from "@/features/providers/components/RatingModal";

export default function MobileJobsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [ratingTarget, setRatingTarget] = useState<{ bookingId: string; providerId: string } | null>(null);

  useEffect(() => {
    const fetchJobs = async () => {
      try {
        // Fetch current user's bookings (as provider/agent)
    
        const res = await api.get('/bookings/my-bookings'); 
        setJobs(res.data);
      } catch (error) {
        console.error("Failed to fetch jobs", error);
      } finally {
        setLoading(false);
      }
    };
    fetchJobs();
  }, []);

  if (loading) {
    return <div className="flex justify-center p-8"><Loader2 className="animate-spin" /></div>;
  }

  const currentJob = jobs[0]; // Naive "current"
  const upcomingJobs = jobs.slice(1);

  return (
    <>
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold font-heading">Today's Route</h2>
        <span className="text-xs text-slate-400">{format(new Date(), "MMM d")}</span>
      </div>

      {/* Current Job Card */}
      {currentJob ? (
        <div className="bg-slate-900 rounded-xl p-5 border border-violet-500/30 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-violet-500"></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <span className="inline-block px-2 py-1 bg-violet-500/10 text-violet-400 text-[10px] font-bold uppercase tracking-wider rounded mb-2">
                Current Job
              </span>
              <h3 className="text-lg font-bold text-white">
                {currentJob.service?.name || "Service Visit"}
              </h3>
              <p className="text-sm text-slate-400 flex items-center gap-1 mt-1">
                <MapPin className="h-3 w-3" />
                {currentJob.location_address || "No address provided"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xl font-bold text-white">
                {format(new Date(currentJob.scheduled_time), "HH:mm")}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 mt-4">
            <Button className="w-full bg-slate-800 hover:bg-slate-700 text-slate-300">
              Details
            </Button>
            <Button className="w-full bg-violet-600 hover:bg-violet-500 text-white">
              <Navigation className="mr-2 h-4 w-4" /> Navigator
            </Button>
          </div>
          {currentJob.status === 'completed' && currentJob.provider_id && (
            <Button
              className="w-full mt-2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white"
              onClick={() => setRatingTarget({ bookingId: currentJob.id, providerId: currentJob.provider_id })}
            >
              Rate this service
            </Button>
          )}
        </div>
      ) : (
        <div className="p-8 text-center text-slate-500 bg-slate-100 rounded-xl">
          No active jobs assigned.
        </div>
      )}

      {/* Upcoming Jobs */}
      <div className="space-y-3">
        {upcomingJobs.map((job: any) => (
          <div key={job.id} className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm flex justify-between items-center">
            <div>
              <h3 className="text-sm font-bold text-slate-900">{job.service?.name || "Service"}</h3>
              <p className="text-xs text-slate-500">{job.location_address}</p>
            </div>
            <div className="text-right">
              <p className="text-sm font-bold text-slate-900">
                {format(new Date(job.scheduled_time), "HH:mm")}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>

    {ratingTarget && (
      <RatingModal
        bookingId={ratingTarget.bookingId}
        providerId={ratingTarget.providerId}
        onDone={() => setRatingTarget(null)}
      />
    )}
    </>
  );
}
