import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Navigation, Clock } from 'lucide-react';
import type { TeamMember } from '../types';

interface ReassignDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  selectedTech: TeamMember | null;
  allTechs: TeamMember[];
  onReassign: (jobId: string, newTechId: string) => void;
}

export function ReassignDrawer({ 
  isOpen, 
  onClose, 
  selectedTech, 
  allTechs,
  onReassign 
}: ReassignDrawerProps) {
  if (!selectedTech) return null;

  // Find nearest available tech (Mock logic: just pick the first 'available' one)
  const availableTech = allTechs.find(t => t.id !== selectedTech.id && t.liveStatus.status === 'available');

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="right" className="w-[400px] sm:w-[540px] border-l border-slate-800 bg-slate-950 text-slate-100">
        <SheetHeader>
          <SheetTitle className="text-2xl font-heading text-slate-100 flex items-center gap-2">
            <span className={selectedTech.liveStatus.status === 'delayed' ? 'text-amber-500' : 'text-violet-500'}>
               {selectedTech.fullName}
            </span>
          </SheetTitle>
          <SheetDescription className="text-slate-400">
            Current Status: <span className="uppercase font-mono font-bold">{selectedTech.liveStatus.status}</span>
          </SheetDescription>
        </SheetHeader>

        <div className="py-6 space-y-6">
            {/* Current Job Context */}
            <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
                <h4 className="text-sm font-medium text-slate-400 mb-3 uppercase tracking-wider">Current Assignment</h4>
                <div className="flex items-start gap-3">
                    <div className="h-10 w-10 rounded bg-violet-500/10 flex items-center justify-center text-violet-400">
                        <Navigation className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="font-bold text-slate-200">Repair HVAC Unit #404</p>
                        <p className="text-sm text-slate-500">123 Broadway Ave, NYC</p>
                        <div className="mt-2 flex items-center gap-2 text-xs font-mono text-amber-500">
                             <Clock className="h-3 w-3" />
                             <span>DELAY DETECTED (+15m)</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Smart Suggestion */}
            {selectedTech.liveStatus.status === 'delayed' && (
                <div className="space-y-4">
                     <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wider">Rescue Suggestion</h4>
                     
                     {availableTech ? (
                         <div className="p-4 rounded-lg border border-emerald-500/30 bg-emerald-950/20 hover:bg-emerald-950/30 transition-colors cursor-pointer group">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <Avatar className="h-12 w-12 border-2 border-emerald-500">
                                        <AvatarImage src={availableTech.avatar} />
                                        <AvatarFallback>{availableTech.fullName[0]}</AvatarFallback>
                                    </Avatar>
                                    <div>
                                        <p className="font-bold text-emerald-400">{availableTech.fullName}</p>
                                        <p className="text-xs text-emerald-300/70">4 mins away • Closest Tech</p>
                                    </div>
                                </div>
                                <Button 
                                    size="sm" 
                                    className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/50"
                                    onClick={() => {
                                        if (selectedTech.liveStatus.currentJobId) {
                                            onReassign(selectedTech.liveStatus.currentJobId, availableTech.id);
                                            onClose();
                                        }
                                    }}
                                >
                                    Dispatch
                                </Button>
                            </div>
                         </div>
                     ) : (
                         <div className="p-4 rounded border border-slate-800 bg-slate-900 text-slate-400 text-sm text-center">
                             No available technicians nearby.
                         </div>
                     )}
                </div>
            )}
        </div>

        <SheetFooter>
             <Button variant="ghost" onClick={onClose} className="text-slate-400 hover:text-white">Cancel</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
