import { useEffect, useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { MapPin, List, User } from "lucide-react";
import { useGPSBroadcast } from "../hooks/useGPSBroadcast";
import { useAuthStore } from "@/store/useAuthStore";
import api from "@/lib/axios";

export default function FieldLayout() {
  const currentUserId = useAuthStore((state) => state.user?.id);
  const [agentId, setAgentId] = useState<string | null>(null);

  // GET /api/v1/team returns every field agent for the tenant, including each
  // one's userId — resolve "which entry is me" so the broadcast targets the
  // right FieldAgent.id (a distinct id from the logged-in User.id).
  useEffect(() => {
    if (!currentUserId) return;
    let cancelled = false;

    api.get<{ id: string; userId: string }[]>('/api/v1/team')
      .then(({ data }) => {
        if (cancelled) return;
        const mine = data.find((agent) => agent.userId === currentUserId);
        setAgentId(mine?.id ?? null);
      })
      .catch(() => {
        if (!cancelled) setAgentId(null);
      });

    return () => { cancelled = true; };
  }, [currentUserId]);

  useGPSBroadcast(agentId, true);

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-white">
      {/* Mobile Header */}
      <header className="flex h-16 items-center justify-between px-6 border-b border-slate-800 bg-slate-900">
        <h1 className="text-lg font-bold font-heading text-white">Axiar Field</h1>
        <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" title="Online" />
      </header>

      {/* Scrollable Content */}
      <main className="flex-1 overflow-y-auto p-4 pb-24">
        <Outlet />
      </main>

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 h-20 bg-slate-900 border-t border-slate-800 flex justify-around items-center z-50 pb-2">
        <MobileNavLink to="/mobile/jobs" icon={List} label="Jobs" />
        <MobileNavLink to="/mobile/map" icon={MapPin} label="Map" />
        <MobileNavLink to="/mobile/profile" icon={User} label="Me" />
      </nav>
    </div>
  );
}

function MobileNavLink({ to, icon: Icon, label }: any) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-col items-center gap-1 p-2 rounded-lg transition-colors ${
          isActive ? "text-violet-500" : "text-slate-500 hover:text-slate-300"
        }`
      }
    >
      <Icon className="h-6 w-6" />
      <span className="text-[10px] font-medium">{label}</span>
    </NavLink>
  );
}
