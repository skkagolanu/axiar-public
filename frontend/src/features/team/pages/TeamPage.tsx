import { useState } from 'react';
import { LiveMapBoard } from '../components/LiveMapBoard';
import { useTeamLocation } from '../hooks/useRealtimePos';
import { ReassignDrawer } from '../components/ReassignDrawer';
import { toast } from '@/hooks/use-toast';

export default function TeamPage() {
  const { technicians, routes } = useTeamLocation();
  const [selectedTechId, setSelectedTechId] = useState<string | null>(null);

  const handleReassign = (jobId: string, newTechId: string) => {
      // Logic to call API would go here
      const newTechName = technicians.find(t => t.id === newTechId)?.fullName;
      toast({
          title: "Dispatch Sent",
          description: `Job ${jobId} re-routed to ${newTechName}.`,
          className: "bg-emerald-950 border-emerald-500 text-white"
      });
      // Refresh the team after a reassignment.
  };

  const selectedTech = technicians.find(t => t.id === selectedTechId) || null;

  return (
    <div className="h-full w-full relative p-4 md:p-6 bg-slate-50">
        <LiveMapBoard 
            technicians={technicians}
            routes={routes} 
            onTechClick={setSelectedTechId}
        />
        
        <ReassignDrawer 
            isOpen={!!selectedTechId}
            onClose={() => setSelectedTechId(null)}
            selectedTech={selectedTech}
            allTechs={technicians}
            onReassign={handleReassign}
        />
    </div>
  );
}
